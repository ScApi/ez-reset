# EZ-Reset — rozbudowa GUI / baza modeli WIC (wersja testowa)

## Co działa w tym pakiecie

- Interfejs po polsku: zakładki Połączenie USB, Liczniki, Konserwacja, Wydruki testowe.
- Lista rzeczywistych interfejsów USBPRINT z przyciskiem odświeżenia, wyborem, podwójnym kliknięciem i zapamiętywaniem wybranej ścieżki.
- Asynchroniczna komunikacja USB (pasek aktywności i komunikaty błędów; GUI nie powinno blokować się w trakcie poleceń).
- Graficzne paski poziomów tuszu (BK/C/M/Y i dodatkowe kolory) oraz poziomu zapełnienia pochłaniacza w zakładce „Liczniki”.
- Poziom „pampersa” liczony z EEPROM; progi kolorów: zielony <70%, żółty 70–89,9%, czerwony od 90%. W przypadku wielu liczników każdy ma osobny wskaźnik.
- Poziomy tuszu odczytywane niezależnie od dostępności profilu EEPROM. Nieobsługiwane lub nieznane wartości pokazują „Brak danych”, a nie 0%.
- **Epson L3150 (EcoTank):** jeśli odczyt stanu drukarki się powiedzie, lecz poziomy tuszów nie są udostępniane, GUI wyświetla osobne kolorowe oznaczenia BK/C/M/Y z komunikatem „Sprawdź w zbiorniku”, bez sztucznych procentów. Gdy dany kolor ma wiarygodny odczyt 0–100%, wartość pozostaje widoczna. Błędy komunikacji nadal są wyświetlane jako błędy, nie jako zachęta do kontroli zbiorników.
- Odczyty wizualne odświeżają się po podłączeniu USB, ręcznym odświeżeniu i po resecie EEPROM (ostateczna wartość może wymagać restartu drukarki).
- Reset: backup **zmienianych bajtów** EEPROM, odczyt i weryfikacja zapisu każdego bajtu, przerwanie przy błędzie.
- Przyciski standardowego czyszczenia USB (korzysta z istniejącej funkcji `Printer.clean(0)`, komenda fabryczna 0x84; jej obsługa przez konkretną drukarkę **nie jest potwierdzona**).
- Test dysz: **dwie metody** — preferencje sterownika Epson (użytkownik uruchamia test) oraz eksperymentalne bezpośrednie wysłanie ESC/P2 Remote Mode `NC` jako zadanie RAW (wyłącznie drukarki/sterowniki obsługujące ten protokół, bez gwarancji wydruku).
- Wydruk testowy czarno-biały i kolorowy przez sterownik Windows (GDI), bez arbitralnego przejmowania domyślnej drukarki.
- Weryfikacyjny katalog 12 brakujących nazw WIC (bez danych serwisowych i bez możliwości wykonania resetu na ich podstawie).

### Interpretacja wskaźników

Wartość procentowa pochłaniacza jest szacunkiem zużycia według licznika drukarki, nie pomiarem ilości atramentu w gąbce. Poziomy tuszu są wartościami deklarowanymi przez elektronikę urządzenia; w drukarkach EcoTank mogą nie odpowiadać faktycznemu poziomowi płynu w zbiornikach. Brak licznika albo nieważna wartość (np. -1, 105, 110) nie oznacza 0%.

## Ograniczenia

1. **Nie ma nowych potwierdzonych map EEPROM.** Znane 449 nazw WIC z grup ET/L/WP znajduje już odpowiedniki w XML EZ. Dodatkowe 12 nazw wykryto w innych rodzinach — zapisano je w `wic_candidates.csv` tylko jako informację do potwierdzenia. Nie wolno podłączać komend obcego modelu na podstawie podobnej nazwy.
2. `USBPRINT` wybiera fizyczny interfejs; kolejka Windows służy do wydruków GDI i może nie odpowiadać temu samemu urządzeniu. Potwierdź wybór w oknie.
3. Standardowe czyszczenie wysyła polecenie, **nie ma gwarantowanego potwierdzenia rozpoczęcia cyklu**. Bezpośredni test dysz ESC/P2 może być ignorowany przez współczesny sterownik i nie został jeszcze zweryfikowany sprzętowo. Model należy sprawdzić na urządzeniu.
4. Bez urządzenia Epson podłączonego do Windows nie da się potwierdzić resetu, wydruków ani zachowania sterownika. Kod został przetestowany jednostkowo z atrapami API drukowania.
5. Reset liczników tylko po fizycznym serwisie pochłaniacza. Weryfikacja EEPROM nie umożliwia automatycznego wycofania częściowego resetu.

## Wgranie na fork

Skopiuj pliki z paczki do katalogu głównego forka `ez-reset`, zachowując strukturę ścieżek. Nie kasuj pozostałych plików repozytorium, w szczególności `src/ez_reset/devices.xml`, `printer.py`, `win_usbprint/`.

Na Windows 10/11, Python 3.12+:

```powershell
python -m pip install -e .
python -m ez_reset
```

Budowanie EXE (gdy zainstalowany PyInstaller):

```powershell
python -m pip install pyinstaller
pyinstaller --clean ez-reset.spec
```

Skrypt porównania WIC do EZ (wciąż wymaga oryginalnego `devices.xml`):

```powershell
python tools/aktualizuj_katalog_wic.py --xml src/ez_reset/devices.xml --out raporty
```

Tryb offline z dostarczonym fragmentem katalogu:

```powershell
python tools/aktualizuj_katalog_wic.py --xml src/ez_reset/devices.xml --out raporty --seed-only
```

## Źródła

- https://github.com/CiRIP/ez-reset — kod EZ-Reset.
- https://wicreset.jmultishop.com/support — lista starszych rodzin WIC.
- https://www.wic.support/supported-printers-models-list/ — wykaz WIC.
- https://resetkey.net/wic-reset-utility-supported-models-list — wykaz WIC 5.97 (2026).
- https://github.com/Ircama/epson_print_conf — porównawcza dokumentacja konserwacji Epson.

**Status:** kod przeznaczony do opublikowania w gałęzi testowej forka `ScApi/ez-reset`; `master` pozostaje bez zmian.
