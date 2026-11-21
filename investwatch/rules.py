"""Screening controls mapped to the UKNF resource. No legal determinations."""
from statistics import median

from .analysis import DISCLOSURE, has, matches_name

GAIN = r"zysk\w*|zarobisz|stop\w* zwrotu"
RISK = r"ryzyk\w*|możesz stracić|utrata kapitału|risk of loss"
HISTORY = r"wynik\w* historyczn\w*|zeszł\w* rok\w*|przeszł\w* wynik\w*"
SUPERVISOR = r"\bKNF\b|organ\w* nadzoru"
PAST_WARNING = r"nie (stanowi\w*|jest|są) wiarygodn\w* (wskaźnik\w*|miernik\w*)"
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
    ("R11", "Porównania produktów", "3", r"lepsz\w* niż|tańsz\w* niż|w porównaniu", "źródła i założenia"),
    ("R12A", "Okres i źródło wyników", "4", HISTORY, "źródło, 5 lat i pełne okresy 12-miesięczne"),
    ("R12B", "Koszty i waluty", "4", HISTORY, "waluta, opłaty, prowizje i obciążenia"),
    ("R13", "Dominacja wyników", "4 lit. a", HISTORY, "pełna kompozycja materiału"),
    ("R14", "Ostrzeżenie historyczne", "4 lit. d", HISTORY, "wynik i zastrzeżenie dotyczące przyszłości"),
    ("R15", "Prognozy przyszłych wyników", "6", r"prognoz\w*|przewidywan\w* stop\w* zwrotu", "prognoza i zastrzeżenie"),
    ("R16", "Informacja podatkowa", "7", r"podat\w*|ulg\w* podatkow\w*", "sytuacja klienta i zmiana przepisów"),
    ("R17", "Sugerowanie aprobaty organu", "8", SUPERVISOR, "związek organu z aprobatą produktu"),
    ("R18", "Nadzór jako argument bezpieczeństwa", "8", SUPERVISOR, "związek nadzoru z bezpieczeństwem"),
)


def catalog():
    return [{"rule_id": key, "title": title, "legal_basis": (
              "art. 24 ust. 3 MiFID II" if law == "MiFID"
              else f"art. 44 ust. {law} rozporządzenia delegowanego 2017/565"),
             "trigger": trigger or "materiał promocyjny", "required_media": requirement}
            for key, title, law, trigger, requirement in DEFINITIONS]


def evaluate(meta, rows, result):
    official = "M2" in result["modules"]
    auxiliary = "M1" in result["modules"]
    scope = "M2" if official else "M1_AUXILIARY" if auxiliary else "OUTSIDE_SCOPE"
    evaluations = []
    for definition, (_, _, _, trigger, _) in zip(catalog(), DEFINITIONS):
        key = definition["rule_id"]
        evidence = [row for row in rows if trigger and has(trigger, row["quote"])]
        status, why = "UNASSESSED", "Brak dowodów wymaganych do oceny w dostępnej próbce."
        against = []
        if scope == "OUTSIDE_SCOPE":
            status, why = "NOT_APPLICABLE", "Brak przesłanek przypisania do M1 lub M2."
        elif key == "R01":
            evidence = [row for row in rows if any(matches_name(entity["name"], row["quote"])
                        for entity in result["financial_entities"])]
            if evidence:
                status, why = "PASS", "W dostępnym materiale odczytano nazwę z lokalnej kartoteki."
            else:
                status, why = "NEEDS_REVIEW", "Zweryfikuj pełną nazwę firmy i jej status."
        elif key == "R02":
            evidence = [row for row in rows if has(DISCLOSURE, row["quote"])]
            status, why = (("PASS", "Odczytano oznaczenie promocyjne.") if evidence else
                           ("NEEDS_REVIEW", "Oznaczenia nie znaleziono w dostępnej próbce."))
        elif key == "R03" and evidence:
            def nearby(gain, risk):
                if risk is gain:
                    return True
                a, b = gain["start_ms"], risk["start_ms"]
                return a is not None and b is not None and abs(a - b) <= 3000
            against = [row for row in rows if has(RISK, row["quote"]) and
                       any(nearby(gain, row) for gain in evidence)]
            status = "NEEDS_REVIEW" if against else "POTENTIAL_ISSUE"
            why = ("Odczytano możliwe ostrzeżenie obok korzyści. Sprawdź związek znaczeniowy."
                   if against else "W pobliżu twierdzenia o korzyści nie odczytano ostrzeżenia.")
        elif key == "R04" and evidence:
            for warning in [row for row in evidence if row.get("bbox")]:
                peers = [row["bbox"][3] for row in rows
                         if row.get("frame_sha256") == warning.get("frame_sha256")
                         and row.get("bbox") and not has(RISK, row["quote"])]
                if peers:
                    ratio = warning["bbox"][3] / median(peers)
                    against.append({**warning, "relative_text_height": round(ratio, 3)})
            if against:
                status = ("POTENTIAL_ISSUE" if any(row["relative_text_height"] < 0.8 for row in against)
                          else "NEEDS_REVIEW")
                why = "Porównano wysokość linii OCR na klatce; proporcja jest przybliżona."
            else:
                status, why = "NEEDS_REVIEW", "Brak porównywalnego tekstu w klatce ostrzeżenia."
        elif key in {"R17", "R18"} and evidence:
            phrase = (r"zatwierdz\w*|aprob\w*|polec\w*|akcept\w*" if key == "R17"
                      else r"bezpiecz\w*|gwarant\w*|bez ryzyka")
            evidence = [row for row in evidence if has(phrase, row["quote"])]
            if evidence:
                status, why = "POTENTIAL_ISSUE", "Wzmianka o organie występuje w tej samej wypowiedzi."
        elif key in {"R14", "R15"} and evidence:
            against = [row for row in rows if has(PAST_WARNING, row["quote"])]
            status, why = "NEEDS_REVIEW", ("Zweryfikuj wyrazistość i związek zastrzeżenia z wynikami."
                                           if against else "Nie odczytano zastrzeżenia o przyszłych wynikach.")
        elif key == "R16" and evidence:
            against = [row for row in rows if has(r"indywidualn\w* sytuacj\w*", row["quote"]) and
                       has(r"zmian\w* przepis\w*", row["quote"])]
            status, why = "NEEDS_REVIEW", "Zweryfikuj zależność od sytuacji klienta i zmian przepisów."
        elif key in {"R05", "R06", "R09", "R10", "R11", "R12A", "R12B", "R13"} and evidence:
            status, why = "NEEDS_REVIEW", "Odczytano przesłankę. Sprawdź wskazane dane i kontekst."
        evaluations.append({**definition, "status": status, "scope": scope, "why": why,
                            "url": meta["url"], "evidence": evidence, "counter_evidence": against,
                            "uncertainty": "Ocena ograniczona do zebranych dowodów.",
                            "human_review_required": status in {"NEEDS_REVIEW", "POTENTIAL_ISSUE", "UNASSESSED"}})
    return evaluations
