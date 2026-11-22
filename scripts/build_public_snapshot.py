"""Build a static public snapshot from the reviewed web URLs and authored fixtures."""

from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from investwatch.reels import database
from investwatch.scan_history import unpack

DATA = Path("data")
OUTPUT = Path("docs/online")
MODULES = {
    "M1": "Monitoring reklam",
    "M2": "Informacje o ryzyku",
    "M3": "Shadow Advisory",
}
PUBLIC_WEB = {
    "https://www.xtb.com/pl",
    "https://www.tms.pl/konto-maklerskie",
    "https://bossa.pl/oferta/otwarcie-rachunku",
    "https://www.bm.pkobp.pl/oferta/rachunek-inwestycyjny",
    "https://www.bdm.pl/bdm-podstawowy",
    "https://www.bdm.pl/rachunek-inwestycyjny",
}


def actual():
    with database(DATA / "discovery/discovery.sqlite3") as db:
        for row in db.execute("SELECT body,analysis,first_seen,last_seen FROM materials WHERE source='WEB'"):
            source, report = json.loads(row["body"]), json.loads(row["analysis"])
            if source["url"] not in PUBLIC_WEB or report["authorization"] != "MATCHED_IN_SCOPE" or not report["modules"]:
                continue
            yield {"title": source["title"], "publisher": source["actor"], "url": source["url"],
                   "modules": report["modules"], "source": "Oficjalna publiczna strona WWW", "mode": "REAL",
                   "first_recorded_at": row["first_seen"], "last_seen_at": row["last_seen"],
                   "findings": [{"rule": rule.get("rule_id"), "label": rule["title"], "status": rule["status"]}
                                for rule in report["rules"] if rule["points"]],
                   "registry": [{"name": item["name"], "url": item["registry_url"]}
                                for item in report["companies"]
                                if item.get("registry_url", "").startswith("https://www.knf.gov.pl/")]}


def examples():
    fixtures = set(json.loads((DATA / "validation/module-examples/posts.json").read_text(encoding="utf-8")).values())
    with database(DATA / "reels/platform.sqlite3") as feed:
        created = {row["id"]: row["created"] for row in feed.execute("SELECT id,created FROM reels") if row["id"] in fixtures}
    with database(DATA / "reel-scan/scan.sqlite3") as db:
        seen = set()
        for row in db.execute("""SELECT * FROM scan_reports WHERE json_extract(payload,'$.scenario')=1
                              ORDER BY saved DESC,run DESC"""):
            if row["reel"] not in created or row["reel"] in seen:
                continue
            seen.add(row["reel"])
            report = unpack(db, row)
            if not report["modules"]:
                continue
            yield {"title": report["title"].removesuffix(" · symulacja"), "publisher": report["creator"],
                   "mode": "SIMULATION", "source": "Autorski scenariusz ćwiczeniowy SWRI", "modules": report["modules"],
                   "first_recorded_at": created[row["reel"]], "analyzed_at": row["saved"],
                   "findings": [{"rule": reason.get("rule_id"), "label": reason["text"],
                                 "quote": (reason["evidence"][0]["quote"] if reason["evidence"] else "")}
                                for reason in report["reasons"][:3]]}


def times(value):
    safe = escape(value, quote=True)
    return f'<time datetime="{safe}">{escape(value[:19].replace("T", " "))} UTC</time>'


def card(row):
    source = (f'<a href="{escape(row["url"], quote=True)}">Oryginał publikacji</a>' if row.get("url") else "")
    date_field = "Utworzono w feedzie" if row["mode"] == "SIMULATION" else "Pierwszy zapis w SWRI"
    other_time = (("Analiza", row["analyzed_at"]) if row.get("analyzed_at")
                  else ("Ostatnia obserwacja zapisana przez SWRI", row["last_seen_at"]))
    rows = []
    for finding in row["findings"]:
        rule = escape(finding["rule"] + " · ") if finding.get("rule") else ""
        quote = f'<blockquote>{escape(finding["quote"])}</blockquote>' if finding.get("quote") else ""
        rows.append(f'<li>{rule}{escape(finding["label"])}{quote}</li>')
    details = (f'<details><summary>Sygnały w raporcie</summary><ul>{"".join(rows)}</ul></details>' if rows else "")
    registry = " · ".join(f'<a href="{escape(item["url"], quote=True)}">Wpis KNF · {escape(item["name"])}</a>'
                          for item in row.get("registry", []))
    links = (" · ".join(filter(None, [source, registry])))
    return f'''<article><p class="source">{escape(row["source"])}</p><h4>{escape(row["title"])}</h4>
      <p>{escape(row["publisher"])}</p>
      <dl><dt>{date_field}</dt><dd>{times(row["first_recorded_at"])}</dd>
      <dt>{other_time[0]}</dt><dd>{times(other_time[1])}</dd></dl>
      <p>{links}</p>{details}</article>'''


def section(mode, heading, description, records):
    groups = []
    for key, name in MODULES.items():
        entries = [row for row in records if row["mode"] == mode and key in row["modules"]]
        content = "".join(map(card, entries)) or "<p>Brak materiałów w tej migawce.</p>"
        groups.append(f'<section id="{mode.lower()}-{key.lower()}"><h3>{key} · {name} <span>{len(entries)}</span></h3>'
                      f'<div class="cards">{content}</div></section>')
    return f'<section id="{mode.lower()}"><h2>{heading}</h2><p>{description}</p>{"".join(groups)}</section>'


def render(records, generated):
    actual_section = section("REAL", "Dane rzeczywiste",
                             "Publiczne oferty ze zweryfikowanych witryn. Raporty są przesiewowe.", records)
    sample_section = section("SIMULATION", "Symulacja", "Autorskie przykłady. Postacie i oferty są fikcyjne.", records)
    return f'''<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SWRI · Monitoring rynku</title><style>
:root{{color-scheme:dark;--ink:#f1f3ff;--muted:#c0c9e1;--card:#171e36;--line:#405077;--link:#b7c9ff}}
*{{box-sizing:border-box}} body{{margin:0;background:#0d1226;color:var(--ink);font:1rem/1.55 system-ui,sans-serif}}
header,main{{max-width:76rem;margin:auto;padding:1.25rem}} header{{padding-block:2.5rem 1.3rem}}
h1{{font-size:clamp(2.4rem,6vw,4.2rem);margin:.1rem 0;line-height:1.07;letter-spacing:-.045em}}
h2{{font-size:clamp(1.7rem,4vw,2.5rem);margin:1.75rem 0 .2rem}} h3{{margin:1.4rem 0 .5rem}}
h4{{font-size:1.1rem;margin:.12rem 0}} h3 span{{color:#9deadd;font-size:.9rem;margin-inline:.4rem}}
p{{margin:.35rem 0}} .source,dt,header p{{color:var(--muted)}} .source{{font-size:.87rem}}
nav{{display:flex;gap:.75rem;flex-wrap:wrap;margin-top:1.1rem}} nav a{{padding:.4rem .7rem;border:1px solid var(--line);border-radius:.35rem}}
a,summary{{color:var(--link)}} summary{{cursor:pointer}} .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,21rem),1fr));gap:.7rem}}
article{{background:var(--card);border:1px solid var(--line);border-radius:.55rem;padding:1rem;min-width:0;overflow-wrap:anywhere}}
dt{{font-size:.84rem}} dd{{margin:0 0 .35rem}} blockquote{{margin:.3rem .4rem;padding-left:.45rem;border-left:2px solid #9deadd;color:var(--muted)}}
:focus-visible{{outline:3px solid #9deadd;outline-offset:3px}} li{{margin:.25rem 0}}
</style></head><body><header><p>SWRI / InvestWatch</p><h1>Monitoring rynku</h1>
<p>Stan z {times(generated)}. Czasy w strefie Europe/Warsaw. Analiza wykonana lokalnie.</p>
<nav aria-label="Sekcje"><a href="#real">Dane rzeczywiste</a><a href="#simulation">Symulacja</a>
<a href="snapshot.json" download>Pobierz dane JSON</a></nav></header>
<main>{actual_section}{sample_section}</main>
<script>
const format = new Intl.DateTimeFormat('pl-PL', {{dateStyle:'medium',timeStyle:'medium',timeZone:'Europe/Warsaw'}});
for (const node of document.querySelectorAll('time')) {{
  const date = new Date(node.dateTime);
  if (!Number.isNaN(date.getTime())) node.textContent = format.format(date);
}}
</script></body></html>'''


def main():
    records = [*actual(), *examples()]
    real_m2 = sum(row["mode"] == "REAL" and "M2" in row["modules"] for row in records)
    if real_m2 < 5:
        raise SystemExit(f"M2: znaleziono {real_m2}/5 raportów z publicznych witryn")
    for module in MODULES:
        count = sum(row["mode"] == "SIMULATION" and module in row["modules"] for row in records)
        if count < 5:
            raise SystemExit(f"{module}: w symulacji znaleziono {count}/5 przykładów")
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "snapshot.json").write_text(
        json.dumps({"generated_at": generated, "timezone": "Europe/Warsaw", "records": records},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / "index.html").write_text(render(records, generated) + "\n", encoding="utf-8")
    print(f"Public snapshot with {len(records)} records.")


if __name__ == "__main__":
    main()
