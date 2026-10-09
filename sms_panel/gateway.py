"""Klient SMSGate w trybie lokalnym (Basic Auth, http://<ip>:8080).

Endpointy sprawdzone w dokumentacji i źródłach aplikacji:
POST /messages, GET /messages, GET /inbox. Szczegóły w DECISIONS.md.
"""
import re
from datetime import datetime, timezone

import httpx

MSG = {
    "address": "Ten adres nie wygląda poprawnie. Wpisz go dokładnie tak, jak pokazuje aplikacja SMSGate, "
               "na przykład 192.168.1.50:8080.",
    "wrong": "Pod tym adresem odpowiada inne urządzenie, nie SMSGate. Sprawdź adres w aplikacji na telefonie.",
    "auth": "Telefon odpowiada, ale login lub hasło są błędne. Przepisz je jeszcze raz z aplikacji SMSGate "
            "(wielkość liter ma znaczenie).",
    "unreachable": "Nie mogę połączyć się z telefonem. Sprawdź, czy telefon jest w tej samej sieci Wi-Fi co "
                   "komputer, czy w aplikacji SMSGate serwer lokalny jest włączony (napis „Online”) i czy adres "
                   "jest przepisany bez pomyłek.",
}


AGAIN = "kliknij „Wyślij ponownie”."
ERRORS = [  # (fragment tekstu błędu z SMSGate, co się stało i co zrobić) - nazwy z docs.sms-gate.app/faq/errors
    ("LIMIT_EXCEEDED", "Telefon albo operator odmówił: przekroczony limit SMS-ów (albo wiadomość jest za długa). "
                       "Odczekaj pół godziny, sprawdź, czy telefon nie pyta o zgodę, i " + AGAIN),
    ("GENERIC_FAILURE", "Telefon nie mógł wysłać SMS-a. Sprawdź zasięg i środki na karcie, włącz i wyłącz tryb "
                        "samolotowy, a potem " + AGAIN),
    ("NO_DEFAULT_SMS_APP", "W telefonie nie ma domyślnej aplikacji do SMS-ów albo domyślnej karty SIM. Ustaw je "
                           "w ustawieniach telefonu (Aplikacje → Aplikacje domyślne) i " + AGAIN),
    ("No SIMs found", "Telefon nie widzi karty SIM. Wyjmij ją i włóż ponownie, uruchom telefon jeszcze raz i " + AGAIN),
    ("RIL_MODEM_ERR", "Telefon ma kłopot z siecią komórkową. Uruchom go ponownie i " + AGAIN),
    ("RADIO_OFF", "Telefon ma wyłączoną sieć komórkową (tryb samolotowy?). Włącz ją i " + AGAIN),
    ("NO_SERVICE", "Telefon nie ma zasięgu. Przenieś go w miejsce z zasięgiem i " + AGAIN),
    ("SEND_SMS", "Aplikacja SMSGate nie ma zgody na wysyłanie SMS-ów. W telefonie: Ustawienia → Aplikacje → "
                 "SMSGate → Uprawnienia → SMS → Zezwól. Potem " + AGAIN),
]


def explain_error(err):
    """Błąd z telefonu -> zdanie po polsku z podpowiedzią. Nieznany błąd zostaje, z ogólną radą."""
    err = (err or "").strip()
    for key, text in ERRORS:
        if key.lower() in err.lower():
            return text
    return (err.rstrip(".") + ". " if err else "Telefon nie podał powodu. ") + "Sprawdź numer i " + AGAIN


class GatewayError(Exception):
    def __init__(self, kind, message=None):
        super().__init__(message or MSG[kind])
        self.kind = kind  # address | wrong | auth | unreachable | rejected


def parse_address(raw):
    s = re.sub(r"^https?://", "", (raw or "").strip()).rstrip("/")
    m = re.fullmatch(r"([A-Za-z0-9.\-]+)(?::(\d{1,5}))?", s)
    if not m:
        raise GatewayError("address")
    return f"http://{m[1]}:{m[2] or 8080}"


def to_utc_iso(value):
    """Data z telefonu -> nasz format UTC. Gdy nie da się odczytać: teraz."""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        dt = datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class Gateway:
    def __init__(self, base_url, login, password, client):
        self.base, self.auth, self.http = base_url, (login, password), client

    def _req(self, method, path, **kw):
        try:
            r = self.http.request(method, self.base + path, auth=self.auth, **kw)
        except httpx.HTTPError as e:
            raise GatewayError("unreachable") from e
        if r.status_code == 401:
            raise GatewayError("auth")
        return r

    def _list(self, path, **params):
        out, offset = [], 0
        while True:
            r = self._req("GET", path, params={**params, "limit": 500, "offset": offset})
            try:
                page = r.json() if r.status_code == 200 else None
            except ValueError:
                page = None
            if not isinstance(page, list):
                raise GatewayError("wrong")
            out += page
            if len(page) < 500:
                return out
            offset += 500

    def check(self):
        """Rzuca GatewayError z komunikatem dla człowieka, gdy coś jest nie tak."""
        self._list("/messages", **{"from": _z(datetime.now(timezone.utc))})

    def send(self, msg_id, phone, text):
        r = self._req("POST", "/messages", json={
            "id": msg_id, "textMessage": {"text": text}, "phoneNumbers": [phone], "withDeliveryReport": True})
        if r.status_code in (200, 201, 202, 409):  # 409 = telefon już ma wiadomość o tym id (ponowienie)
            return
        if r.status_code == 400:
            try:
                reason = r.json().get("message", "")
            except ValueError:
                reason = ""
            raise GatewayError("rejected", reason or "Telefon odrzucił wiadomość.")
        raise GatewayError("wrong")

    def states(self, since: datetime):
        """{id: (stan, błąd)} dla wiadomości wychodzących od podanej chwili."""
        out = {}
        for m in self._list("/messages", **{"from": _z(since)}):
            rec = (m.get("recipients") or [{}])[0]
            out[m.get("id")] = (m.get("state"), rec.get("error"))
        return out

    def inbox(self, since: datetime):
        out = self._list("/inbox", type="SMS", **{"from": _z(since)})
        try:
            # ponytail: tylko informacja „przyszedł MMS”; zdjęcia telefon oddaje wyłącznie przez webhook z HTTPS
            out += self._list("/inbox", type="MMS", **{"from": _z(since)})
        except GatewayError as e:
            if e.kind != "wrong":   # starsza wersja SMSGate nie zna MMS-ów - SMS-y mają działać dalej
                raise
        return out


def _z(dt: datetime):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
