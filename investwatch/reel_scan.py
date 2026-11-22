"""Opaque feed client and a separate, durable scanning queue."""

from collections import Counter
from datetime import datetime, timezone
import json
import logging
from math import log, sqrt
import os
from pathlib import Path
import re
import shutil
from threading import Event, Lock, Thread
from time import monotonic, perf_counter
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from .rules import catalog, DEFINITIONS
from .reel_llm import MODEL, ReelModel
from .reel_review import classify, collect
from .reels import database, initialize, MAX_BYTES
from .scan_history import migrate_reports, snapshot, store_report, unpack

STRATEGIES = {"Przewiń": None, "Krótszy seans": ("watch", 0.35),
              "Dłuższy seans": ("watch", 0.90), "Zapisz": ("save", 1.0)}
REJECTED = ("OUT_OF_SCOPE", "FINANCE_NEUTRAL", "OUT_OF_MARKET", "SCREENED_CLEAR")
REEL_ID = re.compile(r"[0-9a-f]{32}")
logger = logging.getLogger(__name__)


def stamp():
    return datetime.now(timezone.utc).isoformat()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class FeedClient:
    def __init__(self, origin, viewer):
        address = urlsplit(origin)
        if (address.scheme != "http" or address.hostname != "127.0.0.1" or address.path not in {"", "/"}
                or address.username or address.password or address.query or address.fragment):
            raise ValueError("Lokalny skaner wymaga adresu HTTP na 127.0.0.1")
        self.origin = origin.rstrip("/")
        self.viewer = viewer
        self.opener = build_opener(NoRedirect(), ProxyHandler({}))

    def _request(self, route, query=(), payload=None):
        target = self.origin + "/api/reels" + route
        if query:
            target += "?" + urlencode(query)
        body = json.dumps(payload).encode() if payload is not None else None
        return self.opener.open(Request(target, data=body, headers={"Content-Type": "application/json"}), timeout=15)

    def next(self, seen):
        params = [("viewer", self.viewer), ("limit", 1), *(("seen", item) for item in seen)]
        with self._request("/feed", params) as response:
            result = json.load(response)
        return result[0] if result else None

    def item(self, reel):
        with self._request(f"/posts/{reel}") as response:
            return json.load(response)

    def asset(self, item, destination):
        if not REEL_ID.fullmatch(item["id"]):
            raise ValueError("Niepoprawny identyfikator rolki w feedzie")
        with self._request(f"/posts/{item['id']}/media") as response, destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                if output.tell() + len(chunk) > MAX_BYTES:
                    raise ValueError("Przekroczono limit źródłowego pliku")
                output.write(chunk)

    def signal(self, reel, action, value=1):
        with self._request(f"/posts/{reel}/signals", {"viewer": self.viewer}, {"action": action, "value": value}):
            pass

    def source(self, post):
        return self.origin + "/rolki?post=" + post["id"]

    def profile(self, post):
        return self.origin + "/rolki?autor=" + quote(post["creator"], safe="")


class Strategy:
    """UCB balances exploration and observed relevant recommendations."""

    def __init__(self, previous=()):
        self.trials = Counter({item["name"]: item["trials"] for item in previous if item["name"] in STRATEGIES})
        self.hits = Counter({item["name"]: item["hits"] for item in previous if item["name"] in STRATEGIES})

    def choose(self):
        return max(STRATEGIES, key=lambda arm: (
            self.hits[arm] / self.trials[arm] + sqrt(2 * log(sum(self.trials.values())) / self.trials[arm])
            if self.trials[arm] else float("inf")))

    def observe(self, arm, relevant):
        self.trials[arm] += 1
        self.hits[arm] += int(relevant)

    def report(self):
        return [{"name": arm, "trials": self.trials[arm], "hits": self.hits[arm]} for arm in STRATEGIES]


class Scanner:
    def __init__(self, root, origin, registry):
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.path = root / "scan.sqlite3"
        self.origin = origin
        self.registry = registry
        self.model = ReelModel(root.parent)
        self.lock = Lock()
        self.analysis_lock = Lock()
        self.stopping = Event()
        self.thread = None
        initialize(self.path, """
            CREATE TABLE IF NOT EXISTS scan_runs (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, started TEXT NOT NULL, ended TEXT,
                current TEXT, error TEXT, strategies TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS scan_reports (
                run TEXT NOT NULL REFERENCES scan_runs(id), reel TEXT NOT NULL, saved TEXT NOT NULL,
                seconds REAL NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run,reel)
            );
            CREATE INDEX IF NOT EXISTS reports_reel ON scan_reports(reel, saved DESC);
            CREATE TABLE IF NOT EXISTS scan_lines (
                run TEXT NOT NULL, reel TEXT NOT NULL, position INTEGER NOT NULL, kind TEXT NOT NULL,
                start_ms INTEGER, end_ms INTEGER, quote TEXT NOT NULL, metadata TEXT NOT NULL,
                PRIMARY KEY(run,reel,position),
                FOREIGN KEY(run,reel) REFERENCES scan_reports(run,reel)
            );
            CREATE TABLE IF NOT EXISTS scan_settings (
                id INTEGER PRIMARY KEY CHECK(id=1), reset_at TEXT NOT NULL, viewer TEXT NOT NULL
            );
            INSERT OR IGNORE INTO scan_settings VALUES (1,'','scout-local-v2');
        """)
        with database(self.path) as db:
            migrate_reports(db)
            columns = {column["name"] for column in db.execute("PRAGMA table_info(scan_runs)")}
            if "stage" not in columns:
                db.execute("ALTER TABLE scan_runs ADD COLUMN stage TEXT")
            if "progress_percent" not in columns:
                db.execute("ALTER TABLE scan_runs ADD COLUMN progress_percent INTEGER")

    def recover(self):
        with database(self.path) as db:
            db.execute("""UPDATE scan_runs SET status='INTERRUPTED', ended=?, current=NULL, stage=NULL, progress_percent=NULL
                       WHERE status IN ('STARTING','SCANNING','WAITING','STOPPING')""", (stamp(),))

    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, reel: str | None = None):
        if reel and not REEL_ID.fullmatch(reel):
            raise HTTPException(400, "Niepoprawna rolka")
        with self.lock:
            if self.active():
                if reel:
                    raise HTTPException(409, "Poczekaj na koniec bieżącej sesji")
                return self.status()
            run = uuid4().hex
            with database(self.path) as db:
                db.execute("INSERT INTO scan_runs(id,status,started) VALUES (?,?,?)", (run, "STARTING", stamp()))
            self.stopping.clear()
            self.thread = Thread(target=self.run, args=(run, reel), name="reel-scanner", daemon=True)
            self.thread.start()
            return self.status()

    def stop(self):
        with self.lock:
            if self.active():
                self.stopping.set()
                with database(self.path) as db:
                    db.execute("""UPDATE scan_runs SET status='STOPPING'
                                  WHERE status IN ('STARTING','SCANNING','WAITING')""")
            return self.status()

    def close(self):
        self.stop()
        if self.thread:
            self.thread.join()
        self.model.close()

    def reset(self):
        with self.lock:
            if self.active():
                raise HTTPException(409, "Zatrzymaj skanowanie przed resetem")
            with database(self.path) as db:
                db.execute("UPDATE scan_settings SET reset_at=?,viewer=? WHERE id=1",
                           (stamp(), "scout-" + uuid4().hex))
            return self.status()

    def sessions(self):
        with database(self.path) as db:
            return [dict(row) for row in db.execute("""
                SELECT scan_runs.id,started,ended,status,COUNT(scan_reports.reel) AS scanned
                FROM scan_runs LEFT JOIN scan_reports ON scan_runs.id=scan_reports.run
                WHERE started>(SELECT reset_at FROM scan_settings WHERE id=1)
                GROUP BY scan_runs.id ORDER BY started DESC
            """)]

    def status(self, session: str | None = None):
        models = {"ASR": "faster-whisper " + Path(os.environ.get("IW_WHISPER_MODEL", "base")).name.removeprefix("whisper-"),
                  "OCR": "Tesseract pol+eng", "QUALIFY": MODEL if self.model.available else "Reguły lokalne",
                  "UKNF": MODEL + " i reguły" if self.model.available else "Reguły lokalne"}
        with database(self.path) as db:
            row = db.execute("""SELECT * FROM scan_runs WHERE (? IS NULL OR id=?)
                                 AND started>(SELECT reset_at FROM scan_settings WHERE id=1)
                                 ORDER BY started DESC LIMIT 1""", (session, session)).fetchone()
            if row is None:
                if session:
                    raise HTTPException(404, "Podgląd tej sesji nie jest dostępny")
                return {"status": "IDLE", "scanned": 0, "strategies": [], "models": models}
            decisions = dict(db.execute("""
                SELECT json_extract(payload,'$.decision'),COUNT(*) FROM scan_reports WHERE run=? GROUP BY 1
            """, (row["id"],)))
            average = db.execute("SELECT ROUND(AVG(seconds),2) FROM scan_reports WHERE run=?", (row["id"],)).fetchone()[0]
        return {**dict(row), "strategies": json.loads(row["strategies"]), "scanned": sum(decisions.values()),
                "decisions": decisions, "rejected": sum(decisions.get(key, 0) for key in REJECTED),
                "average_seconds": average, "models": models}

    def reports(self, decision=None, risk=None, limit=100, offset=0, session=None):
        conditions = """FROM (
            SELECT scan_reports.*, ROW_NUMBER() OVER (PARTITION BY reel ORDER BY saved DESC) AS position
            FROM scan_reports JOIN scan_runs ON scan_reports.run=scan_runs.id
            WHERE started>(SELECT reset_at FROM scan_settings WHERE id=1) AND (? IS NULL OR run=?)
        ) WHERE position=1 AND (? IS NULL OR json_extract(payload,'$.decision')=?
              OR (?='REJECTED' AND json_extract(payload,'$.decision') IN (?,?,?,?)))
          AND (? IS NULL OR json_extract(payload,'$.risk')=?)"""
        params = (session, session, decision, decision, decision, *REJECTED, risk, risk)
        order = ("COALESCE(json_extract(payload,'$.priority_count'), json_extract(payload,'$.finding_count'), 0) DESC, "
                 "CASE json_extract(payload,'$.risk') WHEN 'HIGH' THEN 3 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0 END DESC, ")
        with database(self.path) as db:
            total = db.execute("SELECT COUNT(*) " + conditions, params).fetchone()[0]
            page = db.execute("SELECT * " + conditions + " ORDER BY " + order + "saved DESC LIMIT ? OFFSET ?",
                              (*params, limit, offset)).fetchall()
            return {"total": total, "items": [self.summary(row, unpack(db, row)) for row in page]}

    def ratings(self):
        with database(self.path) as db:
            rows = db.execute("""
                SELECT payload FROM (
                    SELECT payload, ROW_NUMBER() OVER (PARTITION BY reel ORDER BY saved DESC) AS position
                    FROM scan_reports JOIN scan_runs ON scan_reports.run=scan_runs.id
                    WHERE started>(SELECT reset_at FROM scan_settings WHERE id=1)
                ) WHERE position=1 AND json_extract(payload,'$.decision')='REVIEW'
            """).fetchall()
        ratings, points = {}, Counter()
        for row in rows:
            report = json.loads(row["payload"])
            entities = report["companies"]
            groups = [("Firma", company) for company in entities]
            groups.extend(("Wzmianka o firmie", company) for company in report.get("unverified_companies", []))
            if report["role"] != "Firma" or not entities:
                groups.append((report["role"], report["creator"]))
            for role, name in set(groups):
                metrics = ratings.setdefault((role, name), Counter())
                metrics[report["risk"]] += 1
                points[(role, name)] += report.get("priority_count", report.get("finding_count", 0)) or 0
        output = []
        for (role, name), metrics in ratings.items():
            total = metrics.total()
            score = round(points[(role, name)] / total, 1)
            output.append({"name": name, "role": role, "count": total, "priority": score,
                           "criteria_count": len(DEFINITIONS), "levels": dict(metrics)})
        return sorted(output, key=lambda item: (-item["priority"], -item["count"], item["name"]))

    @staticmethod
    def summary(row, report):
        criteria_count = report.get("criteria_count")
        priority_count = report.get("priority_count", report.get("finding_count"))
        return {key: report[key] for key in (
            "title", "creator", "role", "decision", "risk", "modules", "companies", "url", "reasons"
        )} | {"run": row["run"], "reel": row["reel"], "seconds": row["seconds"], "saved": row["saved"],
              "category": report.get("category", "Temat nieustalony"), "market_language": report.get("market_language"),
              "priority_count": priority_count, "priority_percent": (
                  round(priority_count * 100 / criteria_count) if priority_count is not None and criteria_count else None),
              "content_type": report.get("content_type"),
              "uknf_status": report.get("uknf_status"), "criteria_count": criteria_count,
              "finding_count": report.get("finding_count")}

    def detail(self, run, reel):
        with database(self.path) as db:
            row = db.execute("""SELECT scan_reports.* FROM scan_reports JOIN scan_runs ON scan_reports.run=scan_runs.id
                                WHERE run=? AND reel=? AND started>(SELECT reset_at FROM scan_settings WHERE id=1)""",
                             (run, reel)).fetchone()
            if row is None:
                raise HTTPException(404, "Brak wyniku analizy")
            report = unpack(db, row, detail=True)
            return {**self.summary(row, report), **report}

    def progress(self, run, status, current=None):
        with database(self.path) as db:
            db.execute("""UPDATE scan_runs SET status=?,current=?,stage=?,progress_percent=?
                          WHERE id=? AND status!='STOPPING'""",
                       (status, current, "FETCH" if current else None, 0 if current else None, run))

    def reel_progress(self, run, stage, percent):
        with database(self.path) as db:
            db.execute("""UPDATE scan_runs SET stage=?,progress_percent=?
                          WHERE id=? AND current IS NOT NULL AND progress_percent<=?
                          AND (stage!=? OR progress_percent!=?)""", (stage, percent, run, percent, stage, percent))

    def analyze(self, client, run, post):
        work = self.root / "evidence" / run / post["id"]
        work.mkdir(parents=True, exist_ok=True)
        asset = work / ("frame-still.jpg" if post["kind"] == "image" else "clip.mp4")
        source = client.source(post)
        def progress(stage, percent):
            self.reel_progress(run, stage, percent)

        try:
            client.asset(post, asset)
            with self.analysis_lock:
                rows, coverage, limits = collect(asset, post, work, progress)
                progress("CONTEXT", 82)
                return classify(post, rows, coverage, limits, self.registry(), client.profile(post), source,
                                progress=progress, model=self.model)
        except Exception as error:
            # Keep failures in the review trail. Never label these as irrelevant.
            logger.exception("Reel analysis failed for %s", post["id"])
            return {"decision": "UNRESOLVED", "risk": None, "financial": False, "role": "Powiązanie nieustalone",
                    "uknf_status": "UNASSESSED", "criteria_count": len(DEFINITIONS),
                    "modules": [], "companies": [], "creator": post["creator"], "url": source,
                    "reasons": [{"text": "Analiza pliku nie została ukończona.", "evidence": []}],
                    "coverage": {}, "timeline": [], "rules": [], "limitations": [type(error).__name__]}
        finally:
            if post["kind"] == "video":
                asset.unlink(missing_ok=True)
            elif not asset.is_file():
                shutil.rmtree(work, ignore_errors=True)

    def run(self, run, reel=None):
        seen = []
        with database(self.path) as db:
            settings = db.execute("SELECT * FROM scan_settings WHERE id=1").fetchone()
            past = db.execute("""SELECT strategies FROM scan_runs WHERE started>? AND strategies!='[]'
                                 ORDER BY started DESC LIMIT 1""", (settings["reset_at"],)).fetchone()
        strategy = Strategy(json.loads(past[0]) if past and not reel else ())
        previous = None
        status, error = "COMPLETED", None
        waiting_since = None
        try:
            client = FeedClient(self.origin, settings["viewer"])
            while not self.stopping.is_set() and len(seen) < 200:
                item = client.item(reel) if reel else client.next(seen)
                if item is None:
                    self.progress(run, "WAITING")
                    waiting_since = waiting_since or monotonic()
                    if monotonic() - waiting_since >= 18:
                        break
                    self.stopping.wait(2)
                    continue
                if not REEL_ID.fullmatch(item["id"]) or item["id"] in seen:
                    raise ValueError("Nieprawidłowy wynik feedu")
                waiting_since = None
                self.progress(run, "SCANNING", item["title"])
                before = perf_counter()
                report = self.analyze(client, run, item)
                self.reel_progress(run, "SAVE", 98)
                if previous is not None and report["decision"] != "UNRESOLVED":
                    strategy.observe(previous, report["financial"] and report["decision"] != "OUT_OF_MARKET")
                previous = None
                report["feedback"] = "Brak ujemnego sygnału"
                if reel:
                    report["feedback"] = "Analiza ręcznie wybranej rolki. Preferencje pozostają bez zmian."
                elif report["decision"] == "OUT_OF_MARKET":
                    try:
                        client.signal(item["id"], "hide")
                        report["feedback"] = "Pominięto rolkę spoza rynku bez obniżania preferencji jej tematu."
                    except OSError:
                        report["feedback"] = "Platforma nie zapisała pominięcia rolki."
                elif report["decision"] == "OUT_OF_SCOPE":
                    try:
                        client.signal(item["id"], "not_interested")
                        report["feedback"] = "Oznaczono „Nie interesuje mnie” w profilu skanera."
                    except OSError:
                        report["feedback"] = "Platforma nie zapisała sygnału niezainteresowania."
                elif report["decision"] != "UNRESOLVED":
                    arm = strategy.choose()
                    signal = STRATEGIES[arm]
                    if signal is not None:
                        try:
                            client.signal(item["id"], *signal)
                        except OSError:
                            arm = None
                    if arm is not None:
                        previous = arm
                        report["feedback"] = "Strategia obserwacji: " + arm
                with database(self.path) as db:
                    store_report(db, run, item["id"], stamp(), round(perf_counter() - before, 2),
                                 {"title": item["title"], "kind": item["kind"], **report})
                    db.execute("UPDATE scan_runs SET stage='DONE',progress_percent=100 WHERE id=?", (run,))
                    if not reel:
                        db.execute("UPDATE scan_runs SET strategies=? WHERE id=?",
                                   (json.dumps(strategy.report(), ensure_ascii=False), run))
                seen.append(item["id"])
                if reel:
                    break
            if self.stopping.is_set():
                status = "STOPPED"
        except Exception as failure:
            logger.exception("Reel scan interrupted")
            status, error = "FAILED", type(failure).__name__
        finally:
            with database(self.path) as db:
                db.execute("UPDATE scan_runs SET status=?,ended=?,current=NULL,stage=NULL,progress_percent=NULL,error=? WHERE id=?",
                           (status, stamp(), error, run))


def scan_routes(scanner):
    router = APIRouter(prefix="/api/scan")
    router.get("/status")(scanner.status)
    router.post("/start", status_code=202)(scanner.start)
    router.post("/stop")(scanner.stop)
    router.post("/reset")(scanner.reset)
    router.get("/sessions")(scanner.sessions)
    router.get("/criteria")(catalog)
    router.get("/ratings")(scanner.ratings)
    router.get("/reports/{run}/{reel}")(scanner.detail)

    @router.get("/reports")
    def reports(decision: str | None = None, risk: str | None = None, limit: int = Query(20, ge=1, le=100),
                offset: int = Query(0, ge=0), session: str | None = None):
        return scanner.reports(decision, risk, limit, offset, session)

    @router.get("/sessions/{run}/preview")
    def preview(run: str, download: bool = False):
        state = scanner.status(run)
        if not state.get("ended"):
            raise HTTPException(409, "Podgląd będzie dostępny po zakończeniu sesji")
        items = scanner.reports(limit=-1, session=run)["items"]
        headers = {"Content-Disposition": f'attachment; filename="swri-podglad-{run[:10]}.html"'} if download else {}
        return HTMLResponse(snapshot(state, items), headers=headers)

    @router.get("/evidence/{run}/{reel}/{name}")
    def evidence(run: str, reel: str, name: str):
        if (not REEL_ID.fullmatch(run) or not REEL_ID.fullmatch(reel)
                or not re.fullmatch(r"frame-(?:[0-9]+\.png|still\.jpg)", name)):
            raise HTTPException(404)
        scanner.status(run)
        path = scanner.root / "evidence" / run / reel / name
        if not path.is_file():
            raise HTTPException(404, "Brak klatki")
        return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})

    return router
