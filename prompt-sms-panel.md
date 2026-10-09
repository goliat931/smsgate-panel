# Prompt dla Claude Code: lokalny panel SMS na bazie SMSGate

Wklej całość poniżej do Claude Code w pustym katalogu projektu.

---

## Cel

Zbuduj prostą, lokalną aplikację webową ("SMS Panel") do zarządzania komunikacją SMS-ową z użyciem bramki **SMSGate** (https://sms-gate.app, dokumentacja: https://docs.sms-gate.app, repo: https://github.com/capcom6/android-sms-gateway) działającej na telefonie z Androidem w **trybie lokalnym** (telefon i komputer w tej samej sieci Wi-Fi).

Zastosowania: wysyłka grupowa do uczestników wydarzeń/zamówień (np. zmiana godziny lub lokalizacji), odbieranie odpowiedzi i prowadzenie osobnych wątków z każdą osobą.

**Najważniejsze wymaganie: instalacja i konfiguracja mają być banalne dla osoby nietechnicznej.** Użytkownik nie zna terminala, Pythona ani Dockera.

## Zanim zaczniesz pisać kod

1. Przeczytaj aktualną dokumentację SMSGate (tryb lokalny: wysyłanie, listowanie wiadomości, statusy, webhooki, uwierzytelnianie Basic Auth, port domyślny, nagłówki). **Nie zakładaj endpointów z pamięci**, sprawdź je w dokumentacji i w oficjalnej bibliotece `android-sms-gateway` (PyPI / github.com/android-sms-gateway/client-py).
2. Zaproponuj krótki plan (stos, struktura, sposób pakowania) i dopiero wtedy implementuj. Jeśli coś w dokumentacji jest niejednoznaczne (np. czy webhooki w trybie lokalnym wymagają, by telefon widział komputer), napisz to wprost i wybierz bezpieczne rozwiązanie awaryjne (np. odpytywanie `GET /messages` co kilka sekund).

## Wymagania funkcjonalne

**Ekran Ustawienia (pierwsze uruchomienie = kreator):**
- Pola: *Adres telefonu (IP:port, np. 192.168.1.50:8080)*, *Login*, *Hasło* (z przyciskiem pokaż/ukryj).
- Przycisk **"Sprawdź połączenie"** z czytelnym komunikatem po polsku (OK / zły adres / zły login lub hasło / telefon nieosiągalny, z podpowiedzią co zrobić).
- Krótka instrukcja z obrazkami lub opisem kroków: gdzie w aplikacji SMSGate na telefonie znaleźć IP, port, login i hasło oraz jak włączyć serwer lokalny.
- Po zapisaniu automatycznie rejestruj webhook odbioru wiadomości (jeśli dokumentacja to przewiduje) lub włącz tryb odpytywania.

**Kontakty i grupy:**
- Dodawanie ręczne oraz import z CSV (kolumny: imię, telefon, opcjonalnie notatka/grupa). Normalizuj numery do formatu międzynarodowego (domyślnie +48), wykrywaj duplikaty i błędne numery.
- Grupy/tagi (np. "Tabliczki - zamówili", "Impreza X"), jeden kontakt może mieć wiele grup.

**Wysyłka grupowa:**
- Wybór grupy lub pojedynczych osób, treść wiadomości z zmiennymi, np. `{imie}`.
- **Podgląd przed wysyłką** (pierwsze 3 wiadomości po podstawieniu, liczba odbiorców, liczba segmentów SMS) i obowiązkowe potwierdzenie.
- Wysyłka z kontrolowanym tempem (domyślnie np. 1 SMS na 3-5 s, konfigurowalne), żeby nie ryzykować blokady numeru przez operatora. Pasek postępu, możliwość wstrzymania/anulowania.
- Szablony wiadomości do zapisania i ponownego użycia.

**Skrzynka i wątki:**
- Widok jak w komunikatorze: lista rozmów po lewej (nieprzeczytane wyróżnione, sortowanie po ostatniej aktywności), wątek z jedną osobą po prawej, pole odpowiedzi.
- Odpowiedzi przychodzące od nieznanych numerów trafiają do skrzynki jako "Nieznany numer" z możliwością dodania do kontaktów.
- Statusy wiadomości wychodzących: w kolejce / wysłano / dostarczono / błąd (na podstawie statusów z SMSGate).
- Filtry: "Wymaga odpowiedzi" (ostatnia wiadomość od osoby), "Nie odpowiedzieli" w wybranej kampanii.
- Obsługa rezygnacji: wiadomość zawierająca np. STOP/NIE PISZ oznacza kontakt jako "nie wysyłaj" i blokuje wysyłkę grupową do niego.

**Historia:** lista kampanii (wysyłek grupowych) z podsumowaniem: ilu odbiorców, dostarczono, błędy, odpowiedzi. Eksport do CSV.

## Wymagania niefunkcjonalne

- **Interfejs wyłącznie po polsku**, prosty, duże czytelne przyciski, brak żargonu. Komunikaty błędów mówią, co zrobić, a nie pokazują stack trace.
- **Stos (zaproponuj i uzasadnij, preferowane):** Python 3.11+, FastAPI (lub Flask), SQLite, szablony Jinja2 + lekki JS (HTMX lub vanilla), bez budowania frontendu (bez Node.js u użytkownika). Użyj oficjalnej biblioteki `android-sms-gateway`, jeśli pokrywa potrzebne funkcje; w przeciwnym razie `httpx`.
- **Bezpieczeństwo:** serwer nasłuchuje tylko na `127.0.0.1` (opcjonalnie przełącznik "udostępnij w sieci lokalnej" wymagany przez webhooki, jeśli dokumentacja tego wymaga, wtedy z ostrzeżeniem i prostym hasłem do panelu). Hasło do bramki przechowuj lokalnie, nigdy nie loguj danych logowania ani treści wiadomości na poziomie INFO. Plik bazy i konfiguracji w katalogu użytkownika (np. `%APPDATA%/SmsPanel` na Windows, `~/Library/Application Support/SmsPanel` na macOS).
- **Dane tylko lokalnie.** Żadnej telemetrii, żadnych zewnętrznych usług.
- Odporność: ponawianie przy chwilowej niedostępności telefonu, kolejka wysyłki przeżywa restart aplikacji, brak duplikatów wiadomości przy ponownym uruchomieniu.

## Instalacja dla osoby nietechnicznej (kluczowe)

Cel: **pobierz, kliknij dwa razy, otwiera się przeglądarka z panelem.**

1. Dostarcz **gotowy plik wykonywalny** zbudowany PyInstallerem (tryb `--onefile` lub folder z `SmsPanel.exe`), tak by użytkownik **nie musiał instalować Pythona**. Priorytet: **Windows 10/11**, następnie macOS.
2. Po uruchomieniu aplikacja: startuje serwer na wolnym porcie, sama otwiera przeglądarkę na `http://127.0.0.1:<port>`, pokazuje w małym oknie lub w konsoli jednozdaniowy komunikat "Panel działa, nie zamykaj tego okna", obsługuje łagodne zamknięcie (Ctrl+C / zamknięcie okna).
3. Dodaj skrypt budowania (`build.ps1` oraz `build.sh`) i opcjonalnie definicję CI (GitLab CI lub GitHub Actions) budującą artefakt `.exe`.
4. Napisz **`INSTRUKCJA.md` po polsku** dla laika, z numerowanymi krokami:
   - jak zainstalować SMSGate na telefonie (APK z GitHub, zgoda na instalację z nieznanych źródeł, uprawnienia SMS),
   - jak włączyć serwer lokalny i gdzie odczytać IP/port/login/hasło,
   - jak sprawdzić, że telefon i komputer są w tej samej sieci Wi-Fi,
   - jak uruchomić panel i wypełnić trzy pola ustawień,
   - najczęstsze problemy (zapora Windows, telefon w trybie oszczędzania baterii zabija usługę, inna sieć Wi-Fi, zmiana IP telefonu: zalecenie rezerwacji adresu w routerze).
5. Obsłuż pierwszy start w Windows: komunikat SmartScreen/zapory ("Zezwól na dostęp") opisany w instrukcji.

## Jakość i testy

- Testy `pytest` dla: normalizacji numerów, podstawiania zmiennych, kolejki wysyłki (z atrapą bramki), parsowania webhooków/odpowiedzi, wykrywania rezygnacji.
- Dołącz **tryb demo / atrapę bramki** (`--demo`), żeby dało się przetestować cały panel bez telefonu.
- Struktura repo czytelna, `README.md` dla developera (jak uruchomić ze źródeł, jak zbudować exe), `pyproject.toml` (Poetry lub uv).

## Poza zakresem pierwszej wersji (nie implementuj, ale zostaw miejsce w architekturze)

- Szkice odpowiedzi generowane przez AI do zatwierdzenia jednym kliknięciem (opcjonalne pole na klucz API w ustawieniach).
- Wysyłka zaplanowana na godzinę, wiele telefonów/kart SIM, MMS.

## Sposób pracy

- Pracuj etapami: (1) plan, (2) szkielet + ustawienia + test połączenia + tryb demo, (3) kontakty i wysyłka, (4) skrzynka i webhooki, (5) pakowanie + instrukcja. Po każdym etapie uruchom testy i krótko podsumuj.
- Gdy musisz coś zgadnąć, wybierz najprostsze rozwiązanie z punktu widzenia laika i zapisz decyzję w `DECISIONS.md`.
- Na końcu przejdź własnoręcznie scenariusz "świeży użytkownik" z `INSTRUKCJA.md` w trybie demo i zgłoś, co jest niejasne.
