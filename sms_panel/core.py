"""Czysta logika: numery, segmenty SMS, zmienne w treści, rezygnacje, CSV."""
import csv
import io
import re
import unicodedata

GSM7 = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
           "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
GSM7_EXT = set("^{}\\[~]|€")  # liczą się podwójnie


def normalize_phone(raw, default_cc="48"):
    """Zwraca numer w formacie +48123456789 albo None, gdy numer jest błędny."""
    # ponytail: prosta walidacja (długość, polskie 9 cyfr); pełne reguły krajów -> biblioteka phonenumbers
    s = re.sub(r"[\s\-().]", "", raw or "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if not s.startswith("+"):
        if len(s) == 9:
            s = f"+{default_cc}{s}"
        elif len(s) == 11 and s.startswith(default_cc):
            s = "+" + s
        else:
            return None
    if not re.fullmatch(r"\+\d{8,15}", s):
        return None
    if s.startswith("+48") and len(s) != 12:
        return None
    return s


def sms_segments(text):
    """(liczba segmentów, liczba znaków, czy unicode). Polskie litery wymuszają unicode (70 zn./SMS)."""
    if all(ch in GSM7 or ch in GSM7_EXT for ch in text):
        n, single, multi, uni = sum(2 if ch in GSM7_EXT else 1 for ch in text), 160, 153, False
    else:
        n, single, multi, uni = len(text.encode("utf-16-le")) // 2, 70, 67, True
    return (1 if n <= single else -(-n // multi)), n, uni


_PLAIN = str.maketrans({**dict(zip("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")),
                         "„": '"', "”": '"', "–": "-", "—": "-", "…": "..."})


def plain(text):
    """Bez polskich liter i ozdobnych znaków: SMS mieści wtedy 160 znaków zamiast 70."""
    return text.translate(_PLAIN)


def render(body, name="", phone="", note="", surname=""):
    """Podstawia {imie}, {nazwisko}, {telefon}, {notatka}. Nieznane klamry zostawia bez zmian."""
    vals = {"imie": name, "imię": name, "nazwisko": surname, "telefon": phone, "notatka": note}
    return re.sub(r"\{(\w+)\}", lambda m: vals.get(m[1].lower(), m[0]), body)


OPTOUT = ("STOP", "NIE PISZ", "WYPISZ", "REZYGNUJE", "REZYGNACJA")


def is_optout(text):
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).upper()
    t = " ".join(re.findall(r"\w+", t))
    return any(re.search(rf"\b{k}\b", t) for k in OPTOUT)


# Rozpoznawanie kolumn po nagłówku: fragment tekstu -> rodzaj. Kolejność ma znaczenie.
ALIASES = [
    ("full", ("imię i nazwisko", "imie i nazwisko", "nazwisko i imi", "full name", "display name")),
    ("surname", ("nazwisk", "last name", "family name", "surname")),
    ("name", ("imi", "first name", "given name")),
    ("phone", ("telefon", "phone", "mobile", "komórk", "komork", "numer", "tel", "nr")),
    ("email", ("mail",)),
    ("note", ("notat", "uwag", "note", "opis", "komentarz")),
    ("group", ("grup", "group", "tag", "label", "kategori")),
    ("full", ("nazwa", "name", "osoba", "kontakt")),
]
COLUMN_PL = {"name": "imię", "surname": "nazwisko", "full": "imię i nazwisko", "phone": "telefon",
             "email": "e-mail", "note": "notatka", "group": "grupa"}


def _kind(header):
    h = header.lower()
    return next((kind for kind, keys in ALIASES if any(k in h for k in keys)), None)


def _first_phone(cell):
    """Komórka może mieć kilka numerów (eksport z Google: „a ::: b”) - bierzemy pierwszy poprawny."""
    return next((p for p in map(normalize_phone, re.split(r":::|[,/]", cell)) if p), None)


def _email(cell):
    m = re.search(r"[^@\s,;:]+@[^@\s,;:]+\.[^@\s,;:]+", cell)
    return m[0] if m else ""


def parse_csv(data: bytes):
    """Zwraca (wiersze, błędy, rozpoznane kolumny).

    Wiersz: dict(name, surname, phone, email, note, groups). Błąd: (nr wiersza, treść, powód).
    Kolumny mogą być w dowolnej kolejności. Z nagłówkiem rozpoznajemy je po nazwach, a telefon
    i e-mail dodatkowo po zawartości. Bez nagłówka: telefon i e-mail po zawartości, kolumny przed
    telefonem to imię (i nazwisko), kolumny po telefonie to notatka i grupa.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1250", errors="replace")  # Excel w polskim Windows
    lines = text.splitlines()
    delim = max(";,\t", key=lines[0].count) if lines else ";"
    numbered = [(no, [c.strip() for c in r]) for no, r in enumerate(csv.reader(io.StringIO(text), delimiter=delim), 1)]
    numbered = [(no, r) for no, r in numbered if any(r)]
    if not numbered:
        return [], [], []
    cell = lambda r, i: r[i] if i is not None and i < len(r) else ""
    first = numbered[0][1]
    kinds = [_kind(c) for c in first]
    has_header = any(kinds) and not any(_first_phone(c) or _email(c) for c in first)
    if has_header:
        numbered = numbered[1:]
    else:
        kinds = []
    width = max([len(first)] + [len(r) for _, r in numbered])

    def pick(kind, test):
        """Kolumna danego rodzaju: najpierw wśród nazwanych w nagłówku, potem dowolna - ta z największą liczbą trafień."""
        named = [i for i, k in enumerate(kinds) if k == kind]
        for pool in (named, range(width)):
            scored = [(sum(1 for _, r in numbered if test(cell(r, i))), -i) for i in pool]
            if scored and max(scored)[0] > 0:
                return -max(scored)[1]
        return named[0] if named else None

    cols = {"phone": pick("phone", _first_phone)}
    cols["email"] = pick("email", _email)
    if has_header:
        for kind in ("name", "surname", "full", "note", "group"):
            cols[kind] = next((i for i, k in enumerate(kinds) if k == kind and i not in (cols["phone"], cols["email"])), None)
    else:
        if cols["phone"] is None:
            cols["phone"] = min(1, width - 1)
        rest = [i for i in range(width) if i not in (cols["phone"], cols["email"])]
        before = [i for i in rest if i < cols["phone"]]
        after = [i for i in rest if i > cols["phone"]]
        if len(before) == 1:
            cols["full"] = before[0]
        elif before:
            cols["name"], cols["surname"] = before[0], before[1]
        cols.update(zip(("note", "group"), after))
    cols = {k: i for k, i in cols.items() if i is not None}

    out, errors, seen = [], [], {}   # seen: numer -> (nr wiersza, odczytana osoba)
    for no, r in numbered:
        get = lambda k: cell(r, cols.get(k))
        phone = _first_phone(get("phone"))
        if not phone:
            errors.append((no, delim.join(r), "błędny numer telefonu" if get("phone") else "brak numeru telefonu"))
            continue
        groups = [g.strip() for g in re.split(r":::|[|,]", get("group"))]
        groups = [g for g in groups if g and not g.startswith("*")]
        if phone in seen:   # ten sam numer drugi raz: osoba już jest, dopisujemy jej tylko grupy z tego wiersza
            first_no, first = seen[phone]
            first["groups"] += [g for g in groups if g not in first["groups"]]
            who = f"{first['name']} {first['surname']}".strip()
            errors.append((no, delim.join(r), f"ten sam numer jest już wyżej w tym pliku, w wierszu {first_no} ({who}). "
                                              "Chodzi o plik, nie o kontakty w panelu"))
            continue
        name, surname = get("name"), get("surname")
        if not (name or surname):
            name = get("full")
        if not surname:  # „Jan Kowalski” w jednej kolumnie
            name, _, surname = name.partition(" ")
        out.append({"name": name.strip() or surname.strip() or phone, "surname": surname.strip() if name.strip() else "",
                    "phone": phone, "email": _email(get("email")), "note": get("note"), "groups": groups})
        seen[phone] = (no, out[-1])
    if "name" in cols or "surname" in cols:
        cols.pop("full", None)  # była tylko zapasem
    return out, errors, [COLUMN_PL[k] for k in COLUMN_PL if k in cols]


def vcard(contacts, group=""):
    """Plik wizytówek (.vcf, vCard 3.0) do zaimportowania w telefonie."""
    def esc(s):
        for ch, to in (("\\", "\\\\"), (";", "\\;"), (",", "\\,"), ("\n", "\\n")):
            s = (s or "").replace(ch, to)
        return s.replace("\r", "")   # samotny znak powrotu karetki mógłby dopisać obce pole do wizytówki
    lines = []
    for c in contacts:
        full = f"{c['name']} {c['surname']}".strip()
        lines += ["BEGIN:VCARD", "VERSION:3.0", f"N:{esc(c['surname'])};{esc(c['name'])};;;", f"FN:{esc(full)}",
                  f"TEL;TYPE=CELL:{c['phone']}"]
        if c["email"]:
            lines.append(f"EMAIL;TYPE=INTERNET:{esc(c['email'])}")
        if c["note"]:
            lines.append(f"NOTE:{esc(c['note'])}")
        if group:
            lines.append(f"CATEGORIES:{esc(group)}")
        lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"
