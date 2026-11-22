# Monitoring rynku

Na Windowsie po aktualizacji uruchom z katalogu repozytorium:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd --prefix frontend run build
.\start.ps1 -SiteDir .\frontend\dist
```

Otwórz [panel analityczny](http://127.0.0.1:8000/analiza). Istniejące importy i eksport CSV są na `/dashboard`. Skaner i symulowany feed działają jak wcześniej pod `/skanowanie` i `/rolki`.

## Pozyskiwanie

Kolejka transakcyjna SQLite pobiera skonfigurowane źródła w jednym procesie. W panelu **Źródła i kolejka** widać postęp, błędy i liczbę zwróconych rekordów. Kolejne uruchomienie aktualizuje datę obserwacji i ponownie analizuje zmianę treści lub kartoteki. Rekordy są deduplikowane wg źródła, typu i identyfikatora. Jeśli platforma zwróci 429, zadania dla niej czekają co najmniej tyle, ile wynika z limitu i nagłówka `Retry-After`. 401, 403 i odmowa `robots.txt` zatrzymują zadanie.

- **Meta Ad Library** obejmuje płatne kampanie docierające do Polski. Facebook i Instagram są filtrami opartymi na metadanych kampanii. Ustaw w środowisku Windows `IW_META_AD_LIBRARY_TOKEN` z zatwierdzonym dostępem. [Ads Archive](https://developers.facebook.com/docs/graph-api/reference/ads_archive/)
- **TikTok Commercial Content API** obsługuje osobno płatne kampanie docierające do Polski i zgłoszone współprace twórców z Polski. Ustaw `IW_TIKTOK_COMMERCIAL_TOKEN` z zakresem `research.adlib.basic`. Wartość wymaga odnowienia po wygaśnięciu zgodnie z procedurą TikToka. Źródło współprac może nie zwrócić opisu, audio ani klatek. [Query Ads](https://developers.tiktok.com/docs/en/commercial-content-api-query-ads) · [Query Commercial Content](https://developers.tiktok.com/docs/en/commercial-content-api-query-commercial-content)
- **WWW** czyta publiczny HTML z listy konfiguracji, m.in. strony ofert i usług. Przy pobieraniu respektuje `robots.txt`, używa identyfikowalnego User-Agent, ogranicza liczbę stron, nie podąża za przekierowaniami i odrzuca adresy wewnętrzne oraz domeny głównych platform społecznościowych. Poproś organizację o jawny, uprawniony punkt wejścia w razie blokady lub dynamicznej witryny. Kolektor nie stosuje rotacji adresów IP ani tożsamości do kontynuowania pobierania po blokadzie.

Status **Skonfigurowane** wskazuje, że SWRI odczytał token. Dostęp potwierdza zakończone zapytanie do API. W błędach Meta kolejka zapisuje numeryczny kod i podkod bez treści odpowiedzi. `META_190_463` oznacza wygaśnięcie tokenu, a `META_10` lub `META_200` wskazują brak uprawnienia. [Kody błędów Graph API](https://developers.facebook.com/docs/graph-api/guides/error-handling)

Umieść plik `data/discovery/sources.json` albo podaj jego ścieżkę przez `IW_DISCOVERY_CONFIG`. Zastosuj zmiany przez ponowne uruchomienie. Poniżej przykład z jedną stroną i wykonywaniem ręcznym:

```json
{
  "terms": ["rachunek maklerski", "inwestowanie", "doradztwo inwestycyjne"],
  "tiktok_creators": [],
  "tiktok_video_hosts": [],
  "websites": [{"url": "https://www.xtb.com/pl", "publisher": "XTB S.A.", "pages": 1}],
  "days": 30,
  "api_pages": 2,
  "meta_version": "v27.0",
  "scheduled": false,
  "interval_minutes": 360
}
```

Opcjonalny `link_prefix` pozwala śledzić odnośniki w tej samej domenie i w zadanej sekcji. Ustaw `scheduled: true`, żeby działający proces dodawał zadania co `interval_minutes`. Termin harmonogramu jest zapisany w bazie. Po wznowieniu procesu niewykonane zadanie wraca do kolejki. W bezpośrednich wywołaniach platform działa tylko zakres oficjalnie udostępniony. Rozpoznawanie nieoznaczonych współprac na pełnym feedzie działa w symulacji. Organiczną rolkę z uzyskanym uprawnieniem można nadal zgłosić ręcznie przez `/dashboard`.

Jeśli zatwierdzony dostęp TikToka zezwala na zapis i analizę materiałów, wpisz dokładne nazwy zatwierdzonych hostów CDN w `tiktok_video_hosts`. Kolektor analizuje jeden udostępniony wariant wideo na kampanię. Pusta lista oznacza same metadane. Adresy tymczasowe z podpisem nie trafiają do bazy ani raportu.

## Moduły i kalibracja

W kartotece KNF dodaj zweryfikowaną firmę, warianty nazwy, formę działalności w Polsce i oficjalną witrynę lub identyfikator konta. Dla kampanii można wpisać `META:<page_id>` lub `TIKTOK:<business_id>`. Pełną nazwę, formę działalności i zakres usług sprawdź w oficjalnym rejestrze. Sama nazwa konta może być skopiowana. [Rejestr firm inwestycyjnych KNF](https://www.knf.gov.pl/podmioty/Podmioty_rynku_kapitalowego/Firmy_inwestycyjne_i_Agenci_firm_inwestycyjnych)

| Moduł | Przesłanki | Dane w karcie |
| --- | --- | --- |
| M1 | Polski przekaz promocyjny osoby trzeciej i dopasowanie do firmy z kartoteki, w tym potwierdzona działalność transgraniczna | Firma, publikujący, typ promocji, treść i dokładny URL. Przy współpracy bez tekstu panel wskazuje potrzebę uzupełnienia danych. |
| M2 | Materiał marketingowy przypisany do potwierdzonego kanału firmy krajowej lub oddziału w Polsce | 19 reguł UKNF, treść, dostępne pomiary i liczba kryteriów wymagających uwagi. Nieocenione kryteria wskazują brak odpowiedniego dowodu. |
| M3 | Oferta spersonalizowanej rekomendacji transakcji na instrumencie lub sygnał takiej rekomendacji wymagający potwierdzenia usługi | Podmiot, oferta, cytaty, URL i status weryfikacji zakresu zezwolenia. Ogólnodostępne komentarze rynkowe są traktowane jako osobny typ treści. [Art. 9 rozporządzenia 2017/565](https://eur-lex.europa.eu/eli/reg_del/2017/565/oj) |

Kolektor normalizuje tekst i przygotowuje wektory leksykalne do wiązania podobnych materiałów dotyczących tej samej firmy. Powiązania są wskazówką nawigacyjną. Analizator używa istniejącego Qwen3.5-2B Q4 w llama.cpp z regułami UKNF. Po dołączeniu autoryzowanego pliku wybiera również Whisper (preferowane `medium` CPU INT8) i Tesseract. Zapis dowodów rozróżnia opis, mowę, OCR i dane, których brak. Przy samym HTML lub metadanych panel nie wyprowadza wniosku o rozmiarze, kontrastach ani o braku ostrzeżenia w pełnej publikacji.

Lista sortuje według najsilniejszego udokumentowanego sygnału. Wysoki priorytet ma wagę od 75, średni od 40, niski od 1. Licznik kryteriów M2 jest niezależny od tego priorytetu. Próg selekcji 0–100 jest zapisywany w bazie. Zmienia listę przy włączonym filtrze oraz wykres 14-dniowy. TP, FP, FN i TN powstają wyłącznie z materiałów ocenionych ręcznie jako `Potwierdzono sygnał` lub `Odrzucone`. Alerty nowych wysokich priorytetów w danych rzeczywistych są nadawane WebSocketem, z sekwencją do wznowienia po rozłączeniu.

## Dane lokalne

- `data/discovery/discovery.sqlite3` zawiera kolejkę, źródła, aktualną treść, ocenę, decyzje i alerty.
- `data/discovery/objects/` zawiera wyłącznie dołączone, znormalizowane pliki. Kluczem jest SHA-256. Klatki dowodowe są w `data/discovery/evidence/`.
- Dane symulacji pozostają w `data/reels/` i `data/reel-scan/`. Reset skanera ukrywa jego dotychczasowe wyniki w widoku symulacji.
- `data/investwatch.sqlite3` zachowuje kartotekę KNF i dotychczasowy panel importu.

Dostęp lokalny po `127.0.0.1` wykorzystuje systemową kontrolę dostępu do komputera. Identyfikator analityka jest polem dziennika decyzji. Zmienne API ustawiaj w środowisku uruchomieniowym, poza repozytorium. Plik `.env.example` jest przykładem nazw zmiennych.

## Scenariusze i podgląd online

Skrypt `scripts/seed_module_examples.py` publikuje autorskie materiały ćwiczeniowe w istniejącym lokalnym feedzie i tworzy raporty przy użyciu skanera. Na Windowsie wykorzystuje FFmpeg, Tesseract i głos Microsoft Paulina dla trzech klipów. Instalacja `requirements-dev.txt` udostępnia używany przez skrypt klient HTTP. Scenariusze pozostają w trybie **Symulacja**. Ich raporty można ponownie wygenerować po resecie skanera.

`scripts/build_public_snapshot.py` tworzy `docs/online/snapshot.json` z zakończonych analiz. Do migawki trafiają wybrane publiczne witryny i autorskie scenariusze SWRI. Podgląd wyświetla pierwszy zapis, ostatnie pozyskanie lub zakończenie analizy w strefie Europe/Warsaw. Są to czasy zapisane w SQLite.

Z katalogu głównego repozytorium zbuduj publiczny wariant interfejsu.

```powershell
npm.cmd --prefix frontend run build -- --configuration published --base-href /swri-preview/ --output-path ../data/validation/pages-build
```

Przenieś pliki kompilacji i `docs/online/snapshot.json` do katalogu głównego repozytorium `PiEtReK135/swri-preview`, z którego GitHub Pages serwuje podgląd. Zachowaj plik `.nojekyll` i przekierowanie pod `monitoring/`. [Podgląd na GitHub Pages](https://pietrek135.github.io/swri-preview/)
