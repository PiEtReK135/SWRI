"""Evidence-first screening; all labels are for operator review."""
import re

FINANCE = r"\b(broker\w*|maklersk\w*|cfd|forex|etf|akcj\w*|obligacj\w*|instrument\w* finansow\w*|kryptowalut\w*)\b"
CTA = r"\b(za[łl][óo][żz] konto|otwórz konto|zarejestruj|polecam|wypróbuj|użyj kodu|skorzystaj|dołącz|link w bio|mój kod|kod polecający)\b"
COUNTER = r"\b(ostrzegam|nie polecam|nie zakładaj|nie klikaj|satyra|cytat z reklamy|scam|oszustwo)\b"
DISCLOSURE = r"#reklama\b|materiał sponsorowany|płatna współpraca|współpraca reklamowa"
ADVISORY = r"indywidualn\w*|twoj\w* sytuacj\w*|twój portfel|twoj\w* potrzeb\w*|dopasuję"
TRADE = r"\b(kup|sprzedaj|trzymaj|kupić|sprzedać|nabyć|zbyć)\b"


def has(pattern, value):
    return re.search(pattern, value, re.IGNORECASE) is not None


def matches_name(name, text):
    return name and has(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text)


def screen(meta, rows, registry=()):
    evidence, entities, counter = [], {}, []
    promotion = advisory = False
    registry = [entry for entry in registry if bool(entry.get("is_demo")) == bool(meta.get("is_demo"))]
    for index, row in enumerate(rows):
        quote = row["quote"]
        start = row["start_ms"]
        neighbors = [other["quote"] for other in rows
                     if start is not None and other["start_ms"] is not None
                     and abs(start - other["start_ms"]) <= 3500]
        context = " ".join(neighbors) or quote
        matched = [entry for entry in registry if any(
            matches_name(alias, quote) for alias in [entry["name"], *entry["aliases"]])]
        for entry in matched:
            entities[entry["name"]] = entry
        financial = (has(FINANCE, context) or bool(matched)) and not has(r"książk\w*", quote)
        critical = has(COUNTER, context)
        has_cta = has(CTA, quote) and financial
        has_advice = financial and has(ADVISORY, context) and has(TRADE, quote)
        if critical and (has_cta or has_advice):
            counter.append(quote)
        elif has_cta or has_advice:
            promotion |= has_cta
            advisory |= has_advice
            evidence.append({**row, "source_offset": index, "url": meta["url"],
                             "signal": "PROMOTION" if has_cta else "PERSONAL_RECOMMENDATION",
                             "context_before": rows[index - 1]["quote"] if index else "",
                             "context_after": rows[index + 1]["quote"] if index + 1 < len(rows) else ""})
    relation = meta.get("relation", "UNKNOWN")
    official = next((entity for entity in registry if entity.get("in_scope")
                     and entity.get("publisher_url") and
                     entity["publisher_url"] == meta.get("publisher_url")
                     and bool(entity.get("is_demo")) == bool(meta.get("is_demo"))), None)
    modules = []
    if promotion:
        if relation == "FIRST_PARTY" and official:
            modules.append("M2")
            entities[official["name"]] = official
        elif relation != "FIRST_PARTY":
            modules.append("M1")
    if advisory:
        modules.append("M3")
    disclosure = any(has(DISCLOSURE, row["quote"]) for row in rows)
    return {"modules": modules, "promotion_assessment": "POSSIBLE_PROMOTION" if promotion else "NO_EVIDENCE",
            "financial_entities": list(entities.values()), "counter_indicators": counter,
            "disclosure_observed": "OBSERVED" if disclosure else "NOT_FOUND_IN_AVAILABLE_MATERIAL",
            "evidence": evidence, "publisher_relation": relation,
            "priority_score": (55 + 15 * any(item["start_ms"] is not None for item in evidence)
                               + 10 * bool(entities)) if promotion or advisory else 0,
            "relation_unverified": True, "product_legal_status": "UNASSESSED",
            "legal_conclusion": "NOT_DETERMINED",
            "human_review_required": bool(promotion or advisory),
            "rule_evaluations": [{"rule_id": "R02", "status": "NEEDS_REVIEW",
                                  "why": "Oznaczenia nie znaleziono w dostępnej próbce",
                                  "evidence": evidence}] if promotion and not disclosure else []}
