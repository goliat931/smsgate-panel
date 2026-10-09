"""Wątek w tle: wysyła kolejkę w bezpiecznym tempie i odpytuje telefon o statusy i odpowiedzi."""
import logging
import random
import threading
import time
from datetime import datetime, timedelta, timezone

from .core import is_optout, normalize_phone
from .db import now_iso
from .gateway import GatewayError, explain_error, to_utc_iso

log = logging.getLogger("sms_panel")
POLL_EVERY = 5
RESERVE = 0.8   # wysyłki grupowe biorą najwyżej 80% limitu telefonu; reszta zostaje na odpowiedzi pisane ręcznie
STATE = {"Pending": "accepted", "Processed": "accepted", "Sent": "sent", "Delivered": "delivered",
         "Failed": "failed", "Cancelled": "cancelled", "Cancelling": "cancelled"}


def budget(db):
    """(ile SMS-ów wyszło w bieżącym oknie, limit telefonu, długość okna w minutach).

    Android liczy każdą część długiej wiadomości osobno, więc sumujemy segmenty.
    """
    limit = max(1, int(float(db.get("limit_count", 30))))
    window = max(1.0, float(db.get("limit_window", 30)))
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window)).isoformat(timespec="seconds")
    used = db.one("SELECT COALESCE(SUM(segments),0) n FROM messages WHERE direction='out' AND sent_at > ?", cutoff)["n"]
    return used, limit, window


MMS_NOTE = "📷 MMS (zdjęcie lub inny załącznik). Panel nie pokazuje zdjęć – zobacz je w telefonie."


def store_incoming(db, item):
    """Zapisuje SMS lub MMS przychodzący z GET /inbox. Zwraca True, gdy to nowa wiadomość."""
    sender = item.get("sender") or ""
    phone = normalize_phone(sender) or sender or "?"
    body = item.get("contentPreview") or ""
    if str(item.get("type") or "").startswith("MMS"):
        body = MMS_NOTE + (" Dołączony tekst: " + body if body.strip() else "")
    cur = db.x("INSERT OR IGNORE INTO messages(direction, phone, body, status, gateway_id, read, created_at) "
               "VALUES('in', ?, ?, 'received', ?, 0, ?)",
               phone, body, f"in:{item.get('id')}", to_utc_iso(item.get("createdAt")))
    if not cur.rowcount:
        return False
    if is_optout(body):
        db.x("INSERT OR IGNORE INTO blocked(phone) VALUES(?)", phone)
    return True


class Worker(threading.Thread):
    def __init__(self, db, gateway_factory):
        super().__init__(daemon=True)
        self.db, self.gateway_factory = db, gateway_factory
        self.stop = threading.Event()
        self.online, self.error = None, ""   # None = jeszcze nie wiadomo
        self.failures = 0
        self.limited = False                  # True = kolejka czeka, aż zwolni się limit SMS-ów telefonu
        self.wait_until = self.next_campaign = self.next_poll = 0.0
        # po awarii w trakcie wysyłki: spróbuj jeszcze raz; to samo id => telefon nie wyśle dwa razy (409)
        db.x("UPDATE messages SET status='queued' WHERE status='sending'")

    def run(self):
        while not self.stop.wait(1):
            try:
                self.tick(time.time())
            except Exception as e:  # wątek ma żyć; bez treści wiadomości w logu
                log.warning("Błąd w tle: %s", type(e).__name__)

    def tick(self, now):
        gw = self.gateway_factory()
        if gw is None or now < self.wait_until:
            return
        try:
            # najpierw statusy: błąd limitu z telefonu ma wstrzymać wysyłkę, zanim wyjdzie następny SMS
            if now >= self.next_poll:
                self.next_poll = now + POLL_EVERY
                self._poll(gw)
            self._send_due(gw, now)
            self.online, self.error, self.failures = True, "", 0
        except GatewayError as e:
            # ponawianie z rosnącą przerwą: 5, 10, 15 s - krótko, żeby powrót telefonu było widać od razu
            self.online, self.error = False, str(e)
            self.wait_until = now + min(15, 5 * (self.failures + 1))
            self.failures += 1

    def _send(self, gw, m):
        if m["campaign_id"] and self.db.one("SELECT 1 FROM blocked WHERE phone=?", m["phone"]):
            self.db.x("UPDATE messages SET status='cancelled', error='Rezygnacja (STOP)' WHERE id=?", m["id"])
            return False
        self.db.x("UPDATE messages SET status='sending' WHERE id=?", m["id"])
        try:
            gw.send(m["gateway_id"], m["phone"], m["body"])
        except GatewayError as e:
            if e.kind == "rejected":
                self.db.x("UPDATE messages SET status='failed', error=? WHERE id=?", explain_error(str(e)), m["id"])
                return True
            self.db.x("UPDATE messages SET status='queued' WHERE id=?", m["id"])
            raise
        self.db.x("UPDATE messages SET status='accepted', sent_at=? WHERE id=?", now_iso(), m["id"])
        return True

    def _send_due(self, gw, now):
        self.limited = False

        def fits(m, share):   # czy wiadomość mieści się w limicie telefonu (pusta kolejka okna puszcza zawsze)
            used, limit, _ = budget(self.db)
            ok = not used or used + m["segments"] <= max(1, int(limit * share))
            self.limited = self.limited or not ok
            return ok

        # pojedyncze odpowiedzi idą od razu, ale też liczą się do limitu
        for m in self.db.q("SELECT * FROM messages WHERE status='queued' AND campaign_id IS NULL ORDER BY id"):
            if not fits(m, 1):
                break
            self._send(gw, m)
        # wysyłka grupowa: jedna wiadomość na kilka-kilkanaście sekund
        while now >= self.next_campaign:
            m = self.db.one("SELECT m.* FROM messages m JOIN campaigns c ON c.id=m.campaign_id "
                            "WHERE m.status='queued' AND c.status='running' ORDER BY m.id LIMIT 1")
            if not m or not fits(m, RESERVE):
                break
            if self._send(gw, m):
                lo = float(self.db.get("pace_min", 8))
                hi = max(lo, float(self.db.get("pace_max", 20)))
                self.next_campaign = now + random.uniform(lo, hi)

    def _poll(self, gw):
        utc = datetime.now(timezone.utc)
        cutoff = (utc - timedelta(days=3)).isoformat(timespec="seconds")
        oldest = self.db.one("SELECT MIN(sent_at) t FROM messages WHERE status IN ('accepted','sent') "
                             "AND sent_at > ?", cutoff)["t"]
        if oldest:
            since = datetime.fromisoformat(oldest) - timedelta(hours=1)  # zapas na różnicę zegarów
            for gid, (state, err) in gw.states(since).items():
                if state not in STATE:
                    continue
                failed = STATE[state] == "failed"
                cur = self.db.x("UPDATE messages SET status=?, error=? WHERE gateway_id=? "
                                "AND status IN ('accepted','sent')", STATE[state],
                                explain_error(err) if failed else err, gid)
                if failed and cur.rowcount and "LIMIT_EXCEEDED" in (err or "").upper():
                    # limit telefonu lub operatora: nie pchamy dalej w pętli, użytkownik sam wznowi
                    self.db.x("UPDATE campaigns SET status='paused' WHERE status='running' AND id="
                              "(SELECT campaign_id FROM messages WHERE gateway_id=?)", gid)
        since = datetime.fromisoformat(self.db.get("inbox_since") or now_iso())
        newest = since
        for item in gw.inbox(since - timedelta(minutes=10)):
            store_incoming(self.db, item)
            newest = max(newest, datetime.fromisoformat(to_utc_iso(item.get("createdAt"))))
        self.db.set("inbox_since", min(newest, utc).isoformat(timespec="seconds"))
