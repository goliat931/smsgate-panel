"""Atrapa bramki SMSGate (tryb --demo i testy). To samo API HTTP co prawdziwy telefon.

Zachowanie: wiadomość po 1 s jest „Sent”, po 3 s „Delivered”. Numery kończące się na 000
kończą błędem, a na 111 błędem limitu SMS-ów. Numery z parzystą ostatnią cyfrą odpisują po 5 s, kończące się na 9 odpisują STOP.
Login i hasło: demo / demo.
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .gateway import explain_error


def make_demo(now=time.time):
    r = APIRouter()
    sent = {}  # id -> dict(phone, text, t)

    def auth(request: Request):
        import base64
        expected = "Basic " + base64.b64encode(b"demo:demo").decode()
        if request.headers.get("authorization") != expected:
            raise HTTPException(401)

    def state(m):
        age = now() - m["t"]
        if age < 1:
            return "Pending", None
        if m["phone"].endswith("111"):
            return "Failed", "RESULT_ERROR_LIMIT_EXCEEDED"
        if m["phone"].endswith("000"):
            return "Failed", "Numer nie istnieje (demo)"
        return ("Sent" if age < 3 else "Delivered"), None

    def view(mid, m):
        st, err = state(m)
        rec = {"phoneNumber": m["phone"], "state": st}
        if err:
            rec["error"] = err
        return {"id": mid, "state": st, "recipients": [rec], "isHashed": False, "isEncrypted": False}

    @r.get("/messages")
    def list_messages(request: Request, limit: int = 50, offset: int = 0):
        auth(request)
        return [view(i, m) for i, m in sent.items()][offset:offset + limit]

    @r.post("/messages")
    async def post_message(request: Request):
        auth(request)
        body = await request.json()
        if body["id"] in sent:
            return JSONResponse({"message": "duplicate id"}, 409)
        sent[body["id"]] = {"phone": body["phoneNumbers"][0], "text": body["textMessage"]["text"], "t": now()}
        return JSONResponse(view(body["id"], sent[body["id"]]), 202)

    @r.get("/inbox")
    def inbox(request: Request, limit: int = 50, offset: int = 0, type: str = "SMS"):
        auth(request)
        out = []
        if type != "SMS":
            return out
        for mid, m in sent.items():
            last = m["phone"][-1]
            if m["phone"].endswith(("000", "111")) or now() - m["t"] < 5:
                continue
            if last == "9":
                text = "STOP"
            elif last in "02468":
                text = "Dziękuję, będę!"
            else:
                continue
            out.append({"id": "r-" + mid, "type": "SMS", "sender": m["phone"], "contentPreview": text,
                        "createdAt": datetime.fromtimestamp(m["t"] + 5, timezone.utc).isoformat()})
        return out[offset:offset + limit]

    return r


# ---------- przykładowe dane trybu demo ----------

PEOPLE = [  # imię, nazwisko, telefon, e-mail, notatka, grupy
    ("Anna", "Nowak", "+48600100202", "anna.nowak@example.com", "2 tabliczki", ["Tabliczki – zamówili", "Impreza firmowa"]),
    ("Jan", "Kowalski", "+48600100209", "jan.kowalski@example.com", "", ["Tabliczki – zamówili"]),
    ("Ola", "Wiśniewska", "+48600100205", "", "odbiór osobisty", ["Tabliczki – zamówili", "Wolontariusze"]),
    ("Piotr", "Zieliński", "+48600100000", "piotr@example.com", "numer chyba nieaktualny", ["Tabliczki – zamówili"]),
    ("Katarzyna", "Lewandowska", "+48600100204", "k.lewandowska@example.com", "", ["Tabliczki – zamówili", "Impreza firmowa"]),
    ("Marek", "Wójcik", "+48600100206", "", "wegetarianin", ["Impreza firmowa"]),
    ("Ewa", "Kamińska", "+48600100208", "ewa.kaminska@example.com", "", ["Impreza firmowa", "Wolontariusze"]),
    ("Tomasz", "Dąbrowski", "+48600100201", "", "", ["Impreza firmowa"]),
    ("Magda", "Szymańska", "+48600100203", "magda@example.com", "przyjedzie z dziećmi", ["Impreza firmowa"]),
    ("Paweł", "Kozłowski", "+48600100207", "", "", ["Wolontariusze"]),
]


def reset(db):
    """Czyści dane (zostawia ustawienia) i wczytuje przykłady."""
    for table in ("messages", "campaigns", "contact_grp", "grp", "contacts", "blocked", "templates"):
        db.x(f"DELETE FROM {table}")
    seed(db)


def seed(db):
    """Przykładowe kontakty, grupy, wysyłki i rozmowy - tylko do pustej bazy."""
    if db.one("SELECT 1 FROM contacts") or db.one("SELECT 1 FROM messages"):
        return
    from datetime import timedelta

    def ago(**kw):
        return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat(timespec="seconds")

    first = {}
    for name, surname, phone, email, note, groups in PEOPLE:
        first[phone] = name
        cid = db.x("INSERT INTO contacts(name, surname, phone, email, note) VALUES(?,?,?,?,?)",
                   name, surname, phone, email, note).lastrowid
        for g in groups:
            db.x("INSERT OR IGNORE INTO grp(name) VALUES(?)", g)
            db.x("INSERT INTO contact_grp(contact_id, grp_id) SELECT ?, id FROM grp WHERE name=?", cid, g)
    db.x("INSERT INTO templates(name, body) VALUES(?,?)", "Odbiór zamówienia",
         "Dzień dobry {imie}, zamówienie jest gotowe do odbioru. Zapraszamy pon-pt 9-17.")
    db.x("INSERT INTO templates(name, body) VALUES(?,?)", "Zmiana godziny",
         "Cześć {imie}, uwaga: zmiana godziny spotkania na 18:00. Do zobaczenia!")

    events = []  # (kiedy, kierunek, telefon, treść, status, kampania, przeczytane, błąd)

    def campaign(name, body, when, states):
        cid = db.x("INSERT INTO campaigns(name, body, created_at) VALUES(?,?,?)", name, body, ago(**when)).lastrowid
        for phone, status in states.items():
            events.append((ago(**when), "out", phone, body.replace("{imie}", first[phone]), status, cid, 1,
                           explain_error("Numer nie istnieje (demo)") if status == "failed" else None))

    def sms(when, direction, phone, body, read=1):
        events.append((ago(**when), direction, phone, body, "received" if direction == "in" else "delivered",
                       None, read, None))

    campaign("Tabliczki – odbiór zamówień", "Dzień dobry {imie}, tabliczki są gotowe do odbioru. Zapraszamy pon-pt 9-17.",
             dict(days=5),
             {"+48600100202": "delivered", "+48600100209": "delivered", "+48600100205": "delivered",
              "+48600100000": "failed", "+48600100204": "sent"})
    sms(dict(days=5, minutes=-12), "in", "+48600100202", "Dziękuję, odbiorę w piątek po 15")
    sms(dict(days=5, minutes=-20), "out", "+48600100202", "Świetnie, do zobaczenia w piątek!")
    sms(dict(days=5, minutes=-40), "in", "+48600100209", "STOP")
    sms(dict(days=4, hours=20), "in", "+48600100205", "A czy można odebrać w sobotę?", read=0)

    campaign("Impreza firmowa – zmiana godziny", "Cześć {imie}, uwaga: impreza zaczyna się o 18:00, nie o 17:00. Do zobaczenia!",
             dict(days=1),
             {"+48600100202": "delivered", "+48600100204": "delivered", "+48600100206": "delivered",
              "+48600100208": "delivered", "+48600100201": "sent", "+48600100203": "delivered"})
    sms(dict(hours=23), "in", "+48600100206", "Ok, będę!")
    sms(dict(hours=22), "in", "+48600100208", "Dzięki za info. Mogę przyjść z osobą towarzyszącą?", read=0)
    sms(dict(hours=21), "in", "+48600100203", "Super, będziemy we czwórkę")
    sms(dict(hours=20), "out", "+48600100203", "Zapisane, cztery miejsca.")
    from .worker import MMS_NOTE
    sms(dict(hours=22, minutes=-1), "in", "+48600100208", MMS_NOTE, read=0)
    sms(dict(hours=2), "in", "+48511222333", "Dzień dobry, czy są jeszcze wolne miejsca na imprezę?", read=0)

    for i, (ts, direction, phone, body, status, cid, read, error) in enumerate(sorted(events, key=lambda e: e[0])):
        db.x("INSERT INTO messages(direction, phone, body, status, gateway_id, campaign_id, error, read, created_at, sent_at) "
             "VALUES(?,?,?,?,?,?,?,?,?,?)", direction, phone, body, status, f"demo-{i}", cid, error, read, ts, ts)
    db.x("INSERT OR IGNORE INTO blocked(phone) VALUES('+48600100209')")
