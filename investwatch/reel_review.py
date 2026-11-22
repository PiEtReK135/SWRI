"""Evidence, editorial classification, and review priority for feed posts."""

import http.client
import re
import subprocess
from time import perf_counter
import unicodedata

from . import analysis, media, rules
from .reel_llm import EvidenceContext, MODEL, QUALIFIED, Review

MODEL_ERRORS = (OSError, ValueError, KeyError, IndexError, TypeError, http.client.HTTPException)

CRYPTO = r"\b(?:bit[ck]oin\w*|bitkon\w*|kryptowalut\w*|ethereum|btc)\b"
FINANCE = (r"\b(?:inwest\w*|broker\w*|makler\w*|akcj\w*|obligacj\w*|etf\w*|cfd|forex|"
           r"bit[ck]oin\w*|bitkon\w*|krypto\w*|gield\w*|xtb|zloto|zlot\w* (?:sie|wobec)|"
           r"stop\w* procentow\w*|kurs\w* walut\w*|portfel\w* inwest\w*|rynek\w* kapitalow\w*|"
           r"rynku kapitalow\w*|papier\w* wartosciow\w*|(?:usd|eur|chf)\s*/\s*pln|wig20|nasdaq|"
           r"notowan\w*|trading|stocks|invest\w*)\b")
EXPLICIT_FINANCE = r"\b(?:broker\w*|makler\w*|etf\w*|cfd|forex|gield\w*|obligacj\w*|bitcoin\w*|kryptowalut\w*)\b"
COMMERCIAL_OFFER = (r"\b(?:\d+\s*(?:zl\w*)\s*bonus\w*|(?:moj|uzyj|wpisz) kod\w*|"
                    r"kod (?:afiliacyjny|polecajacy)|platna wspolpraca|material sponsorowany)\b")
INSTRUMENT = r"\b(?:akcj\w*|obligacj\w*|cfd|etf\w*|fundusz\w*|opcj\w*|swap\w*|kontrakt\w* termin\w*|stocks)\b"
PROMO = (r"\b(?:zaloz|zalozcie|otworz|otworzcie) (?:sobie )?(?:rachunek|konto)\b|\b(?:kod (?:rabatowy|polecajacy|afiliacyjny)|"
         r"(?:moj|moim|mojego|mojemu) kod\w*|(?:uzyj|wpisz|podaj|wpiszecie) kod\w*|"
         r"(?:dostan\w*|dostac|otrzyma\w*) (?:\d+ (?:zl|zlot\w*)|bonus\w*)|"
         r"promocj\w* (?:\w+ ){0,2}(?:makler\w*|broker\w*|platform\w*)|"
         r"zarejestruj\w*|link (?:w bio|afiliacyjny|polecajacy)|kup (?:moj|kurs|dostep)|"
         r"wspolpraca (?:platna|reklamowa)|platna wspolpraca|material sponsorowany|sponsoruje|"
         r"moj kurs|platna grup\w*|dolacz do (?:platformy|grupy|kursu)|referral|sign up|use (?:my|the) code)\b|#reklama\b")
SELF = r"\b(?:moj (?:kurs|program|abonament|ebook)|moj\w* (?:platn\w* )?grup\w*|moje szkolenie|my course)\b"
PERSONAL = r"\b(?:na podstawie twoj\w*|twoj\w* sytuacj\w*|dopasuj\w* do (?:ciebie|twoj\w*)|indywidualn\w* rekomendacj\w*|twoj\w* potrzeb\w*)\b"
DIRECT = r"\b(?:kup|kupcie|kupic|kupujcie|sprzedaj|sprzedajcie|sprzedac|trzymaj|trzymajcie|buy|sell)\b"
PUBLIC_TRADE = (r"\b(?:kup|kupcie|kupujcie|sprzedaj|sprzedajcie|trzymaj|trzymajcie|"
                r"zainwestuj|zainwestujcie|polecam (?:kupic|kupno|sprzedaz)|"
                r"warto (?:kupic|sprzedac|trzymac|zainwestowac)|buy|sell)\b")
MARKET_TARGET = f"(?:{INSTRUMENT}|{CRYPTO}|" + (
    r"\b(?:kurs\w*|cen\w*|notowan\w*|kapitalizacj\w*|wig20|nasdaq|s&p\s*500|wycen\w*|indeks\w*|rynek\w*|rynku)\b)")
THESIS = (r"\b(?:niedowartosciowan\w*|przewartosciowan\w*|potencjal\w* (?:wzrostu|spadku)|"
          r"(?:moja|nasza) (?:teza|analiza|wycena|rekomendacja)|wyceniam\w*|cen\w* docelow\w*|"
          r"sygnal\w* (?:kupna|sprzedazy)|rekomendacj\w* (?:kupna|sprzedazy))\b")
EXAMPLE = (r"\b(?:fikcyjn\w*|hipotetyczn\w*|symulacj\w* edukacyjn\w*|na potrzeby (?:przykladu|lekcji)|"
           r"przyklad\w* edukacyjn\w*|cytat z reklamy|parodia)\b")
FORECAST_QUOTE = r"\b(?:wedlug (?:analitykow|ekonomistow|raportu|prognozy|depeszy)|analitycy prognozuja|cytuje)\b"
COUNTER = r"\b(?:ostrzegam|nie polecam|nie kupuj\w*|nie sprzedaj\w*|nie uzywaj\w*|nie zakladaj\w*|oszustwo|satyra|cytat z reklamy|parodia)\b"
BROKER = r"\b(?:broker\w*|makler\w*|dom\w* maklersk\w*|biur\w* maklersk\w*|platform\w* (?:inwest\w*|transakcyjn\w*))\b"
SERVICE_ACTION = (r"\b(?:uzywaj\w*|uzyj\w*|korzystaj\w*|skorzystaj\w*|wybierz\w*|"
                  r"polecam\w*|rekomenduj\w*|handluj\w* (?:u|na)|kupuj\w* (?:u|przez))\b")
QUOTING = r"\b(?:cytuje|przytocze|w reklamie (?:powiedziano|mowiono)|padaja slowa|w tym przykladzie|na symulatorze)\b"
OWN_POSITION = r"\b(?:od siebie|moja rekomendacja|osobiscie polecam|moja rzeczywista rekomendacja|w praktyce polecam)\b"
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


def contextual_evidence(timeline, sources, target, exclude=EXAMPLE):
    """Match a claim to its subject in the same sentence or neighbouring evidence."""
    evidence = []
    for row in sources:
        start = row["start_ms"]
        end = row["end_ms"] or start
        neighbours = [other for other in timeline if (other is row or
                      (start is not None and other["start_ms"] is not None and
                       other["start_ms"] <= end + 3500 and (other["end_ms"] or other["start_ms"]) >= start - 3500))]
        # Quoting an example can cancel a neighbouring claim, but it never cancels a separate promotion.
        context = " ".join(other["quote"] for other in neighbours)
        if matches(target, context) and not matches(exclude, context):
            evidence.extend(other for other in neighbours if other is row or matches(target, other["quote"]))
    return [row for row in timeline if row in evidence]


def author_claims(rows):
    """Carry explicit quotation/example framing through successive speech segments."""
    framed = False
    claims = []
    for row in rows:
        quote = row["quote"]
        if row["kind"] == "ASR":
            if matches(OWN_POSITION, quote):
                framed = False
            if matches(f"(?:{EXAMPLE}|{QUOTING})", quote):
                framed = True
            if framed:
                continue
        if not matches(f"(?:{COUNTER}|{EXAMPLE}|{QUOTING})", quote):
            claims.append(row)
    return claims


def broker_endorsements(rows):
    """Join recommendations to named services, including references across distant parts."""
    brokers = [row for row in rows if matches(BROKER, row["quote"])]
    if not brokers:
        return []
    hits = contextual_evidence(rows, [row for row in rows if matches(SERVICE_ACTION, row["quote"])], BROKER)
    def reference(row):
        return matches(r"\b(?:z niego|tej platformy|tym broker\w*|u nich)\b|"
                       r"\b(?:tylko )?(?:tego|go)(?:[,.;]|$)", row["quote"])
    explicit = [row for row in brokers if matches(SERVICE_ACTION, row["quote"])]
    linked = [row for row in rows if matches(SERVICE_ACTION, row["quote"]) and reference(row) and
              any(earlier["kind"] == row["kind"] and earlier["start_ms"] is not None and
                  row["start_ms"] is not None and earlier["start_ms"] < row["start_ms"] for earlier in brokers)]
    return [row for row in rows if row in hits or row in explicit or row in linked]


def apply_model_checks(evaluations, checks, context, partial):
    by_rule = {check.rule: check for check in checks}
    accepted = []
    for rule in evaluations:
        check = by_rule.get(rule["rule_id"])
        if not check:
            continue
        evidence = context.resolve(check.evidence)
        counters = context.resolve(check.counter)
        key = rule["rule_id"]
        if check.status == "observed":
            # Keep only suggestions independently connected to the control's evidence.
            verified = [row for row in evidence if row in rule["evidence"]]
            if verified:
                rule["semantic_evidence"] = verified
                rule["method"] = "Reguły + " + MODEL
                accepted.append(key)
            continue
        if key in {"R01", "R04", "R05", "R08", "R13"} or rule["status"] in {"NOT_APPLICABLE", "UNASSESSED"}:
            # The text model cannot establish a legal identity, measure a frame, or invent an applicable trigger.
            continue
        if not any(row in rule["evidence"] for row in evidence):
            continue
        status = {"issue": "POTENTIAL_ISSUE", "ok": "PASS", "verify": "NEEDS_REVIEW"}[check.status]
        why = " ".join(check.reason.split())
        if key == "R03":
            counters = [source for source in counters if analysis.has(rules.RISK, source["quote"])
                        and not analysis.has(r"\bbez ryzyka\b", source["quote"])]
            if not counters and rule["status"] == "POTENTIAL_ISSUE" and any(
                    analysis.has(rules.GAIN, source["quote"]) for source in evidence):
                # The model extracts the benefit. The code establishes whether its proof includes a warning.
                status = "POTENTIAL_ISSUE"
                why = "Wskazane fragmenty obiecują korzyść. W jej pobliżu nie odczytano ostrzeżenia o stracie."
        if key == "R02" and not counters and rule["status"] == "NEEDS_REVIEW" and any(
                matches(PROMO, source["quote"]) for source in evidence):
            status = "NEEDS_REVIEW"
            why = "Wskazane fragmenty zachęcają do skorzystania z oferty. W próbce brak jawnego oznaczenia reklamy."
        if status == "PASS" and not counters:
            continue
        if (check.status == "issue" and rule["rule_id"] in {"R06", "R07", "R17", "R18"} and
                rule["status"] == "NOT_APPLICABLE"):
            continue
        if status == "POTENTIAL_ISSUE" and rule["status"] == "PASS":
            if rule["rule_id"] == "R02":
                continue
            status = "NEEDS_REVIEW"
            counters = rule["counter_evidence"] or rule["evidence"]
            why = "Model i kontrola reguł wykazały różnicę w ocenie zastrzeżenia."
        if status == "POTENTIAL_ISSUE" and (counters or (partial and rule["rule_id"] in rules.ABSENCE_BASED)):
            status = "NEEDS_REVIEW"
            why += " Sprawdź zastrzeżenia i kompletność kanałów."
        if rule["rule_id"] == "R03" and rule["status"] == "POTENTIAL_ISSUE" and status == "PASS":
            # A distant screen warning cannot prove proximity for every benefit.
            status = "NEEDS_REVIEW"
            why = "Model wskazał ostrzeżenie. Kontrola czasu nie potwierdziła go przy każdej korzyści."
        weight = max(rule["priority_weight"], rule["points"])
        points = weight if status == "POTENTIAL_ISSUE" else min(15, max(5, weight // 3)) if status == "NEEDS_REVIEW" else 0
        rule.update(status=status, why=why, method=MODEL, points=points, evidence=evidence,
                    counter_evidence=counters, human_review_required=status != "PASS")
        accepted.append(rule["rule_id"])
    return accepted


def classify(post, rows, coverage, limitations, registry, profile_url, public_url, progress=None, model=None):
    timeline = sorted(rows, key=lambda row: (row["start_ms"] is not None, row["start_ms"] or 0))
    declared = [item for item in registry if not item.get("is_demo") and any(
        analysis.matches_name(name, row["quote"])
        for name in (item["name"], *item.get("aliases", [])) for row in timeline)]
    official = next((item for item in registry if not item.get("is_demo") and item.get("in_scope")
                     and item.get("publisher_url") == profile_url), None)
    credible = [row for row in timeline if row["kind"] != "ASR" or row.get("avg_logprob", 0) >= -1.05]
    uncertain_speech = len(credible) != len(timeline)
    claims = author_claims(credible)
    finance_rows = [row for row in credible if matches(FINANCE, row["quote"])]
    endorsements = broker_endorsements(claims)
    promo_rows = [row for row in claims if matches(PROMO, row["quote"]) or row in endorsements]
    addressed_actions = contextual_evidence(claims, [row for row in claims if matches(PUBLIC_TRADE, row["quote"])],
                                           f"(?:{INSTRUMENT}|{CRYPTO})", f"(?:{COUNTER}|{EXAMPLE})")
    advice_rows = contextual_evidence(claims, [row for row in claims if matches(DIRECT, row["quote"])],
                                      INSTRUMENT, f"(?:{COUNTER}|{EXAMPLE})")
    personalized = [row for row in credible if matches(PERSONAL, row["quote"])]
    advice_rows = [row for row in advice_rows if any(other is row or other["kind"] == "DESCRIPTION" or (
        row["start_ms"] is not None and other["start_ms"] is not None
        and abs(row["start_ms"] - other["start_ms"]) <= 5000) for other in personalized)]
    financial = bool(finance_rows or declared)
    promotion = financial and bool(promo_rows)
    partial = uncertain_speech or any(value == "ERROR" for value in coverage.values())
    market = market_language(timeline)
    if promotion:
        addressed_actions.extend(row for row in finance_rows if row not in addressed_actions
                                 and matches(CRYPTO, row["quote"]) and matches(r"\bzainwestuj\w*\b", row["quote"])
                                 and not matches(COUNTER, row["quote"]))
    future_rows = [row for row in rules.context_hits(claims, rules.PREDICTION)
                   if not analysis.has(rules.PAST_WARNING, row["quote"]) and
                   not analysis.has(rules.FORECAST_WARNING, row["quote"]) and
                   not matches(r"\b(?:mozesz|mozecie) strac\w*", row["quote"])]
    future_target = f"(?:{MARKET_TARGET}|\\b(?:stop\\w* zwrotu|zysk\\w*|wzrost\\w*|spad\\w*)\\b)"
    forecasts = contextual_evidence(claims, future_rows, future_target, f"(?:{EXAMPLE}|{FORECAST_QUOTE})")
    if promotion:
        forecasts = contextual_evidence(claims, future_rows, future_target, FORECAST_QUOTE)
    elif financial and not forecasts and any(matches(MARKET_TARGET, row["quote"]) for row in finance_rows):
        # An explicitly voiced own forecast can use a subject introduced earlier in the reel.
        forecasts = [row for row in future_rows if matches(r"\b(?:moim zdaniem|naszym zdaniem|przewiduje|prognozuje)\b",
                                                           row["quote"]) and not matches(EXAMPLE, row["quote"])]
    theses = contextual_evidence(claims, [row for row in claims if matches(THESIS, row["quote"])], MARKET_TARGET)
    content_type = ("PROMOTION" if promotion else "RECOMMENDATION" if advice_rows or addressed_actions else
                    "FORECAST" if financial and forecasts else "INVESTMENT_ANALYSIS" if financial and theses else
                    "FINANCE_INFORMATION" if financial else "OTHER")
    rule_category = content_type
    context = EvidenceContext.from_timeline(timeline)
    inference = {"qualification": "REGUŁY", "uknf": "SKIPPED", "timeline_rows": len(timeline),
                 "context_rows": len(context.rows), "context_pages": sum(1 for _ in context.pages())}
    answer = None
    qualification_evidence = []
    model_failure = False
    if model and model.available and context.rows:
        if progress:
            progress("QUALIFY", 83)
        started = perf_counter()
        try:
            answer = model.qualify(context)
        except MODEL_ERRORS as error:
            model_failure = True
            inference["qualification"] = "UNAVAILABLE"
            limitations.append(f"Kwalifikacja modelu niedostępna ({type(error).__name__}).")
        else:
            inference.update(qualification=MODEL, qualification_seconds=round(perf_counter() - started, 2),
                             model_category=answer.category, reason=" ".join(answer.reason.split()))
            source = context.resolve(answer.evidence)
            qualification_evidence = source
            content_type = answer.category
            if content_type in QUALIFIED and rule_category not in QUALIFIED and not any(row in claims for row in source):
                content_type = rule_category
                inference["reason"] = "Wskazane fragmenty należą do cytatu lub przykładu, więc nie potwierdzają stanowiska autora."
            if content_type == "FORECAST" and not forecasts:
                forecasts = source
            if content_type == "RECOMMENDATION" and not addressed_actions:
                addressed_actions = source
            if content_type == "PROMOTION" and not promo_rows:
                promo_rows = source
            explicit_offers = [row for row in promo_rows if matches(COMMERCIAL_OFFER, row["quote"])]
            if rule_category == "PROMOTION" and content_type != "PROMOTION" and (endorsements or contextual_evidence(
                    claims, explicit_offers, FINANCE, f"(?:{COUNTER}|{EXAMPLE})")):
                content_type = "PROMOTION"
                qualification_evidence = [row for row in timeline if row in promo_rows or row in addressed_actions]
                inference["reason"] = "W pełnej wypowiedzi jest własna zachęta do skorzystania z usługi finansowej."
            if rule_category == "RECOMMENDATION" and content_type not in QUALIFIED:
                content_type = rule_category
                qualification_evidence = addressed_actions or advice_rows
                inference["reason"] = "W pełnej wypowiedzi jest własna zachęta do transakcji."
            if content_type not in QUALIFIED and any(matches(
                    r"\b(?:moim zdaniem|naszym zdaniem|prognozuje|przewiduje)\b", row["quote"]) for row in forecasts):
                content_type = "FORECAST"
                inference["reason"] = "Wypowiedź zawiera własną prognozę przyszłej wartości inwestycji."
            if content_type == "OTHER" and any(matches(EXPLICIT_FINANCE, row["quote"]) for row in credible):
                content_type = "FINANCE_INFORMATION"
                inference["reason"] = "Materiał dotyczy finansów, a model nie rozpoznał własnej tezy inwestycyjnej."
            if content_type not in QUALIFIED:
                addressed_actions, advice_rows = [], []
            financial = content_type not in {"OTHER", "UNCLEAR"}
            promotion = content_type == "PROMOTION"
    if market not in {"pl", "unknown"}:
        decision = "OUT_OF_MARKET"
    elif content_type in QUALIFIED:
        decision = "REVIEW"
    elif model_failure or content_type == "UNCLEAR":
        decision = "UNRESOLVED"
    elif partial or not credible or (answer is None and not financial and matches(FINANCE, post.get("title", ""))):
        decision = "UNRESOLVED"
    else:
        decision = "FINANCE_NEUTRAL" if financial else "OUT_OF_SCOPE"

    modules = ((["M2"] if official else ["M1"] if promotion else []) + (["M3"] if advice_rows else [])
               if decision == "REVIEW" else [])
    meta = {"url": public_url, "is_demo": False, "relation": "FIRST_PARTY" if official else "UNKNOWN",
            "publisher_url": profile_url}
    result = {"modules": modules, "screening": True, "promotion": promotion, "partial": partial,
              "promotion_evidence": promo_rows if promotion else [], "claim_rows": claims,
              "predictions": forecasts, "financial_entities": list({item["name"]: item for item in (
        [*declared, official] if official else declared)}.values())}
    qualified = decision == "REVIEW"
    if qualified and progress:
        progress("UKNF", 88)
    using_model = model is not None and model.available and bool(context.rows)
    rule_progress = (lambda done, total: progress("UKNF", 88 + 9 * done // total)) if progress and not using_model else None
    evaluations = rules.evaluate(meta, credible, result, rule_progress) if qualified else []
    if qualified:
        inference["uknf"] = "REGUŁY"
    if qualified and using_model:
        started = perf_counter()
        try:
            reviews = model.review(context, content_type,
                                   (lambda done, total: progress("UKNF", 88 + 9 * done // total)) if progress else None)
        except MODEL_ERRORS as error:
            inference["uknf"] = "REGUŁY_AWARYJNIE"
            limitations.append(f"Ocena semantyczna UKNF niedostępna ({type(error).__name__}).")
        else:
            if reviews is not None:
                completed = reviews.complete if isinstance(reviews, Review) else None
                checks = reviews.checks if isinstance(reviews, Review) else reviews
                accepted = apply_model_checks(evaluations, checks, context, partial)
                inference.update(uknf=MODEL, uknf_seconds=round(perf_counter() - started, 2),
                                 accepted_criteria=accepted)
                if completed is not None:
                    inference["semantic_checks"] = len(completed)
                    for evaluation in evaluations:
                        key = evaluation["rule_id"]
                        evaluation["semantic_status"] = (
                            "INCOMPLETE" if key not in completed else "RULE_ONLY" if evaluation["points"] and key not in accepted
                            else "CHECKED")
                    if len(completed) != len(evaluations):
                        inference["uknf"] = "REGUŁY_AWARYJNIE" if not completed else "MODEL_PARTIAL"
                        limitations.append("Nie wszystkie odpowiedzi modelu przeszły walidację. Pełna kontrola reguł pozostała dostępna.")
        if progress:
            progress("UKNF", 97)
    evaluations.sort(key=lambda rule: -rule["points"])
    finding_count = sum(rule["points"] > 0 for rule in evaluations)
    criteria_count = len(rules.DEFINITIONS)
    if qualified and not finding_count:
        decision = ("UNRESOLVED" if partial or inference["uknf"] in {"REGUŁY_AWARYJNIE", "MODEL_PARTIAL"}
                    else "SCREENED_CLEAR")

    reasons = []
    for evaluation in evaluations:
        if evaluation["points"]:
            reasons.append((evaluation["title"] + ". " + evaluation["why"], evaluation["evidence"],
                            evaluation["rule_id"], evaluation["points"]))
    if advice_rows and decision == "REVIEW":
        reasons.append(("Sygnał rekomendacji dopasowanej do odbiorcy dotyczącej instrumentu.", advice_rows, None, 0))
    if addressed_actions and decision == "REVIEW":
        reasons.append(("Publiczna zachęta do transakcji. Sprawdź kontekst i charakter produktu.",
                        addressed_actions, None, 0))
    if promotion and decision == "REVIEW":
        reasons.append(("Wykryto zachętę promocyjną w kontekście finansowym.", promo_rows, None, 0))
    if decision != "REVIEW":
        reason = {"FINANCE_NEUTRAL": "Materiał edukacyjny lub informacyjny bez zakwalifikowanego sygnału inwestycyjnego.",
                  "OUT_OF_SCOPE": "Poza tematyką finansową.",
                  "UNRESOLVED": "Za mało wiarygodnych danych do rozstrzygnięcia.",
                  "OUT_OF_MARKET": "Brak wystarczających sygnałów kierowania przekazu do Polski.",
                  "SCREENED_CLEAR": "Testy UKNF nie wykazały sygnału wymagającego priorytetu."}[decision]
        reasons = [(reason, qualification_evidence, None, 0)]
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
    return {"decision": decision, "risk": rules.priority_level(max((rule["points"] for rule in evaluations), default=0)),
            "priority_count": finding_count if qualified else None, "criteria_count": criteria_count,
            "priority_percent": round(finding_count * 100 / criteria_count) if qualified else None,
            "content_type": content_type, "inference": inference,
            "uknf_status": "EVALUATED" if qualified else "UNASSESSED" if decision == "UNRESOLVED" else "NOT_QUALIFIED",
            "finding_count": finding_count, "financial": financial, "modules": modules,
            "category": topic, "market_language": market,
            "reasons": [{"text": reason, "evidence": sorted(evidence, key=lambda row: row["start_ms"] or 0),
                         "rule_id": key, "points": points} for reason, evidence, key, points in reasons],
            "timeline": timeline, "coverage": coverage, "limitations": limitations,
            "rules": evaluations, "companies": [item["name"] for item in entities],
            "unverified_companies": unverified,
            "role": role, "creator": post["creator"], "url": public_url}


def collect(path, post, work, progress):
    rows = [media.segment("DESCRIPTION", post["description"])] if post["description"].strip() else []
    coverage = {"DESCRIPTION": "CHECKED", "ASR": "NOT_APPLICABLE", "OCR": "ERROR"}
    limits = []
    expected = (OSError, ValueError, RuntimeError, subprocess.SubprocessError, ImportError)
    if post["kind"] == "image":
        progress("OCR", 55)
        try:
            rows.extend(media.ocr_frame(path, media.ocr_languages()))
            coverage["OCR"] = "CHECKED"
        except expected as error:
            limits.append(f"OCR obrazu niedostępne ({type(error).__name__}).")
        return rows, coverage, limits

    duration, streams = media.probe(path)
    if "audio" in streams:
        progress("ASR", 10)
        try:
            speech = media.asr(path, progress=lambda fraction: progress("ASR", 12 + round(fraction * 40)))
            rows.extend(speech)
            coverage["ASR"] = "CHECKED"
            if not speech:
                limits.append("ASR nie zapisało rozpoznawalnej mowy.")
        except expected as error:
            coverage["ASR"] = "ERROR"
            limits.append(f"ASR niedostępne ({type(error).__name__}).")
    interval = 1
    progress("OCR", 55)
    limits.append(f"OCR analizuje klatkę co {interval} s oraz chwile rozpoczęcia wypowiedzi. Może pominąć krótkie napisy.")
    try:
        rows.extend(media.ocr_batch(path, duration, rows, work, interval,
                                    progress=lambda fraction: progress("OCR", 57 + round(fraction * 23))))
        coverage["OCR"] = "CHECKED"
    except expected as error:
        limits.append(f"OCR filmu niedostępne ({type(error).__name__}).")
    return rows, coverage, limits
