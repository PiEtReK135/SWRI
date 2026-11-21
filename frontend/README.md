# XYZ · HackNation 2026

Strona informacyjna w Angularze 21 dla dwóch modułów wyzwania InvestWatch. Przedstawia monitoring reklam publikowanych przez podmioty trzecie, ocenę informacji o ryzyku i planowany podział pracy agentów. Przycisk „Otwórz panel” prowadzi do panelu InvestWatch udostępnianego przez backend.

## Uruchomienie

Wymagany Node.js 24 LTS (obsługiwane są też wersje wskazane w `package.json`).

```sh
npm ci
npm start
```

Serwer `http://localhost:4200` służy do pracy nad samą stroną. Polecenie `npm run build` zapisuje kompilację w `dist/`. Kompletną aplikację uruchom z katalogu repozytorium przez `.\start.ps1 -SiteDir .\frontend\dist`.

Ekran demonstracyjny pod `/admin/login` i panel pod `/dashboard` są dostępne lokalnie bez uwierzytelniania.

## Struktura kodu

- `src/app/app.html` — sekcje strony, nawigacja kotwicowa i schemat modułów.
- `src/app/project-modules.ts` — opisy obu modułów i planowanych wyników.
- `src/app/review-criteria.ts` — kryteria z materiału „Zasób dla uczestników” pogrupowane w cztery planowane obszary oceny.
- `src/app/app.css` i `src/styles.css` — układ, paleta i style globalne.

Założenia wizualne oparto na [Taste Skill](https://github.com/Leonxlnx/taste-skill), a organizację kodu na zasadach [ECC Coding Standards](https://github.com/affaan-m/ECC/tree/main/skills/coding-standards).
