# INVESTWATCH SOCIAL DISCOVERY & EVIDENCE
## Prompt wykonawczy dla Codexa — zwykłe filmy, ukryta promocja finansowa, i7-1360P / 16 GB RAM

> Skopiuj od sekcji „ROLA I CEL” do Codexa w katalogu projektu. Załącz do repozytorium oryginalne pliki wyzwania w `docs/requirements/`, jeżeli są dostępne. Zadanie dotyczy UKNF, nie KAS. Poniższa specyfikacja dotyczy lokalnego MVP na 18 godzin pracy dwóch osób.

---

# ROLA I CEL

Jesteś głównym inżynierem realizującym MVP „InvestWatch Social Discovery & Evidence” w ramach wyzwania Urzędu Komisji Nadzoru Finansowego (UKNF), HackNation 2026. Wykonaj realną implementację w bieżącym repozytorium: kod, konfigurację, testy, README, działające demo i raport z rzeczywiście uruchomionych testów. Nie kończ na projekcie architektury. Nie deklaruj funkcjonalności, które są atrapami.

**Główna funkcja:** wykrywanie potencjalnie ukrytej promocji usług/instrumentów finansowych w *zwykłych organicznych filmach* (TikTok, Instagram Reels, inne krótkie wideo), a NIE wyłącznie w reklamach zakupionych w systemie reklamowym Meta. Film podróżniczy, lifestyle'owy, poradnikowy czy komediowy też może zawierać kilkusekundową promocję. Opis i hashtag bez słów finansowych nie wystarczają do odrzucenia filmu: sygnał może pojawić się tylko w mowie, napisach lub grafice.

Podstawą są pięć załączników UKNF: główny opis InvestWatch, załącznik tematu 1, załącznik tematu 2, załącznik tematu 3 oraz „kryteria oceny informacji o ryzyku” z 18 numerowanymi regułami (w tym 12a i 12b). Jeśli dokumenty są w `docs/requirements/`, przeczytaj wszystkie w całości, a na końcu utwórz `docs/requirements_traceability.md` mapujący wymagania na implementację/testy. Jeśli ich nie ma, użyj poniższej specyfikacji i zgłoś brak — nie udawaj ponownej lektury.

## KRYTYCZNE ROZRÓŻNIENIE ZAKRESU UKNF

**M1 — Finfluencerzy i podmioty trzecie:** wykrywaj promowanie firm inwestycyjnych oraz ich instrumentów i usług przez osoby prywatne/podmioty trzecie. Uwzględnij polskojęzyczną promocję zagranicznych firm działających transgranicznie w Polsce. Raport musi łączyć firmę, promującego, dokładną treść i URL oraz umożliwiać późniejszą aktualizację.

**M2 — Informacje o ryzyku:** zgodnie z zadaniem dotyczy *materiałów publikowanych bezpośrednio przez objęte zakresem firmy inwestycyjne*. Tu stosuje się właściwe testy poprawności informacji o ryzyku. Gdy podobną nieprawidłowość zauważysz w filmie niezależnego twórcy, zapisz ją jako pomocniczy sygnał M1, a nie automatycznie jako naruszenie M2.

**M3 — Shadow Advisory:** wykrywanie ofert mogących wskazywać na usługę doradztwa inwestycyjnego bez właściwego uprawnienia. Ogólna edukacja, publiczny komentarz rynkowy lub wzmianka o akcjach nie stanowi automatycznie indywidualnego doradztwa. Przy analizie uwzględniaj potrzeby i sytuację klienta oraz charakter rekomendacji dotyczącej konkretnych instrumentów. Brak dopasowania do lokalnej bazy rejestrowej NIE jest dowodem braku zezwolenia.

**Nie myl „kryptoreklamy” (ukrytej promocji) z „kryptowalutami”.** Przedmiotem są usługi finansowe/instrumenty zgodne z definicjami załączników. Materiały o kryptowalutach mogą być kandydatami do analizy, ale sam temat krypto nie dowodzi podlegania określonej regule ani nieautoryzowanego doradztwa. Status kwalifikacji prawnej produktu ma być osobną, weryfikowaną kategorią.

Nigdy nie oznaczaj automatycznie osoby jako „łamiącej prawo”, „oszusta” ani firmy jako „nieautoryzowanej”. W użytecznych polach stosuj: `POTENTIAL_ISSUE`, `NEEDS_REVIEW`, `NO_EVIDENCE`, `UNASSESSED`, `NOT_APPLICABLE`, `VERIFIED_FACT`. Pozostaw ostateczne rozstrzygnięcie operatorowi.

---

# 1. SPRZĘT I OPERACYJNE OGRANICZENIA

- Windows 11, Intel Core i7-1360P, 16 GB RAM, brak dedykowanego GPU NVIDIA.
- Lokalne modele open source; zero płatnych API AI; offline demo analityczne musi działać bez sieci.
- Preferowany stos: Python 3.11+, FastAPI, SQLAlchemy/SQLite WAL (przyszła migracja do PostgreSQL), React + TypeScript + Vite, Tailwind, Recharts, Pydantic, APScheduler lub lekki planista w procesie, Ollama, faster-whisper, FFmpeg, Tesseract OCR pol+eng.
- Model LLM domyślny Qwen3 1.7B lub porównywalny mały model polskojęzyczny przez Ollama; skonfiguruj tryb bez rozszerzonego rozumowania, jeśli obsługiwany. `temperature=0` dla ekstrakcji, JSON Schema + walidacja.
- Whisper domyślnie `base` + CPU INT8; `small` opcjonalny po zmierzeniu zużycia pamięci i jakości na polskiej mowie. Napisy dostarczone z autoryzowanego źródła preferuj do szybkiej analizy, ale sprawdzaj jakość i pochodzenie.
- Jeden worker zajmujący się ciężkimi zadaniami AI. Nie trzymaj w pamięci jednocześnie wielu dużych modeli. Kolejka sieciowa może działać niezależnie od kolejki CPU. Zwalniaj pamięć i kontroluj liczbę wątków.
- OCR wykonuj na kilku wybranych klatkach (np. co 3–5 sekund, plus w pobliżu wykrytych wypowiedzi i zmian planszy), nie każdej klatce.
- Po uruchomieniu wykonaj benchmark na tym komputerze; wyniki czasów są pomiarami, a nie deklaracjami.
- Docker Compose dla aplikacji/bazy, ale zapewnij też prosty `start.ps1` i możliwość uruchomienia Ollama/ASR na hoście Windows, gdy kontenery obciążają pamięć.

---

# 2. POLITYKA DOSTĘPU DO ŹRÓDEŁ — FUNKCJONALNOŚĆ, NIE OBEJŚCIE

Istotnym problemem jest dostęp do *organicznych filmów*, nie do płatnych reklam. Nie traktuj Meta Ad Library jako głównego źródła discovery. Dopuszczalne drogi:

1. `AuthorizedPublicVideoAPIAdapter`: oficjalne API, jeśli projekt faktycznie ma przyznane uprawnienia (np. TikTok Research API lub odpowiednie Meta Content Library). Sprawdź dokładnie dostępne pola, ograniczenia, warunki pobierania mediów i wymogi środowiska. Implementacja nie może zakładać, że posiadanie tokenu otwiera dostęp do plików wideo.
2. `UserProvidedVideoAdapter`: lokalne MP4/MP3, SRT/VTT/TXT i JSON dostarczone zgodnie z uprawnieniami. To pełnoprawny, działający tryb MVP.
3. `ManualQueueAdapter`: operator podaje publiczny URL filmu, opis, twórcę i opcjonalny autoryzowany plik. System kolejkuje i bada to, co legalnie dostępne; sam URL nie oznacza automatycznie możliwości pobrania wideo.
4. `SearchSeedAdapter`: wyszukiwane hasła i wyniki z usług udostępniających dozwolone metody dostępu; indeksuj tylko dostępne metadane i linki. Nie obiecuj pełnego pokrycia Instagrama/TikToka. Zadbaj o możliwość wczytania listy URL z CSV/JSON.
5. `AuthorizedBrowserAdapter`: rozszerzalny interfejs przyszłej interakcji przeglądarkowej dla źródeł i zakresów, do których użytkownik posiada stosowną zgodę. Dla Instagrama/TikToka domyślnie nie wykonuj nieautoryzowanego automatycznego przewijania, scrapingu, logowania, sztucznego trenowania feedu, polubień ani pobierania mediów.
6. `DemoOrganicFeedAdapter`: lokalny, deterministyczny strumień zwykłych filmów z domieszką ukrytych promocji. Oznaczaj `DEMO` i nie pokazuj ich jako prawdziwych przypadków.

**Kiedy wystąpi CAPTCHA / login / 403 / rate limit:** zatrzymaj konkretne zadanie w `ACTION_REQUIRED` lub `SOURCE_BLOCKED`, wyślij alert w panelu, pokaż przyczynę i ręczną procedurę, nie rozwiązuj CAPTCHA automatycznie, nie rotuj proxy tożsamości ani nie omijaj barier. Nie „przełamuj” blokad.

Planowanie wyszukiwań i autonomiczna analiza powinny działać bez względu na brak uprawnień platformowych. Rzeczywisty automatyczny monitoring organicznych postów będzie funkcją warunkową (`connector_capability=APPROVED`), a nie fikcyjną funkcją demo.

---

# 3. STRATEGIA DISCOVERY: SZUKAJ W ZWYKŁYCH FILMACH, NIE TYLKO FINANSOWYCH

Podziel źródła na cztery kanały:

- `FINANCIAL_TOPICS`: brokerzy, akcje, forex, kontrakty CFD, fundusze, sygnały inwestycyjne, obligacje, platformy, zarządzanie aktywami itd.
- `NON_FINANCIAL_CONTEXT`: lifestyle, podróże, fitness, motoryzacja, edukacja, technologia, biznes, vlogi, rozrywka — tu ukryte reklamy mogą wystąpić bez finansowego opisu.
- `WATCHLIST_CREATORS`: wcześniej zidentyfikowani twórcy, do których monitoring został skonfigurowany na podstawie uprawnionych źródeł i konkretnego uzasadnienia.
- `WATCHLIST_ENTITIES`: oficjalne firmy inwestycyjne, marki handlowe, produkty, aliasy oraz nazwane podmioty wymagające weryfikacji.

Nie próbuj „wymusić” samych finansów na algorytmie polecającym przez botowe interakcje. To zawęża próbkę i nie daje pewności jej reprezentatywności. Utwórz jawny plan zapytań, z historią skuteczności i źródeł, w tym próbkę kontrolną materiałów niezwiązanych tematycznie z finansami. Nie wyciągaj wniosków o całym rynku z jednego feedu.

Przykładowe kategorie słów:
- sygnały bezpośrednie: „broker”, „inwestuję”, „konto maklerskie”, „CFD”, „forex”, „doradca inwestycyjny”, „wealth management”, „rodzinne biuro inwestycyjne”, „portfolio”, „zyski na giełdzie”;
- sygnały pośrednie: „link w bio”, „mój sposób na dodatkowy dochód”, „aplikacja, której używam”, „kod polecający”, „zysk bez wysiłku”, „zarabiam pasywnie”, „dołącz do grupy”, „bez ryzyka”, „gwarantowane wyniki”;
- relacje: nazwy marek z rejestru UKNF, aliasy, linki afiliacyjne, domeny rejestracji, promocje produktów, oznaczenia współpracy;
- negatywne/odróżniające: cytowanie reklamy w celu krytyki, materiał ostrzegawczy, edukacja bez promowania produktu, mem i satyra.

Nie wystarczy wykryć słowo „inwestycja”. Trzeba wykryć **akt promowania**: produkt/usługę + zachętę do skorzystania + ewentualne wskaźniki korzyści/relacji. Pojedynczy kod rabatowy nie dowodzi płatnej współpracy.

## Harmonogram działań (konfigurowalny, tylko dla dozwolonych źródeł)

- `BOOTSTRAP` przy pierwszym uruchomieniu: import rejestru firm, aliasów, listy fraz, przykładowych twórców i zasobów testowych. Cel: stworzyć bazę referencyjną.
- `DISCOVERY_SWEEP` na żądanie lub przykładowo co 30–60 minut w ramach limitów danego źródła: nowe wyniki zapytań/nowe filmy z watchlisty. Cel: odkryć potencjalne organiczne materiały.
- `LIGHT_TRIAGE` natychmiast po pozyskaniu metadanych: tanie reguły i metadane, brak LLM. Cel: zdecydować, co wymaga weryfikacji; nie wyrzucać jednoznacznie nieznanych filmów spoza finansów bez kontroli próbkowej.
- `CAPTION_CHECK` w ciągu kilku sekund po pojawieniu się nowych, autoryzowanych napisów. Cel: szybka analiza tanim kosztem.
- `ASR` tylko gdy są autoryzowane media audio, a napisy są nieobecne, niepewne lub niekompletne. Cel: uzyskać dowody z mowy.
- `OCR` gdy dostępny obraz i kontekst wskazuje na tekst na ekranie, nazwę platformy, link, kod lub ostrzeżenie; przy niskiej pewności analizuj też próbkę kontrolną. Cel: znaleźć sygnały niewypowiedziane w audio.
- `DEEP_REVIEW` tylko po sygnale trafności lub z próby kontrolnej: lokalny LLM + reguły prawne + dopasowanie podmiotów. Cel: ograniczyć koszt CPU.
- `RECHECK` codziennie lub na żądanie dla materiałów oznaczonych jako istotne (w granicach dostępu). Cel: sprawdzić dostępność URL, zmiany opisu i status rejestru; niczego nie ukrywać, jeśli film został usunięty.
- `DAILY_SUMMARY` raz dziennie: liczba zebranych, odfiltrowanych, niezbadanych, alarmów, materiałów wymagających zgody i przypadków oczekujących na ręczną ocenę.

W hackathonowym demo harmonogram można przyspieszyć na lokalnym adapterze do kilku minut, ale w interfejsie oznacz `DEMO_CLOCK`.

---

# 4. ARCHITEKTURA AGENTÓW — KTO / KIEDY / PO CO / CO ZWRACA

Projektuj logiczne agenty, lecz NIE uruchamiaj osobnego LLM dla każdego. Trwała kolejka, kilka reguł deterministycznych i jeden lekki model lokalny.

## A0. `PolicyAndSourceAgent`
Kiedy: przed każdym źródłem i pobraniem danych. Po co: sprawdzić metodę dostępu i ograniczenia. Zwraca: `source_mode`, `rights_status`, `allowed_fields`, `allowed_media`, `permission_note`, `next_action`. Blokuje niedozwolone operacje.

## A1. `DiscoveryPlannerAgent`
Kiedy: BOOTSTRAP, cykliczny discovery, dodanie firmy lub twórcy do watchlisty. Po co: zbudować zapytania zarówno finansowe, jak i szerokie, aby wykrywać kryptoreklamy w vlogach. Zwraca: `query`, `intent`, `source`, `planned_at`, `expected_signal`, `query_version`, `sampling_stratum`.

## A2. `SourceCollectorAgent`
Kiedy: źródło zaakceptowało zapytanie. Po co: zaciągać metadane, URL, dostępne napisy oraz plik tylko przy odpowiednich uprawnieniach. Zwraca: znormalizowany `ContentItem` z pochodzeniem pól i statusami braków.

## A3. `TriageAgent`
Kiedy: po A2 lub imporcie ręcznym. Po co: tanio wykryć potencjalne materiały, bez opierania się tylko na opisie. Zwraca `candidate`, `need_audio`, `need_ocr`, `relevance_signals`, `uncertainty`, `reason_for_skip`, `control_sample`. Dla filmów bez metadanych finansowych włącz możliwość badania losowej/stratyfikowanej próbki, szczególnie gdy audio jest dostępne; losowość z ustalonym seedem.

## A4. `TranscriptAgent`
Kiedy: audio dostępne i analiza wymaga transkrypcji. Po co: wykryć wypowiedzi przemycane w dowolnym fragmencie. Zwraca segmenty `start_ms`, `end_ms`, `text`, `language`, `method`, `model_version`, `quality_notes`. Preferuj dostępne autoryzowane napisy; Whisper INT8 jako uzupełnienie. Nie zmyślaj brakujących słów.

## A5. `VisualEvidenceAgent`
Kiedy: obraz dostępny, występuje tekst, logo, kod, link lub kontrola czytelności. Po co: odzyskać treści niewypowiedziane i ostrzeżenia małą czcionką. Zwraca `frame_time_ms`, `ocr_text`, `bbox`, `relative_font_size_estimate`, `visibility_notes`, `frame_sha256`, `artifact_path`. Szacuj czas wyświetlania na podstawie kolejnych klatek z niepewnością; nie podawaj bezwarunkowego „brak ryzyka”, jeśli skan był rzadki.

## A6. `PromotionAndContextAgent`
Kiedy: po połączeniu opisu, napisów, ASR, OCR, linków i metadanych. Po co: odróżnić wzmiankę, edukację i krytykę od potencjalnej reklamy lub nawoływania do skorzystania. Zwraca `content_intent` (EDUCATION/REVIEW/COMMENTARY/PROMOTION/POSSIBLE_PROMOTION/UNKNOWN), `promotion_cues`, `counter_indicators`, `disclosure`, `calls_to_action`, `affiliate_indicators`, `relation_unverified`, cytaty z timestampami. Nie wnioskuj o faktycznej zapłacie bez dowodu.

## A7. `FinancialEntityAgent`
Kiedy: gdy pojawia się produkt, marka, domena, firma lub osoba doradcza. Po co: oddzielić twórcę, reklamodawcę, markę, operatora usługi i firmę prawną. Zwraca `entity_name`, `type`, `aliases`, `exact_match`, `verified_registry_match`, `registry_url`, `registry_checked_at`, `match_confidence`, `review_needed`. Nie myl marki z podmiotem; brak wyniku nie dowodzi nielegalności.

## A8. `UKNFRouterAgent`
Kiedy: po analizie promocji i podmiotów. Po co: prawidłowo zakwalifikować do M1, M2, M3. Zwraca multi-label z przesłankami, `publisher_relation` (FIRST_PARTY/THIRD_PARTY/UNKNOWN), `why_in_scope`, `why_out_of_scope`, `unknowns`. M2 tylko przy pierwszostronnych materiałach firm objętych definicją; w pozostałych filmach reguły ryzyka jako sygnały pomocnicze M1.

## A9. `RuleEngineAgent`
Kiedy: materiały objęte danym modułem, po wydobyciu dowodów. Po co: uruchomić określone kontrole UKNF, a nie domyślnie wszystkie. Zwraca pełny rejestr reguł z `PASS/POTENTIAL_ISSUE/NEEDS_REVIEW/NOT_APPLICABLE/UNASSESSED/ERROR` oraz dowody i źródła. Reguły na podstawie R01–R18 poniżej.

## A10. `SecondPassVerifierAgent`
Kiedy: wykryty sygnał wysokiego priorytetu, sprzeczne źródła lub niska jakość ASR. Po co: sprawdzić bez ponownego wynajdywania treści, czy cytat faktycznie występuje, reguła ma zastosowanie i nie ma kontrdowodu. Zwraca `CONFIRMED_EVIDENCE`, `CONTRADICTED`, `INSUFFICIENT`, `NEEDS_OPERATOR`, z opisem. Korzysta z tego samego małego LLM tylko dla trudnych przypadków, zaś weryfikacja cytatów jest deterministyczna.

## A11. `EvidenceAndReportAgent`
Kiedy: po zakończeniu analizy lub błędzie z niepełnymi danymi. Po co: stworzyć audytowalny raport bez kategorycznych osądów. Zwraca JSON i HTML z linkiem, cytatami, klatkami, regułami, statusami, wersjami, ścieżkami dowodów oraz historią działań.

## A12. `MonitoringAndHumanReviewAgent`
Kiedy: ważny alert, brak prawa dostępu, błąd, CAPTCHA, niejednoznaczność, zmiana statusu źródła. Po co: skierować czynność do człowieka i nie zatrzymać całego pipeline'u. Zwraca `ACTION_REQUIRED` z dokładnym powodem, sugerowaną ręczną czynnością i `retry_after`, jeżeli właściwe.

---

# 5. REGUŁY ANALIZY Z ZAŁĄCZNIKA UKNF

Implementuj 19 testów o nazwach: R01, R02, R03, R04, R05, R06, R07, R08, R09, R10, R11, R12A, R12B, R13, R14, R15, R16, R17, R18. Załącznik nadaje im numery 1–18, a pozycja 12 jest rozbita na 12a/12b.

- R01 identyfikacja firmy (oficjalna nazwa w materiale).
- R02 oznaczenie reklamy/promocji.
- R03 ryzyko przy potencjalnych zyskach; sprawdzaj bliskość czasową i znaczeniową.
- R04 rozmiar czcionki ostrzeżenia.
- R05 kontrast, przesłonięcie, ekspozycja.
- R06 ukryte ostrzeżenia, przypisy, niska widoczność.
- R07 informacja dostępna dopiero po kliknięciu/rozwinięciu, gdy dowody umożliwiają ocenę.
- R08 responsywność materiału przy różnych ekranach — `UNASSESSED`, gdy brak odpowiednich renderów.
- R09 zrozumiałość ostrzeżeń dla odbiorcy.
- R10 język ostrzeżenia względem materiału.
- R11 porównania produktów i usług, źródło i założenia.
- R12A wyniki historyczne: okres i źródło, wg załącznika ostatnie 5 lat i pełne okresy 12-miesięczne.
- R12B wyniki historyczne: waluty i wpływ kosztów/opłat/prowizji.
- R13 dominacja wyników historycznych w materiale.
- R14 ostrzeżenie, że przeszłe wyniki nie są wiarygodnym wskaźnikiem przyszłych.
- R15 prognozy przyszłych wyników i odpowiednie ostrzeżenie.
- R16 wzmianki podatkowe i zależność od sytuacji klienta oraz zmian przepisów.
- R17 sugestia zatwierdzenia produktu/usługi przez KNF lub inny organ.
- R18 wykorzystywanie nadzoru jako dowodu bezpieczeństwa inwestycji.

Dla każdej reguły przechowuj: oryginalną podstawę prawną z załącznika, trigger, warunki zastosowania, media wymagane do oceny, wynik, cytat/klatkę/URL, przesłanki za i przeciw, informację o niepewności i `human_review_required`.

Nie przepisuj mechanicznie interpretacji prawnej poza zakres załącznika. Nie twórz automatycznych wyroków prawnych. Szczególnie kontroluj błąd: `brak OCR` nie oznacza `brak ostrzeżenia`. Film z częściowo niedostępnym źródłem nigdy nie otrzymuje automatycznego `PASS` we wszystkich regułach.

---

# 6. POMIAR PROMOCJI UKRYTEJ W ZWYKŁYM FILMIE

Zaprojektuj ekstraktor świadectw promocyjnych, szukający:
- nazwy platformy/produktu/usługi w pojedynczym zdaniu w środku niezwiązanego filmu;
- „korzystam z X”, „polecam X”, „załóż konto przez link”, „mój kod”, „partner filmu”, „współpraca”, „zysk miesięczny”;
- linku w bio, kodu polecającego, QR, nazwy domeny;
- prezentowanego na ekranie interfejsu brokera lub logotypu (OCR, jeśli możliwe; rozpoznawanie graficzne jako P2);
- nagłej zmiany tematu na usługi finansowe;
- zestawienia korzyści, wezwania do działania, nazwy firmy oraz odbiorcy w jednym fragmencie;
- braku oznaczenia reklamowego wyłącznie jako *sygnału*, nie pewnego naruszenia;
- alternatywnych wyjaśnień: krytyka, satyra, cytowanie innego twórcy, neutralny news.

Każdy znaleziony sygnał ma wskazywać `evidence_type`, `source_offset`, `exact_quote_or_ocr`, `timestamp`, `speaker_or_screen`, `url`, `context_before`, `context_after`. Jeżeli sygnał powstał ze streszczenia LLM, nie traktuj streszczenia jako bezpośredniego dowodu.

Przed oceną relacji finansowej wyodrębnij:
- wzmianka vs promocja,
- promocja vs płatna współpraca (płatność często nieustalona),
- firma inwestycyjna vs niezweryfikowana marka,
- rekomendacja ogólna vs usługa dopasowana do klienta,
- produktu należący do zakresu instrumentów finansowych vs produkt o nieustalonym statusie.

---

# 7. DANE DO KATALOGU I PÓŹNIEJSZEGO RAPORTU

Zbuduj relacje między `Content`, `Creator`, `Brand`, `LegalEntity`, `FinancialProduct`, `Claim`, `Evidence`, `RuleEvaluation`, `ReviewCase`, `DiscoveryQuery`, `Job`, `AuditEvent`, `SourcePermission`.

**Identyfikacja filmu:** `source_platform`, `source_url`, `platform_post_id`, `published_at`, `collected_at`, `last_verified_at`, `availability_status`, `language`, `duration_seconds`, `caption`, `hashtags`, `content_hash`, `source_method`, `data_rights`, `is_demo`.

**Twórca:** `handle`, `public_profile_url`, `display_name`, `platform_user_id` jeśli dozwolone, `creator_type` (INDIVIDUAL / ENTITY / UNKNOWN), `historical_content_count`, data ostatniej obserwacji. Nie pobieraj zbędnych danych prywatnych.

**Firma/produkt:** dosłowna nazwa, typ instrumentu/usługi, marka, alias, domena, spółka prawna, status rejestrowy i jego źródło, data sprawdzenia, rozdzielenie relacji „wymieniona” od „reklamowana”.

**Dane semantyczne:** dokładne roszczenia (claims), obietnice wyniku, sugestie braku ryzyka, CTA, kod afiliacyjny, zaszyty link, disclosure, możliwa relacja reklamowa, treść usługi doradczej.

**Dane dowodowe:** segmenty mowy z czasem, tekst napisów z pochodzeniem, OCR klatki z bbox, pliki/sha256 jeśli wolno je utrwalać, dokładny URL, data analizy, ograniczenia (np. brak dostępu do bio, niekompletny opis), wszystkie cytaty z weryfikacją względem źródła.

**Wyniki:** M1/M2/M3, zastosowane reguły z wynikami, priorytet triage 0–100 (NIE prawdopodobieństwo naruszenia), jakość dowodów, status ręcznej oceny, przypisany operator, historia decyzji, wersja reguł, model i parametry, ryzyko błędów ASR.

**Raport JSON + HTML + zbiorczy CSV:** topografika dokumentu: kto, co, kiedy, gdzie, jaki fragment, jaka przesłanka, z czym powiązane, jak zweryfikowano, co pozostaje nieustalone, jaka czynność jest rekomendowana. Zachowaj możliwość ponownej aktualizacji i eksportu.

Przykładowy raport demonstracyjny (fikcyjne nazwy, jawnie `is_demo=true`):

```json
{
  "is_demo": true,
  "source_platform": "LOCAL_DEMO_FEED",
  "source_url": "demo://organic/lifestyle-001",
  "creator": {"handle": "@przykladowy_vlog", "relation": "THIRD_PARTY"},
  "content_type": "ORGANIC_VIDEO",
  "promotion_assessment": "POSSIBLE_PROMOTION",
  "disclosure_observed": "NOT_FOUND_IN_AVAILABLE_MATERIAL",
  "modules": ["M1"],
  "financial_entities": [{"name_mentioned": "Przykladowy Broker", "registry_status": "NOT_VERIFIED"}],
  "evidence": [{"kind": "TRANSCRIPT", "start_ms": 18000, "end_ms": 24000, "quote": "Załóż konto z mojego linku, żeby inwestować."}],
  "rule_evaluations": [{"rule_id": "R02", "status": "NEEDS_REVIEW", "why": "Możliwe promowanie usługi, niepotwierdzony charakter współpracy"}],
  "priority_score": 66,
  "legal_conclusion": "NOT_DETERMINED",
  "human_review_required": true
}
```

---

# 8. KONTRAKTY SYSTEMOWE, KOLEJKA, POWIADOMIENIA

Stany zadania: `QUEUED`, `DISCOVERING`, `SOURCE_PENDING`, `ACQUIRED`, `TRIAGED`, `TRANSCRIBING`, `OCR`, `EXTRACTING_CLAIMS`, `ENTITY_RESOLUTION`, `CLASSIFYING`, `RULE_CHECK`, `VERIFYING`, `REPORTING`, `COMPLETED`, `ACTION_REQUIRED`, `RETRY_PENDING`, `FAILED`, `CANCELLED`.

Wymagania:
- zadania trwałe po restarcie;
- deduplikacja przez platforma+ID+wariant, oraz hash pliku;
- idempotentne ponowienia;
- retry z limitem i backoff dla błędów przejściowych, ale NIE po świadomym bloku dostępu;
- limity równoległych tasków, 1 CPU inference worker;
- zapisywanie `reason`, `source_request_id`, wersji promptów i modeli;
- ochrona przed SSRF, path traversal i prompt injection w treściach;
- `ACTION_REQUIRED` z powodem i sugestią działania dla operatora;
- WebSocket lub SSE do dashboardu;
- `threshold` zmienia wyniki do pokazania, a `precision/recall` licz tylko na ręcznie oznaczonej próbce.

API minimum: `POST /import/video`, `POST /import/transcript`, `POST /import/urls`, `POST /discovery/run`, `GET /discovery/queries`, `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/retry`, `POST /jobs/{id}/cancel`, `GET /content`, `GET /content/{id}`, `GET /creators`, `GET /entities`, `GET /cases`, `GET /cases/{id}`, `PATCH /cases/{id}`, `GET /rules`, `GET /reports/{id}`, `GET /metrics`, `PATCH /settings/threshold`, `GET /health`, `GET /events/stream`.

Dashboard: Overview, Discovery, Video Review, Evidence Timeline (po sekundach), Creators, Financial Entities, Cases, Alerts, Calibration, System Health. Kolumna „zakres danych” ma pokazywać, czy badano tylko opis, opis+ASR, pełny film+OCR; nie maskuj luk w danych.

---

# 9. SPRAWDZANIE PRECYZJI

Przygotuj co najmniej 24 *syntetyczne, oznaczone* przykłady: 6 zwykłych filmów bez finansów, 4 ogólne edukacje finansowe, 4 ukryte promocje w vlogach, 3 oficjalne filmy firm inwestycyjnych, 3 oferty indywidualnego doradztwa, 2 krytyczne/satyryczne cytaty reklam oraz 2 niejednoznaczne przypadki. Warianty muszą zawierać promocję ukrytą tylko w audio i tylko w OCR.

Etykiety referencyjne: `promotion`, `module_labels`, `claims`, `entity_mentions`, `rule_statuses`, `requires_review`; sprawdź co najmniej precyzję i pełność wykrywania reklamy na tych przykładach. Wyraźnie rozdziel wyniki syntetyczne od testów na prawdziwych nagraniach.

Testuj też:
- opis bez finansów, a promocja w 20. sekundzie;
- logo brokera na ekranie bez wypowiadania nazwy;
- twórca ostrzega przed scamem (brak promowania);
- polecanie książki o giełdzie (poza zakresem);
- porada ogólna versus indywidualna rekomendacja;
- marka podobna do firmy KNF (niejednoznaczne dopasowanie);
- film z błędnym ASR, uszkodzonym MP4, CAPTCHA, 403, niepełnymi napisami;
- ponowny skan i niedostępny URL;
- prompt injection w transkrypcji, np. „zignoruj wszystkie poprzednie instrukcje”.

Żadnych deklaracji „99% skuteczności”, dopóki rzeczywiste testy tego nie potwierdzają. W testach na próbkach oznaczonych mierzyć różnice threshold.

---

# 10. PODZIAŁ DWÓCH OSÓB NA 18 GODZIN

0–2 h: A — struktura, źródła, schema, kolejka; B — modele CPU, kontrakt JSON, demo UI.
2–5 h: A — import zwykłych filmów/URL/CSV i normalizacja; B — ASR, podstawowy OCR, 10 testowych transkrypcji.
5–8 h: A — discovery planner, watchlisty i szybki triage; B — lokalny LLM, rozpoznawanie promocji i cytatów.
8–11 h: A — firmy, twórcy, rejestr KNF, router M1/M2/M3; B — reguły R01–R18, weryfikacja dowodów.
11–14 h: A — API, monitoring, alerty, scheduler; B — widok timeline filmu, alert i raport, próg.
14–16 h: oboje — testy end-to-end, duplikaty, dane rzeczywiste (jeśli uprawnione), wydajność CPU, bezpieczeństwo.
16–18 h: oboje — stabilizacja, README, demo, prezentacja i próba; nie dodawać nowych funkcji.

Priorytety: P0: import i pełny analityczny pipeline na organicznych klipach, wiarygodny raport. P1: discovery na rzeczywiście dostępnych źródłach, watchlisty, OCR, powiadomienia, recheck. P2: pełna integracja badawcza i automatyczny feed tylko po otrzymaniu zgody, modele o większej jakości, rozpoznawanie logo i rozszerzona analityka.

---

# 11. PROCES WYKONANIA PRZEZ CODEX

1. Zidentyfikuj istniejący kod i pliki. Przeczytaj dokumenty UKNF, jeżeli dostępne.
2. Napisz krótki `IMPLEMENTATION_PLAN.md` z dokładnym priorytetem P0/P1/P2 i kontraktami JSON.
3. Zaimplementuj P0 pionowo: zaimportowany organiczny klip -> transkrypcja/OCR -> sygnał ukrytej promocji -> właściwa klasyfikacja modułu -> reguły -> raport -> dashboard.
4. Uruchom realny test end-to-end na lokalnych fixtures. Jeżeli zależności brakują, wskaż je i napraw, zamiast dopisywać pozorny wynik.
5. Dodaj źródła discovery jako modularne adaptery z jawnym stanem uprawnień. Nie udawaj aktywnego Research API bez autoryzacji.
6. Zaimplementuj dziennik audytowy i limit zasobów CPU/RAM.
7. Dodaj 24 syntetyczne przykłady oraz pomiar precyzji i pełności na oznaczonych przypadkach.
8. Zaimplementuj status operatora, alerty i zmianę progów.
9. Wykonaj `pip-audit` i `npm audit` i zapisz wyniki oraz ewentualne poprawki. Sekrety wyłącznie `.env`, `.env.example` bez sekretów.
10. Przygotuj Docker Compose oraz start na Windows. Instrukcja ma być konkretna i krótka. Pełny pipeline lokalny ma działać bez płatnych usług.
11. Przygotuj prezentację demo: najpierw zwykły vlog, potem promocja wypowiedziana w środku, cytat z 00:18, twórca, firma, źródło, M1 i alert; następnie oficjalny materiał firmy M2, oraz oferta doradztwa M3.
12. Na końcu wypisz faktycznie działające funkcje, benchmark CPU, testy, niedziałające integracje i ograniczenia. Nie podawaj szacunków jako zmierzonych wyników.

**Kryterium ukończenia:** działające demo wykrywa *ukrytą promocję finansową w zwykłym filmie*, wskazuje konkretny fragment dowodowy i prawidłowo kieruje przypadek do M1/M2/M3 zgodnie z dokumentacją UKNF. **ROZPOCZNIJ IMPLEMENTACJĘ.**
