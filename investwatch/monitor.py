"""Local discovery and review. Source URLs are data, never HTTP request targets."""
import asyncio
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import subprocess
from pathlib import Path
from typing import Literal
import uuid

from fastapi import File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from .store import now
from .rules import catalog

SEEDS = {
    "FINANCIAL_TOPICS": ["konto maklerskie", "kontrakty CFD", "doradztwo inwestycyjne"],
    "NON_FINANCIAL_CONTEXT": ["jesienny vlog w górach", "fitness", "motoryzacja", "technologia"],
}
REVIEW = {"NEW", "IN_REVIEW", "CONFIRMED_EVIDENCE", "DISMISSED"}
BLOCKS = {"CAPTCHA", "LOGIN", "403", "429", "UNAVAILABLE"}


class Watch(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class RegistryEntry(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    publisher_url: str = ""
    publisher_ids: list[str] = Field(default_factory=list, max_length=30)
    advisory_authorized: bool | None = None
    market_presence: Literal["PL_DOMESTIC", "PL_BRANCH", "CROSS_BORDER", "UNSPECIFIED"] = "UNSPECIFIED"
    registry_url: str
    registry_checked_at: str
    in_scope: bool = False


class CaseUpdate(BaseModel):
    review: str
    operator: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=1000)


class Threshold(BaseModel):
    threshold: int = Field(ge=0, le=100)


class Observation(BaseModel):
    status: str
    note: str = Field(default="", max_length=500)


def event(db, job, status, reason=None):
    db.execute("INSERT INTO events(job,status,at,reason) VALUES (?,?,?,?)", (job, status, now(), reason))


def tick(store):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    with store.db() as db:
        for row in db.execute("""SELECT id,report,metadata FROM jobs WHERE status='COMPLETED'
            AND NOT EXISTS (SELECT 1 FROM events WHERE job=jobs.id
            AND status IN ('RECHECK_REQUIRED','SOURCE_CHECKED') AND at>=?)""", (cutoff,)):
            result, meta = json.loads(row["report"]), json.loads(row["metadata"])
            if meta["url"].startswith(("https://", "http://")) and result["modules"] and result["analyzed_at"] < cutoff:
                event(db, row["id"], "RECHECK_REQUIRED", "Sprawdź URL i rejestr ręcznie, a następnie zapisz obserwację.")


def attach(app, store, get_item, submit):
    from .api import valid_url

    @app.post("/import/urls", status_code=202)
    def urls(file: UploadFile = File(...), rights_confirmed: bool = Form(False)):
        if not rights_confirmed:
            raise HTTPException(400, "Potwierdź prawo do importu metadanych")
        try:
            data = file.file.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise HTTPException(413, "Limit 2 MB")
            raw = data.decode("utf-8-sig")
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in {".json", ".csv"}:
                raise ValueError
            records = json.loads(raw) if suffix == ".json" else list(csv.DictReader(io.StringIO(raw)))
            if not isinstance(records, list) or len(records) > 500:
                raise ValueError
            records = [{"url": item} if isinstance(item, str) else item for item in records]
            if any(not isinstance(item, dict) or not isinstance(item.get("url"), str)
                   or not item["url"] or len(item["url"]) > 2048 or not valid_url(item["url"]) for item in records):
                raise ValueError
        except (ValueError, csv.Error):
            raise HTTPException(400, "Oczekiwano CSV z kolumną url lub JSON z listą URL/obiektów")
        return [submit(store, {"url": item["url"], "title": str(item.get("title", ""))[:200],
                               "creator": str(item.get("creator", ""))[:200],
                               "description": str(item.get("description", ""))[:10000], "relation": "UNKNOWN",
                               "source_mode": "SEARCH_SEED", "rights_status": "OPERATOR_CONFIRMED",
                               "is_demo": False}) for item in records]

    @app.post("/demo/run", status_code=202)
    def demo():
        from .demo import seed
        try:
            return seed(store, submit)
        except (OSError, subprocess.SubprocessError) as error:
            raise HTTPException(503, "Demo wymaga FFmpeg z filtrem drawtext i czcionkami") from error

    @app.get("/sources")
    def sources():
        return {"USER_PROVIDED": "AVAILABLE", "MANUAL_QUEUE": "AVAILABLE", "SEARCH_SEED": "CSV_JSON_IMPORT",
                "DEMO_ORGANIC_FEED": "AVAILABLE", "AUTHORIZED_PUBLIC_VIDEO_API": "NOT_APPROVED",
                "AUTHORIZED_BROWSER": "NOT_APPROVED", "media_download": False}

    @app.post("/discovery/run")
    def discovery():
        plan_id = uuid.uuid4().hex
        with store.db() as db:
            seeds = [(kind, query, "") for kind, queries in SEEDS.items() for query in queries]
            seeds.extend(("WATCHLIST_" + row["kind"], row["name"], row["reason"])
                         for row in db.execute("SELECT * FROM watchlist"))
            drafts = [{"query": query, "sampling_stratum": kind, "source": "SEARCH_SEED",
                       "status": "ACTION_REQUIRED", "planned_at": now(), "query_version": "1",
                       "run_id": plan_id, "intent": reason or kind,
                       "expected_signal": "Potencjalna promocja organiczna",
                       "next_action": "Wyszukaj ręcznie i zaimportuj dostępne metadane."}
                      for kind, query, reason in seeds]
            db.executemany("INSERT INTO queries(data) VALUES (?)",
                           [(json.dumps(query, ensure_ascii=False),) for query in drafts])
        return drafts

    @app.get("/discovery/queries")
    def queries():
        with store.db() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM queries ORDER BY id DESC LIMIT 200")]

    @app.get("/watchlist")
    def watchlist():
        with store.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM watchlist ORDER BY kind,name")]

    @app.post("/watchlist")
    def watch(item: Watch):
        if item.kind not in {"CREATORS", "ENTITIES"}:
            raise HTTPException(400, "Niepoprawny typ listy")
        with store.db() as db:
            db.execute("INSERT OR REPLACE INTO watchlist VALUES(?,?,?)", (item.kind, item.name, item.reason))
        return item

    @app.post("/entities")
    def add_entity(item: RegistryEntry):
        if not item.registry_url or not valid_url(item.registry_url) or not valid_url(item.publisher_url):
            raise HTTPException(400, "Podaj poprawne adresy HTTP(S)")
        try:
            datetime.fromisoformat(item.registry_checked_at)
        except ValueError:
            raise HTTPException(400, "Podaj datę weryfikacji w formacie ISO")
        row = {**item.model_dump(), "registry_status": "OPERATOR_RECORDED", "is_demo": False}
        with store.db() as db:
            db.execute("INSERT OR REPLACE INTO registry VALUES(?,?)",
                       (item.name, json.dumps(row, ensure_ascii=False)))
        return row

    @app.get("/entities")
    def entities():
        return store.registry()

    @app.get("/creators")
    def creators():
        return sorted({row["metadata"]["creator"] for row in store.items() if row["metadata"]["creator"]})

    @app.get("/rules")
    def rules():
        return catalog()

    @app.get("/cases")
    def cases():
        return [row for row in store.items() if (row["report"] or {}).get("human_review_required")]

    @app.get("/cases/{job}")
    def case(job: str):
        return get_item(job)

    @app.patch("/cases/{job}")
    def review(job: str, change: CaseUpdate):
        get_item(job)
        if change.review not in REVIEW:
            raise HTTPException(400, "Niepoprawny status oceny")
        with store.db() as db:
            db.execute("UPDATE jobs SET review=?,operator=?,note=? WHERE id=?",
                       (change.review, change.operator, change.note, job))
            event(db, job, change.review, f"{change.operator}: {change.note}")
        return get_item(job)

    @app.post("/jobs/{job}/cancel")
    @app.post("/jobs/{job}/retry")
    def change(job: str, request: Request):
        get_item(job)
        retry = request.url.path.endswith("/retry")
        with store.db() as db:
            if retry:
                result = db.execute("""UPDATE jobs SET status='QUEUED', reason=NULL WHERE id=?
                     AND status IN ('FAILED','CANCELLED','COMPLETED','ACTION_REQUIRED')
                     AND NOT EXISTS (SELECT 1 FROM events WHERE job=? AND status='SOURCE_BLOCKED'
                         AND id>(SELECT COALESCE(MAX(id),0) FROM events WHERE job=? AND status='SOURCE_CHECKED'))""",
                    (job, job, job))
            else:
                result = db.execute("UPDATE jobs SET status='CANCELLED' WHERE id=? AND status='QUEUED'", (job,))
            if not result.rowcount:
                raise HTTPException(409, "Trwa analiza lub wymagane jest ręczne sprawdzenie źródła")
            event(db, job, "QUEUED" if retry else "CANCELLED")
        return get_item(job)

    @app.post("/content/{job}/source-observation")
    def observation(job: str, check: Observation):
        get_item(job)
        if check.status not in BLOCKS | {"AVAILABLE", "CHANGED"}:
            raise HTTPException(400, "Niepoprawny stan źródła")
        with store.db() as db:
            status = "SOURCE_BLOCKED" if check.status in BLOCKS else "SOURCE_CHECKED"
            event(db, job, status, f"{check.status}: {check.note}")
        return {"status": status}

    def threshold():
        with store.db() as db:
            value = db.execute("SELECT value FROM settings WHERE name='threshold'").fetchone()
        return int(value[0]) if value else 55

    @app.patch("/settings/threshold")
    def calibrate(value: Threshold):
        with store.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES('threshold',?)", (str(value.threshold),))
        return value

    @app.get("/metrics")
    def metrics():
        rows = store.items()
        scores = [(row["report"] or {}).get("priority_score", 0) for row in rows]
        minimum = threshold()
        days = sorted({row["created"][:10] for row in rows})[-14:]
        trend = [{"day": day, "alerts": sum(row["created"].startswith(day) and 0 < score >= minimum
                   for row, score in zip(rows, scores))} for day in days]
        return {"threshold": minimum, "total": len(rows), "alerts": sum(0 < score >= minimum for score in scores),
                "trend": trend,
                "states": {status: sum(row["status"] == status for row in rows)
                           for status in sorted({row["status"] for row in rows})}}

    @app.get("/reports.csv")
    def csv_report():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "demo", "creator", "url", "modules", "score", "review"])
        def cell(value):
            return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
        for item in store.items():
            meta, finding = item["metadata"], item["report"] or {}
            writer.writerow([item["id"], meta["is_demo"], cell(meta["creator"]), cell(meta["url"]),
                             ",".join(finding.get("modules", [])), finding.get("priority_score"), item["review"]])
        return Response(output.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=investwatch.csv"})

    @app.get("/alerts")
    def alerts():
        with store.db() as db:
            events = [dict(row) for row in db.execute("""SELECT * FROM events WHERE status IN
                     ('ACTION_REQUIRED','SOURCE_BLOCKED','RECHECK_REQUIRED','FAILED') ORDER BY id DESC LIMIT 100""")]
        minimum = threshold()
        events.extend({"job": row["id"], "status": "PRIORITY_ALERT", "at": row["report"]["analyzed_at"],
                       "reason": f"Priorytet {row['report']['priority_score']}"}
                      for row in store.items() if 0 < (row["report"] or {}).get("priority_score", 0) >= minimum)
        return sorted(events, key=lambda row: row["at"], reverse=True)

    @app.get("/events/stream")
    async def stream(request: Request, after: int = 0):
        try:
            after = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            pass
        async def updates():
            cursor = after
            while True:
                with store.db() as db:
                    batch = [dict(row) for row in db.execute(
                        "SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100", (cursor,))]
                for row in batch:
                    cursor = row["id"]
                    yield f"id: {cursor}\ndata: {json.dumps(row)}\n\n"
                if not batch:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(updates(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
