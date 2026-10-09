"""Kolejka wysyłki, statusy, odpowiedzi i rezygnacje - na atrapie bramki, z ręcznie przesuwanym zegarem."""
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sms_panel.db import DB, now_iso
from sms_panel.demo import make_demo
from sms_panel.gateway import Gateway, GatewayError, parse_address
from sms_panel.worker import Worker, store_incoming


class Env:
    def __init__(self):
        self.t = 1_000_000.0
        self.db = DB(":memory:")
        self.db.set("address", "x")
        self.db.set("pace_min", 3)
        self.db.set("pace_max", 3)
        api = FastAPI()
        api.include_router(make_demo(now=lambda: self.t))
        self.http = TestClient(api)
        self.up = True
        self.worker = Worker(self.db, self.gateway)

    def gateway(self, password="demo"):
        client = self.http if self.up else httpx.Client(transport=httpx.MockTransport(self._down))
        return Gateway("http://testserver", "demo", password, client)

    @staticmethod
    def _down(request):
        raise httpx.ConnectError("telefon wyłączony")

    def campaign(self, phones):
        cid = self.db.x("INSERT INTO campaigns(name, body, created_at) VALUES('K','x',?)", now_iso()).lastrowid
        for p in phones:
            self.queue(p, cid)
        return cid

    def queue(self, phone, cid=None):
        self.db.x("INSERT INTO messages(direction, phone, body, status, gateway_id, campaign_id, created_at) "
                  "VALUES('out',?,'Cześć','queued',?,?,?)", phone, uuid.uuid4().hex, cid, now_iso())

    def tick(self, seconds=0.0):
        self.t += seconds
        self.worker.tick(self.t)

    def statuses(self):
        return [r["status"] for r in self.db.q("SELECT status FROM messages WHERE direction='out' ORDER BY id")]


@pytest.fixture
def env():
    return Env()


def test_campaign_is_paced(env):
    env.campaign(["+48600100201", "+48600100203", "+48600100205"])
    env.tick()
    assert env.statuses() == ["accepted", "queued", "queued"]
    env.tick(1)   # za wcześnie na następną
    assert env.statuses().count("queued") == 2
    env.tick(2)   # minęły 3 s
    assert env.statuses().count("queued") == 1
    env.tick(3)
    assert "queued" not in env.statuses()


def test_single_reply_skips_the_pace(env):
    env.campaign(["+48600100201", "+48600100203"])
    env.tick()
    env.queue("+48600100207")  # zwykła odpowiedź w rozmowie
    env.tick(0.5)
    assert env.statuses() == ["accepted", "queued", "accepted"]


def test_statuses_delivered_and_failed(env):
    env.campaign(["+48600100201"])
    env.queue("+48600100000")  # atrapa: numery ...000 kończą błędem
    env.tick()
    env.tick(10)
    rows = env.db.q("SELECT status, error FROM messages ORDER BY id")
    assert [r["status"] for r in rows] == ["delivered", "failed"]
    assert "demo" in rows[1]["error"]


def test_pause_resume_cancel(env):
    cid = env.campaign(["+48600100201", "+48600100203", "+48600100205"])
    env.tick()
    env.db.x("UPDATE campaigns SET status='paused' WHERE id=?", cid)
    env.tick(10)
    assert env.statuses().count("queued") == 2
    env.db.x("UPDATE campaigns SET status='running' WHERE id=?", cid)
    env.tick(10)
    assert env.statuses().count("queued") == 1


def test_phone_offline_retries_without_losing_or_duplicating(env):
    env.campaign(["+48600100201"])
    env.up = False
    env.tick()
    assert env.statuses() == ["queued"] and env.worker.online is False
    env.up = True
    env.tick(1)    # jeszcze trwa przerwa przed ponowieniem
    assert env.statuses() == ["queued"]
    env.tick(10)
    assert env.statuses() == ["accepted"] and env.worker.online is True
    assert len(env.gateway().states(since=__import__("datetime").datetime.now().astimezone())) == 1


def test_restart_mid_send_does_not_send_twice(env):
    env.campaign(["+48600100201"])
    m = env.db.one("SELECT * FROM messages")
    env.gateway().send(m["gateway_id"], m["phone"], m["body"])       # telefon dostał wiadomość...
    env.db.x("UPDATE messages SET status='sending'")                  # ...a panel padł przed zapisem
    env.worker = Worker(env.db, env.gateway)                          # ponowne uruchomienie
    assert env.statuses() == ["queued"]
    env.tick()
    assert env.statuses() == ["accepted"]
    assert len(env.http.get("/messages", auth=("demo", "demo")).json()) == 1


def test_replies_arrive_once_and_stop_blocks_group_sending(env):
    env.db.set("inbox_since", "2000-01-01T00:00:00+00:00")
    env.campaign(["+48600100202", "+48600100209"])   # ...2 odpisuje, ...9 odpisuje STOP
    env.tick()
    env.tick(3)
    env.tick(10)
    env.tick(10)                                     # drugie odpytanie nie może zdublować odpowiedzi
    inbox = env.db.q("SELECT phone, body, read FROM messages WHERE direction='in' ORDER BY phone")
    assert [(r["phone"], r["body"], r["read"]) for r in inbox] == [
        ("+48600100202", "Dziękuję, będę!", 0), ("+48600100209", "STOP", 0)]
    assert [r["phone"] for r in env.db.q("SELECT phone FROM blocked")] == ["+48600100209"]
    # kolejna wysyłka grupowa pomija osobę, która zrezygnowała
    env.campaign(["+48600100209"])
    env.tick(10)
    last = env.db.one("SELECT status, error FROM messages WHERE direction='out' ORDER BY id DESC")
    assert last["status"] == "cancelled" and "STOP" in last["error"]


def test_store_incoming_parses_inbox_item():
    db = DB(":memory:")
    item = {"id": "abc", "type": "SMS", "sender": "600 100 200", "contentPreview": "Będę o 18",
            "createdAt": "2026-01-02T12:00:00.000+02:00"}
    assert store_incoming(db, item) is True
    assert store_incoming(db, item) is False       # ten sam SMS drugi raz
    m = db.one("SELECT * FROM messages")
    assert (m["phone"], m["body"], m["created_at"], m["read"]) == (
        "+48600100200", "Będę o 18", "2026-01-02T10:00:00+00:00", 0)
    # nadawca, który nie jest numerem (np. nazwa firmy), też trafia do skrzynki
    assert store_incoming(db, {"id": "x", "sender": "InPost", "contentPreview": "Paczka", "createdAt": "zła data"})
    assert db.one("SELECT phone FROM messages WHERE gateway_id='in:x'")["phone"] == "InPost"


def test_connection_check_messages(env):
    env.gateway().check()
    with pytest.raises(GatewayError) as e:
        env.gateway(password="zle").check()
    assert e.value.kind == "auth" and "hasło" in str(e.value)
    env.up = False
    with pytest.raises(GatewayError) as e:
        env.gateway().check()
    assert e.value.kind == "unreachable"
    with pytest.raises(GatewayError) as e:
        parse_address("to nie adres")
    assert e.value.kind == "address"
    assert parse_address(" http://192.168.1.50/ ") == "http://192.168.1.50:8080"
    assert parse_address("192.168.1.50:9090") == "http://192.168.1.50:9090"


def test_android_limit_is_respected_with_reserve_for_replies(env):
    from datetime import datetime, timedelta, timezone
    env.db.set("limit_count", 10)
    env.db.set("limit_window", 30)
    env.campaign([f"+4860010{i:04d}".replace("000", "123") for i in range(1, 13)])   # 12 osób
    for _ in range(20):
        env.tick(5)
    # wysyłka grupowa bierze najwyżej 80% limitu: 8 z 10
    assert env.statuses().count("accepted") + env.statuses().count("delivered") + env.statuses().count("sent") == 8
    assert env.worker.limited is True
    # odpowiedzi pisane ręcznie korzystają z zapasu: jeszcze 2, trzecia czeka
    for _ in range(3):
        env.queue("+48600100207")
    env.tick(5)
    assert env.statuses()[-3:].count("queued") == 1
    # długa wiadomość liczy się jak kilka SMS-ów; gdy okno się przesunie, kolejka rusza sama
    old = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat(timespec="seconds")
    env.db.x("UPDATE messages SET sent_at=? WHERE sent_at IS NOT NULL", old)
    env.db.x("UPDATE messages SET segments=3 WHERE status='queued' AND campaign_id IS NOT NULL")
    for _ in range(20):
        env.tick(5)
    left = env.db.one("SELECT COUNT(*) n FROM messages WHERE status='queued' AND campaign_id IS NOT NULL")["n"]
    assert left == 2          # 1 odpowiedź + 2 x 3 segmenty = 7 <= 8; trzecia (10) już nie


def test_limit_error_from_phone_pauses_campaign_with_polish_hint(env):
    cid = env.campaign(["+48600100111", "+48600100203"])    # atrapa: ...111 = RESULT_ERROR_LIMIT_EXCEEDED
    env.tick()
    env.tick(6)
    first = env.db.one("SELECT status, error FROM messages ORDER BY id")
    assert first["status"] == "failed" and "limit SMS-ów" in first["error"] and "RESULT" not in first["error"]
    assert env.db.one("SELECT status FROM campaigns WHERE id=?", cid)["status"] == "paused"
    env.tick(30)
    assert env.statuses()[1] == "queued"                    # nic więcej nie wychodzi, dopóki użytkownik nie wznowi


def test_explain_error_and_plain_text():
    from sms_panel.core import plain, sms_segments
    from sms_panel.gateway import explain_error
    assert "zasięg" in explain_error("RESULT_ERROR_GENERIC_FAILURE")
    assert "domyślnej aplikacji" in explain_error("RESULT_NO_DEFAULT_SMS_APP")
    assert "karty SIM" in explain_error("Can't send message: No SIMs found")
    assert explain_error("coś nowego") == "coś nowego. Sprawdź numer i kliknij „Wyślij ponownie”."
    assert "Wyślij ponownie" in explain_error(None)
    text = "Cześć Łukasz – „żółć” gęślą jaźń…"
    assert plain(text) == 'Czesc Lukasz - "zolc" gesla jazn...'
    assert sms_segments("ż" * 100)[0] == 2 and sms_segments(plain("ż" * 100))[0] == 1


def test_mms_is_stored_as_a_note_and_old_phone_without_mms_still_works():
    from datetime import datetime, timezone

    from sms_panel.worker import MMS_NOTE
    db = DB(":memory:")
    assert store_incoming(db, {"id": "m1", "type": "MMS", "sender": "600100200", "contentPreview": "", "createdAt": None})
    assert db.one("SELECT body FROM messages")["body"] == MMS_NOTE

    def handler(request):   # telefon ze starszym SMSGate: SMS-y oddaje, o MMS-y nie da się zapytać
        if request.url.params["type"] == "MMS":
            return httpx.Response(400, json={"message": "bad type"})
        return httpx.Response(200, json=[{"id": "s1", "type": "SMS", "sender": "600100200"}])
    gw = Gateway("http://t", "a", "b", httpx.Client(transport=httpx.MockTransport(handler)))
    assert [m["id"] for m in gw.inbox(datetime.now(timezone.utc))] == ["s1"]
