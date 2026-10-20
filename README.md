# SMS Panel

<p align="center">
  <a href="https://youtu.be/Ga1Mi0z-MFY">
    <img src="https://img.youtube.com/vi/Ga1Mi0z-MFY/maxresdefault.jpg" alt="Instrukcja wideo" width="900">
  </a>
</p>

[▶ Obejrzyj instrukcję wideo](https://youtu.be/Ga1Mi0z-MFY)

[![Pobierz Windows EXE](https://img.shields.io/badge/Windows-EXE-0078D6?logo=windows&logoColor=white)](https://github.com/goliat931/smsgate-panel/releases/latest/download/SmsPanel.exe)

[![Pobierz macOS](https://img.shields.io/badge/macOS-App-000000?logo=apple&logoColor=white)](https://github.com/goliat931/smsgate-panel/releases/latest/download/SmsPanel)

Lokalny panel WWW do SMS-ów przez telefon z Androidem i [SMSGate](https://sms-gate.app) w trybie lokalnym:
kontakty i grupy (import CSV, eksport wizytówek .vcf), wysyłka grupowa z podglądem i bezpiecznym tempem, skrzynka z wątkami, historia z eksportem CSV.

- Instrukcja dla użytkownika: [INSTRUKCJA.md](INSTRUKCJA.md)
- Dlaczego tak, a nie inaczej: [DECISIONS.md](DECISIONS.md)

## Uruchomienie ze źródeł

Wymaga [uv](https://docs.astral.sh/uv/) (sam pobierze Pythona 3.12).

```sh
uv sync
uv run python -m sms_panel --demo     # atrapa telefonu, nic nie wysyła (login/hasło: demo/demo)
uv run python -m sms_panel            # prawdziwy telefon
uv run pytest
```

Opcje: `--demo`, `--port N`, `--no-browser`. Zmienna `SMSPANEL_DATA` zmienia katalog danych
(domyślnie `%APPDATA%\SmsPanel`, na macOS `~/Library/Application Support/SmsPanel`; demo ma osobny `SmsPanel-demo`).

## Budowanie pliku wykonywalnego

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1    # Windows -> dist\SmsPanel.exe
```
```sh
sh build.sh                                           # macOS / Linux -> dist/SmsPanel
```

Skrypt uruchamia testy i PyInstallera, a do `dist/` dokłada `INSTRUKCJA.md` (i `Tryb-demo.bat` na Windows).
Użytkownikowi przekazujesz cały folder `dist`. CI: `.github/workflows/build.yml` buduje artefakty dla Windows
i macOS po wypchnięciu taga `v*`.

## Struktura

```
sms_panel/
  __main__.py   start: port, jedna kopia naraz, przeglądarka, uvicorn
  web.py        wszystkie ekrany (FastAPI + Jinja2)
  worker.py     wątek w tle: kolejka wysyłki, statusy, odbiór odpowiedzi
  gateway.py    klient HTTP SMSGate + komunikaty błędów po polsku
  demo.py       atrapa bramki (to samo API) dla --demo i testów + dane przykładowe
  core.py       numery, segmenty SMS, zmienne {imie}, STOP, import CSV, wizytówki vCard
  db.py         schemat SQLite, katalog danych
  templates/, static/
tests/          pytest: logika, kolejka na atrapie, pełny scenariusz przez HTTP
```

## Stan weryfikacji

Sprawdzone: testy, ręczny scenariusz w trybie demo, zbudowany `SmsPanel.exe` na Windows 11.
**Niesprawdzone: prawdziwy telefon z SMSGate**, build na macOS, workflow CI.
