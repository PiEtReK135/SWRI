"""SQLite persistence and a single, restartable media worker."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time

from . import media
from .analysis import screen
from .rules import evaluate
from .verifier import verify


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, status TEXT NOT NULL,
                    created TEXT NOT NULL, metadata TEXT NOT NULL, report TEXT, reason TEXT,
                    review TEXT NOT NULL DEFAULT 'NEW', operator TEXT, note TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, job TEXT, status TEXT, at TEXT, reason TEXT
                );
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS registry (name TEXT PRIMARY KEY, data TEXT);
                CREATE TABLE IF NOT EXISTS watchlist (kind TEXT, name TEXT, reason TEXT,
                    PRIMARY KEY(kind, name));
                CREATE TABLE IF NOT EXISTS queries (id INTEGER PRIMARY KEY, data TEXT);
            """)

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.root / "investwatch.sqlite3")
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def state(self, job, status, reason=None, report=None):
        with self.db() as db:
            db.execute("UPDATE jobs SET status=?, reason=?, report=COALESCE(?,report) WHERE id=?",
                       (status, reason, json.dumps(report, ensure_ascii=False) if report else None, job))
            db.execute("INSERT INTO events(job,status,at,reason) VALUES (?,?,?,?)",
                       (job, status, now(), reason))

    def row(self, job):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
            return self.decode(row) if row else None

    @staticmethod
    def decode(row):
        result = dict(row)
        for key in ("metadata", "report"):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def items(self):
        with self.db() as db:
            return [self.decode(row) for row in db.execute("SELECT * FROM jobs ORDER BY created DESC,id")]

    def registry(self):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM registry")]

    def run(self, stop, recheck=None):
        with self.db() as db:
            db.execute("UPDATE jobs SET status='QUEUED' WHERE status IN "
                       "('ACQUIRED','TRANSCRIBING','OCR','CLASSIFYING','REPORTING')")
        next_tick = time.monotonic() + 60
        while not stop.wait(0.2):
            if recheck and time.monotonic() >= next_tick:
                recheck(self)
                next_tick = time.monotonic() + 60
            with self.db() as db:
                row = db.execute("""UPDATE jobs SET status='ACQUIRED' WHERE id=(
                    SELECT id FROM jobs WHERE status='QUEUED' ORDER BY created LIMIT 1)
                    RETURNING *""").fetchone()
                if row:
                    db.execute("INSERT INTO events(job,status,at) VALUES (?,?,?)",
                               (row["id"], "ACQUIRED", now()))
            if row:
                try:
                    self.analyze(self.decode(row))
                except Exception as error:
                    self.state(row["id"], "FAILED", f"{type(error).__name__}: {error}")

    def analyze(self, row):
        job, meta = row["id"], row["metadata"]
        work = self.root / job
        segments, gaps = [], []
        duration = None
        if meta.get("caption"):
            try:
                segments = media.captions((work / meta["caption"]).read_text(encoding="utf-8-sig"),
                                          Path(meta["caption"]).suffix)
            except (OSError, ValueError) as error:
                gaps.append(f"Napisy: {error}")
        if meta.get("media"):
            path = work / meta["media"]
            try:
                duration, streams = media.probe(path)
            except Exception:
                streams = set()
                gaps.append("Nie udało się odczytać typu lub czasu trwania pliku (limit 300 s).")
            if duration and any(item["end_ms"] is not None and item["end_ms"] > duration * 1000 + 500
                                for item in segments):
                gaps.append("Odrzucono napisy wykraczające poza czas trwania pliku.")
                segments = [item for item in segments if item["end_ms"] is None
                            or item["end_ms"] <= duration * 1000 + 500]
                meta = {**meta, "captions_complete": False}
            if "audio" in streams and (not segments or not meta.get("captions_complete")):
                self.state(job, "TRANSCRIBING")
                try:
                    segments.extend(media.asr(path))
                except Exception as error:
                    gaps.append(f"ASR niedostępne ({type(error).__name__}); sprawdź lokalny model.")
            if "video" in streams:
                self.state(job, "OCR")
                try:
                    segments.extend(media.ocr(path, duration, segments, work))
                except Exception as error:
                    gaps.append(f"OCR niepełne ({type(error).__name__}).")
                gaps.append("OCR próbkowane co 3 sekundy i w wybranych momentach napisów.")
        if not segments:
            gaps.append("Brak dostępnego tekstu z audio, napisów lub obrazu.")
        usable = bool(segments)
        if meta["description"]:
            segments.append(media.segment("DESCRIPTION", meta["description"]))
        segments.sort(key=lambda item: item["start_ms"] if item["start_ms"] is not None else -1)
        self.state(job, "CLASSIFYING")
        registry = self.registry()
        finding = screen(meta, segments, registry)
        finding["rule_evaluations"] = evaluate(meta, segments, finding)
        finding["second_pass"] = verify(finding["evidence"])
        report = {**meta, **finding, "id": job, "analyzed_at": now(),
                  "duration_seconds": duration, "collected_at": row["created"],
                  "rules_version": "1", "coverage": sorted({s["kind"] for s in segments}),
                  "timeline": segments, "limitations": gaps,
                  "source_request_id": job, "content_type": "ORGANIC_VIDEO"}
        self.state(job, "REPORTING")
        self.state(job, "COMPLETED" if usable else "ACTION_REQUIRED",
                   None if usable else "Dodaj autoryzowane napisy lub sprawdź lokalne media i modele.", report)
