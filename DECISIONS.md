# Decyzje projektowe

Zapis rzeczy, które trzeba było rozstrzygnąć. Zasada: gdy jest wybór, wygrywa to, co prostsze dla laika.

## Co sprawdziłem w dokumentacji i źródłach SMSGate (2026-10-07, aplikacja v1.77.1)

Źródła: docs.sms-gate.app, specyfikacja OpenAPI (capcom6.github.io/android-sms-gateway/swagger.json),
kod aplikacji (`modules/localserver/`, `modules/webhooks/`, `modules/incoming/`), klient `client-py`.

| Fakt | Skąd |
|---|---|
| Tryb lokalny: `http://<ip>:8080`, tylko Basic Auth, login i hasło generuje aplikacja | docs: Local Server |
| Wysyłka: `POST /messages` (alias `/message`), ciało `{id, textMessage:{text}, phoneNumbers, withDeliveryReport}`, odpowiedź 202 | OpenAPI, `MessagesRoutes.kt` |
| Powtórzone `id` → **409 Conflict** | `MessagesRoutes.kt` |
| Statusy: `GET /messages?from=&limit=&offset=`; stany `Pending, Processed, Sent, Delivered, Failed, Cancelling, Cancelled` | OpenAPI |
| Odbiór: `GET /inbox?type=SMS&from=&limit=&offset=` – **tylko w trybie lokalnym**; pole `contentPreview` dla SMS-a tekstowego zawiera **pełną treść** | docs: Reading Messages, `IncomingMessagesService.toPreview()` |
| Webhook musi mieć adres `https://…` albo `http://127.0.0.1` (pętla zwrotna **telefonu**) | `WebHooksService.kt`, docs: FAQ Webhooks |

## 1. Odpytywanie zamiast webhooków

Prompt pytał, czy w trybie lokalnym telefon musi „widzieć” komputer. Odpowiedź: tak, i to **po HTTPS z zaufanym
certyfikatem** – aplikacja odrzuca `http://192.168.x.x`. Obejścia (certyfikat z CA projektu, tunel, wersja
`app-insecure.apk`, `adb reverse`) nie nadają się dla laika.

Dlatego panel **co 5 s odpytuje** `GET /inbox` i `GET /messages`. Skutki:

- Odpowiedzi pojawiają się z opóźnieniem do ok. 5–10 s. Dla tego zastosowania bez znaczenia.
- Panel nie musi być widoczny w sieci → **słucha tylko na `127.0.0.1`**, przełącznik „udostępnij w sieci lokalnej”
  i hasło do panelu nie są potrzebne i **nie zostały zrobione**.
- Nie ma parsera webhooków. „Parsowanie odpowiedzi” to `worker.store_incoming()` (element z `GET /inbox`) i jest przetestowane.
  Gdyby kiedyś dodać webhooki: nowy endpoint woła tę samą funkcję (pola `sender`, `message`, `receivedAt`, `messageId`).

## 2. `httpx` zamiast biblioteki `android-sms-gateway`

Biblioteka pokrywa potrzebne funkcje, ale używamy 3 endpointów. Własny klient (`gateway.py`, ~90 linii) daje:
komunikaty błędów po polsku rozróżniające „zły adres / złe hasło / telefon nieosiągalny”, mniej zależności w `.exe`
oraz możliwość podstawienia atrapy po HTTP – tryb demo i testy przechodzą przez **ten sam kod klienta** co prawdziwy telefon.

## 3. Brak duplikatów i odporność na restart

- Każda wiadomość dostaje własne `id` (UUID) **w chwili dodania do kolejki** i z tym `id` idzie do telefonu.
  Po awarii w trakcie wysyłki panel wysyła ponownie; telefon odpowiada 409 i nic nie wychodzi dwa razy.
- Kolejka to tabela `messages` w SQLite (status `queued`), więc przeżywa zamknięcie okna.
- Odpowiedzi: `gateway_id` jest unikalne, `INSERT OR IGNORE` – ponowne odpytanie nie dubluje.
- Podwójne kliknięcie „Wyślij”: jednorazowy `nonce` z podglądu, unikalny w tabeli `campaigns`.
- Drugie uruchomienie `SmsPanel.exe`: wykrywa działający panel (plik `port` + `/_ping`) i tylko otwiera przeglądarkę.
  Dwie kopie na jednej bazie mogłyby wysłać podwójnie.
- Telefon nieosiągalny: wiadomość wraca do kolejki, ponowienia po 5, 10, 20, 40, 60 s.

## 4. Tempo wysyłki

Domyślnie losowo 8–20 s (pierwotnie 3–5 s) między SMS-ami wysyłki grupowej (ustawienia → „Bezpieczna wysyłka”).
Pojedyncze odpowiedzi w rozmowie idą od razu, poza kolejnością. Panel wysyła po jednej wiadomości na żądanie
(nie jedno żądanie na 100 numerów), żeby mieć status i wstrzymanie per osoba.

## 5. Stare SMS-y nie są wczytywane

Panel pobiera odpowiedzi dopiero od chwili pierwszego zapisania ustawień. Powód: prywatność (telefon to zwykle
prywatny numer) i mniej zamieszania w skrzynce.

## 6. Rezygnacje (STOP)

Słowa: `STOP`, `NIE PISZ`, `WYPISZ`, `REZYGNUJE`, `REZYGNACJA` – jako całe słowa, bez względu na wielkość liter i ogonki.
Możliwe fałszywe trafienia („non stop”). Wybrałem ostrożność: lepiej kogoś niepotrzebnie pominąć niż wysłać
wbrew woli; blokadę zdejmuje się jednym kliknięciem. Blokada dotyczy tylko wysyłek grupowych – ręcznie odpisać można.
Jest przypisana do numeru (tabela `blocked`), więc działa też dla nieznanych numerów.

## 7. Numery telefonów

Bez zewnętrznej biblioteki: 9 cyfr → `+48…`, `0048…`/`48…` → `+48…`, numer z plusem musi mieć 8–15 cyfr,
polski dokładnie 9. Numer zagraniczny trzeba wpisać z plusem. Gdyby to nie wystarczało → biblioteka `phonenumbers`.

## 8. Hasło do bramki

Zapisane jawnie w `panel.db` w katalogu użytkownika (`%APPDATA%\SmsPanel`). Hasło chroni tylko dostęp do telefonu
w sieci lokalnej, a kto czyta pliki użytkownika, ten i tak ma jego sesję. Systemowy magazyn haseł (`keyring`) to
dodatkowa zależność i źródło problemów w `.exe` – do dodania, jeśli będzie potrzeba.
Logi: tylko poziom WARNING, bez treści wiadomości i danych logowania; log dostępu HTTP wyłączony (adresy zawierają numery).

## 9. Ochrona przed obcymi stronami WWW

Panel potrafi wysyłać SMS-y, więc strona otwarta w tej samej przeglądarce nie może go wywołać w tle.
Middleware odrzuca żądania z obcym nagłówkiem `Host` (DNS rebinding) i żądania zmieniające z obcym `Origin` (CSRF).

## 10. Pakowanie

PyInstaller `--onefile --console`. Okno konsoli zostaje celowo: to jest „małe okno z komunikatem”, a jego zamknięcie
to zrozumiały sposób wyłączenia panelu. Stały port 8765 (demo: 8766), a gdy zajęty – dowolny wolny; dzięki temu
zakładka w przeglądarce zwykle działa. Plik nie jest podpisany cyfrowo → SmartScreen pokaże ostrzeżenie (opisane w instrukcji).

## 11. Stos

Python 3.12, FastAPI + Uvicorn, SQLite z biblioteki standardowej (bez ORM), Jinja2, ~50 linii czystego JS
(bez HTMX – odświeżanie na żywo to jedna pętla `fetch`). Bez Node.js, bez budowania frontendu.
Dostęp do SQLite: jedno połączenie i globalna blokada – wystarcza dla jednego użytkownika.

## Miejsce na funkcje spoza pierwszej wersji (niezaimplementowane)

- **Szkice odpowiedzi AI:** ustawienia to tabela klucz–wartość (`settings`), klucz API to kolejny wpis; przycisk
  w `inbox.html` obok pola odpowiedzi wstawiałby szkic do `<textarea>` – zatwierdzenie to istniejące „Wyślij”.
- **Wysyłka o zadanej godzinie:** kolumna `send_after` w `messages` i warunek w `Worker._send_due`
  (albo pole `scheduleAt` z API SMSGate).
- **Wiele telefonów / kart SIM:** dziś jeden zestaw ustawień; trzeba tabeli `phones` i kolumny w `messages`;
  API ma pole `simNumber`.
- **MMS:** API ma `mmsMessage` i typy `MMS` w `/inbox`; panel pobiera tylko `type=SMS`.

## Zmiany po pierwszych uwagach (2026-10-07)

- **Nazwisko i e-mail** to osobne pola kontaktu (`surname`, `email`); stare bazy dostają kolumny przy starcie.
  `{imie}` wstawia samo imię, doszło `{nazwisko}`. E-mail jest tylko przechowywany i eksportowany – panel nie wysyła poczty.
- **Import CSV bez ekranu mapowania kolumn.** Panel sam rozpoznaje kolumny: po nazwach w nagłówku (dopasowanie po
  fragmencie, np. „Komórka”, „Adres e-mail”, „Last Name”), a telefon i e-mail dodatkowo po zawartości. Po imporcie
  pokazuje, co rozpoznał. Ręczne przypisywanie kolumn (lista rozwijana nad każdą kolumną) byłoby pewniejsze dla
  nietypowych plików, ale to dodatkowy krok dla każdego importu – do dodania, jeśli rozpoznawanie będzie zawodzić.
- **Znany numer przy imporcie:** nic nie jest nadpisywane, uzupełniane są tylko puste pola i dopisywane grupy.
- **Grupy mają własną zakładkę.** Tworzenie, zmiana nazwy, usuwanie, dodawanie/usuwanie/przenoszenie/kopiowanie
  osób – wszystko w `/grupy`. W „Kontaktach” zostało tylko filtrowanie listy i przypisanie grup jednej osobie.
  Zmiana nazwy na już istniejącą jest odrzucana (łączenie grup = „zaznacz wszystkich → przenieś”).
- **Wizytówki:** vCard 3.0, UTF-8, jeden plik `.vcf` na grupę (lub wszystkie kontakty). Nazwa grupy idzie w polu
  `CATEGORIES`; z tego, co wiem, Kontakty Google na Androidzie tego pola nie zamieniają na etykietę – **niesprawdzone
  na telefonie**, instrukcja mówi o tym wprost.
- **Dane przykładowe w demo** wczytują się przy starcie do pustej bazy demo; przycisk w Ustawieniach (tylko w demo)
  kasuje dane demo i wczytuje je od nowa. Kreator ustawień w demo został, bo jest częścią ćwiczenia.

## Zmiany po przeglądzie czytelności (2026-10-07)

Przegląd według zasad `sms-gateway-ux`, na zrzutach ekranu w trybie demo. Dwie decyzje właściciela:
panel jest **tylko na komputer** (wąskich ekranów nie dopracowujemy) i ekrany mają **prowadzić krok po kroku**.

- **Kroki.** Wysyłka: 1 Odbiorcy → 2 Treść → 3 Podgląd → 4 Wysyłka. Kroki 1 i 2 to jeden formularz przełączany
  w przeglądarce (bez JS widać oba naraz), więc serwer nie trzyma stanu kreatora. „Wróć i popraw” odsyła dane
  z podglądu z powrotem do formularza.
- **Import w trzech krokach** z podglądem przed zapisem. Odczytane wiersze czekają w pamięci procesu
  (`app.state.pending_import`), jeden import naraz – panel ma jednego użytkownika.
- **Licznik SMS-ów liczy serwer** (`POST /wysylka/licz`), a nie JavaScript: jedna implementacja `sms_segments`,
  ten sam wynik co w podglądzie.
- **„Wyślij ponownie”** wraca tę samą wiadomość do kolejki z nowym identyfikatorem (stary telefon odrzuciłby jako
  duplikat). W wysyłce anulowanej przycisku nie ma, bo kolejka tej wysyłki już nie rusza.
- **Liczby w wysyłce są rozłączne i sumują się do liczby odbiorców:** w kolejce / wysłano bez potwierdzenia /
  dostarczono / błędy / anulowano. Pasek postępu nie liczy anulowanych.
- **Brak połączenia z telefonem** to czerwony pasek na każdej stronie, z powodem i odnośnikiem do ustawień.
- **„Nie odpowiedzieli”** bez wybranej wysyłki pokazuje ostatnią wysyłkę zamiast wszystkich rozmów.
- Statusy mają znak + tekst (znak z CSS), tekst wszędzie ma co najmniej 16 px, pola mają etykiety.
- Niesprawdzone na żywo: czerwony pasek przy prawdziwej utracie połączenia (sprawdzone tylko w kodzie i szablonie).

## Limity SMS, tempo i ryzyko blokady (dodatek do wymagań, 2026-10-07)

Wymagania z dodatku właściciela (research: Telerivet, XDA, RestSMS, dokumentacja SMSGate).

- **Limit Androida pilnuje panel, nie użytkownik.** Ustawienia `limit_count` / `limit_window` (domyślnie 30 SMS-ów
  na 30 minut). Kolejka liczy **segmenty** wysłane w przesuwanym oknie (`messages.segments`, `sent_at`) i nie wysyła,
  gdy kolejna wiadomość by się nie zmieściła. Wysyłki grupowe biorą najwyżej 80% limitu (`RESERVE`), reszta zostaje
  na odpowiedzi pisane ręcznie; odpowiedzi też liczą się do limitu i czekają dopiero przy 100%.
  Zastępuje to wcześniejsze pole wyboru „wysyłaj wolno” (62–70 s), które było obejściem tego samego problemu.
- **Okno liczone zegarem rzeczywistym** (`sent_at`), tempo między SMS-ami zegarem przekazanym do `tick` – jak dotąd.
  W testach okno przesuwa się przez cofnięcie `sent_at` w bazie.
- **Tempo domyślne 8–20 s** (heurystyka z dodatku, nie wartość z dokumentacji). Zapisane wcześniej wartości zostają.
- **Szacowany czas** = większa z dwóch liczb: liczba osób × średnia przerwa albo (segmenty ponad wolny budżet) /
  budżet × okno. To przybliżenie, pokazywane jako „około”.
- **„Bez polskich znaków”**: `core.plain` zamienia polskie litery oraz „ ” – … na odpowiedniki z alfabetu GSM-7,
  po podstawieniu imienia. Domyślnie wyłączone; licznik i podgląd pokazują, ile SMS-ów by ubyło.
- **Duża wysyłka**: ponad `max_recipients` (50) osób wymaga drugiego pola potwierdzenia, sprawdzanego też na serwerze.
- **Błędy telefonu** tłumaczy `gateway.explain_error` (nazwy błędów z docs.sms-gate.app/faq/errors). Przy
  `RESULT_ERROR_LIMIT_EXCEEDED` wysyłka przechodzi w „Wstrzymana”; statusy są sprawdzane przed wysłaniem kolejnego SMS-a.
- **Wiadomość przyjęta przez telefon i niewysłana od 3 minut** → żółty pasek „Sprawdź ekran telefonu”.
  To domysł: panel nie widzi okienka Androida, widzi tylko brak postępu.
- **Higiena treści** w podglądzie: skrócony link, identyczna treść do 5+ osób bez imienia, treść już wysyłana.
- Strona pomocy `/pomoc/limit` w panelu powtarza skrót rozdziału z INSTRUKCJI (wariant A i B).
- **Niesprawdzone:** czy polecenia `adb` działają na Androidzie 14/15 i nakładkach producentów; czy Android na
  telefonie użytkownika liczy segmenty tak samo; limity operatorów (brak publicznych liczb).

## Połączenie, MMS-y i powiadomienia (2026-10-08)

- **Stan połączenia**: wynik sprawdzenia przy zapisie ustawień od razu staje się stanem połączenia; ponawianie po
  utracie co 5/10/15 s (było do 60 s), nawiązanie połączenia najwyżej 3 s, strona odświeża stan co 3 s.
- **MMS-y**: `GET /inbox` oddaje tylko podgląd tekstu. Załączniki SMSGate przekazuje wyłącznie zdarzeniem
  `mms:downloaded` (webhook), a webhook poza 127.0.0.1 wymaga HTTPS z zaufanym certyfikatem. Dla prostoty pierwszego
  uruchomienia panel pyta dodatkowo o `type=MMS` i pokazuje wpis „przyszedł MMS – zobacz w telefonie”. Błąd tego
  zapytania (starsza wersja SMSGate) jest ignorowany. Niesprawdzone na prawdziwym telefonie: co dokładnie jest
  w `contentPreview` dla MMS-a. Pełne zdjęcia = webhook + certyfikat, do zrobienia, gdy będą potrzebne.
- **Powiadomienia**: Notification API przeglądarki (127.0.0.1 jest „bezpiecznym” adresem), bez serwera push.
  Włącznik w Ustawieniach zapamiętany w `localStorage` (zgoda i tak jest per przeglądarka);
  zgoda nadana ręcznie w przeglądarce też włącza powiadomienia, wyłącza je dopiero przycisk. Dymek pokazuje się
  zawsze (także gdy panel jest na wierzchu – inaczej w demo wygląda, jakby nie działał); zawiera nadawcę, bez treści. Schowana karta odpytuje neutralną stronę, żeby otwarta
  rozmowa nie oznaczała wiadomości jako przeczytanych.

## Audyt bezpieczeństwa (2026-10-09)

Założenie: panel działa tylko na komputerze użytkownika (nasłuch wyłącznie na 127.0.0.1), bez logowania.

Sprawdzone i w porządku: nasłuch tylko lokalny; ochrona przed wywołaniem z obcej strony (nagłówki Host i
Origin/Referer, test); zapytania SQL z parametrami; szablony z automatycznym escapowaniem, bez `|safe`;
brak treści wiadomości i numerów w logach (log dostępu wyłączony); dane poza katalogiem projektu (`%APPDATA%`);
zależności bez znanych podatności (pip-audit, 2026-10-09).

Poprawione: nagłówki zakazujące osadzania panelu w ramce (clickjacking) i `nosniff`; komórki eksportu CSV
zaczynające się od `= + - @` dostają apostrof (formuły w Excelu); usunięty znak CR z pól wizytówek;
minimalne uprawnienia w GitHub Actions; z testów usunięte prawdziwe dane osobowe.

Świadomie zostawione:
- Hasło do SMSGate leży jawnym tekstem w lokalnej bazie i wraca do formularza ustawień (pole zamaskowane).
  To hasło działa tylko w sieci domowej i jest widoczne na ekranie telefonu.
- Połączenie panel-telefon to zwykłe HTTP w sieci Wi-Fi (tak działa tryb lokalny SMSGate): ktoś w tej samej
  sieci może podsłuchać hasło i treść SMS-ów. Nie używać w publicznych sieciach Wi-Fi.
- Każdy program i każdy użytkownik zalogowany na tym komputerze ma dostęp do panelu (brak logowania).
- Brak limitu wielkości wczytywanego pliku CSV (plik wybiera sam użytkownik).
- Plik exe nie jest podpisany - Windows SmartScreen może ostrzegać przy pierwszym uruchomieniu.
