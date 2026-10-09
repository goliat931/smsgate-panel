# Panel SMS – instrukcja krok po kroku

Panel SMS to program na komputer, którym wysyłasz i odbierasz SMS-y **przez swój telefon z Androidem**.
SMS-y wychodzą z Twojego numeru i Twojej karty SIM (płacisz za nie tak jak zwykle, według swojej taryfy).
Wszystko zostaje na Twoim komputerze i telefonie – nic nie jest wysyłane do internetu.

Potrzebujesz:

- telefonu z Androidem i kartą SIM,
- komputera z Windows 10 lub 11,
- telefon i komputer muszą być w **tej samej sieci Wi-Fi** (np. domowej).

Całość zajmuje około 10 minut. Robisz to tylko raz.

---

## Część 1. Zainstaluj aplikację SMSGate na telefonie

1. Na telefonie otwórz przeglądarkę (np. Chrome) i wejdź na stronę:
   **https://github.com/capcom6/android-sms-gateway/releases/latest**
2. Przewiń w dół do listy „Assets” i dotknij pliku **`app-release.apk`**. Plik się pobierze.
   (Nie wybieraj `app-insecure.apk`.)
3. Dotknij pobranego pliku. Telefon zapyta, czy zezwolić na instalację z tego źródła:
   dotknij **Ustawienia**, włącz **Zezwalaj z tego źródła**, wróć i dotknij **Zainstaluj**.
   - Jeśli pojawi się ostrzeżenie Google Play Protect, wybierz **Zainstaluj mimo to**.
     Aplikacji nie ma w Sklepie Play, bo Google nie dopuszcza tam aplikacji wysyłających SMS-y. Jej kod jest publiczny.
4. Otwórz aplikację **SMSGate**. Gdy zapyta o uprawnienia do **SMS-ów** i **powiadomień** – wybierz **Zezwól**.
   Bez tego nie będzie mogła wysyłać ani odbierać wiadomości.

## Część 2. Włącz serwer lokalny w telefonie

1. W aplikacji SMSGate włącz przełącznik **Local Server**. (Przełącznik „Cloud Server” zostaw wyłączony.)
2. Dotknij dużego przycisku **Offline** na dole ekranu. Po chwili zmieni się na **Online**.
3. W ramce **Local Server** zobaczysz trzy rzeczy. Zapisz je na kartce albo zostaw telefon odblokowany obok komputera:

   | W telefonie        | Przykład              | W Panelu SMS wpiszesz jako |
   |--------------------|-----------------------|----------------------------|
   | **Local address**  | `192.168.1.50:8080`   | Adres telefonu             |
   | **Username**       | `sms`                 | Login                      |
   | **Password**       | `aB3xY9kLmN2pQ7`      | Hasło                      |

   Jeśli hasło jest zakryte kropkami, dotknij go, żeby je zobaczyć.
   „Public address” nie jest potrzebny – pomiń go.

4. **Ważne – żeby telefon nie „usypiał” aplikacji:** w SMSGate wejdź w zakładkę **Settings** i:
   - dotknij **Battery optimization** i zezwól aplikacji na działanie bez ograniczeń,
   - włącz **Start on boot** (aplikacja sama wystartuje po ponownym uruchomieniu telefonu).

## Część 3. Sprawdź, czy telefon i komputer są w tej samej sieci Wi-Fi

1. Na telefonie: przeciągnij palcem z góry ekranu i przytrzymaj ikonę Wi-Fi. Zobacz **nazwę sieci**, z którą jest połączony.
2. Na komputerze: kliknij ikonę Wi-Fi w prawym dolnym rogu ekranu. Nazwa sieci musi być **taka sama**.
3. Jeśli komputer jest podłączony kablem do tego samego routera, co Wi-Fi telefonu – też jest dobrze.

Nie zadziała: telefon na danych komórkowych (LTE/5G), sieć „dla gości”, dwa różne routery.

## Część 4. Uruchom Panel SMS na komputerze

1. Skopiuj folder z plikiem **`SmsPanel.exe`** w wygodne miejsce, np. na Pulpit.
2. Kliknij go dwa razy.
3. **Przy pierwszym uruchomieniu Windows może pokazać dwa okna:**
   - Niebieskie okno „System Windows ochronił ten komputer” – kliknij **Więcej informacji**, a potem **Uruchom mimo to**.
     (Pojawia się, bo program nie pochodzi ze sklepu Microsoft.)
   - Okno „Zapora Windows Defender zablokowała niektóre funkcje” – zaznacz **Sieci prywatne** i kliknij **Zezwól na dostęp**.
4. Pojawi się czarne okno z napisem **„Panel SMS działa. Nie zamykaj tego okna.”** – możesz je zminimalizować,
   ale nie zamykaj. Zamknięcie tego okna wyłącza panel.
5. Po sekundzie sama otworzy się przeglądarka z panelem. Jeśli się nie otworzy, wpisz w przeglądarce adres
   pokazany w czarnym oknie (zwykle `http://127.0.0.1:8765`).

## Część 5. Wypełnij trzy pola

1. W panelu zobaczysz ekran **„Witaj! Połączmy panel z telefonem”**.
2. Przepisz z telefonu: **Adres telefonu**, **Login**, **Hasło** (patrz tabelka w Części 2).
3. Kliknij **Sprawdź połączenie**.
   - Zielony napis „Połączenie działa” – świetnie, kliknij **Zapisz**.
   - Czerwony napis – przeczytaj go, mówi, co poprawić. Zobacz też „Najczęstsze problemy” niżej.
4. Gotowe. Panel przeniesie Cię do **Kontaktów**.

---

## Jak używać panelu

- **Kontakty** – lista wszystkich osób. **Dodaj jedną osobę** rozwija formularz (imię, nazwisko, telefon, e-mail, notatka),
  a **Wczytaj listę z pliku** prowadzi w trzech krokach przez wczytanie pliku CSV
  (Excel: *Plik → Zapisz jako → CSV*). Szczegóły niżej, w części „Wczytywanie listy z pliku”.
- **Grupy** – tu w jednym miejscu tworzysz grupy (np. „Impreza X”, „Tabliczki – zamówili”), zmieniasz im nazwy,
  dodajesz i usuwasz osoby, przenosisz lub kopiujesz osoby między grupami i usuwasz grupy.
  Usunięcie grupy albo osoby z grupy **nie usuwa** jej z kontaktów.
- **Nowa wysyłka** – panel prowadzi w czterech krokach: **1. Odbiorcy** (zaznacz grupy lub osoby),
  **2. Treść** (przycisk **Wstaw imię** wstawi każdemu jego imię; pod polem widać, ile SMS-ów zajmie wiadomość),
  **3. Podgląd** i **4. Wysyłka**. Nic nie wyjdzie, dopóki nie potwierdzisz w ostatnim kroku.
- Wiadomości grupowe wychodzą **powoli (jedna co kilka sekund)** – to celowe, żeby operator nie zablokował numeru.
  Wysyłkę można wstrzymać albo anulować.
- **Skrzynka** – rozmowy jak w komunikatorze. Odpowiedzi pojawiają się same po kilku sekundach.
  Pogrubione = nieprzeczytane. Zakładka „Wymaga odpowiedzi” pokazuje osoby, które czekają na Twoją odpowiedź,
  a „Nie odpowiedzieli” – osoby, które nie odpisały na wybraną wysyłkę.
- Jeśli ktoś odpisze **STOP** (albo „nie pisz”, „wypisz”, „rezygnuję”), panel oznaczy go „nie wysyłaj”
  i pominie w wysyłkach grupowych. Można to cofnąć w rozmowie lub w kontakcie.
- **Historia** – lista wysyłek: ile dostarczono, błędy, ile osób odpowiedziało. Można pobrać jako plik.
  Przy wiadomości z błędem jest przycisk **Wyślij ponownie**.
- Gdy panel straci połączenie z telefonem, na górze pojawi się **czerwony pasek** z podpowiedzią, co sprawdzić.
  Wiadomości czekają wtedy w kolejce i wyjdą same, gdy połączenie wróci.
- Panel widzi tylko odpowiedzi, które przyszły **po** połączeniu go z telefonem. Starszych SMS-ów nie wczytuje.

**Chcesz najpierw poćwiczyć bez telefonu?** Zobacz „Tryb demo” na końcu.

### Wczytywanie listy z pliku (CSV)

Najprościej: w pierwszym wierszu arkusza wpisz nazwy kolumn, pod spodem osoby. Na stronie **Kontakty** jest
przykładowy plik do pobrania (po kliknięciu **Wczytaj listę z pliku**).

Wczytywanie ma trzy kroki: **1. Wybierz plik**, **2. Sprawdź** – panel pokazuje, co odczytał, i jeszcze niczego nie
zapisuje, **3. Gotowe** – dopiero po kliknięciu „Wczytaj do kontaktów”.

| imię | nazwisko | telefon | e-mail | notatka | grupa |
|------|----------|---------|--------|---------|-------|
| Anna | Nowak | 600 100 200 | anna@example.com | 2 tabliczki | Impreza X |

- Obowiązkowy jest tylko **telefon**. Reszta kolumn jest do wyboru, w dowolnej kolejności.
- Nazwy kolumn nie muszą być dokładnie takie: zadziała też „Komórka”, „Nr telefonu”, „Adres e-mail”, „Uwagi”.
- Imię i nazwisko mogą być w jednej kolumnie („Imię i nazwisko”).
- Kolumny, których panel nie zna (np. „Miasto”), są pomijane.
- Kilka grup dla jednej osoby wpisz po przecinku: `Impreza X, Wolontariusze`.
- Plik bez wiersza z nazwami też zadziała, jeśli kolumny idą w kolejności: imię, nazwisko, telefon, potem notatka i grupa.
- Można wczytać plik wyeksportowany z Kontaktów Google.
- W kroku „Sprawdź” panel pokaże, **które kolumny rozpoznał**, ile osób jest nowych i które wiersze pominie (z powodem).
- Jeśli numer już jest w kontaktach, osoba nie zostanie dodana drugi raz – panel tylko uzupełni jej puste pola
  (np. dopisze e-mail) i dołączy ją do grupy.

### Przeniesienie grupy do kontaktów w telefonie (wizytówki)

Przydaje się, gdy chcesz, żeby telefon pokazywał imiona zamiast samych numerów.

1. W panelu wejdź w **Grupy** i przy wybranej grupie kliknij **Wizytówki na telefon**. Pobierze się plik `.vcf`.
2. Prześlij ten plik na telefon – najłatwiej wysłać go e-mailem do siebie albo wrzucić na Dysk Google.
3. Na telefonie dotknij pliku. Telefon zapyta, czy zaimportować kontakty – potwierdź i wybierz konto, na którym mają się zapisać.

W wizytówkach są: imię, nazwisko, telefon, e-mail i notatka. Nazwa grupy też jest zapisana, ale większość telefonów
jej nie odczytuje – kontakty trafią po prostu na listę. W aplikacji Kontakty Google znajdziesz je razem pod etykietą
„Zaimportowano dnia…”, której nazwę można zmienić na nazwę grupy.

### Powiadomienia o nowych wiadomościach

Panel może pokazać dymek Windows, gdy ktoś odpisze – także wtedy, gdy okno panelu jest zminimalizowane.

1. Wejdź w **Ustawienia** i w ramce „Powiadomienia o nowych wiadomościach” kliknij **Włącz powiadomienia**.
2. Przeglądarka zapyta o zgodę – wybierz **Zezwól**. Jeśli pytanie się nie pokaże (Edge czasem je chowa), kliknij
   ikonę obok adresu strony, przy „Powiadomienia” wybierz „Zezwalaj” i odśwież stronę.
3. Kliknij **Pokaż próbne powiadomienie**, żeby sprawdzić, czy dymek się pojawia.

Karta z panelem musi być otwarta w przeglądarce (może być schowana pod innymi oknami). Gdy karta jest długo schowana,
dymek może pojawić się z opóźnieniem do około minuty. W dymku jest tylko informacja, kto napisał – bez treści wiadomości.
Włączenie dotyczy tej jednej przeglądarki.

### MMS-y (zdjęcia)

Panel nie pokazuje zdjęć. Gdy ktoś przyśle MMS, w rozmowie pojawi się wpis „MMS (zdjęcie lub inny załącznik)” –
samo zdjęcie obejrzysz w telefonie, w zwykłej aplikacji do wiadomości.

---

## Najczęstsze problemy

**„Nie mogę połączyć się z telefonem”**
1. Sprawdź w telefonie, czy w SMSGate jest napis **Online**. Jeśli jest Offline – dotknij przycisku.
2. Sprawdź, czy telefon i komputer są w tej samej sieci Wi-Fi (Część 3).
3. Porównaj **Local address** w telefonie z adresem w Ustawieniach panelu, cyfra po cyfrze. Kropki i dwukropek mają znaczenie.
4. Wyłącz na chwilę VPN na komputerze, jeśli go używasz.

**„Login lub hasło są błędne”**
Przepisz je jeszcze raz. Uważaj na podobne znaki: duże `I` i małe `l`, zero `0` i litera `O`. Wielkość liter ma znaczenie.

**Wczoraj działało, dziś nie działa**
Najczęściej router dał telefonowi inny adres. Zobacz w telefonie aktualny **Local address** i wpisz go w panelu w **Ustawieniach**.
Żeby to się nie powtarzało, w ustawieniach routera można ustawić dla telefonu **stały adres (rezerwacja DHCP)** –
poproś o to osobę, która zakładała internet. To jedyna rzecz w tej instrukcji, która wymaga pomocy.

**Telefon po jakimś czasie przestaje odpowiadać**
Telefon „uśpił” aplikację, żeby oszczędzać baterię. Zrób punkt 4 z Części 2 (Battery optimization).
W telefonach Xiaomi, Huawei, Samsung trzeba dodatkowo w ustawieniach telefonu: *Aplikacje → SMSGate → Bateria → Bez ograniczeń*.
Najlepiej, żeby telefon podczas dużej wysyłki był podłączony do ładowarki.

**Zapora Windows: kliknąłem „Anuluj” zamiast „Zezwól”**
Zwykle panel i tak działa. Jeśli nie łączy się z telefonem: w menu Start wpisz „Zezwalaj aplikacji na dostęp przez Zaporę”,
znajdź **SmsPanel**, zaznacz **Prywatne** i kliknij OK.

**Telefon pyta o zgodę na wysyłkę SMS-ów („aplikacja wysyła dużo wiadomości”)**
Zobacz osobny rozdział niżej: „Telefon pyta o zgodę na wysyłkę SMS-ów”.

**Na górze panelu jest żółty pasek „Sprawdź ekran telefonu”**
Telefon przyjął wiadomości, ale ich nie wysyła. Najczęściej na ekranie telefonu czeka okienko z pytaniem o zgodę –
odblokuj telefon i kliknij „Zezwól”. Jeśli okienka nie ma, sprawdź zasięg.

**Na górze panelu jest żółty pasek „Panel robi przerwę w wysyłaniu”**
To celowe: panel pilnuje limitu SMS-ów telefonu. Wiadomości wyjdą same, nic nie trzeba robić.

**Wysyłka sama się wstrzymała**
Telefon albo operator odmówił wysłania z powodu limitu. Odczekaj pół godziny, sprawdź ekran telefonu,
kliknij **Wznów wysyłkę**, a przy wiadomościach z błędem **Wyślij ponownie**.

**Wiadomość ma status „Błąd”**
Pod statusem jest napisane po polsku, co się stało i co zrobić (np. brak zasięgu, brak środków, brak karty SIM,
błędny numer). Po usunięciu przyczyny kliknij **Wyślij ponownie**.

**Status zatrzymał się na „Wysłano” i nie zmienia się na „Dostarczono”**
Nie każdy operator odsyła potwierdzenie doręczenia. „Wysłano” oznacza, że SMS wyszedł z telefonu.
W Historii takie wiadomości są opisane jako „bez potwierdzenia”.

**Zamknąłem czarne okno w trakcie wysyłki**
Nic nie przepadło. Uruchom `SmsPanel.exe` ponownie – wysyłka ruszy dalej od miejsca, w którym stanęła, i nikt nie dostanie SMS-a dwa razy.

**Kliknąłem `SmsPanel.exe` drugi raz**
Nic złego – otworzy się ten sam panel w przeglądarce.

---

## Telefon pyta o zgodę na wysyłkę SMS-ów

**Dlaczego to się dzieje.** Android pilnuje, żeby żadna aplikacja nie wysłała zbyt wielu SMS-ów naraz.
Zwykle pozwala na **30 SMS-ów w ciągu 30 minut**. Po przekroczeniu pokazuje okienko „aplikacja wysyła dużą liczbę
wiadomości” i czeka na kliknięcie przy każdej kolejnej.

Limit kończy się szybciej, niż się wydaje:

- długa wiadomość liczy się jak kilka SMS-ów,
- polskie litery (ą, ć, ę, ł, ń, ó, ś, ź, ż) skracają jeden SMS ze 160 do 70 znaków – zwykła wiadomość
  z polskimi znakami to często 2–3 SMS-y, więc 30 SMS-ów wystarcza na 10–15 osób.

### Wariant A – bez komputera (zalecany)

Nic nie musisz ustawiać. Panel liczy wysłane SMS-y i **sam robi przerwy**, żeby nie przekroczyć limitu telefonu.
Większa wysyłka potrwa dłużej (podgląd pokazuje, ile), ale pójdzie sama – można zamknąć przeglądarkę,
wystarczy nie zamykać czarnego okna.

Żeby zmieścić więcej osób:

- w kroku **Treść** zaznacz **Wyślij bez polskich znaków** (ą→a, ł→l) – zwykle wychodzi 2–3 razy mniej SMS-ów,
- pisz krótko; licznik pod polem pokazuje, ile SMS-ów zajmie wiadomość.

Ustawienia są w **Ustawienia → Bezpieczna wysyłka**: przerwa między SMS-ami (zalecane 8–20 sekund),
limit telefonu (30 SMS-ów na 30 minut) i próg „dużej wysyłki” (powyżej 50 osób panel pyta dodatkowo o zgodę).

### Wariant B – jednorazowe podniesienie limitu w telefonie

Wymaga kabla USB i kilku poleceń na komputerze. Jeśli to brzmi obco, poproś kogoś o pomoc – robi się to raz.

1. Na komputerze pobierz „Android SDK Platform-Tools” ze strony developer.android.com i rozpakuj.
2. W telefonie: *Ustawienia → Informacje o telefonie* → dotknij 7 razy **Numer kompilacji**.
   Pojawią się **Opcje programisty** – włącz w nich **Debugowanie USB**.
3. Podłącz telefon kablem i zgódź się na telefonie na debugowanie.
4. W folderze Platform-Tools otwórz okno poleceń (w pasku adresu folderu wpisz `cmd` i naciśnij Enter) i wpisz po kolei:

   ```
   adb shell settings put global sms_outgoing_check_max_count 200
   adb shell settings put global sms_outgoing_check_interval_ms 1800000
   ```

5. Uruchom telefon ponownie.
6. W panelu: **Ustawienia → Bezpieczna wysyłka** → wpisz nowy limit: 200 SMS-ów na 30 minut.
7. Zrób próbę na 3–5 osobach.

**Uwaga:** na niektórych telefonach to nie zadziała, bo producent dodaje własne okienka: Xiaomi / Redmi / Poco
oraz Oppo / Realme / OnePlus. W Xiaomi pomaga wyłączenie „Optymalizacji MIUI” w opcjach programisty.
Ta metoda nie była sprawdzana na każdym telefonie i wersji Androida – dlatego próba na kilku osobach jest ważna.

### Jaki telefon i jaka karta SIM

- Najlepiej **osobny, niedrogi telefon** z Androidem zbliżonym do czystego, np. używany Pixel albo Motorola.
  Unikaj Xiaomi / Redmi / Poco oraz Oppo / Realme.
- Wyłącz dla SMSGate oszczędzanie baterii (Część 2) i zabezpiecz telefon PIN-em – SMS-y widać też w zwykłej aplikacji Wiadomości.
- **Operator też ma swoje zasady.** Operatorzy nie podają publicznie liczby SMS-ów na godzinę, ale regulaminy planów
  z „nielimitowanymi SMS-ami” zwykle zakazują używania karty do wysyłek automatycznych i masowych, a systemy operatora
  wyłapują kartę, która pisze do wielu osób w równych odstępach. Skutkiem może być blokada usług.
  Przeczytaj regulamin swojego planu. Wysyłaj powoli, do osób, które się tego spodziewają, z imieniem w treści,
  bez skróconych linków i bez powtarzania tej samej wiadomości – panel podpowiada to w podglądzie.

---

## Tryb demo (ćwiczenie bez telefonu)

1. Kliknij dwa razy plik **`Tryb-demo.bat`** (leży obok `SmsPanel.exe`).
2. Na górze panelu będzie żółty pasek „TRYB DEMO”.
3. W ustawieniach zostaw wpisane wartości (login `demo`, hasło `demo`), kliknij **Sprawdź połączenie**,
   a potem **Zapisz i przejdź dalej**.

W panelu czekają już przykładowe dane: 10 osób, 3 grupy, 2 wysyłki z historii i kilka rozmów (w tym nieprzeczytane,
jedna rezygnacja STOP i wiadomość od nieznanego numeru). Możesz je dowolnie zmieniać i kasować.
Żeby zacząć od nowa, na dole **Ustawień** kliknij **Usuń dane demo i wczytaj przykłady od nowa**.

W trybie demo żaden SMS nie wychodzi, a „telefon” jest udawany: część numerów sama odpisuje,
numery kończące się na 9 odpisują STOP, kończące się na 000 kończą błędem, a na 111 – błędem limitu SMS-ów. Dane demo są trzymane osobno i nie mieszają się z prawdziwymi.

## Gdzie są moje dane?

W folderze `%APPDATA%\SmsPanel` (wklej ten tekst w pasek adresu Eksploratora plików).
Plik `panel.db` to wszystkie kontakty, rozmowy i ustawienia – skopiuj go, żeby zrobić kopię zapasową.
