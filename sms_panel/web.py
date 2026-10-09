"""Aplikacja webowa: wszystkie ekrany panelu."""
import csv
import io
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .core import normalize_phone, parse_csv, plain, render, sms_segments, vcard
from .db import now_iso
from .demo import make_demo, reset as demo_reset
from .gateway import Gateway, GatewayError, parse_address
from .worker import RESERVE, Worker, budget

HERE = Path(__file__).parent
SHORTENERS = ("bit.ly", "tinyurl.", "t.co/", "cutt.ly", "tiny.pl", "goo.gl", "is.gd", "ow.ly", "rebrand.ly", "lnk.")
log = logging.getLogger("sms_panel")

STATUS_PL = {"queued": "W kolejce", "sending": "Wysyłanie…", "accepted": "Wysyłanie…", "sent": "Wysłano",
             "delivered": "Dostarczono", "failed": "Błąd", "cancelled": "Anulowano", "received": "Odebrano"}

FULL = "trim(c.name || ' ' || c.surname)"          # imię i nazwisko do wyświetlania
BY_NAME = "c.name COLLATE NOCASE, c.surname COLLATE NOCASE"

CAMPAIGNS_SQL = """
SELECT c.*, COUNT(m.id) total,
       COALESCE(SUM(m.status='delivered'),0) delivered,
       COALESCE(SUM(m.status IN ('sent','delivered')),0) sent,
       COALESCE(SUM(m.status IN ('accepted','sent')),0) unconfirmed,
       COALESCE(SUM(m.status='failed'),0) failed,
       COALESCE(SUM(m.status='cancelled'),0) cancelled,
       COALESCE(SUM(m.status IN ('queued','sending')),0) waiting,
       (SELECT COUNT(DISTINCT i.phone) FROM messages i WHERE i.direction='in' AND i.created_at>=c.created_at
          AND i.phone IN (SELECT phone FROM messages WHERE campaign_id=c.id)) replies
FROM campaigns c LEFT JOIN messages m ON m.campaign_id=c.id
WHERE (? IS NULL OR c.id=?) GROUP BY c.id ORDER BY c.id DESC
"""


def local_time(ts, fmt="%d.%m %H:%M"):
    try:
        return datetime.fromisoformat(ts).astimezone().strftime(fmt)
    except (TypeError, ValueError):
        return ts or ""


def campaign_state(c):
    if c["status"] == "cancelled":
        return "Anulowana"
    if c["waiting"] and c["status"] == "paused":
        return "Wstrzymana"
    return "W trakcie" if c["waiting"] else "Zakończona"


def sms_word(n):
    """1 SMS, 2 SMS-y, 5 SMS-ów, 22 SMS-y."""
    if n == 1:
        return "SMS"
    return "SMS-y" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "SMS-ów"


def dur(minutes):
    """Czas dla człowieka: 12 min, 2 godz. 5 min."""
    return f"{minutes} min" if minutes < 90 else f"{minutes // 60} godz. {minutes % 60} min"


def go(url, msg=None):
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    return RedirectResponse(url, 303)


def csv_cell(v):
    """Excel wykonuje komórki zaczynające się od = + - @ jako formuły. Apostrof z przodu robi z nich zwykły tekst.
    Numer telefonu (+48...) zostaje bez zmian."""
    s = str(v)
    return "'" + s if s[:1] in ("=", "@", "\t", "\r") or (s[:1] in "+-" and not s[1:].isdigit() and s[1:]) else v


def csv_response(filename, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(header)
    w.writerows([csv_cell(v) for v in row] for row in rows)
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",  # BOM: Excel
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def create_app(db, demo=False, port=None, start_worker=True):
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["czas"] = local_time
    templates.env.globals.update(STATUS_PL=STATUS_PL, campaign_state=campaign_state, sms_word=sms_word, dur=dur)

    def make_gateway(address, login, password):
        base = (f"http://127.0.0.1:{port}" if port else "http://testserver") + "/_demo" if demo \
            else parse_address(address)
        return Gateway(base, login, password, app.state.http)

    def gateway():
        if not db.get("address"):
            return None
        try:
            return make_gateway(db.get("address"), db.get("login", ""), db.get("password", ""))
        except GatewayError:
            return None

    worker = Worker(db, gateway)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        yield
        worker.stop.set()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.http = httpx.Client(timeout=httpx.Timeout(8, connect=3))
    app.state.worker = worker
    app.state.pending_import = None
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    if demo:
        app.include_router(make_demo(), prefix="/_demo")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        """Panel wysyła SMS-y, więc obce strony WWW nie mogą wywoływać go w tle (CSRF, DNS rebinding)."""
        if port and not request.url.path.startswith("/_demo"):
            ours = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if request.headers.get("host") not in ours:
                return PlainTextResponse("Niedozwolony adres.", 403)
            if request.method not in ("GET", "HEAD"):
                src = request.headers.get("origin") or request.headers.get("referer") or ""
                if urlsplit(src).netloc not in ours:
                    return PlainTextResponse("Niedozwolone źródło żądania.", 403)
        response = await call_next(request)
        # obca strona nie może osadzić panelu w ramce i podsunąć kliknięcia (clickjacking)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(Exception)
    async def oops(request: Request, exc: Exception):
        log.warning("Błąd strony %s: %s", request.url.path, type(exc).__name__)
        return page(request, "error.html", status_code=500)

    def page(request, template, status_code=200, **ctx):
        unread = db.one("SELECT COUNT(DISTINCT phone) n FROM messages WHERE direction='in' AND read=0")["n"]
        t = datetime.now(timezone.utc)
        stuck = db.one("SELECT COUNT(*) n FROM messages WHERE status='accepted' AND sent_at < ? AND sent_at > ?",
                       (t - timedelta(minutes=3)).isoformat(timespec="seconds"),
                       (t - timedelta(days=1)).isoformat(timespec="seconds"))["n"]
        # ostatnia wiadomość przychodząca: po niej przeglądarka poznaje, że trzeba pokazać powiadomienie
        last_in = db.one("SELECT m.id, m.phone, TRIM(COALESCE(c.name,'') || ' ' || COALESCE(c.surname,'')) name "
                         "FROM messages m LEFT JOIN contacts c ON c.phone=m.phone "
                         "WHERE m.direction='in' ORDER BY m.id DESC LIMIT 1")
        ctx.update(stuck=stuck, limited=worker.limited, last_in=last_in)
        ctx.update(demo=demo, msg=request.query_params.get("msg"), unread=unread, path=request.url.path,
                   configured=bool(db.get("address")), online=worker.online, phone_error=worker.error)
        return templates.TemplateResponse(request, template, ctx, status_code=status_code)

    def groups():
        return db.q("SELECT g.*, (SELECT COUNT(*) FROM contact_grp cg WHERE cg.grp_id=g.id) n "
                    "FROM grp g ORDER BY g.name COLLATE NOCASE")

    def ensure_group(name):
        db.x("INSERT OR IGNORE INTO grp(name) VALUES(?)", name)
        return db.one("SELECT id FROM grp WHERE name=?", name)["id"]

    def set_blocked(phone, on):
        db.x("INSERT OR IGNORE INTO blocked(phone) VALUES(?)" if on else "DELETE FROM blocked WHERE phone=?", phone)

    def recipients(group_ids, contact_ids):
        """Kontakty z wybranych grup i zaznaczone pojedynczo, bez powtórzeń."""
        g = ",".join("?" * len(group_ids)) or "NULL"
        c = ",".join("?" * len(contact_ids)) or "NULL"
        return db.q(f"SELECT c.*, EXISTS(SELECT 1 FROM blocked b WHERE b.phone=c.phone) blocked FROM contacts c "
                    f"WHERE c.id IN ({c}) OR c.id IN (SELECT contact_id FROM contact_grp WHERE grp_id IN ({g})) "
                    f"ORDER BY {BY_NAME}", *contact_ids, *group_ids)

    def estimate(count, segments):
        """(minuty do końca, czy hamuje limit telefonu). Liczy tempo i przesuwane okno limitu."""
        used, limit, window = budget(db)
        cap = max(1, int(limit * RESERVE))
        free = max(0, cap - used)
        pace = (float(db.get("pace_min", 8)) + float(db.get("pace_max", 20))) / 2
        by_limit = (segments - free) / cap * window if segments > free else 0
        return max(1, round(max(count * pace / 60, by_limit))), segments > free

    def hygiene(body, count):
        """Podpowiedzi, które zmniejszają ryzyko, że operator uzna wysyłkę za spam."""
        out = []
        if any(k in body.lower() for k in SHORTENERS):
            out.append("W treści jest skrócony link. Operatorzy często blokują takie SMS-y – wklej pełny adres strony.")
        if count >= 5 and "{" not in body:
            out.append("Wszyscy dostaną identyczną treść. Kliknij „Wróć i popraw” i użyj „Wstaw imię” – "
                       "wiadomości z imieniem rzadziej trafiają do filtrów operatora.")
        if db.one("SELECT 1 FROM campaigns WHERE body=? AND status<>'cancelled'", body):
            out.append("Taka sama treść była już wysyłana. Powtarzanie tej samej wiadomości zwiększa ryzyko blokady numeru.")
        return out

    @app.get("/pomoc/limit")
    def help_limit(request: Request):
        used, limit, window = budget(db)
        return page(request, "help_limit.html", used=used, limit=limit, window=int(window))

    @app.get("/_ping")
    def ping():
        return PlainTextResponse("SmsPanel")

    @app.get("/")
    def home():
        return go("/skrzynka" if db.get("address") else "/ustawienia")

    # ---------- Ustawienia ----------

    def settings_page(request, **ctx):
        base = dict(address=db.get("address", ""), login=db.get("login", ""), password=db.get("password", ""),
                    pace_min=db.get("pace_min", "8"), pace_max=db.get("pace_max", "20"),
                    limit_count=db.get("limit_count", "30"), limit_window=db.get("limit_window", "30"),
                    max_recipients=db.get("max_recipients", "50"), reserve=int(RESERVE * 100))
        if demo and not base["address"]:
            base.update(address="192.168.1.50:8080", login="demo", password="demo")
        return page(request, "settings.html", **{**base, **ctx})

    def check(address, login, password):
        try:
            make_gateway(address, login, password).check()
            return True, "Połączenie działa. Telefon odpowiada."
        except GatewayError as e:
            return False, str(e)

    @app.get("/ustawienia")
    def settings(request: Request):
        return settings_page(request)

    @app.post("/ustawienia/test")
    def settings_test(address: str = Form(""), login: str = Form(""), password: str = Form("")):
        ok, message = check(address.strip(), login.strip(), password)
        return {"ok": ok, "message": message}

    @app.post("/ustawienia")
    def settings_save(request: Request, address: str = Form(""), login: str = Form(""), password: str = Form(""),
                      pace_min: float = Form(8), pace_max: float = Form(20), limit_count: int = Form(30),
                      limit_window: int = Form(30), max_recipients: int = Form(50)):
        address, login = address.strip(), login.strip()
        pace_min = max(1.0, pace_min)
        pace_max = max(pace_min, pace_max)
        ok, message = check(address, login, password)
        if not ok and not db.get("address"):
            # pierwsze uruchomienie: nie zapisuj ustawień, które nie działają
            return settings_page(request, address=address, login=login, password=password, test=(ok, message))
        for k, v in dict(address=address, login=login, password=password, pace_min=pace_min, pace_max=pace_max,
                         limit_count=max(1, limit_count), limit_window=max(1, limit_window),
                         max_recipients=max(1, max_recipients)).items():
            db.set(k, v)
        if not db.get("inbox_since"):
            db.set("inbox_since", now_iso())  # odbieramy odpowiedzi od tej chwili, bez starych prywatnych SMS-ów
        worker.wait_until = worker.failures = 0
        worker.online, worker.error = ok, "" if ok else message
        if not ok:
            return settings_page(request, test=(ok, "Ustawienia zapisane, ale połączenie z telefonem nie działa. "
                                                   "Co sprawdzić – jest na czerwonym pasku u góry."))
        return go("/kontakty" if not db.one("SELECT 1 FROM contacts") else "/ustawienia",
                  "Gotowe! Panel jest połączony z telefonem.")

    @app.post("/demo/przyklady")
    def demo_examples():
        if demo:
            demo_reset(db)
        return go("/skrzynka", "Wczytano przykładowe dane.")

    # ---------- Kontakty ----------

    def contacts_page(request, **ctx):
        grupa = request.query_params.get("grupa")
        gid = int(grupa) if grupa and grupa.isdigit() else None
        rows = db.q(
            "SELECT c.*, EXISTS(SELECT 1 FROM blocked b WHERE b.phone=c.phone) blocked, "
            "(SELECT group_concat(g.name, ', ') FROM grp g JOIN contact_grp cg ON cg.grp_id=g.id "
            " WHERE cg.contact_id=c.id) grupy FROM contacts c "
            "WHERE (? IS NULL OR c.id IN (SELECT contact_id FROM contact_grp WHERE grp_id=?)) "
            f"ORDER BY {BY_NAME}", gid, gid)
        return page(request, "contacts.html", contacts=rows, groups=groups(), gid=gid,
                    new_phone=request.query_params.get("telefon", ""), **ctx)

    @app.get("/kontakty")
    def contacts(request: Request):
        return contacts_page(request)

    def save_groups(cid, group_ids, new_group):
        db.x("DELETE FROM contact_grp WHERE contact_id=?", cid)
        ids = set(group_ids)
        if new_group.strip():
            ids.add(ensure_group(new_group.strip()))
        for g in ids:
            db.x("INSERT OR IGNORE INTO contact_grp(contact_id, grp_id) VALUES(?,?)", cid, g)

    @app.post("/kontakty")
    def contact_add(request: Request, name: str = Form(""), surname: str = Form(""), phone: str = Form(""),
                    email: str = Form(""), note: str = Form(""), grupy: list[int] = Form([]),
                    new_group: str = Form("")):
        form = dict(name=name, surname=surname, phone=phone, email=email, note=note)
        num = normalize_phone(phone)
        if not num:
            return contacts_page(request, form=form, error=f"Numer „{phone}” wygląda na błędny. Wpisz 9 cyfr, "
                                 "np. 600 100 200, albo numer zagraniczny z plusem, np. +49 151 2345678.")
        old = db.one(f"SELECT {FULL} kto FROM contacts c WHERE phone=?", num)
        if old:
            return contacts_page(request, form=form, error=f"Ten numer już jest w kontaktach jako „{old['kto']}”.")
        cid = db.x("INSERT INTO contacts(name, surname, phone, email, note) VALUES(?,?,?,?,?)",
                   name.strip() or num, surname.strip(), num, email.strip(), note.strip()).lastrowid
        save_groups(cid, grupy, new_group)
        return go("/kontakty", "Dodano kontakt.")

    @app.get("/kontakty/import")
    def import_start(request: Request):
        return page(request, "import.html", step=1, groups=groups())

    @app.post("/kontakty/import")
    async def import_check(request: Request, plik: UploadFile = File(...), grupa: str = Form("")):
        rows, errors, columns = parse_csv(await plik.read())
        known = {r["phone"] for r in db.q("SELECT phone FROM contacts")}
        # ponytail: jeden czekający import w pamięci (panel ma jednego użytkownika);
        # dwa importy naraz w dwóch kartach -> trzymać je pod osobnymi kluczami.
        app.state.pending_import = dict(rows=rows, grupa=grupa.strip())
        return page(request, "import.html", step=2, rows=rows, errors=errors, columns=columns, grupa=grupa.strip(),
                    new=sum(r["phone"] not in known for r in rows), existed=sum(r["phone"] in known for r in rows))

    @app.post("/kontakty/import/zapisz")
    def import_save(request: Request):
        pending, app.state.pending_import = app.state.pending_import, None
        if not pending:
            return go("/kontakty/import", "Ten plik nie czeka już na zapisanie. Wybierz go jeszcze raz.")
        grupa, added, existed = pending["grupa"], 0, 0
        for r in pending["rows"]:
            old = db.one("SELECT id FROM contacts WHERE phone=?", r["phone"])
            if old:  # znany numer: niczego nie nadpisujemy, tylko uzupełniamy puste pola
                cid, existed = old["id"], existed + 1
                db.x("UPDATE contacts SET surname=CASE WHEN surname='' THEN ? ELSE surname END, "
                     "email=CASE WHEN email='' THEN ? ELSE email END, note=CASE WHEN note='' THEN ? ELSE note END "
                     "WHERE id=?", r["surname"], r["email"], r["note"], cid)
            else:
                cid = db.x("INSERT INTO contacts(name, surname, phone, email, note) VALUES(?,?,?,?,?)",
                           r["name"], r["surname"], r["phone"], r["email"], r["note"]).lastrowid
                added += 1
            for g in r["groups"] + ([grupa] if grupa else []):
                db.x("INSERT OR IGNORE INTO contact_grp(contact_id, grp_id) VALUES(?,?)", cid, ensure_group(g))
        return page(request, "import.html", step=3, added=added, existed=existed,
                    group=db.one("SELECT * FROM grp WHERE name=?", grupa) if grupa else None)

    @app.get("/kontakty/{cid}")
    def contact_edit(request: Request, cid: int):
        c = db.one("SELECT c.*, EXISTS(SELECT 1 FROM blocked b WHERE b.phone=c.phone) blocked "
                   "FROM contacts c WHERE id=?", cid)
        if not c:
            return go("/kontakty", "Nie ma już takiego kontaktu.")
        mine = {r["grp_id"] for r in db.q("SELECT grp_id FROM contact_grp WHERE contact_id=?", cid)}
        return page(request, "contact_edit.html", c=c, groups=groups(), mine=mine,
                    error=request.query_params.get("blad"))

    @app.post("/kontakty/{cid}")
    def contact_save(cid: int, name: str = Form(""), surname: str = Form(""), phone: str = Form(""),
                     email: str = Form(""), note: str = Form(""), grupy: list[int] = Form([]),
                     new_group: str = Form(""), blocked: str = Form("")):
        num = normalize_phone(phone)
        if not num:
            return go(f"/kontakty/{cid}?blad=" + quote("Numer telefonu wygląda na błędny. Wpisz 9 cyfr, np. 600 100 200, i zapisz jeszcze raz."))
        if db.one("SELECT 1 FROM contacts WHERE phone=? AND id<>?", num, cid):
            return go(f"/kontakty/{cid}?blad=" + quote("Inny kontakt ma już ten numer. Wpisz inny numer albo usuń tamten kontakt."))
        db.x("UPDATE contacts SET name=?, surname=?, phone=?, email=?, note=? WHERE id=?",
             name.strip() or num, surname.strip(), num, email.strip(), note.strip(), cid)
        save_groups(cid, grupy, new_group)
        set_blocked(num, bool(blocked))
        return go("/kontakty", "Zapisano zmiany.")

    @app.post("/kontakty/{cid}/usun")
    def contact_delete(cid: int):
        db.x("DELETE FROM contact_grp WHERE contact_id=?", cid)
        db.x("DELETE FROM contacts WHERE id=?", cid)
        return go("/kontakty", "Usunięto kontakt. Historia rozmowy została w skrzynce.")

    # ---------- Grupy ----------

    def members(gid, inside=True):
        return db.q("SELECT c.*, EXISTS(SELECT 1 FROM blocked b WHERE b.phone=c.phone) blocked FROM contacts c "
                    f"WHERE c.id {'IN' if inside else 'NOT IN'} (SELECT contact_id FROM contact_grp WHERE grp_id=?) "
                    f"ORDER BY {BY_NAME}", gid)

    @app.get("/grupy")
    def groups_page(request: Request):
        return page(request, "groups.html", groups=groups(),
                    total=db.one("SELECT COUNT(*) n FROM contacts")["n"])

    @app.post("/grupy")
    def group_add(name: str = Form("")):
        name = name.strip()
        if not name:
            return go("/grupy")
        if db.one("SELECT 1 FROM grp WHERE name=?", name):
            return go("/grupy", f"Grupa „{name}” już istnieje.")
        return go(f"/grupy/{ensure_group(name)}", "Utworzono grupę. Teraz dodaj do niej osoby.")

    @app.get("/grupy/{gid}")
    def group_page(request: Request, gid: int):
        g = db.one("SELECT * FROM grp WHERE id=?", gid)
        if not g:
            return go("/grupy", "Nie ma już takiej grupy.")
        return page(request, "group.html", g=g, members=members(gid), others=members(gid, inside=False),
                    groups=[x for x in groups() if x["id"] != gid])

    @app.get("/grupy/{gid}/vcf")
    def group_vcf(gid: int):
        """Wizytówki grupy do wczytania w telefonie. gid=0: wszystkie kontakty."""
        g = db.one("SELECT * FROM grp WHERE id=?", gid)
        if gid and not g:
            return go("/grupy", "Nie ma już takiej grupy.")
        rows = members(gid) if g else db.q(f"SELECT c.* FROM contacts c ORDER BY {BY_NAME}")
        label = g["name"] if g else "Wszystkie kontakty"
        return Response(vcard(rows, g["name"] if g else ""), media_type="text/vcard; charset=utf-8", headers={
            "Content-Disposition": f"attachment; filename=\"kontakty-{gid}.vcf\"; filename*=UTF-8''{quote(label)}.vcf"})

    @app.post("/grupy/{gid}/nazwa")
    def group_rename(gid: int, name: str = Form("")):
        name = name.strip()
        if not name:
            return go(f"/grupy/{gid}", "Nazwa grupy nie może być pusta.")
        if db.one("SELECT 1 FROM grp WHERE name=? AND id<>?", name, gid):
            return go(f"/grupy/{gid}", f"Inna grupa nazywa się już „{name}”. Jeśli chcesz je połączyć, "
                                       "zaznacz wszystkie osoby i użyj „Przenieś do innej grupy”.")
        db.x("UPDATE grp SET name=? WHERE id=?", name, gid)
        return go(f"/grupy/{gid}", "Zmieniono nazwę grupy.")

    # ponytail: zaznaczone osoby idą jako osobne pola formularza (limit Starlette: 1000 naraz);
    # przy większych grupach -> jedno pole z listą id, jak w /wysylka/start.
    @app.post("/grupy/{gid}/dodaj")
    def group_add_members(gid: int, ids: list[int] = Form([])):
        for cid in ids:
            db.x("INSERT OR IGNORE INTO contact_grp(contact_id, grp_id) VALUES(?,?)", cid, gid)
        return go(f"/grupy/{gid}", f"Dodano do grupy: {len(ids)}." if ids else "Najpierw zaznacz osoby do dodania.")

    @app.post("/grupy/{gid}/czlonkowie")
    def group_members_action(gid: int, ids: list[int] = Form([]), akcja: str = Form(""), cel: int = Form(0)):
        if not ids:
            return go(f"/grupy/{gid}", "Najpierw zaznacz osoby na liście.")
        target = db.one("SELECT * FROM grp WHERE id=? AND id<>?", cel, gid)
        if akcja in ("przenies", "kopiuj"):
            if not target:
                return go(f"/grupy/{gid}", "Wybierz z listy grupę docelową.")
            for cid in ids:
                db.x("INSERT OR IGNORE INTO contact_grp(contact_id, grp_id) VALUES(?,?)", cid, cel)
        if akcja in ("przenies", "usun"):
            for cid in ids:
                db.x("DELETE FROM contact_grp WHERE contact_id=? AND grp_id=?", cid, gid)
        done = {"przenies": "Przeniesiono do grupy „%s”: %d.", "kopiuj": "Skopiowano do grupy „%s”: %d.",
                "usun": "Usunięto z tej grupy%s: %d. Kontakty zostały."}.get(akcja)
        return go(f"/grupy/{gid}", done % (target["name"] if target and akcja != "usun" else "", len(ids)) if done else None)

    @app.post("/grupy/{gid}/usun")
    def group_delete(gid: int):
        db.x("DELETE FROM contact_grp WHERE grp_id=?", gid)
        db.x("DELETE FROM grp WHERE id=?", gid)
        return go("/grupy", "Usunięto grupę. Kontakty zostały.")

    # ---------- Wysyłka grupowa ----------

    def send_page(request, **ctx):
        in_groups = {r["contact_id"]: r["g"] for r in db.q(
            "SELECT contact_id, group_concat(grp_id) g FROM contact_grp GROUP BY contact_id")}
        base = dict(groups=groups(), contacts=recipients([], [r["id"] for r in db.q("SELECT id FROM contacts")]),
                    templates_=db.q("SELECT * FROM templates ORDER BY name COLLATE NOCASE"), in_groups=in_groups,
                    form=dict(name="", body="", grupy=[], osoby=[], bez_pl=False), step=1)
        return page(request, "send.html", **{**base, **ctx})

    @app.get("/wysylka")
    def send(request: Request, grupa: int = 0):
        return send_page(request, form=dict(name="", body="", grupy=[grupa], osoby=[], bez_pl=False))

    def texts_for(body, to, bez_pl):
        out = [render(body, c["name"], c["phone"], c["note"], c["surname"]) for c in to]
        return [plain(t) for t in out] if bez_pl else out

    @app.post("/wysylka/podglad")
    def send_preview(request: Request, name: str = Form(""), body: str = Form(""), grupy: list[int] = Form([]),
                     osoby: list[int] = Form([]), template_name: str = Form(""), bez_pl: str = Form("")):
        form = dict(name=name, body=body, grupy=grupy, osoby=osoby, bez_pl=bool(bez_pl))
        everyone = recipients(grupy, osoby)
        to = [c for c in everyone if not c["blocked"]]
        if not body.strip():
            return send_page(request, form=form, step=2 if to else 1, error="Wpisz treść wiadomości.")
        if not to:
            return send_page(request, form=form, error="Nie wybrano żadnego odbiorcy. Zaznacz grupę lub osoby.")
        if template_name.strip():
            db.x("INSERT INTO templates(name, body) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET body=excluded.body",
                 template_name.strip(), body)
        texts = texts_for(body, to, bez_pl)
        segs = [sms_segments(t)[0] for t in texts]
        uni = any(sms_segments(t)[2] for t in texts)
        minutes, slowed = estimate(len(to), sum(segs))
        used, limit, window = budget(db)
        cap = int(db.get("max_recipients", 50))
        return page(request, "preview.html", form=form, to=to, skipped=[c for c in everyone if c["blocked"]],
                    samples=list(zip(to, texts))[:3], seg_max=max(segs), seg_total=sum(segs), unicode=uni,
                    seg_plain=sum(sms_segments(plain(t))[0] for t in texts) if uni else 0,
                    minutes=minutes, slowed=slowed, limit=limit, window=int(window), used=used,
                    big=cap if len(to) > cap else 0, tips=hygiene(body, len(to)),
                    campaign_name=name.strip() or f"Wysyłka {local_time(now_iso(), '%d.%m.%Y %H:%M')}",
                    nonce=uuid.uuid4().hex)

    @app.post("/wysylka/popraw")
    def send_back(request: Request, name: str = Form(""), body: str = Form(""), grupy: list[int] = Form([]),
                  osoby: list[int] = Form([]), bez_pl: str = Form("")):
        return send_page(request, step=2, form=dict(name=name, body=body, grupy=grupy, osoby=osoby, bez_pl=bool(bez_pl)))

    @app.post("/wysylka/licz")
    def send_count(body: str = Form(""), bez_pl: str = Form("")):
        """Licznik pod polem treści. Liczy serwer, żeby wynik był ten sam co w podglądzie."""
        if not body:
            return {"text": ""}
        seg, chars, uni = sms_segments(plain(body) if bez_pl else body)
        text = f"Ta wiadomość to {seg} {sms_word(seg)} ({chars} zn.)."
        if uni:
            less = sms_segments(plain(body))[0]
            text += (f" Polskie litery skracają jeden SMS do 70 znaków – bez nich byłby to {less} {sms_word(less)}."
                     if less < seg else " Polskie litery skracają jeden SMS do 70 znaków.")
        return {"text": text + (" Imię lub nazwisko mogą trochę zmienić długość." if "{" in body else "")}

    @app.post("/wysylka/start")
    def send_start(name: str = Form(...), body: str = Form(...), ids: str = Form(...), nonce: str = Form(...),
                   potwierdzam: str = Form(""), bez_pl: str = Form(""), duza: str = Form("")):
        if not potwierdzam:
            return go("/wysylka", "Wysyłka nie ruszyła: nie zaznaczono potwierdzenia.")
        old = db.one("SELECT id FROM campaigns WHERE nonce=?", nonce)
        if old:  # podwójne kliknięcie / odświeżenie strony
            return go(f"/kampanie/{old['id']}")
        ts = now_iso()
        to = [c for c in recipients([], [int(i) for i in ids.split(",") if i.isdigit()]) if not c["blocked"]]
        if len(to) > int(db.get("max_recipients", 50)) and not duza:
            return go("/wysylka", "Wysyłka nie ruszyła: to duża wysyłka i wymaga dodatkowego potwierdzenia w podglądzie.")
        with db.lock:
            db.x("BEGIN")
            try:
                cid = db.x("INSERT INTO campaigns(name, body, nonce, created_at) VALUES(?,?,?,?)",
                           name, body, nonce, ts).lastrowid
                for c, text in zip(to, texts_for(body, to, bez_pl)):
                    db.x("INSERT INTO messages(direction, phone, body, status, gateway_id, campaign_id, created_at, "
                         "segments) VALUES('out',?,?,'queued',?,?,?,?)",
                         c["phone"], text, uuid.uuid4().hex, cid, ts, sms_segments(text)[0])
                db.x("COMMIT")
            except Exception:
                db.x("ROLLBACK")
                raise
        return go(f"/kampanie/{cid}", "Wysyłka ruszyła. Możesz zostawić tę stronę otwartą i patrzeć na postęp.")

    @app.post("/szablony/{tid}/usun")
    def template_delete(tid: int):
        db.x("DELETE FROM templates WHERE id=?", tid)
        return go("/wysylka", "Usunięto szablon.")

    # ---------- Historia (kampanie) ----------

    def campaign_rows(cid):
        return db.q(
            f"SELECT m.*, {FULL} name, c.id contact_id, "
            "EXISTS(SELECT 1 FROM messages i WHERE i.direction='in' AND i.phone=m.phone "
            "       AND i.created_at>=m.created_at) replied "
            "FROM messages m LEFT JOIN contacts c ON c.phone=m.phone WHERE m.campaign_id=? ORDER BY m.id", cid)

    @app.get("/kampanie")
    def campaigns(request: Request):
        return page(request, "campaigns.html", campaigns=db.q(CAMPAIGNS_SQL, None, None))

    @app.get("/kampanie.csv")
    def campaigns_csv():
        return csv_response("historia-wysylek.csv",
                            ["Nazwa", "Data", "Stan", "Odbiorcy", "Wysłano", "Dostarczono", "Błędy", "Odpowiedzi"],
                            [[c["name"], local_time(c["created_at"], "%Y-%m-%d %H:%M"), campaign_state(c), c["total"],
                              c["sent"], c["delivered"], c["failed"], c["replies"]]
                             for c in db.q(CAMPAIGNS_SQL, None, None)])

    @app.get("/kampanie/{cid}")
    def campaign(request: Request, cid: int):
        c = db.one(CAMPAIGNS_SQL, cid, cid)
        if not c:
            return go("/kampanie", "Nie ma takiej wysyłki.")
        left = db.one("SELECT COALESCE(SUM(segments),0) n FROM messages WHERE campaign_id=? "
                      "AND status IN ('queued','sending')", cid)["n"]
        minutes_left, slowed = estimate(c["waiting"], left)
        used, limit, window = budget(db)
        return page(request, "campaign.html", c=c, rows=campaign_rows(cid), minutes_left=minutes_left,
                    slowed=slowed, limit=limit, window=int(window))

    @app.get("/kampanie/{cid}/csv")
    def campaign_csv(cid: int):
        return csv_response(f"wysylka-{cid}.csv", ["Imię", "Telefon", "Status", "Błąd", "Odpowiedział(a)", "Treść"],
                            [[r["name"] or "", r["phone"], STATUS_PL[r["status"]], r["error"] or "",
                              "tak" if r["replied"] else "nie", r["body"]] for r in campaign_rows(cid)])

    @app.post("/wiadomosci/{mid}/ponow")
    def message_retry(mid: int):
        m = db.one("SELECT * FROM messages WHERE id=? AND direction='out'", mid)
        if not m:
            return go("/skrzynka")
        # nowy identyfikator: telefon odrzuciłby powtórkę ze starym jako duplikat.
        # Warunek status='failed' chroni przed podwójnym kliknięciem.
        db.x("UPDATE messages SET status='queued', error=NULL, gateway_id=? WHERE id=? AND status='failed'",
             uuid.uuid4().hex, mid)
        back = f"/kampanie/{m['campaign_id']}" if m["campaign_id"] else "/skrzynka?tel=" + quote(m["phone"])
        return go(back, "Wiadomość wróciła do kolejki i zaraz zostanie wysłana ponownie.")

    @app.post("/kampanie/{cid}/{akcja}")
    def campaign_action(cid: int, akcja: str):
        if akcja == "pauza":
            db.x("UPDATE campaigns SET status='paused' WHERE id=? AND status='running'", cid)
        elif akcja == "wznow":
            db.x("UPDATE campaigns SET status='running' WHERE id=? AND status='paused'", cid)
        elif akcja == "anuluj":
            db.x("UPDATE campaigns SET status='cancelled' WHERE id=?", cid)
            db.x("UPDATE messages SET status='cancelled' WHERE campaign_id=? AND status='queued'", cid)
        return go(f"/kampanie/{cid}")

    # ---------- Skrzynka ----------

    @app.get("/skrzynka")
    def inbox(request: Request, tel: str = "", filtr: str = "", kampania: int = 0):
        where, args = "1=1", []
        campaigns = db.q("SELECT id, name FROM campaigns ORDER BY id DESC")
        if filtr == "brak" and not kampania and campaigns:
            kampania = campaigns[0]["id"]
        if filtr == "wymaga":
            where = "m.direction='in'"
        elif filtr == "brak" and kampania:
            where = ("m.phone IN (SELECT phone FROM messages WHERE campaign_id=?) AND NOT EXISTS("
                     "SELECT 1 FROM messages i JOIN campaigns k ON k.id=? WHERE i.direction='in' "
                     "AND i.phone=m.phone AND i.created_at>=k.created_at)")
            args = [kampania, kampania]
        if tel:  # otwarta rozmowa = przeczytana
            db.x("UPDATE messages SET read=1 WHERE phone=? AND read=0", tel)
        threads = db.q(
            f"SELECT m.phone, m.body, m.direction, m.created_at, {FULL} name, "
            "(SELECT COUNT(*) FROM messages u WHERE u.phone=m.phone AND u.direction='in' AND u.read=0) unread, "
            "EXISTS(SELECT 1 FROM blocked b WHERE b.phone=m.phone) blocked "
            "FROM messages m LEFT JOIN contacts c ON c.phone=m.phone "
            f"WHERE m.id IN (SELECT MAX(id) FROM messages GROUP BY phone) AND {where} ORDER BY m.id DESC", *args)
        thread = contact = None
        blocked = False
        if tel:
            thread = db.q("SELECT * FROM messages WHERE phone=? ORDER BY id", tel)
            contact = db.one("SELECT * FROM contacts WHERE phone=?", tel)
            blocked = bool(db.one("SELECT 1 FROM blocked WHERE phone=?", tel))
        return page(request, "inbox.html", threads=threads, thread=thread, tel=tel, contact=contact,
                    blocked=blocked, filtr=filtr, kampania=kampania,
                    campaigns=campaigns)

    @app.post("/skrzynka/odpowiedz")
    def reply(tel: str = Form(...), body: str = Form("")):
        if body.strip():
            db.x("INSERT INTO messages(direction, phone, body, status, gateway_id, created_at, segments) "
                 "VALUES('out',?,?,'queued',?,?,?)", tel, body.strip(), uuid.uuid4().hex, now_iso(),
                 sms_segments(body.strip())[0])
        return go("/skrzynka?tel=" + quote(tel))

    @app.post("/skrzynka/blokada")
    def block(tel: str = Form(...), on: int = Form(0)):
        set_blocked(tel, on)
        return go("/skrzynka?tel=" + quote(tel))

    return app
