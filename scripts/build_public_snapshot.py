"""Build a static public snapshot from the reviewed web URLs and authored fixtures."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from investwatch.reels import database
from investwatch.discovery import simulation
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
            yield {"id": source["url"], "title": source["title"], "actor": source["actor"], "url": source["url"],
                   "modules": report["modules"], "source": "WEB", "mode": "REAL", "kind": "WEB_PAGE",
                   "published": source.get("published", ""), "first_seen": row["first_seen"], "last_seen": row["last_seen"],
                   "authorization": report["authorization"], "risk": report["risk"], "score": report["score"],
                   "findings": [{**finding, "quotes": []} for finding in report["findings"]],
                   "companies": [{"name": item["name"], "registry_url": item["registry_url"],
                                  "registry_checked_at": item.get("registry_checked_at", "")}
                                 for item in report["companies"]
                                 if (item.get("registry_url") or "").startswith("https://www.knf.gov.pl/")]}


def examples():
    fixtures = {reel: key for key, reel in json.loads(
        (DATA / "validation/module-examples/posts.json").read_text(encoding="utf-8")).items()}
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
            material = simulation({**report, "run": row["run"], "reel": row["reel"], "saved": row["saved"]})
            yield {"id": fixtures[row["reel"]], "title": material["title"].removesuffix(" · symulacja"),
                   "actor": material["actor"], "mode": "SIMULATION", "source": "LOCAL_FEED",
                   "kind": material["kind"], "modules": material["modules"], "risk": material["risk"],
                   "score": material["score"], "companies": material["companies"], "url": "", "published": "",
                   "first_seen": created[row["reel"]], "last_seen": row["saved"], "analyzed_at": row["saved"],
                   "findings": [{**finding, "quotes": finding["quotes"][:1]} for finding in material["findings"]]}


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
    print(f"Public snapshot with {len(records)} records.")


if __name__ == "__main__":
    main()
