# Rolki i skaner InvestWatch

## Użycie

- `/rolki` odtwarza filmy z dźwiękiem i zdjęcia. Feed obsługuje przewijanie, strzałki na klawiaturze i przyciski nawigacji. **Dodaj rolkę** zapisuje plik, autora, temat i opis.
- `/skanowanie?start=1` automatycznie rozpoczyna sesję. Skaner kończy po 18 sekundach bez nowych materiałów lub po 200 rolkach. Przycisk **Zatrzymaj** kończy bieżącą analizę. **Przeanalizuj ponownie** uruchamia pojedynczą rolkę bez zmiany preferencji. **Resetuj skaner** tworzy świeży profil i usuwa poprzednie sesje z aktywnych widoków. Jest to logiczny reset, a wcześniejsze dane pozostają w lokalnych plikach bazy. **Resetuj moje preferencje** w feedzie zmienia wyłącznie profil bieżącej przeglądarki.
- `/#analiza` pokazuje materiały do sprawdzenia, posortowane według priorytetu. **Informacje szczegółowe** obejmują też neutralne treści finansowe, odrzucone rolki oraz analizy wymagające ponowienia. Dostępny jest raport JSON.

## Przepływ danych

1. **Publikacja.** Platforma przyjmuje MP4, WebM, MOV, JPEG, PNG oraz WebP. FFmpeg sprawdza i zapisuje filmy jako MP4 z dźwiękiem oraz zdjęcia jako JPEG. Metadane, reakcje i komentarze są w `data/reels/platform.sqlite3`, pliki w `data/reels/media/`.
2. **Rekomendacje.** Platforma gromadzi sygnały widza osobno dla każdej rolki. Obejrzenie liczy się jako udział rzeczywiście odtworzonych fragmentów, polubienie jako +1, zapis +3, komentarz +2, skopiowanie linku +2, a pełne obejrzenie +2. Tematy obserwowane przez widza dostają wyższy wynik. Sygnał **Nie interesuje mnie** ukrywa rolkę dla danego widza i obniża preferencję jej tematu o 3. Kolejność uwzględnia także zbiorczą aktywność i datę publikacji.
3. **Odkrywanie.** Platforma przypisuje temat z tytułu i opisu, z większą wagą opisu. Skaner pobiera rolki przez lokalne API feedu i ustala własną kategorię z opisu, mowy i OCR. Sygnały tematyczne z tytułu mogą wskazać potrzebę ponownej analizy, jeśli dowodów brakuje. Do decyzji o reklamie liczą się zebrane dowody.
4. **Strategia.** UCB rozdziela obserwacje pomiędzy przewinięcie, krótszy seans, dłuższy seans i zapis. Za trafienie liczy kolejną poleconą rolkę, jeśli analiza potwierdzi temat finansowy. Wybór bierze pod uwagę średnią trafień i liczbę prób każdej strategii. Symulowane obejrzenia i zapisy skanera zmieniają tylko jego profil. Skaner nie dodaje komentarzy ani publicznych reakcji.
5. **Ekstrakcja.** Domyślny model faster-whisper medium działa lokalnie na CPU w INT8. Używa detekcji języka i mowy oraz przeszukiwania wiązkowego o szerokości 5. Tesseract odczytuje tekst w `pol+eng` partiami. Krótkie i przypadkowe rozpoznania odrzuca filtr długości, spójności i pewności odczytu. Krótkie oznaczenia finansowe zachowuje odrębna reguła wysokiej pewności.
6. **Decyzja i dowody.** Sprawdzamy kierowanie do polskich odbiorców, temat, promocję i formę rekomendacji. Polskojęzyczna zapowiedź zagranicznego filmu sama nie zmienia jego zakresu. Materiał spoza polskiego rynku jest pomijany, a sygnał **Nie interesuje mnie** dotyczy treści pozafinansowych. Publiczna zachęta do kupna bitcoina może trafić do przeglądu bez automatycznego przypisania do M3. Status firmy i polskiego oddziału wymaga potwierdzenia. Raport zestawia transkrypcję, OCR i opis w osobnych sekcjach.
7. **Priorytet i rating.** M2 wymaga powiązania adresu profilu `/rolki?autor=...` z lokalną kartoteką w `/entities`. M1 obejmuje sygnały promocji spoza potwierdzonego profilu firmy i wymaga ustalenia relacji. M3 sprawdza związek między konkretną dyspozycją dotyczącą instrumentu a sytuacją odbiorcy. Przy firmie analizator wykorzystuje zestaw kryteriów UKNF i oznacza kontrole wymagające człowieka. Rating przelicza średnią priorytetów (niski 1, średni 2, wysoki 3) na skalę 0–100 i pokazuje liczebność. Osobne role obejmują firmy, twórców i autopromocję. Nazwy znalezione w treści bez potwierdzenia w kartotece są wyraźnie oznaczone.

Wizualnie feed korzysta z własnego układu odtwarzacza i kolorów SWRI. Z Taste Skill zastosowano kontrast, spójną hierarchię oraz rzeczywiste media. Z ECC zastosowano rozdział odpowiedzialności, czytelne kontrakty wejścia i testy regresji.

## Zakres oceny regulacyjnej

- [Rozporządzenie delegowane (UE) 2017/565, art. 9 i 44](https://eur-lex.europa.eu/eli/reg_del/2017/565/oj/?locale=pl) daje podstawę do rozróżnienia rekomendacji osobistej oraz do oceny sposobu przedstawienia korzyści, ryzyka i informacji nadzorczych w komunikacji objętych podmiotów.
- [Ustawa o obrocie instrumentami finansowymi, art. 2, 3 i 76](https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20051831538) oraz temat 3 wyzwania określają zakres przesłanek doradztwa inwestycyjnego. Dopasowanie w lokalnej kartotece wymaga weryfikacji w [rejestrach KNF](https://www.knf.gov.pl/podmioty/Podmioty_rynku_kapitalowego/Firmy_inwestycyjne_i_Agenci_firm_inwestycyjnych).
- [ESMA o rekomendacjach publicznych w mediach społecznościowych](https://www.esma.europa.eu/press-news/esma-news/requirements-when-posting-investments-recommendations-social-media) opisuje odrębny zakres MAR. Ręczna ocena obejmuje m.in. identyfikację, źródła i konflikty interesów. Priorytet sprawy wskazuje, co sprawdzić i nie przesądza o naruszeniu.

Reguły tekstowe nie obejmują pełnej interpretacji prawnej, obrazu bez tekstu ani kontekstu poza rolką. Brak znalezionego ostrzeżenia oznacza brak odczytu w dostępnych dowodach. Próbkowanie może pominąć krótkie komunikaty, ASR może przekręcać słowa, a ranking po 1–2 obserwacjach nie pozwala ocenić skuteczności strategii.

## Materiały startowe i pomiar

Import opcjonalny tworzy rolki z fragmentów polskojęzycznych nagrań Wolnych Lektur. Pokazuje przebieg autentycznego nagrania i podaje autorstwo oraz źródło. Źródła i zasady wykorzystania: [Stepy akermańskie](https://wolnelektury.pl/katalog/lektura/sonety-krymskie-stepy-akermanskie/), [Ptasie radio](https://wolnelektury.pl/katalog/lektura/tuwim-ptasie-radio/), [zasady Wolnych Lektur](https://wolnelektury.pl/info/zasady-wykorzystania/).

Poniższe wcześniejsze próbki są zachowane w lokalnych danych i dostępne pod dotychczasowymi linkami. Nie są wyświetlane w bieżącym feedzie.

- [Jak działają ETF-y, Tagesschau (ARD)](https://commons.wikimedia.org/wiki/File:Gut_zu_wissen,_Wie_funktionieren_ETFs%3F_-_Tagesschau.webm), CC BY-SA 4.0, transkodowano.
- [Zwiastun Big Buck Bunny, Blender Foundation](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/video), CC BY 3.0, transkodowano.
- [Apollo 11, archiwum NASA](https://images.nasa.gov/details/as11-40-5903), [warunki NASA](https://www.nasa.gov/nasa-brand-center/images-and-media/), zmieniono format zapisu.

Testy w `tests/test_reels.py` sprawdzają źródła dowodów, połączenie kanałów, fałszywe alarmy na neutralnych treściach, braki danych, rozdział profili i uczenie strategii. Test strategii ma znane wyniki sygnałów i powtarza próbę dla różnych najlepszych reakcji. Rzeczywisty feed służy do pomiaru czasu przetworzenia oraz inspekcji raportów. Trzy materiały bez reklam nie są próbą do oszacowania wykrywalności rzeczywistych naruszeń.

Pomiary wcześniejszego zestawu z 21 listopada 2026 na Windows 11, i7-1360P, CPU-only. Czas liczono od pobrania pojedynczej rolki do zapisu decyzji, bez oczekiwania na nowe publikacje.

| Materiał | Długość | Czas analizy | Decyzja |
|---|---:|---:|---|
| Big Buck Bunny | 33 s | 14,67 s | Odrzucona |
| Jak działają ETF-y? | 59 s | 59,86 s | Finanse bez promocji |
| Apollo 11 | Zdjęcie | 0,85 s | Odrzucona |

Średnia po zmianie OCR wyniosła 25,13 s na rolkę wobec 37,09 s przed zmianą. To pojedyncze sesje z tym samym zestawem, przy zmiennym obciążeniu komputera. W kontrolowanym teście UCB każda reakcja była optymalna w osobnej symulacji. W 100 próbach strategia wybrała reakcję optymalną 82 razy w każdym scenariuszu. W rzeczywistym feedzie odnotowano tylko jedną obserwację dla UCB, za mało do porównania reakcji.

Ponowna analiza testowej rolki inwestycyjnej (24,23 s) na tym samym komputerze zajęła 78,16 s. Samo rozpoznanie mowy zajęło 26,83 s dla medium z `beam_size=5` i 19,59 s dla base z `beam_size=1`. Medium uchwycił przekaz o promocji brokera, bonusie i Bitcoinie. Wynik skierowano do weryfikacji jako M1 ze średnim ryzykiem. Dokładna nazwa brokera i kod wymagają odsłuchu. Po zmianie filtrów OCR kontrolne zdjęcie Apollo 11 dało zero fragmentów tekstu.

## Możliwy późniejszy hosting

Obecnie uruchamiaj na `127.0.0.1`. SQLite WAL i osobne pliki pozwalają przenieść lokalną instalację na inny komputer przez kopię katalogu danych wykonaną przy zatrzymanej aplikacji. Do udostępnienia online architektura przewiduje osobne API odtwarzania i panel analityka, uwierzytelnianie publikacji i panelu, bazę PostgreSQL oraz magazyn plików z obsługą żądań zakresowych. Skaner może pozostać w prywatnej sieci obok platformy. Publiczny hosting wymaga dodania tych warstw i jawnego skonfigurowania dozwolonego źródła.

## Dane i podgląd sesji

Pliki baz pozostają na komputerze w `data/reels/platform.sqlite3` i `data/reel-scan/scan.sqlite3`. Wynik należy do sesji, a data zapisu jest przypisana do każdego raportu. Migracja zachowuje stare raporty. Tekst dowodów znajduje się w tabeli `scan_lines`, natomiast metadane i powody w `scan_reports` odwołują się do tych wierszy. JSON nadal służy do wymiany danych przez API.

Zakończoną sesję można otworzyć lub pobrać przez **Historię analiz lokalnych**. Statyczny HTML zawiera datę i godzinę, tytuły, kategorie, decyzje i uzasadnienia. Można go hostować niezależnie od aplikacji. Do osobnego repozytorium GitHub Pages trafia wyłącznie eksport w pliku `index.html`. Reset w aplikacji zmienia lokalny widok. Wyeksportowany lub opublikowany HTML stanowi niezależną kopię.
