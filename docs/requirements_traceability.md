# Śledzenie wymagań UKNF

Źródła oryginalne są w [requirements](requirements/). Treść załączników tematów 1 i 2 zawiera te same definicje i odnośniki do rejestrów. Definicje zastosowano w różnych zakresach zależnie od tematu.

| Źródło i wymaganie | Implementacja | Weryfikacja lub luka |
|---|---|---|
| Opis UKNF i temat 1 – treść organiczna, promujący, lokalizacja, firma, recheck | `media.py`, `analysis.py`, `store.py`, `monitor.py` i oś czasu | Test MP4+SRT i demo OCR-only. Firmę łączą aliasy operatora. Aktualizacja stanu URL przez ręczną obserwację. |
| Temat 2 – reklamy wprost od firm | `analysis.screen`, kartoteka profili z datą i źródłem, `rules.evaluate` | Demo M2 i M1 z regułami pomocniczymi. Brak automatycznego importu KNF. |
| Kryteria ryzyka R01–R18, w tym R12A/B | `rules.DEFINITIONS` i wyniki per raport | Test kompletu 19 pozycji, R17 i R08; R07/R08 bez materiału interaktywnego pozostają nieocenione. R04/R05/R06/R09–R13 zaznaczają przesłanki do ręcznych pomiarów. |
| Temat 3 – indywidualna rekomendacja oparta na potrzebach i sytuacji klienta | `analysis.screen` stosuje sygnał sytuacji klienta, typ instrumentu i działanie na nim | Demo M3 i porównanie z edukacją ogólną. Kwalifikacja instrumentu i uprawnień jest ręczna. |
| Opis UKNF – agregacja, trwałe zadania, raporty i powiadomienia | SQLite WAL, audyt, JSON/HTML/CSV, SSE, progi i status operatora | Test restartu, źródeł, zmiany progu i zapisu sprawy. Anulować można zadania oczekujące. |
| Opis UKNF – pozyskiwanie danych | Lokalny import, metadane CSV/JSON, plany ręcznego discovery, listy obserwacyjne i demo | Import URL i blokada CAPTCHA testowane. Brak zatwierdzonego dostępu dla API platform i automatycznej obserwacji feedu. |
| Specyfikacja – lokalne AI i kontrola zasobów | FFmpeg, Tesseract, opcjonalne Whisper INT8 i druga ocena z Ollama | Testy OCR i pracy bez AI. Whisper i Ollama wymagają lokalnych modeli; faktyczne wyniki w raporcie walidacji. |
| Opis UKNF – prototyp UI i wdrożenie | Panel HTML/JS, start PowerShell, Compose | UI bez zależności npm. Panel pokazuje trend alertów. Odrębny frontend React pozostaje poza dostarczonym zakresem. |
