import pytest

from sms_panel.core import is_optout, normalize_phone, parse_csv, render, sms_segments, vcard


@pytest.mark.parametrize("raw,expected", [
    ("600100200", "+48600100200"),
    ("600 100 200", "+48600100200"),
    ("600-100-200", "+48600100200"),
    ("(48) 600 100 200", "+48600100200"),
    ("+48 600 100 200", "+48600100200"),
    ("0048600100200", "+48600100200"),
    ("+49 151 2345678", "+491512345678"),
    ("12345", None),            # za krótki
    ("+48 600 100 20", None),   # polski numer musi mieć 9 cyfr
    ("6001002001", None),       # 10 cyfr bez plusa
    ("abc", None),
    ("", None),
    (None, None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_render_variables():
    assert render("Cześć {imie}!", name="Ania") == "Cześć Ania!"
    assert render("{Imię}, tel. {telefon} ({notatka})", "Jan", "+48600100200", "VIP") == "Jan, tel. +48600100200 (VIP)"
    # nieznane klamry i samotne nawiasy nie psują treści
    assert render("Kod {rabat} {imie} {", name="Ola") == "Kod {rabat} Ola {"
    assert render("Szanowny Panie {nazwisko}", "Jan", surname="Kowalski") == "Szanowny Panie Kowalski"


def test_sms_segments():
    assert sms_segments("a" * 160)[0] == 1
    assert sms_segments("a" * 161)[0] == 2
    assert sms_segments("a" * 306)[0] == 2
    assert sms_segments("a" * 307)[0] == 3
    # polskie znaki => unicode: 70 znaków w jednym, 67 w wieloczęściowym
    assert sms_segments("ż" * 70) == (1, 70, True)
    assert sms_segments("ż" * 71)[0] == 2
    assert sms_segments("ż" * 135)[0] == 3
    # znaki rozszerzone GSM liczą się podwójnie
    assert sms_segments("€" * 80)[1] == 160


@pytest.mark.parametrize("text,expected", [
    ("STOP", True), ("stop", True), ("Stop!", True), ("  stop.  ", True),
    ("NIE PISZ", True), ("nie pisz do mnie więcej", True), ("Wypisz mnie", True),
    ("Rezygnuję", True), ("rezygnuje", True),
    ("Dziękuję, będę!", False), ("Przystopuj trochę", False), ("Nie piszę się na to", False), ("", False),
])
def test_optout(text, expected):
    assert is_optout(text) is expected


def row(name, surname, phone, email="", note="", groups=()):
    return {"name": name, "surname": surname, "phone": phone, "email": email, "note": note, "groups": list(groups)}


def test_parse_csv_with_header_and_errors():
    data = ("Imię;Nazwisko;Telefon;E-mail;Notatka;Grupa\n"
            "Ania;Nowak;600 100 200;ania@example.com;VIP;Impreza X\n"
            "Jan;Kowalski;123;;;\n"
            "Ola;Lis;600100200;;;\n"
            "Ewa;Kot;+48 601 000 111;to nie mail;;A|B\n"
            "Bez;Numeru;;;;\n")
    rows, errors, columns = parse_csv(data.encode("utf-8-sig"))
    assert rows == [row("Ania", "Nowak", "+48600100200", "ania@example.com", "VIP", ["Impreza X"]),
                    row("Ewa", "Kot", "+48601000111", groups=["A", "B"])]
    assert [(no, why) for no, _, why in errors] == [
        (3, "błędny numer telefonu"),
        (4, "ten sam numer jest już wyżej w tym pliku, w wierszu 2 (Ania Nowak). Chodzi o plik, nie o kontakty w panelu"),
        (6, "brak numeru telefonu")]
    assert columns == ["imię", "nazwisko", "telefon", "e-mail", "notatka", "grupa"]


def test_parse_csv_columns_in_any_order_with_other_names_and_extras():
    data = "Lp.,Adres e-mail,Nazwisko,Miasto,Komórka,Imię\n1,ewa@example.com,Lis,Kraków,600100202,Ewa\n"
    rows, errors, _ = parse_csv(data.encode())
    assert rows == [row("Ewa", "Lis", "+48600100202", "ewa@example.com")] and not errors


def test_parse_csv_full_name_in_one_column():
    rows, _, columns = parse_csv("Imię i nazwisko;Telefon\nJan Maria Kowalski;600100201\nMadonna;600100202\n".encode())
    assert rows == [row("Jan", "Maria Kowalski", "+48600100201"), row("Madonna", "", "+48600100202")]
    assert columns == ["imię i nazwisko", "telefon"]


def test_parse_csv_without_header_finds_phone_and_email_by_content():
    # stary prosty układ: imię, telefon, notatka, grupa
    rows, errors, _ = parse_csv("Żaneta,600100200\nJan Kowalski,601100200,notatka,Grupa A\n".encode("cp1250"))
    assert not errors
    assert rows == [row("Żaneta", "", "+48600100200"),
                    row("Jan", "Kowalski", "+48601100200", note="notatka", groups=["Grupa A"])]
    # imię i nazwisko osobno, e-mail gdziekolwiek
    rows, _, columns = parse_csv(b"ola@example.com;Ola;Lis;600100205;uwaga\n")
    assert rows == [row("Ola", "Lis", "+48600100205", "ola@example.com", "uwaga")]
    assert columns == ["imię", "nazwisko", "telefon", "e-mail", "notatka"]


def test_parse_csv_google_contacts_export():
    data = ("First Name,Middle Name,Last Name,Labels,E-mail 1 - Label,E-mail 1 - Value,Phone 1 - Label,Phone 1 - Value\n"
            "Anna,,Nowak,* myContacts ::: Impreza,* Home,anna@example.com,Mobile,+48 600 100 200 ::: 601100200\n")
    rows, errors, _ = parse_csv(data.encode())
    assert rows == [row("Anna", "Nowak", "+48600100200", "anna@example.com", groups=["Impreza"])] and not errors


def test_bundled_example_file_imports_cleanly():
    from pathlib import Path
    rows, errors, columns = parse_csv(Path("sms_panel/static/przyklad.csv").read_bytes())
    assert len(rows) == 3 and not errors and len(columns) == 6
    assert rows[2]["groups"] == ["Impreza X", "Wolontariusze"]


def test_vcard():
    out = vcard([{"name": "Jan", "surname": "Kowalski; jr", "phone": "+48600100200", "email": "j@example.com", "note": "a,b"},
                 {"name": "Ola", "surname": "", "phone": "+48600100205", "email": "", "note": ""}], "Impreza X")
    assert out == ("BEGIN:VCARD\r\nVERSION:3.0\r\nN:Kowalski\\; jr;Jan;;;\r\nFN:Jan Kowalski\\; jr\r\n"
                   "TEL;TYPE=CELL:+48600100200\r\nEMAIL;TYPE=INTERNET:j@example.com\r\nNOTE:a\\,b\r\n"
                   "CATEGORIES:Impreza X\r\nEND:VCARD\r\n"
                   "BEGIN:VCARD\r\nVERSION:3.0\r\nN:;Ola;;;\r\nFN:Ola\r\nTEL;TYPE=CELL:+48600100205\r\n"
                   "CATEGORIES:Impreza X\r\nEND:VCARD\r\n")


def test_repeated_number_in_file_points_to_first_row_and_keeps_its_groups():
    data = "imię;nazwisko;telefon;grupa\nAdam;Testowy;600100200;A\nAnna;Testowa;600 100 200;B\n"
    rows, errors, _ = parse_csv(data.encode())
    assert rows == [row("Adam", "Testowy", "+48600100200", groups=["A", "B"])]
    assert errors[0][0] == 3 and "w wierszu 2 (Adam Testowy)" in errors[0][2]
