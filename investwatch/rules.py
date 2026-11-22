"""Screening controls mapped to the UKNF resource. No legal determinations."""
from statistics import median
import re

from .analysis import DISCLOSURE, has, matches_name

GAIN = r"\bzysk(?:|i|ów|u|iem)\b|zarobi\w*|stop\w* zwrotu|\d+\s*zł\w*\s*bonus\w*|(?:wzroś\w*|wzro[nś]\w*) (?:o|do) \d"
RISK = r"ryzyk\w*|możesz stracić|utrata kapitału|risk of loss|you (?:may|can) lose"
SPECIFIC_RISK = r"moż\w* stracić|utrat\w* kapitału|ujemn\w* stop\w*|can lose|may lose"
GUARANTEE = r"\b(?:gwarantowan\w* zysk\w*|gwarancj\w* zysk\w*|zarobisz bez ryzyka|zysk bez ryzyka|guaranteed profit\w*)\b"
HISTORY = (r"wynik\w* historyczn\w*|przeszł\w* wynik\w*|(?:w zeszłym roku|w \d{4}(?: roku)?|"
           r"w ostatnich \w+ latach).{0,65}(?:\d+\s*(?:%|procent)|stop\w* zwrotu)")
SUPERVISOR = r"\bKNF\b|organ\w* nadzoru"
PAST_WARNING = r"nie (?:stanowi\w*|jest|są) (?:wiarygodn\w*|pewn\w*) (?:wskaźnik\w*|miernik\w*)|nie gwarantuj\w*.{0,30}przyszł\w* wynik\w*"
PREDICTION = (r"(?:nasza|moja|moj[ea]|przewiduj\w*|prognozuj\w*)\s+(?:prognoz\w*|[\w ]{0,40}(?:wzrost|spadek|zysk))|"
              r"prognoz\w* (?:cen\w*|stop\w* zwrotu|wynik\w*)|przewiduj\w*|"
              r"\b(?:będzie|będą) (?:kosztowa\w*|wart\w*|droższ\w*|tańsz\w*)\b|"
              r"\b(?:uzyskasz|uzyskacie|osiągniesz|osiągniecie|zarobisz|zarobicie|zarobimy)\b.{0,55}"
              r"(?:\bzysk\w*|\bstop\w* zwrotu|\d+\s*(?:%|procent|zł))|"
              r"\b(?:wzrośnie|wzrosną|spadnie|spadną|podrożeje|podrożeją|sięgnie|osiągnie|osiągną|zyska|zyskają|straci|stracą)\b")
PRIORITY_WEIGHTS = {"R01": 25, "R02": 45, "R03": 65, "R04": 40, "R05": 45,
                    "R06": 55, "R07": 45, "R08": 25, "R09": 30, "R10": 45,
                    "R11": 45, "R12A": 45, "R12B": 45, "R13": 35, "R14": 60,
                    "R15": 60, "R16": 45, "R17": 85, "R18": 85}
ABSENCE_BASED = {"R01", "R02", "R03", "R11", "R12A", "R12B", "R14", "R15", "R16"}
SOURCE = r"\bźródł\w*|\bna podstawie danych\b|\bdane (?:GPW|NBP|Bloomberg)\b"
HIDDEN = r"\bprzypis\w*|\bsekcj\w* legal\b|\bmał\w* druk\w*"
CLICK = r"\b(?:kliknij|rozwiń|link w bio|link w opisie|otwórz szczegóły)\b"
FORECAST_WARNING = r"(?:prognoz\w*|przewidywa\w*).{0,85}(?:nie (?:jest|są|stanowi\w*|gwarantuj\w*)|brak gwarancji)"
COMPARISON = r"\b(?:lepsz\w*|tańsz\w*|droższ\w*|bezpieczniejsz\w*)\s+(?:niż|od)\b|\bw porównaniu\b|\bprzewyższ\w*"
COMPARED_SERVICE = r"\b(?:inwestycj\w*|broker\w*|makler\w*|platform\w*|fundusz\w*|rachun\w*|ofert\w*)\b"
SUPERLATIVE = (rf"\bnaj(?:lepsz|tańsz|bezpieczniejsz)\w*\s+(?:\w+\s+){{0,2}}{COMPARED_SERVICE}|"
               rf"{COMPARED_SERVICE}.{{0,45}}\bnaj(?:lepsz|tańsz|bezpieczniejsz)\w*\b")
JARGON = r"\b(?:depozyt zabezpieczający|margin call|dźwignia|stop.?out|drawdown|zmienność implikowana)\b"
DEFINITIONS = (
    ("R01", "Oficjalna nazwa firmy", "2 lit. a", "", "nazwa rejestrowa i treść"),
    ("R02", "Oznaczenie reklamy", "MiFID", "", "pełny materiał i opis"),
    ("R03", "Ryzyko obok korzyści", "2 lit. b", GAIN, "sąsiedztwo czasowe i znaczeniowe"),
    ("R04", "Rozmiar czcionki", "2 lit. c", RISK, "porównywalne klatki i rozmiar tekstu"),
    ("R05", "Ekspozycja i kontrast", "2 lit. c i e", RISK, "klatki i czas wyświetlania"),
    ("R06", "Ukrywanie ryzyka", "2 lit. e", RISK, "klatki i kontekst przypisów"),
    ("R07", "Dostęp za kliknięciem", "2 lit. b i e", RISK, "interakcja z publikacją"),
    ("R08", "Responsywność", "2 lit. g", "", "rendery na różnych ekranach"),
    ("R09", "Zrozumiałość", "2 lit. d", RISK, "ostrzeżenie i grupa docelowa"),
    ("R10", "Spójność języka", "2 lit. f", RISK, "język ostrzeżenia i głównego przekazu"),
    ("R11", "Porównania produktów", "3", f"(?:{COMPARISON}|{SUPERLATIVE})", "źródła i założenia"),
    ("R12A", "Okres i źródło wyników", "4", HISTORY, "źródło, 5 lat i pełne okresy 12-miesięczne"),
    ("R12B", "Koszty i waluty", "4", HISTORY, "waluta, opłaty, prowizje i obciążenia"),
    ("R13", "Dominacja wyników", "4 lit. a", HISTORY, "pełna kompozycja materiału"),
    ("R14", "Ostrzeżenie historyczne", "4 lit. d", HISTORY, "wynik i zastrzeżenie dotyczące przyszłości"),
    ("R15", "Prognozy przyszłych wyników", "6", PREDICTION, "prognoza i zastrzeżenie"),
    ("R16", "Informacja podatkowa", "7", r"podat\w*|ulg\w* podatkow\w*", "sytuacja klienta i zmiana przepisów"),
    ("R17", "Sugerowanie aprobaty organu", "8", SUPERVISOR, "związek organu z aprobatą produktu"),
    ("R18", "Nadzór jako argument bezpieczeństwa", "8", SUPERVISOR, "związek nadzoru z bezpieczeństwem"),
)


def catalog():
    return [{"rule_id": key, "title": title, "legal_basis": (
              "art. 24 ust. 3 MiFID II" if law == "MiFID"
              else f"art. 44 ust. {law} rozporządzenia delegowanego 2017/565"),
             "trigger": trigger or "materiał promocyjny", "required_media": requirement,
             "priority_weight": PRIORITY_WEIGHTS[key]}
            for key, title, law, trigger, requirement in DEFINITIONS]


def context_hits(rows, pattern):
    """Find whole lines and phrases split across adjacent lines of the same channel."""
    hits = {index for index, row in enumerate(rows) if has(pattern, row["quote"])}
    previous = {}
    for index, row in enumerate(rows):
        prior = previous.get(row["kind"])
        previous[row["kind"]] = index
        if prior is None or row["start_ms"] is None or rows[prior]["start_ms"] is None:
            continue
        other = rows[prior]
        gap = row["start_ms"] - (other["end_ms"] or other["start_ms"])
        if gap > 3000:
            continue
        left = other["quote"]
        merged = left + " " + row["quote"]
        if any(match.start() < len(left) < match.end() for match in re.finditer(pattern, merged, re.I)):
            hits.update((prior, index))
    return [row for index, row in enumerate(rows) if index in hits]


def priority_level(score):
    return "HIGH" if score >= 75 else "MEDIUM" if score >= 40 else "LOW" if score else None


def responsive_height(row):
    width, height = row["frame_size"]
    line = row["bbox"][3]
    # Representative local player boxes for 360px, 768px and 1440px viewports.
    modes = {"telefon": (320, 440), "tablet": (407, 575), "komputer": (432, 608)}
    return {device: round(line * min(w / width, h / height), 1) for device, (w, h) in modes.items()}


def exposure_of_history(rows, history):
    compared = []
    for row in history:
        peers = [other["bbox"][3] for other in rows if other.get("bbox") and other not in history
                 and other.get("frame_sha256") == row.get("frame_sha256")]
        if peers and row.get("bbox"):
            compared.append({**row, "relative_text_height": round(row["bbox"][3] / median(peers), 2)})
    return compared


def evaluate(meta, rows, result, progress=None):
    official = "M2" in result["modules"]
    auxiliary = "M1" in result["modules"]
    scope = "M2" if official else "M1_AUXILIARY" if auxiliary else (
        "INVESTMENT_SCREENING" if result.get("screening") else "OUTSIDE_SCOPE")
    promotional = result.get("promotion", official or auxiliary)
    partial = result.get("partial", False)
    warning_rows = [row for row in context_hits(rows, RISK)
                    if not has(r"\bbez ryzyka\b|\bnie ma ryzyka\b", row["quote"])]
    claims = result.get("claim_rows", rows)
    gains = context_hits(claims, GAIN)
    screen_warnings = [row for row in warning_rows if row.get("bbox") and row.get("frame_size")]
    evaluations = []
    for index, (definition, (_, _, _, trigger, _)) in enumerate(zip(catalog(), DEFINITIONS), 1):
        key = definition["rule_id"]
        evidence = (result["predictions"] if key == "R15" and "predictions" in result else gains if key == "R03"
                    else context_hits(claims if key in {"R11", "R12A", "R12B", "R13", "R14", "R16", "R17", "R18"}
                                      else rows, trigger) if trigger else [])
        status, why = "UNASSESSED", "Brak dowodów wymaganych do oceny w dostępnej próbce."
        against = []
        guarantee = False
        if scope == "OUTSIDE_SCOPE":
            status, why = "NOT_APPLICABLE", "Brak przesłanek przypisania do M1 lub M2."
        elif (key == "R01" and not (promotional or official)) or (key == "R02" and not promotional):
            status, why = "NOT_APPLICABLE", "Brak przesłanek zastosowania kryterium do tej publikacji."
        elif key == "R01":
            evidence = [row for row in rows if any(matches_name(entity["name"], row["quote"])
                        for entity in result["financial_entities"])]
            if evidence:
                status, why = "PASS", "W dostępnym materiale odczytano nazwę z lokalnej kartoteki."
            else:
                status, why = "NEEDS_REVIEW", "Zweryfikuj pełną nazwę firmy i jej status."
                evidence = result.get("promotion_evidence", [])
        elif key == "R02":
            evidence = [row for row in context_hits(rows, DISCLOSURE + r"|^reklama\s*[.!]?$|współpraca sponsorowana")
                        if not has(r"nie (?:jest|był\w*) .{0,18}(?:reklam\w*|sponsorowan\w*)|cytat z reklamy", row["quote"])]
            status, why = (("PASS", "Odczytano oznaczenie promocyjne.") if evidence else
                           ("NEEDS_REVIEW", "Oznaczenia nie znaleziono w dostępnej próbce."))
            if not evidence:
                evidence = result.get("promotion_evidence", [])
        elif key == "R03" and evidence:
            def nearby(gain, risk):
                if risk is gain:
                    return True
                a, b = gain["start_ms"], risk["start_ms"]
                if a is None and b is None:
                    return gain["kind"] == risk["kind"]
                return (a is not None and b is not None and b <= (gain["end_ms"] or a) + 3000
                        and (risk["end_ms"] or b) >= a - 3000)
            against = [row for row in warning_rows if any(nearby(gain, row) for gain in evidence)]
            missing = [gain for gain in evidence if not any(nearby(gain, warning) for warning in against)]
            specific = [row for row in against if has(SPECIFIC_RISK, row["quote"])]
            status = "POTENTIAL_ISSUE" if missing else "NEEDS_REVIEW"
            why = ("Przy co najmniej jednej obietnicy korzyści nie odczytano ostrzeżenia." if missing else
                   "Odczytano możliwe ostrzeżenie obok korzyści. Sprawdź związek znaczeniowy.")
            if not missing and all(any(nearby(gain, row) for row in specific) for gain in evidence):
                status, why = "PASS", "Odczytano konkretne ostrzeżenie w pobliżu twierdzenia o korzyści."
            guarantees = context_hits(claims, GUARANTEE)
            if guarantees:
                guarantee = True
                status, why = "POTENTIAL_ISSUE", "Wykryto obietnicę gwarantowanego zysku lub zysku bez ryzyka."
                evidence = guarantees
            elif missing:
                evidence = missing
        elif key == "R04" and warning_rows:
            evidence = warning_rows
            for warning in [row for row in warning_rows if row.get("bbox")]:
                peers = [row["bbox"][3] for row in rows
                         if row.get("frame_sha256") == warning.get("frame_sha256")
                         and row.get("bbox") and not has(RISK, row["quote"])]
                if peers:
                    ratio = warning["bbox"][3] / median(peers)
                    against.append({**warning, "relative_text_height": round(ratio, 3)})
            if against:
                status = ("POTENTIAL_ISSUE" if any(row["relative_text_height"] < 0.9 for row in against)
                          else "NEEDS_REVIEW" if any(row["relative_text_height"] < 1 for row in against) else "PASS")
                why = "Porównano wysokość linii OCR na klatce; proporcja jest przybliżona."
            else:
                why = "Brak porównywalnego tekstu w klatce ostrzeżenia."
        elif key == "R05":
            evidence = screen_warnings
            measured = [row for row in evidence if row.get("luminance_span") is not None]
            weak = [row for row in measured if row["luminance_span"] < 40]
            if weak:
                evidence = weak
                status, why = "NEEDS_REVIEW", "W obszarze ostrzeżenia jest mała różnica jasności. Sprawdź kontrast i nakładki w klatce."
            elif measured:
                why = "Zmierzono różnicę jasności. Pełna ocena ekspozycji i przysłonięcia wymaga obejrzenia klatek."
            else:
                why = "Brak odczytanego ostrzeżenia na klatce do pomiaru kontrastu i położenia."
        elif key == "R08":
            evidence = [{**row, "responsive_css_px": responsive_height(row)} for row in screen_warnings]
            small = [row for row in evidence if min(row["responsive_css_px"].values()) < 12]
            if small:
                evidence = small
                status, why = "NEEDS_REVIEW", "Symulacja lokalnego odtwarzacza wskazuje tekst poniżej 12 px na co najmniej jednym ekranie."
            elif evidence:
                status, why = "PASS", "W próbie lokalnego odtwarzacza tekst osiąga co najmniej 12 px na trzech ekranach. Nakładki wymagają osobnej oceny."
            else:
                why = "Brak rozpoznanego pola tekstu ostrzeżenia do symulacji ekranów."
        elif key in {"R17", "R18"} and evidence:
            phrase = (r"zatwierdz\w*|aprob\w*|polec\w*|akcept\w*" if key == "R17"
                      else r"bezpiecz\w*|gwarant\w*|bez ryzyka")
            linked = context_hits(claims, f"(?:{SUPERVISOR}).{{0,75}}(?:{phrase})|(?:{phrase}).{{0,75}}(?:{SUPERVISOR})")
            evidence = [row for row in linked if not has(r"nie (?:zatwierdz\w*|polec\w*|oznacza|gwarant\w*)", row["quote"])]
            if evidence:
                status, why = "POTENTIAL_ISSUE", "Wzmianka o organie występuje w tej samej wypowiedzi."
        elif key in {"R14", "R15"} and evidence:
            against = context_hits(rows, PAST_WARNING if key == "R14" else FORECAST_WARNING)
            status, why = (("NEEDS_REVIEW", "Odczytano zastrzeżenie. Zweryfikuj jego wyrazistość i związek z wynikami.")
                           if against else ("POTENTIAL_ISSUE", "Nie odczytano zastrzeżenia o przyszłych wynikach."))
        elif key == "R16" and evidence:
            situations = context_hits(rows, r"indywidualn\w* sytuacj\w*")
            changes = context_hits(rows, r"zmian\w* przepis\w*|moż\w* (?:ulec zmianie|się zmienić)")
            against = [*situations, *changes]
            status, why = (("PASS", "Odczytano zależność od sytuacji klienta i możliwość zmian.")
                           if situations and changes else ("POTENTIAL_ISSUE", "Nie odczytano obu zastrzeżeń podatkowych."))
        elif key in {"R06", "R07"} and evidence:
            marker = HIDDEN if key == "R06" else CLICK
            linked = context_hits(rows, f"(?:{RISK}).{{0,55}}(?:{marker})|(?:{marker}).{{0,55}}(?:{RISK})")
            if linked:
                evidence = linked
                status, why = "POTENTIAL_ISSUE", ("Treść odsyła do przypisu lub sekcji Legal."
                                                 if key == "R06" else "Po informację o ryzyku materiał kieruje do innej warstwy.")
            elif key == "R06":
                low = [row for row in screen_warnings if row["bbox"][1] >= row["frame_size"][1] * .85
                       and row["bbox"][3] < row["frame_size"][1] * .035]
                if low:
                    evidence = low
                    status, why = "NEEDS_REVIEW", "Małe ostrzeżenie znajduje się przy dolnej krawędzi. Sprawdź, czy nie jest ukryte w przypisie."
                else:
                    why = "Sprawdzono odesłania i położenie odczytanego tekstu. Pełna widoczność wymaga obejrzenia klatki."
            elif result.get("screening") and any(row["kind"] == "DESCRIPTION" or row in screen_warnings for row in warning_rows):
                evidence = [row for row in warning_rows if row["kind"] == "DESCRIPTION" or row in screen_warnings]
                status, why = "PASS", "Odczytano ostrzeżenie bezpośrednio w klatce lub w widocznym opisie lokalnej rolki."
        elif key == "R10" and evidence:
            main_polish = any(row["kind"] == "ASR" and row.get("language") == "pl" for row in rows)
            foreign = [row for row in evidence if row["kind"] != "ASR" and
                       has(r"risk of loss|you (?:may|can) lose", row["quote"]) and not has(r"ryzyk\w*", row["quote"])]
            if main_polish and foreign:
                evidence = foreign
                against = context_hits(rows, r"moż\w* stracić|utrat\w* kapitału|ujemn\w* stop\w*")
                status, why = ("NEEDS_REVIEW" if against else "POTENTIAL_ISSUE",
                               "Odczytano angielskie ostrzeżenie w materiale z polską ścieżką mowy.")
            elif main_polish and any(has(SPECIFIC_RISK, row["quote"]) for row in warning_rows):
                status, why = "PASS", "Konkretny komunikat o stracie jest po polsku, tak jak rozpoznana ścieżka mowy."
        elif key == "R11" and evidence:
            sources = context_hits(rows, SOURCE)
            fields = context_hits(rows, r"\bzałoż\w*|\bprzy (?:tej samej|jednakow\w*)")
            against = [*sources, *fields]
            if sources and fields:
                status, why = "NEEDS_REVIEW", "Wskazano źródło i założenia. Sprawdź porównywalność produktów."
            elif not context_hits(claims, COMPARISON):
                status, why = "NEEDS_REVIEW", "Wykryto nieuzasadnione w próbce twierdzenie o przewadze. Sprawdź, czy stanowi porównanie produktów lub usług."
            else:
                status, why = "POTENTIAL_ISSUE", "Nie odczytano źródła lub założeń porównania."
        elif key == "R12A" and evidence:
            sources = context_hits(rows, SOURCE)
            periods = context_hits(rows, r"\b(?:5|pięciu|pięć) lat\b|\b\d{4}\s*[-–]\s*\d{4}\b|\bza okres\b")
            full_cycles = context_hits(rows, r"\bpełn\w* (?:okres\w* )?(?:12.miesięczn\w*|lat\w*|lata)\b")
            against = [*sources, *periods, *full_cycles]
            if not sources or not periods:
                status, why = "POTENTIAL_ISSUE", "Nie odczytano źródła lub okresu referencyjnego danych historycznych."
            elif not full_cycles:
                status, why = "NEEDS_REVIEW", "Odczytano źródło i okres. Zweryfikuj komplet pełnych okresów dwunastomiesięcznych i okres dostępności produktu."
            else:
                status, why = "NEEDS_REVIEW", "Odczytano źródło i deklarację pełnych okresów. Zweryfikuj zakres w danych źródłowych."
        elif key == "R12B" and evidence:
            currency = [row for row in evidence if has(r"\b(?:USD|EUR|GBP|dolar\w*|euro)\b", row["quote"])]
            fx = context_hits(rows, r"zmian\w* kurs\w*|ryzyk\w* walutow\w*")
            fees = context_hits(rows, r"\b(?:prowizj\w*|opłat\w*|obciąż\w*)\b")
            against = [*fx, *fees]
            if currency and not fx:
                status, why = "POTENTIAL_ISSUE", "Nie odczytano ostrzeżenia kursowego przy wyniku w obcej walucie."
            elif any(has(r"\bbrutto\b", row["quote"]) for row in evidence) and not fees:
                status, why = "POTENTIAL_ISSUE", "Przy wyniku brutto nie odczytano wpływu opłat ani prowizji."
            else:
                status, why = "NEEDS_REVIEW", "Sprawdź wpływ opłat i waluty na prezentowane wyniki."
        elif key == "R09" and warning_rows:
            evidence = warning_rows
            complex_rows = [row for row in warning_rows if has(JARGON, row["quote"]) or len(row["quote"].split()) > 32]
            if complex_rows:
                evidence = complex_rows
                status, why = "NEEDS_REVIEW", "Ostrzeżenie zawiera żargon lub rozbudowane zdanie. Zweryfikuj zrozumiałość dla odbiorcy."
            elif any(has(SPECIFIC_RISK, row["quote"]) for row in evidence):
                status, why = "PASS", "Odczytano prosty, bezpośredni komunikat o możliwości straty."
        elif key == "R13" and evidence:
            against = exposure_of_history(rows, evidence)
            if any(row["relative_text_height"] > 1.5 for row in against):
                status, why = "NEEDS_REVIEW", "Tekst wyników jest wyraźnie większy od innych elementów na tej samej klatce."
            else:
                why = "Sprawdzono wysokości tekstu, gdy były porównywalne. Dominacja w kompozycji całego materiału wymaga oceny klatek."
        needs_warning = key in {"R04", "R05", "R06", "R07", "R08", "R09", "R10"} and bool(gains)
        if status == "UNASSESSED" and not evidence and key not in {"R07", "R08"} and not needs_warning:
            if partial:
                why = "Nie znaleziono przesłanki w dostępnych kanałach. Niepełna ekstrakcja wymaga ponownej kontroli."
            else:
                status, why = "NOT_APPLICABLE", "Brak przesłanki po przeszukaniu dostępnej mowy, tekstu na ekranie i opisu."
        if partial and key in ABSENCE_BASED and status == "POTENTIAL_ISSUE" and not guarantee:
            status, why = "NEEDS_REVIEW", why + " Co najmniej jeden kanał pozostał nieprzebadany."
        weight = 85 if guarantee else definition["priority_weight"]
        points = weight if status == "POTENTIAL_ISSUE" else min(15, max(5, weight // 3)) if status == "NEEDS_REVIEW" else 0
        evaluations.append({**definition, "status": status, "scope": scope, "why": why, "method": "Reguły lokalne",
                            "points": points, "url": meta["url"], "evidence": evidence, "counter_evidence": against,
                            "uncertainty": "Ocena ograniczona do zebranych dowodów.",
                            "human_review_required": status in {"NEEDS_REVIEW", "POTENTIAL_ISSUE", "UNASSESSED"}})
        if progress:
            progress(index, len(DEFINITIONS))
    return evaluations
