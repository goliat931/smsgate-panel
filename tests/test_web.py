"""Scenariusz „świeży użytkownik” w trybie demo: ustawienia -> kontakty -> wysyłka -> skrzynka -> historia."""
import time

from fastapi.testclient import TestClient

from sms_panel.db import DB
from sms_panel.web import create_app


def make():
    db = DB(":memory:")
    app = create_app(db, demo=True, start_worker=False)
    client = TestClient(app)
    app.state.http = client          # atrapa bramki działa w tej samej aplikacji pod /_demo
    return db, app, client


def test_fresh_user_flow():
    db, app, c = make()
    worker = app.state.worker

    r = c.get("/", follow_redirects=True)
    assert "Połączmy panel z telefonem" in r.text

    bad = c.post("/ustawienia/test", data={"address": "192.168.1.50:8080", "login": "demo", "password": "zle"}).json()
    assert bad["ok"] is False and "hasło" in bad["message"]
    good = {"address": "192.168.1.50:8080", "login": "demo", "password": "demo"}
    assert c.post("/ustawienia/test", data=good).json()["ok"] is True
    # błędne dane przy pierwszym uruchomieniu nie są zapisywane
    assert "błędne" in c.post("/ustawienia", data={**good, "password": "zle"}).text
    assert db.get("address") is None
    assert "Gotowe" in c.post("/ustawienia", data=good, follow_redirects=True).text

    r = c.post("/kontakty", data={"name": "Ania", "phone": "600 100 202", "new_group": "Impreza X"}, follow_redirects=True)
    assert "+48600100202" in r.text and "Impreza X" in r.text
    assert "już jest w kontaktach" in c.post("/kontakty", data={"name": "Ania2", "phone": "600100202"}).text
    assert "błędny" in c.post("/kontakty", data={"name": "Zły", "phone": "123"}).text
    csv = "imie;telefon;notatka;grupa\nJan;600100209;;Impreza X\nOla;600100205;;Impreza X\nZły;12;;\n"
    r = c.post("/kontakty/import", files={"plik": ("lista.csv", csv.encode())})
    # krok 2: sam podgląd, nic jeszcze nie zapisano
    assert "Nowe osoby: <b>2</b>" in r.text and "błędny numer telefonu" in r.text
    assert db.one("SELECT COUNT(*) n FROM contacts")["n"] == 1
    assert "Dodano nowych osób: <b>2</b>" in c.post("/kontakty/import/zapisz").text
    assert "Wybierz go jeszcze raz" in c.post("/kontakty/import/zapisz", follow_redirects=True).text   # drugi klik
    gid = db.one("SELECT id FROM grp")["id"]

    r = c.post("/wysylka/podglad", data={"body": "Cześć {imie}, zmiana godziny na 18:00", "grupy": [gid],
                                         "template_name": "Zmiana godziny"})
    assert "Cześć Ania, zmiana godziny na 18:00" in r.text and "Wyślij do 3 osób" in r.text
    assert db.one("SELECT name FROM templates")["name"] == "Zmiana godziny"
    start = {"name": "Test", "body": "Cześć {imie}, zmiana godziny na 18:00", "nonce": "n1",
             "ids": ",".join(str(r["id"]) for r in db.q("SELECT id FROM contacts"))}
    assert "nie zaznaczono potwierdzenia" in c.post("/wysylka/start", data=start, follow_redirects=True).text
    c.post("/wysylka/start", data={**start, "potwierdzam": "1"})
    c.post("/wysylka/start", data={**start, "potwierdzam": "1"})   # podwójne kliknięcie
    assert db.one("SELECT COUNT(*) n FROM messages")["n"] == 3

    db.set("pace_min", 1)
    db.set("pace_max", 1)
    t = time.time()
    for i in range(4):
        worker.tick(t + i * 2)
    assert db.one("SELECT COUNT(*) n FROM messages WHERE status='queued'")["n"] == 0
    time.sleep(5.2)                   # atrapa odpisuje po 5 s
    worker.tick(t + 60)

    r = c.get("/kampanie")
    assert "Zakończona" in r.text
    assert "Ania;+48600100202;Dostarczono;;tak" in c.get("/kampanie/1/csv").text
    assert "Test" in c.get("/kampanie.csv").text

    r = c.get("/skrzynka?filtr=wymaga")
    assert "Ania" in r.text and "Jan" in r.text and "Ola" not in r.text
    r = c.get("/skrzynka?filtr=brak&kampania=1")
    assert "Ola" in r.text and "Ania" not in r.text
    assert db.one("SELECT 1 FROM blocked WHERE phone='+48600100209'")   # Jan odpisał STOP

    r = c.get("/skrzynka", params={"tel": "+48600100202"})
    assert "Dziękuję, będę!" in r.text
    assert db.one("SELECT COUNT(*) n FROM messages WHERE phone='+48600100202' AND read=0")["n"] == 0
    c.post("/skrzynka/odpowiedz", data={"tel": "+48600100202", "body": "Super, do zobaczenia"})
    worker.tick(t + 70)
    assert db.one("SELECT status FROM messages ORDER BY id DESC")["status"] == "accepted"

    # Jan zrezygnował: podgląd kolejnej wysyłki go pomija
    r = c.post("/wysylka/podglad", data={"body": "Druga", "grupy": [gid]})
    assert "Pominę 1" in r.text and "Wyślij do 2 osób" in r.text


def test_unknown_number_can_be_added_to_contacts():
    db, app, c = make()
    from sms_panel.worker import store_incoming
    store_incoming(db, {"id": "1", "sender": "+48700800900", "contentPreview": "Halo?", "createdAt": None})
    r = c.get("/skrzynka", params={"tel": "+48700800900"})
    assert "Nieznany numer" in r.text and "Dodaj do kontaktów" in r.text
    assert 'value="+48700800900"' in c.get("/kontakty", params={"telefon": "+48700800900"}).text


def test_foreign_site_cannot_trigger_actions():
    app = create_app(DB(":memory:"), demo=True, port=8765, start_worker=False)
    c = TestClient(app, base_url="http://127.0.0.1:8765")
    assert c.get("/_ping").text == "SmsPanel"
    assert c.post("/grupy", data={"name": "x"}, headers={"origin": "https://zla-strona.example"}).status_code == 403
    assert c.post("/grupy", data={"name": "x"}, headers={"origin": "http://127.0.0.1:8765"},
                  follow_redirects=False).status_code == 303
    assert c.get("/_ping", headers={"host": "zla-strona.example"}).status_code == 403


def test_import_keeps_surname_email_and_fills_gaps():
    db, app, c = make()
    c.post("/kontakty", data={"name": "Ania", "phone": "600100202"})
    csv = "nazwisko;imię;e-mail;telefon\nNowak;Anna;anna@example.com;600 100 202\nLis;Ewa;;600100208\n"
    r = c.post("/kontakty/import", files={"plik": ("lista.csv", csv.encode())}, data={"grupa": "Nowi"})
    assert "Już są w kontaktach: <b>1</b>" in r.text and "Rozpoznane kolumny: <b>imię, nazwisko, telefon, e-mail</b>" in r.text
    assert "Dodano nowych osób: <b>1</b>" in c.post("/kontakty/import/zapisz").text
    ania = db.one("SELECT * FROM contacts WHERE phone='+48600100202'")
    assert (ania["name"], ania["surname"], ania["email"]) == ("Ania", "Nowak", "anna@example.com")   # imię nie nadpisane
    assert "Ewa Lis" in c.get("/kontakty").text
    assert db.one("SELECT COUNT(*) n FROM contact_grp")["n"] == 2


def test_groups_rename_move_copy_remove_and_vcard():
    db, app, c = make()
    for name, phone in [("Ania", "600100201"), ("Jan", "600100202"), ("Ola", "600100203")]:
        c.post("/kontakty", data={"name": name, "surname": "Testowa", "phone": phone, "new_group": "A"})
    a = db.one("SELECT id FROM grp WHERE name='A'")["id"]
    assert "Teraz dodaj" in c.post("/grupy", data={"name": "B"}, follow_redirects=True).text
    b = db.one("SELECT id FROM grp WHERE name='B'")["id"]
    ids = [r["id"] for r in db.q("SELECT id FROM contacts ORDER BY id")]

    def members(g):
        return [r["contact_id"] for r in db.q("SELECT contact_id FROM contact_grp WHERE grp_id=? ORDER BY 1", g)]

    assert "już istnieje" in c.post("/grupy", data={"name": "A"}, follow_redirects=True).text
    assert "nazywa się już" in c.post(f"/grupy/{b}/nazwa", data={"name": "A"}, follow_redirects=True).text
    assert "Grupa: Impreza X" in c.post(f"/grupy/{b}/nazwa", data={"name": "Impreza X"}, follow_redirects=True).text

    assert "Najpierw zaznacz" in c.post(f"/grupy/{a}/czlonkowie", data={"akcja": "usun"}, follow_redirects=True).text
    assert "Wybierz z listy" in c.post(f"/grupy/{a}/czlonkowie", data={"akcja": "przenies", "ids": ids[:1]},
                                       follow_redirects=True).text
    c.post(f"/grupy/{a}/czlonkowie", data={"akcja": "przenies", "ids": ids[:1], "cel": b})
    assert (members(a), members(b)) == (ids[1:], ids[:1])
    c.post(f"/grupy/{a}/czlonkowie", data={"akcja": "kopiuj", "ids": ids[1:2], "cel": b})
    assert (members(a), members(b)) == (ids[1:], ids[:2])
    c.post(f"/grupy/{a}/czlonkowie", data={"akcja": "usun", "ids": ids[2:]})
    assert members(a) == ids[1:2]
    c.post(f"/grupy/{a}/dodaj", data={"ids": [ids[0], ids[2]]})
    assert members(a) == ids

    r = c.get(f"/grupy/{b}/vcf")
    assert r.headers["content-type"].startswith("text/vcard") and "Impreza%20X.vcf" in r.headers["content-disposition"]
    assert r.text.count("BEGIN:VCARD") == 2 and "FN:Ania Testowa" in r.text and "CATEGORIES:Impreza X" in r.text
    assert c.get("/grupy/0/vcf").text.count("BEGIN:VCARD") == 3

    c.post(f"/grupy/{a}/usun")
    assert db.one("SELECT COUNT(*) n FROM contacts")["n"] == 3 and not members(a)
    assert "Impreza X" in c.get("/grupy").text and "Impreza X" in c.get(f"/wysylka?grupa={b}").text


def test_demo_examples_fill_every_screen():
    from sms_panel.demo import reset, seed
    db, app, c = make()
    seed(db)
    seed(db)   # drugi raz nic nie dubluje
    assert db.one("SELECT COUNT(*) n FROM contacts")["n"] == 10
    assert "Anna Nowak" in c.get("/kontakty").text and "anna.nowak@example.com" in c.get("/kontakty").text
    assert "Tabliczki – zamówili" in c.get("/grupy").text
    r = c.get("/kampanie")
    assert "Tabliczki – odbiór zamówień" in r.text and "Impreza firmowa – zmiana godziny" in r.text
    r = c.get("/skrzynka?filtr=wymaga")
    assert "Nieznany numer" in r.text and "Ewa Kamińska" in r.text and "Marek Wójcik" in r.text
    assert "Dzień dobry Anna, tabliczki" in c.get("/skrzynka", params={"tel": "+48600100202"}).text
    r = c.get("/skrzynka?filtr=brak&kampania=2")
    assert "Tomasz Dąbrowski" in r.text and "Marek Wójcik" not in r.text
    c.post("/kontakty", data={"name": "Nowy", "phone": "600900900"})
    c.post("/demo/przyklady")
    assert db.one("SELECT COUNT(*) n FROM contacts")["n"] == 10


def test_counter_retry_and_default_campaign_filter():
    from sms_panel.demo import seed
    db, app, c = make()
    seed(db)
    assert c.post("/wysylka/licz", data={"body": "a" * 161}).json()["text"].startswith("Ta wiadomość to 2 SMS-y (161 zn.)")
    assert "70 znaków" in c.post("/wysylka/licz", data={"body": "ż" * 71}).json()["text"]
    # „Nie odpowiedzieli” bez wybranej wysyłki pokazuje ostatnią, a nie wszystkie rozmowy
    r = c.get("/skrzynka?filtr=brak")
    assert "Tomasz Dąbrowski" in r.text and "Marek Wójcik" not in r.text
    # „Wyślij ponownie”: wraca do kolejki z nowym identyfikatorem, drugi klik niczego nie dubluje
    m = db.one("SELECT * FROM messages WHERE status='failed'")
    assert "Wyślij ponownie" in c.get(f"/kampanie/{m['campaign_id']}").text
    c.post(f"/wiadomosci/{m['id']}/ponow")
    c.post(f"/wiadomosci/{m['id']}/ponow")
    again = db.one("SELECT * FROM messages WHERE id=?", m["id"])
    assert again["status"] == "queued" and again["gateway_id"] != m["gateway_id"]
    assert db.one("SELECT COUNT(*) n FROM messages WHERE phone=? AND direction='out'", m["phone"])["n"] == 1
    # osoba po STOP: wyjaśnienie w rozmowie
    assert "poprosiła o brak wiadomości" in c.get("/skrzynka", params={"tel": "+48600100209"}).text
    # utrata połączenia z telefonem: wyraźny pasek na każdej stronie
    db.set("address", "192.168.1.50:8080")
    app.state.worker.online, app.state.worker.error = False, "Telefon nie odpowiada."
    r = c.get("/kontakty")
    assert "Brak połączenia z telefonem. Ponawiam próbę" in r.text and "Telefon nie odpowiada." in r.text


def test_preview_limit_warning_plain_text_big_send_and_hints():
    from sms_panel.demo import seed
    db, app, c = make()
    seed(db)
    db.set("max_recipients", 3)
    gid = db.one("SELECT id FROM grp WHERE name='Impreza firmowa'")["id"]      # 6 osób
    long = "Zażółć gęślą jaźń. " * 12                                           # 4 SMS-y z polskimi znakami
    r = c.post("/wysylka/podglad", data={"body": long, "grupy": [gid]})
    # 6 x 4 = 24 SMS-y to cały budżet (80% z 30), w oknie nic nie wyszło -> jeszcze bez ostrzeżenia o limicie
    assert "zejdzie <b>24</b>" in r.text and "Jak zwiększyć limit Androida" not in r.text
    db.set("limit_count", 10)
    r = c.post("/wysylka/podglad", data={"body": long, "grupy": [gid]})
    assert "Jak zwiększyć limit Androida" in r.text and "Bez polskich znaków byłoby to 12 zamiast 24" in r.text
    assert "około 60 min" in r.text                             # 16 SMS-ów ponad budżet 8 na 30 min
    assert "Wszyscy dostaną identyczną treść" in r.text and "To duża wysyłka: 6 osób" in r.text
    r = c.post("/wysylka/podglad", data={"body": long + " bit.ly/x {imie}", "grupy": [gid], "bez_pl": "1"})
    assert "skrócony link" in r.text and "Zazolc gesla jazn" in r.text and "identyczną" not in r.text
    assert "byłby to 2 SMS-y" in c.post("/wysylka/licz", data={"body": long}).json()["text"]

    ids = ",".join(str(x["contact_id"]) for x in db.q("SELECT contact_id FROM contact_grp WHERE grp_id=?", gid))
    start = {"name": "T", "body": "Żółw {imie}", "nonce": "n9", "ids": ids, "potwierdzam": "1", "bez_pl": "1"}
    assert "duża wysyłka" in c.post("/wysylka/start", data=start, follow_redirects=True).text
    c.post("/wysylka/start", data={**start, "duza": "1"})
    row = db.one("SELECT body, segments FROM messages WHERE campaign_id=(SELECT id FROM campaigns WHERE nonce='n9')")
    assert row["body"].startswith("Zolw ") and row["segments"] == 1
    assert "Taka sama treść była już wysyłana" in c.post("/wysylka/podglad", data={"body": "Żółw {imie}", "grupy": [gid]}).text

    # telefon przyjął wiadomość i od kilku minut nic: podpowiedź, żeby spojrzeć na ekran telefonu
    db.set("address", "192.168.1.50:8080")
    db.x("UPDATE messages SET status='accepted', sent_at=datetime('now','-10 minutes') || '+00:00' WHERE id=(SELECT MAX(id) FROM messages)")
    db.x("UPDATE messages SET sent_at=replace(sent_at,' ','T') WHERE status='accepted'")
    assert "Sprawdź ekran telefonu" in c.get("/kontakty").text
    assert "30 SMS-ów w ciągu 30 minut" in c.get("/pomoc/limit").text
    c.post("/ustawienia", data={"address": "192.168.1.50:8080", "login": "demo", "password": "demo",
                                "limit_count": "200", "limit_window": "30", "max_recipients": "80"})
    assert (db.get("limit_count"), db.get("max_recipients"), db.get("pace_min")) == ("200", "80", "8.0")


def test_saving_settings_sets_connection_state_at_once():
    db, app, c = make()
    good = {"address": "192.168.1.50:8080", "login": "demo", "password": "demo"}
    app.state.worker.online, app.state.worker.error = False, "stary błąd"
    r = c.post("/ustawienia", data=good, follow_redirects=True)
    assert "Gotowe" in r.text and "Brak połączenia z telefonem. Ponawiam" not in r.text and "Telefon połączony" in r.text
    r = c.post("/ustawienia", data={**good, "password": "zle"})
    assert "zapisane, ale" in r.text and "Brak połączenia z telefonem. Ponawiam" in r.text


def test_page_tells_browser_about_newest_incoming_message():
    db, app, c = make()
    from sms_panel.worker import store_incoming
    store_incoming(db, {"id": "n1", "sender": "+48700800900", "contentPreview": "Halo?", "createdAt": None})
    mid = db.one("SELECT MAX(id) n FROM messages")["n"]
    r = c.get("/pomoc/limit")
    assert f'data-ostatnia="{mid}"' in r.text and 'data-od="+48700800900"' in r.text and "Halo?" not in r.text


def test_security_headers_and_csv_formula_cells():
    from sms_panel.web import csv_cell
    db, app, c = make()
    r = c.get("/pomoc/limit")
    assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert csv_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and csv_cell("@x") == "'@x" and csv_cell("-2+3") == "'-2+3"
    assert csv_cell("+48600100200") == "+48600100200" and csv_cell("Anna") == "Anna" and csv_cell(5) == 5

