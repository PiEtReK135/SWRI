# InvestWatch

Lokalny prototyp do przeglądu organicznych filmów i identyfikacji potencjalnej promocji finansowej. Dowody i decyzje operatora są zapisywane w SQLite WAL. Raport zawiera cytaty, klatki, znaczniki czasu oraz zakres przebadanych danych.

## Szybki start na Windows 11

Wymagany jest Node.js 24 LTS z npm. Z katalogu repozytorium wykonaj w PowerShell poniższe polecenia. Instalator używa WinGet do przygotowania Python 3.12, FFmpeg i Tesseract oraz zapisuje pakiety OCR pol/eng i model ASR w `data`.

```powershell
.\setup.ps1
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
.\start.ps1 -SiteDir .\frontend\dist
```

Otwórz `http://127.0.0.1:8000` i wybierz **Otwórz panel**. W sekcji **Discovery** wybierz **Wczytaj filmy demo**. W wierszu **Jesienna wędrówka** wybierz cytat przy 00:18, obejrzyj oś czasu i wyeksportuj raport. Pozostałe przykłady pokazują materiał oficjalny (M2), ofertę doradztwa (M3) i promocję widoczną tylko w OCR.

Własny materiał można przesłać jako plik wideo lub audio i opcjonalne napisy SRT/VTT/TXT. Limit klipu to 300 s i 150 MB. Napisy z pozycjami czasowymi są źródłem cytatów. Przy niepełnych napisach i dostępnym audio pracownik próbuje użyć lokalnego ASR.

Jeśli pobieranie modelu jest niedostępne, użyj `setup.ps1 -SkipModels`. Napisy i OCR działają lokalnie po zakończeniu instalacji. Aby przygotować dodatkowo Ollama i Qwen, uruchom `setup.ps1 -WithOllama`, następnie `.\start.ps1 -WithOllama -SiteDir .\frontend\dist`.

Jeśli npm zgłasza `UNABLE_TO_VERIFY_LEAF_SIGNATURE`, ustaw w tym oknie PowerShell `$env:NODE_OPTIONS = "--use-system-ca"` i ponów `npm.cmd --prefix frontend ci`.

### Strona projektu pod wspólnym adresem

Po restarcie uruchom z katalogu repozytorium `.\start.ps1 -SiteDir .\frontend\dist`. Po zmianie źródeł Angulara ponownie wykonaj `npm.cmd --prefix frontend run build`.

Pod jednym adresem lokalnym działają strona SWRI pod `/`, panel InvestWatch pod `/dashboard` i API, m.in. `/health`, `/content` i `/reports/{id}`. Trasa `/admin/login` pokazuje demonstracyjny formularz. Panel i API są dostępne bez uwierzytelniania, a serwer nasłuchuje na `127.0.0.1`.

Parametr `-SiteDir` przyjmuje katalog gotowej kompilacji z plikiem `index.html`. Polecenie `.\start.ps1` bez tego parametru otwiera sam panel pod `/`.

### Rolki i lokalny skaner

Na stronie głównej wybierz **Otwórz feed rolek**, a następnie **Dodaj rolkę**, aby opublikować własny film lub zdjęcie. Przycisk **Przejdź do skanowania internetu** otwiera osobną kartę i automatycznie rozpoczyna skan feedu SWRI. Wyniki aktualizują się na stronie głównej w sekcji **Raporty**. Wszystkie decyzje są w zakładce **Informacje szczegółowe**.

Opcjonalnie zaimportuj publicznie dostępne materiały startowe, gdy aplikacja już działa:

```powershell
node.exe scripts/import_reel_samples.mjs
```

Import pobiera wskazane materiały ze źródeł wydawców i zapisuje je lokalnie. Sam skaner korzysta z lokalnego API feedu. [Architektura, algorytmy, źródła i wariant hostingu](docs/reels.md).

### Opcjonalne lokalne modele

```powershell
$env:IW_WHISPER_MODEL = "C:\models\faster-whisper-base"
.\start.ps1 -WithASR -SiteDir .\frontend\dist
```

Ścieżka musi zawierać wcześniej pozyskany model CTranslate2 faster-whisper. Analiza używa CPU INT8, czterech wątków i trybu offline. Jeżeli uruchomiono Ollama na porcie 11434 i model jest dostępny lokalnie, ustaw `$env:IW_OLLAMA_MODEL = "qwen3:1.7b"` przed uruchomieniem aplikacji. Model może wskazać istniejące cytaty do ponownego sprawdzenia. Klasyfikacja i ostateczna ocena pozostają niezależne od jego wyboru.

### Compose

```sh
docker compose up --build
```

Panel jest dostępny pod tym samym adresem. Dane są w wolumenie `investwatch-data`. Aby użyć ASR w kontenerze, umieść model w `/data/models/whisper-base` w wolumenie. Aplikację uruchamiaj z jednym procesem Uvicorn i utrzymuj port dostępny lokalnie. Panel nie ma uwierzytelniania.

### Testy

```sh
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m unittest discover -v
python -m pip_audit
npm --prefix frontend ci
npm --prefix frontend run build
```

Testy integracyjne wymagają FFmpeg, Tesseract i czcionki obsługiwanej przez FFmpeg. Zależności Angulara są zapisane w `frontend/package-lock.json`. [Wyniki testów](docs/validation.md) · [Śledzenie wymagań](docs/requirements_traceability.md) · [Prezentacja](docs/InvestWatch-demo.pdf)

## Źródła i interpretacja

Discovery obejmuje ręczną kolejkę URL, import CSV/JSON, plan zapytań z szerokimi tematami i listy obserwacyjne. Polski rejestr jest kartoteką uzupełnianą przez operatora z podaniem źródła i daty, przez `POST /entities`. Dokumentacja kontraktów API jest dostępna pod `/docs`. Po imporcie samego URL system prosi o uzupełnienie dowodów. Ponowienie lokalne analizuje zapisane materiały, a okresowy recheck przypomina o ręcznej weryfikacji URL i rejestru. Integracje TikTok i Instagram mają stan `NOT_APPROVED`.

Reguły M2 dotyczą udokumentowanych pierwszostronnych publikacji firm objętych zakresem. W M1 reguły ryzyka są sygnałami pomocniczymi. W M3 wykryte przesłanki indywidualnej rekomendacji wymagają oceny operatora. Priorytet 0–100 służy do kalibracji alertów, a wynik lokalnego dopasowania firmy nie rozstrzyga o zezwoleniu.
