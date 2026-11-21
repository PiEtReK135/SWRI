"""Compact SQLite reports and standalone, local HTML snapshots."""

from datetime import datetime
from html import escape
import json


def pack(report):
    timeline = report.get("timeline", [])
    stored = list(timeline)
    indexes = {json.dumps(item, sort_keys=True): index for index, item in enumerate(stored)}

    def references(items):
        result = []
        for item in items:
            key = json.dumps(item, sort_keys=True)
            if key not in indexes:
                indexes[key] = len(stored)
                stored.append(item)
            result.append(indexes[key])
        return result

    def compact(items):
        return [{key: references(value) if key in {"evidence", "counter_evidence"} else value
                 for key, value in item.items()} for item in items]

    payload = {key: value for key, value in report.items() if key not in {"timeline", "rules", "reasons"}}
    payload.update(timeline_count=len(timeline), reasons=compact(report["reasons"]), rules=compact(report["rules"]))
    return payload, stored


def store_report(db, run, reel, saved, seconds, report, *, migrating=False):
    payload, stored = pack(report)
    if migrating:
        db.execute("UPDATE scan_reports SET payload=? WHERE run=? AND reel=?",
                   (json.dumps(payload, ensure_ascii=False), run, reel))
    else:
        db.execute("INSERT INTO scan_reports VALUES (?,?,?,?,?)",
                   (run, reel, saved, seconds, json.dumps(payload, ensure_ascii=False)))
    db.executemany("INSERT INTO scan_lines VALUES (?,?,?,?,?,?,?,?)", (
        (run, reel, index, row["kind"], row["start_ms"], row["end_ms"], row["quote"],
         json.dumps({key: value for key, value in row.items()
                     if key not in {"kind", "start_ms", "end_ms", "quote"}}, ensure_ascii=False))
        for index, row in enumerate(stored)
    ))


def migrate_reports(db):
    db.execute("BEGIN IMMEDIATE")
    old = db.execute("""SELECT * FROM scan_reports
                        WHERE json_type(payload,'$.timeline')='array'""").fetchall()
    for row in old:
        store_report(db, row["run"], row["reel"], row["saved"], row["seconds"],
                     json.loads(row["payload"]), migrating=True)


def unpack(db, row, detail=False):
    payload = json.loads(row["payload"])
    count = payload.pop("timeline_count", None)
    if count is None:
        return payload
    lines = {line["position"]: {**json.loads(line["metadata"]), **{key: line[key] for key in
             ("kind", "start_ms", "end_ms", "quote")}} for line in db.execute(
                 "SELECT * FROM scan_lines WHERE run=? AND reel=? ORDER BY position", (row["run"], row["reel"]))}
    for group in ("reasons", "rules") if detail else ("reasons",):
        for item in payload[group]:
            for key in ("evidence", "counter_evidence"):
                if key in item:
                    item[key] = [lines[index] for index in item[key]]
    if detail:
        payload["timeline"] = [lines[index] for index in range(count)]
    return payload


DECISIONS = {"REVIEW": "Do sprawdzenia", "FINANCE_NEUTRAL": "Finanse bez promocji",
             "OUT_OF_SCOPE": "Poza tematyką", "OUT_OF_MARKET": "Poza polskim rynkiem",
             "UNRESOLVED": "Do ponownej analizy"}
PRIORITIES = {"HIGH": "wysoki", "MEDIUM": "średni", "LOW": "niski"}


def display_date(stamp):
    return datetime.fromisoformat(stamp).astimezone().strftime("%d.%m.%Y, %H:%M:%S %z")


def snapshot(run, items):
    cards = []
    for item in items:
        reasons = "".join(f"<li>{escape(reason['text'])}</li>" for reason in item["reasons"])
        priority = PRIORITIES.get(item["risk"])
        status = DECISIONS.get(item["decision"], item["decision"])
        cards.append(f"""<article><h2>{escape(item['title'])}</h2>
<p>{escape(item.get('category', 'Temat nieustalony'))} · {escape(status)}
{f' · priorytet {priority}' if priority else ''}</p>
<p>Analiza: {escape(display_date(item['saved']))}</p><ul>{reasons}</ul></article>""")
    return f"""<!doctype html><html lang="pl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>SWRI — wyniki lokalnej analizy</title>
<style>
:root{{font:16px/1.6 system-ui;color:#0b1a38;background:#f2f6ff}}
main{{width:min(52rem,calc(100% - 2rem));margin:2rem auto}}
h1{{font-size:clamp(2rem,6vw,3.1rem);line-height:1.1}}
article{{background:#fff;border:1px solid #cad9f2;border-radius:.5rem;padding:1rem 1.2rem;margin:.8rem 0;overflow-wrap:anywhere}}
h2,p{{margin:.35rem 0}}
</style><main><h1>SWRI · Podgląd analizy rolek</h1>
<p>Analiza wykonana lokalnie. Podgląd działa jako samodzielny plik HTML.</p>
<p>Sesja: {escape(display_date(run['started']))} · {len(items)} materiałów</p>
<p>Priorytety wskazują sprawy do weryfikacji przez analityka.</p>
{''.join(cards) or '<p>W tej sesji nie zapisano wyników.</p>'}</main></html>"""
