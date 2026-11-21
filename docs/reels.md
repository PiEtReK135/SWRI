# Rolki i skaner InvestWatch

## Użycie

- `/rolki` odtwarza filmy z dźwiękiem i zdjęcia. Feed obsługuje przewijanie, strzałki na klawiaturze i przyciski nawigacji. **Dodaj rolkę** zapisuje plik, autora, temat i opis.
- `/skanowanie?start=1` automatycznie rozpoczyna sesję. Skaner kończy po 18 sekundach bez nowych materiałów lub po 200 rolkach. Przycisk **Zatrzymaj** kończy bieżącą analizę i zamyka sesję. Można rozpocząć kolejną sesję z nowym profilem.
- `/#analiza` pokazuje materiały do sprawdzenia, posortowane według priorytetu. **Informacje szczegółowe** obejmują też neutralne treści finansowe, odrzucone rolki oraz analizy wymagające ponowienia. Dostępny jest raport JSON.

## Przepływ danych

1. **Publikacja.** Platforma przyjmuje MP4, WebM, MOV, JPEG, PNG oraz WebP. FFmpeg sprawdza i zapisuje filmy jako MP4 z dźwiękiem oraz zdjęcia jako JPEG. Metadane, reakcje i komentarze są w `data/reels/platform.sqlite3`, pliki w `data/reels/media/`.
2. **Rekomendacje.** Platforma gromadzi sygnały widza osobno dla każdej rolki. Obejrzenie liczy się jako udział rzeczywiście odtworzonych fragmentów, polubienie jako +1, zapis +3, komentarz +2, skopiowanie linku +2, a pełne obejrzenie +2. Tematy obserwowane przez widza dostają wyższy wynik. Sygnał **Nie interesuje mnie** ukrywa rolkę dla danego widza i obniża preferencję jej tematu o 3. Kolejność uwzględnia także zbiorczą aktywność i datę publikacji.
3. **Odkrywanie.** Skaner zaczyna z nowym profilem i pobiera po jednej rolce przez ten sam interfejs HTTP co feed. Używa wyłącznie adresu pętli zwrotnej. Temat przypisany przez wydawcę służy platformie do rekomendacji. Skaner ocenia materiał na podstawie treści.
4. **Strategia.** UCB rozdziela obserwacje pomiędzy przewinięcie, krótszy seans, dłuższy seans i zapis. Za trafienie liczy kolejną poleconą rolkę, jeśli analiza potwierdzi temat finansowy. Wybór bierze pod uwagę średnią trafień i liczbę prób każdej strategii. Symulowane obejrzenia i zapisy skanera zmieniają tylko jego profil. Skaner nie dodaje komentarzy ani publicznych reakcji.
5. **Ekstrakcja.** Opis wydawcy jest analizowany w całości. Ścieżkę audio odczytuje lokalny faster-whisper base CPU INT8. Tesseract odczytuje tekst w `pol+eng`. Dla filmu FFmpeg wycina klatki w jednej operacji, od co sekundy do co dziewięć sekund, zależnie od długości. Dodatkowe klatki są pobierane na początku wypowiedzi. Tesseract analizuje cały zestaw klatek w jednym wywołaniu. Komentarze widzów wpływają na rekomendacje i są oddzielone od dowodów o treści publikacji.
6. **Decyzja i dowody.** Algorytm łączy kanały i rozróżnia promocję, treść finansową bez promocji, treść spoza zakresu i materiał niedostatecznie rozpoznany. Pozytywne przesłanki promocji lub spersonalizowanego zalecenia wymagają sprawdzenia. Jedynie po decyzji **Odrzucona** skaner wysyła **Nie interesuje mnie**. Wyniki, czas, profil i powody są w `data/reel-scan/scan.sqlite3`. Klatki dowodowe mają oddzielny katalog.
7. **Priorytet i rating.** M2 wymaga powiązania adresu profilu `/rolki?autor=...` z lokalną kartoteką w `/entities`. M1 obejmuje sygnały promocji spoza potwierdzonego profilu firmy i wymaga ustalenia relacji. M3 sprawdza związek między konkretną dyspozycją dotyczącą instrumentu a sytuacją odbiorcy. Przy firmie analizator wykorzystuje zestaw kryteriów UKNF i oznacza kontrole wymagające człowieka. Rating przelicza średnią priorytetów (niski 1, średni 2, wysoki 3) na skalę 0–100 i pokazuje liczebność. Osobne role obejmują firmy, twórców i autopromocję. Nazwy znalezione w treści bez potwierdzenia w kartotece są wyraźnie oznaczone.

Wizualnie feed korzysta z własnego układu odtwarzacza i kolorów SWRI. Z Taste Skill zastosowano kontrast, spójną hierarchię oraz rzeczywiste media. Z ECC zastosowano rozdział odpowiedzialności, czytelne kontrakty wejścia i testy regresji.

## Zakres oceny regulacyjnej

- [Rozporządzenie delegowane (UE) 2017/565, art. 9 i 44](https://eur-lex.europa.eu/eli/reg_del/2017/565/oj/?locale=pl) daje podstawę do rozróżnienia rekomendacji osobistej oraz do oceny sposobu przedstawienia korzyści, ryzyka i informacji nadzorczych w komunikacji objętych podmiotów.
- [Ustawa o obrocie instrumentami finansowymi, art. 2, 3 i 76](https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20051831538) oraz temat 3 wyzwania określają zakres przesłanek doradztwa inwestycyjnego. Dopasowanie w lokalnej kartotece wymaga weryfikacji w [rejestrach KNF](https://www.knf.gov.pl/podmioty/Podmioty_rynku_kapitalowego/Firmy_inwestycyjne_i_Agenci_firm_inwestycyjnych).
- [ESMA o rekomendacjach publicznych w mediach społecznościowych](https://www.esma.europa.eu/press-news/esma-news/requirements-when-posting-investments-recommendations-social-media) opisuje odrębny zakres MAR. Ręczna ocena obejmuje m.in. identyfikację, źródła i konflikty interesów. Priorytet sprawy wskazuje, co sprawdzić i nie przesądza o naruszeniu.

Reguły tekstowe nie obejmują pełnej interpretacji prawnej, obrazu bez tekstu ani kontekstu poza rolką. Brak znalezionego ostrzeżenia oznacza brak odczytu w dostępnych dowodach. Próbkowanie może pominąć krótkie komunikaty, ASR może przekręcać słowa, a ranking po 1–2 obserwacjach nie pozwala ocenić skuteczności strategii.

## Materiały startowe i pomiar

Import opcjonalny pobiera źródła niezależnie opublikowane przed powstaniem skanera. Baza skanera nie zawiera ich oczekiwanych etykiet. Media i wyniki trafiają do ignorowanego katalogu `data`.

- [Jak działają ETF-y, Tagesschau (ARD)](https://commons.wikimedia.org/wiki/File:Gut_zu_wissen,_Wie_funktionieren_ETFs%3F_-_Tagesschau.webm), CC BY-SA 4.0, transkodowano.
- [Zwiastun Big Buck Bunny, Blender Foundation](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/video), CC BY 3.0, transkodowano.
- [Apollo 11, archiwum NASA](https://images.nasa.gov/details/as11-40-5903), [warunki NASA](https://www.nasa.gov/nasa-brand-center/images-and-media/), zmieniono format zapisu.

Testy w `tests/test_reels.py` sprawdzają źródła dowodów, połączenie kanałów, fałszywe alarmy na neutralnych treściach, braki danych, rozdział profili i uczenie strategii. Test strategii ma znane wyniki sygnałów i powtarza próbę dla różnych najlepszych reakcji. Rzeczywisty feed służy do pomiaru czasu przetworzenia oraz inspekcji raportów. Trzy materiały bez reklam nie są próbą do oszacowania wykrywalności rzeczywistych naruszeń.

Pomiary z 21 listopada 2026 na Windows 11, i7-1360P, CPU-only. Czas liczono od pobrania pojedynczej rolki do zapisu decyzji, bez oczekiwania na nowe publikacje.

| Materiał | Długość | Czas analizy | Decyzja |
|---|---:|---:|---|
| Big Buck Bunny | 33 s | 14,67 s | Odrzucona |
| Jak działają ETF-y? | 59 s | 59,86 s | Finanse bez promocji |
| Apollo 11 | Zdjęcie | 0,85 s | Odrzucona |

Średnia po zmianie OCR wyniosła 25,13 s na rolkę wobec 37,09 s przed zmianą. To pojedyncze sesje z tym samym zestawem, przy zmiennym obciążeniu komputera. W kontrolowanym teście UCB każda reakcja była optymalna w osobnej symulacji. W 100 próbach strategia wybrała reakcję optymalną 82 razy w każdym scenariuszu. W rzeczywistym feedzie odnotowano tylko jedną obserwację dla UCB, za mało do porównania reakcji.

## Możliwy późniejszy hosting

Obecnie uruchamiaj na `127.0.0.1`. SQLite WAL i osobne pliki pozwalają przenieść lokalną instalację na inny komputer przez kopię katalogu danych wykonaną przy zatrzymanej aplikacji. Do udostępnienia online architektura przewiduje osobne API odtwarzania i panel analityka, uwierzytelnianie publikacji i panelu, bazę PostgreSQL oraz magazyn plików z obsługą żądań zakresowych. Skaner może pozostać w prywatnej sieci obok platformy. Publiczny hosting wymaga dodania tych warstw i jawnego skonfigurowania dozwolonego źródła.
