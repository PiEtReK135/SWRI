"""Evidence, editorial classification, and review priority for feed posts."""

from math import ceil
import re
import subprocess
import unicodedata

from . import analysis, media, rules

CRYPTO = r"\b(?:bit[ck]oin\w*|bitkon\w*|kryptowalut\w*|ethereum|btc)\b"
FINANCE = (r"\b(?:inwest\w*|broker\w*|makler\w*|akcj\w*|obligacj\w*|etf\w*|cfd|forex|"
           r"bit[ck]oin\w*|bitkon\w*|krypto\w*|gield\w*|xtb|zloto|zlot\w* (?:sie|wobec)|"
           r"stop\w* procentow\w*|kurs\w* walut\w*|portfel\w* inwest\w*|trading|stocks|invest\w*)\b")
INSTRUMENT = r"\b(?:akcj\w*|obligacj\w*|cfd|etf\w*|fundusz\w*|opcj\w*|swap\w*|kontrakt\w* termin\w*|stocks)\b"
PROMO = (r"\b(?:zaloz\w*|otworz\w*) (?:sobie )?(?:rachunek|konto)\b|\b(?:kod (?:rabatowy|polecajacy|afiliacyjny)|"
         r"(?:moj|moim|mojego|mojemu) kod\w*|(?:uzyj|wpisz|podaj|wpiszecie) kod\w*|"
         r"(?:dostan\w*|dostac|otrzyma\w*) (?:\d+ (?:zl|zlot\w*)|bonus\w*)|"
         r"promocj\w* (?:\w+ ){0,2}(?:makler\w*|broker\w*|platform\w*)|"
         r"zarejestruj\w*|link (?:w bio|afiliacyjny|polecajacy)|kup (?:moj|kurs|dostep)|"
         r"wspolpraca (?:platna|reklamowa)|platna wspolpraca|material sponsorowany|sponsoruje|"
         r"moj kurs|platna grup\w*|dolacz do (?:platformy|grupy|kursu)|referral|sign up|use (?:my|the) code)\b|#reklama\b")
SELF = r"\b(?:moj (?:kurs|program|abonament|ebook)|moj\w* (?:platn\w* )?grup\w*|moje szkolenie|my course)\b"
PERSONAL = r"\b(?:na podstawie twoj\w*|twoj\w* sytuacj\w*|dopasuj\w* do (?:ciebie|twoj\w*)|indywidualn\w* rekomendacj\w*|twoj\w* potrzeb\w*)\b"
DIRECT = r"\b(?:kup|kupcie|kupic|kupujcie|sprzedaj|sprzedajcie|sprzedac|trzymaj|trzymajcie|buy|sell)\b"
COUNTER = r"\b(?:ostrzegam|nie polecam|nie kupuj|nie zakladaj|oszustwo|satyra|cytat z reklamy|parodia)\b"
STRONG = r"\b(?:gwarantowan\w* zysk\w*|gwarancj\w* zysk\w*|zarobisz bez ryzyka|zysk bez ryzyka|zatwierdzon\w* przez knf|guaranteed profits?)\b"
BRAND_MENTION = re.compile(
    r"(?i:\b(?:u brokera|platforma|dom maklerski|współpraca z|sponsor:)\s+)"
    r"(?P<name>@?[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9_.-]{1,35}"
    r"(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9_.-]{1,25})?)"
)
POLISH_MARKERS = r"\b(?:jest|sie|oraz|dla|ktory\w*|ktore\w*|przez|mozna|mozesz|musicie|kupic|zobacz|was|polecam|witam|pln|zlot\w*)\b"
FOREIGN_MARKERS = r"\b(?:und|wie|der|die|das|ist|fur|the|and|with|you|your|this)\b"
OTHER_CONTENT = {
    "Sport": r"\b(?:trening\w*|mecz\w*|pilk\w*|biegan\w*|fitness)\b",
    "Kuchnia": r"\b(?:przepis\w*|gotuj\w*|pieczeni\w*|deser\w*|cukier)\b",
    "Podróże i natura": r"\b(?:szlak\w*|tatr\w*|podroz\w*|jezior\w*|wiosn\w*|przyrod\w*)\b",
    "Technologia": r"\b(?:komputer\w*|smartfon\w*|technolog\w*|oprogramowan\w*)\b",
    "Kultura i edukacja": r"\b(?:animacj\w*|zwiastun\w*|ksiazk\w*|muzyk\w*|muze\w*|literatur\w*)\b",
}


def plain(value):
    return "".join(char for char in unicodedata.normalize("NFKD", value.lower().replace("ł", "l"))
                   if not unicodedata.combining(char))


def matches(pattern, value):
    return re.search(pattern, plain(value)) is not None


def looks_polish(value):
    return (len(re.findall(POLISH_MARKERS, plain(value))) >= 2
            or bool(re.search(r"[ąćęłńóśźż]", value.casefold())) and len(value.split()) >= 3)


def market_language(rows):
    speech = [row for row in rows if row["kind"] == "ASR" and row.get("language")
              and row.get("language_probability", 1) >= .65]
    audio = max(speech, key=lambda row: (row["end_ms"] or 0) - (row["start_ms"] or 0), default=None)
    written = [row["quote"] for row in rows if row["kind"] != "ASR"]
    # Polish translations in an otherwise foreign caption are weaker than the actual audio.
    addressed = any(looks_polish(row["quote"]) and (row["kind"] == "OCR"
                    or matches(PROMO, row["quote"]) or matches(DIRECT, row["quote"])) for row in rows
                    if row["kind"] != "ASR")
    if audio and not addressed:
        return audio["language"]
    if addressed or any(looks_polish(text) for text in written):
        return "pl"
    if len(re.findall(FOREIGN_MARKERS, plain(" ".join(written)))) >= 3:
        return "foreign"
    return "unknown"


def classify(post, rows, coverage, limitations, registry, profile_url, public_url):
    timeline = sorted(rows, key=lambda row: (row["start_ms"] is not None, row["start_ms"] or 0))
    declared = [item for item in registry if not item.get("is_demo") and any(
        analysis.matches_name(name, row["quote"])
        for name in (item["name"], *item.get("aliases", [])) for row in timeline)]
    official = next((item for item in registry if not item.get("is_demo") and item.get("in_scope")
                     and item.get("publisher_url") == profile_url), None)
    finance_rows = [row for row in timeline if matches(FINANCE, row["quote"])]
    promo_rows = [row for row in timeline if matches(PROMO, row["quote"]) and not matches(COUNTER, row["quote"])]
    personal_rows = [row for row in timeline if matches(PERSONAL, row["quote"])]
    advice_rows = [row for row in timeline if matches(DIRECT, row["quote"]) and matches(INSTRUMENT, row["quote"])
                   and not matches(COUNTER, row["quote"]) and any(
                       other is row or other["kind"] == "DESCRIPTION" or (
                           row["start_ms"] is not None and other["start_ms"] is not None
                           and abs(row["start_ms"] - other["start_ms"]) <= 5000)
                       for other in personal_rows)]
    financial = bool(finance_rows or declared)
    promotion = financial and bool(promo_rows)
    partial = any(value == "ERROR" for value in coverage.values())
    market = market_language(timeline)
    addressed_actions = [row for row in timeline if matches(DIRECT, row["quote"]) and not matches(COUNTER, row["quote"])
                          and matches(f"(?:{INSTRUMENT}|{CRYPTO})", row["quote"])]
    if promotion:
        addressed_actions.extend(row for row in finance_rows if row not in addressed_actions
                                 and matches(CRYPTO, row["quote"]) and matches(r"\bzainwestuj\w*\b", row["quote"])
                                 and not matches(COUNTER, row["quote"]))
    credible = [row for row in timeline if row["kind"] != "ASR" or row.get("avg_logprob", 0) >= -1.05]
    if market not in {"pl", "unknown"}:
        decision = "OUT_OF_MARKET"
    elif promotion or advice_rows or addressed_actions:
        decision = "REVIEW"
    elif partial or not credible or (not financial and matches(FINANCE, post.get("title", ""))):
        decision = "UNRESOLVED"
    else:
        decision = "FINANCE_NEUTRAL" if financial else "OUT_OF_SCOPE"

    modules = ((["M2" if official else "M1"] if promotion else []) + (["M3"] if advice_rows else [])
               if decision == "REVIEW" else [])
    meta = {"url": public_url, "is_demo": False, "relation": "FIRST_PARTY" if official else "UNKNOWN",
            "publisher_url": profile_url}
    result = {"modules": modules, "financial_entities": list({item["name"]: item for item in (
        [*declared, official] if official else declared)}.values())}
    evaluations = rules.evaluate(meta, timeline, result) if modules and promotion else []
    reasons = []
    if advice_rows and decision == "REVIEW":
        reasons.append(("Sygnał rekomendacji dopasowanej do odbiorcy dotyczącej instrumentu.", advice_rows, "HIGH"))
    if addressed_actions and decision == "REVIEW":
        reasons.append(("Publiczna zachęta do transakcji. Sprawdź kontekst i charakter produktu.",
                        addressed_actions, "MEDIUM"))
    strong = [row for row in timeline if matches(STRONG, row["quote"]) and not matches(COUNTER, row["quote"])]
    if promotion and strong and decision == "REVIEW":
        reasons.append(("Obietnica zysku bez ryzyka lub możliwa sugestia aprobaty KNF.", strong, "HIGH"))
    for evaluation in evaluations:
        if evaluation["status"] in {"POTENTIAL_ISSUE", "NEEDS_REVIEW"}:
            risk = "MEDIUM" if evaluation["status"] == "POTENTIAL_ISSUE" else "LOW"
            if partial and evaluation["rule_id"] in {"R02", "R03", "R14", "R15"}:
                risk = "LOW"
            reasons.append((evaluation["title"] + ". " + evaluation["why"], evaluation["evidence"], risk))
    if promotion and decision == "REVIEW":
        reasons.append(("Wykryto zachętę promocyjną w kontekście finansowym.", [*promo_rows, *finance_rows[:1]], "LOW"))
    if decision == "FINANCE_NEUTRAL":
        reasons.append(("Temat finansowy bez wykrytej promocji ani spersonalizowanej rekomendacji.", finance_rows, None))
    if decision == "OUT_OF_SCOPE":
        reason = ("Wykryto możliwy przekaz promocyjny spoza zakresu inwestycyjnego." if promo_rows
                  else "W przeanalizowanych kanałach brak przesłanek tematyki finansowej.")
        reasons.append((reason, promo_rows, None))
    if decision == "UNRESOLVED":
        reasons.append(("Za mało dowodów do zamknięcia sprawy. Rolka nie obniża preferencji skanera.", [], None))
    if decision == "OUT_OF_MARKET":
        language_evidence = [row for row in timeline if row.get("language") == market and row["kind"] == "ASR"]
        reasons.append(("Rozpoznano przekaz w innym języku bez wystarczających sygnałów kierowania do polskich odbiorców.",
                        language_evidence[:2], None))
    priority = {None: 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    reasons.sort(key=lambda item: priority[item[2]], reverse=True)
    for reason in reasons:
        reason[1].sort(key=lambda row: (row["start_ms"] is not None, row["start_ms"] or 0))
    entities = result["financial_entities"]
    registered = {plain(item["name"]) for item in entities}
    unverified = sorted({match["name"].rstrip(".") for row in timeline if promotion
                         for match in BRAND_MENTION.finditer(row["quote"])
                         if plain(match["name"].rstrip(".")) not in registered})
    if promotion and "xtb" not in registered and any(matches(r"\b(?:xtb|iks te be)\b", row["quote"]) for row in timeline):
        unverified = sorted({*unverified, "XTB"})
    topic_scores = {topic: sum(matches(pattern, row["quote"]) for row in credible)
                    for topic, pattern in OTHER_CONTENT.items()}
    topic = max(topic_scores, key=topic_scores.get)
    if financial or addressed_actions:
        topic = "Finanse i inwestycje"
    elif not topic_scores[topic]:
        topic = "Temat nieustalony"
    self_promoter = any(matches(SELF, row["quote"]) for row in promo_rows)
    if official:
        role = "Firma"
    elif self_promoter:
        role = "Autopromocja"
    elif entities:
        role = "Twórca promujący firmę"
    elif unverified:
        role = "Promocja firmy do potwierdzenia"
    else:
        role = "Powiązanie nieustalone"
    return {"decision": decision, "risk": reasons[0][2], "financial": financial, "modules": modules,
            "category": topic, "market_language": market,
            "reasons": [{"text": reason, "evidence": evidence[:8]} for reason, evidence, _ in reasons],
            "timeline": timeline, "coverage": coverage, "limitations": limitations,
            "rules": evaluations, "companies": [item["name"] for item in entities],
            "unverified_companies": unverified,
            "role": role, "creator": post["creator"], "url": public_url}


def collect(path, post, work):
    rows = [media.segment("DESCRIPTION", post["description"])] if post["description"].strip() else []
    coverage = {"DESCRIPTION": "CHECKED", "ASR": "NOT_APPLICABLE", "OCR": "ERROR"}
    limits = []
    expected = (OSError, ValueError, RuntimeError, subprocess.SubprocessError, ImportError)
    if post["kind"] == "image":
        try:
            rows.extend(media.ocr_frame(path, media.ocr_languages()))
            coverage["OCR"] = "CHECKED"
        except expected as error:
            limits.append(f"OCR obrazu niedostępne ({type(error).__name__}).")
        return rows, coverage, limits

    duration, streams = media.probe(path)
    if "audio" in streams:
        try:
            speech = media.asr(path)
            rows.extend(speech)
            coverage["ASR"] = "CHECKED"
            if not speech:
                limits.append("ASR nie zapisało rozpoznawalnej mowy.")
        except expected as error:
            coverage["ASR"] = "ERROR"
            limits.append(f"ASR niedostępne ({type(error).__name__}).")
    interval = max(1, ceil(duration / 36))
    limits.append(f"OCR analizuje klatkę co {interval} s oraz chwile rozpoczęcia wypowiedzi. Może pominąć krótkie napisy.")
    try:
        rows.extend(media.ocr_batch(path, duration, rows, work, interval))
        coverage["OCR"] = "CHECKED"
    except expected as error:
        limits.append(f"OCR filmu niedostępne ({type(error).__name__}).")
    return rows, coverage, limits
