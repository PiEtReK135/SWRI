# SWRI / InvestWatch

## Quick Start

Na Windowsie 11 zainstaluj Node.js 24 z npm. Poniższe polecenia wykonaj w PowerShell z katalogu repozytorium.

```powershell
.\setup.ps1
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
.\scripts\prepare_reel_llm.ps1
.\start.ps1 -SiteDir .\frontend\dist
```

Otwórz [lokalną stronę SWRI](http://127.0.0.1:8000/). Wybierz **Otwórz feed rolek**, dodaj materiał i wybierz **Przeanalizuj tę rolkę**. Zapisane wyniki znajdziesz w [panelu analitycznym](http://127.0.0.1:8000/analiza).

Przy kolejnym uruchomieniu wystarczy ostatnie polecenie. Po pobraniu zależności i modeli lokalny feed oraz skaner działają offline.

## Wymagania

- **Sprzęt** — sprawdzona konfiguracja to Intel Core i7-1360P i 16 GB RAM. Analiza działa na CPU.
- **Dysk** — zalecane 8 GB wolnego miejsca na instalację i modele oraz dodatkowe miejsce na materiały.
- **Oprogramowanie** — Windows 11, PowerShell i Node.js 24 z npm. Skrypt `setup.ps1` używa WinGet, by doinstalować brakujące składniki (Python 3.12, FFmpeg z ffprobe i Tesseract). Przygotowuje też OCR po polsku i angielsku.

## Konfiguracja usług

| Usługa | Ustawienie |
| --- | --- |
| Analiza lokalna | Instalator pobiera Whisper medium. Skrypt `prepare_reel_llm.ps1` przygotowuje Qwen3.5-2B i llama.cpp. Ścieżkę do własnego modelu Whisper można ustawić w `IW_WHISPER_MODEL`. |
| Katalog danych | Domyślnie `data/`. Własną ścieżkę ustaw w `IW_DATA` przed instalacją modeli i startem. |
| Kolektor WWW | Dodaj witryny w `data/discovery/sources.json`. Inną ścieżkę do konfiguracji można podać w `IW_DISCOVERY_CONFIG`. |
| Meta Ad Library | Ustaw `IW_META_AD_LIBRARY_TOKEN` z zatwierdzonym dostępem do Ad Library API. Źródło obsługuje kampanie Meta z metadanymi Facebooka i Instagrama. |
| TikTok Commercial Content API | Ustaw `IW_TIKTOK_COMMERCIAL_TOKEN` z zatwierdzonym zakresem `research.adlib.basic`. |

Zmienne ustaw w tym samym oknie PowerShell przed startem, np. `$env:IW_DISCOVERY_CONFIG = 'C:\SWRI\sources.json'`. Tokeny przechowuj poza repozytorium.

[Przykład konfiguracji kolektorów](docs/discovery.md#pozyskiwanie) · [Konfiguracja skanera i modeli](docs/reels.md)
