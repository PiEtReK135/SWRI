# Walidacja InvestWatch

Pomiary wykonano w instancji Linux, Python 3.12, procesor AMD EPYC 9V74. Wyniki wydajności na Windows 11 z i7-1360P i 16 GB RAM wymagają osobnego pomiaru.

| Kontrola | Wynik |
|---|---|
| `python -m unittest discover -v` | 7 testów zaliczonych. Obejmują MP4+SRT+OCR, OCR-only, routing M1/M2/M3, restart bazy, uszkodzone media, CAPTCHA, reguły, kalibrację i walidację odpowiedzi lokalnego modelu. |
| MP4 24 s + napisy + OCR + raport JSON | 2,33 s od żądania importu do gotowości zadania w ostatnim pomiarze. |
| Compose | Obraz zbudowano z zaufanym pakietem CA hosta przekazanym jako sekret BuildKit. Uruchomiono kontener i sprawdzono cztery klipy demo, w tym M1/M2/M3 i OCR-only. |
| SSE na działającym serwerze | Odczytano identyfikator i treść zdarzenia z dziennika. |
| Chromium / Playwright | Wczytanie demo, otwarcie „Jesienna wędrówka”, kliknięcie cytatu 00:18, skok odtwarzacza i widoczny link raportu JSON. |
| `node --check investwatch/web/app.js` | Zaliczono. Frontend korzysta z API przeglądarki i nie ma zależności npm. |
| `pip-audit` | Audyt wykrył podatności w pip 25.0.1. Po aktualizacji do 26.2.2 audyt zainstalowanego środowiska z zależnościami bazowymi, AI i testowymi zwrócił `No known vulnerabilities found`. |
| Modele lokalne | Import biblioteki faster-whisper przeszedł. Pobranie modelu z Hugging Face zwróciło 403. Nie wykonano inferencji Whisper na rzeczywistym audio ani połączenia z uruchomioną Ollama. Odpowiedź Ollama sprawdzono testem z podstawionym transportem. |

### Klasyfikacja promocji na próbie syntetycznej

24 oznaczone wejścia tekstowe, w tym 7 pozytywnych. Przykłady opisane jako ASR w tym pomiarze zawierają ręcznie przygotowany tekst. Osobny test integracyjny sprawdza OCR rzeczywistych klatek wygenerowanych klipów.

| Próg | TP | FP | FN | Precyzja | Pełność |
|---:|---:|---:|---:|---:|---:|
| 55 | 7 | 0 | 0 | 1,00 | 1,00 |
| 75 | 5 | 0 | 2 | 1,00 | 0,71 |
| 95 | 0 | 0 | 7 | — | 0,00 |

Wyniki odnoszą się do próby syntetycznej. Pakiet załączników nie zawierał nagrań do testu na danych rzeczywistych.

### Instalacja i integracja strony

W chmurze zweryfikowano pobranie danych OCR `pol` i `eng` wraz z sumami SHA-256 i wykonano 8 testów z tymi pakietami. Test integracyjny serwuje własną stronę referencyjną pod `/`, panel pod `/dashboard` i API pod tym samym originem. Próbka MP4 z napisami i OCR zajęła w tej konfiguracji 3,10 s. Archiwum strony nie zostało odczytane z powodu limitu transferu 32 MiB. Skrypt PowerShell jest przeznaczony dla Windows i nie był wykonywany na komputerze docelowym.
