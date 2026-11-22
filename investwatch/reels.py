"""Local short-video platform. Discovery uses the same API as a viewer."""

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .media import command

TOPICS = ("Rynek i inwestycje", "Technologia", "Kultura", "Podróże i natura",
          "Sport", "Kuchnia", "Inne")
TOPIC_PATTERNS = (
    r"\b(?:inwest\w*|makler\w*|finans\w*|giełd\w*|bitcoin\w*|etf\w*)\b",
    r"\b(?:technolog\w*|komputer\w*|telefon\w*|oprogramowan\w*|internet\w*)\b",
    r"\b(?:kultur\w*|sztuk\w*|muzyk\w*|kolekcj\w*|wikipedi\w*|muze\w*|bibliotek\w*)\b",
    r"\b(?:podróż\w*|tatr\w*|jezior\w*|przyrod\w*|szlak\w*)\b",
    r"\b(?:sport\w*|mecz\w*|trening\w*|rower\w*|biegan\w*)\b",
    r"\b(?:kuchni\w*|gotow\w*|przepis\w*|deser\w*)\b",
)
AUDIO_SAMPLES = (
    "https://wolnelektury.pl/katalog/lektura/sonety-krymskie-stepy-akermanskie/",
    "https://wolnelektury.pl/katalog/lektura/tuwim-ptasie-radio/",
)
RETIRED_SAMPLES = (
    "https://images.nasa.gov/details/as11-40-5903",
    "https://peach.blender.org/about/",
    "https://commons.wikimedia.org/wiki/File:Gut_zu_wissen,_Wie_funktionieren_ETFs%3F_-_Tagesschau.webm",
    *AUDIO_SAMPLES,
)
VIDEO = {".mp4", ".mov", ".webm"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 150 * 1024 * 1024
MAX_SECONDS = 300
ACTIVITY = {"watch": 2.0, "like": 1.0, "save": 3.0, "share": 2.0, "comment": 2.0}


@contextmanager
def database(path):
    with closing(sqlite3.connect(path, timeout=10)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        yield connection


def initialize(path, schema):
    with closing(sqlite3.connect(path, timeout=10)) as connection, connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(schema)


def public_post(row):
    return {key: row[key] for key in (
        "id", "title", "creator", "description", "topic", "kind", "duration",
        "source", "credit", "created"
    )}


def platform_topic(title, description):
    scores = [len(re.findall(pattern, title.casefold())) + 2 * len(re.findall(pattern, description.casefold()))
              for pattern in TOPIC_PATTERNS]
    return TOPICS[scores.index(max(scores))] if any(scores) else "Inne"


class Signal(BaseModel):
    action: str
    value: float = Field(default=1, ge=0, le=1)


class Comment(BaseModel):
    text: str = Field(min_length=1, max_length=600)


def create_platform(root):
    root.mkdir(parents=True, exist_ok=True)
    assets = root / "media"
    assets.mkdir(exist_ok=True)
    path = root / "platform.sqlite3"
    initialize(path, """
        CREATE TABLE IF NOT EXISTS reels (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, creator TEXT NOT NULL, description TEXT NOT NULL,
            topic TEXT NOT NULL, kind TEXT NOT NULL, duration REAL NOT NULL, source TEXT NOT NULL,
            credit TEXT NOT NULL, created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS signals (
            viewer TEXT NOT NULL, reel TEXT NOT NULL REFERENCES reels(id), action TEXT NOT NULL,
            value REAL NOT NULL, PRIMARY KEY(viewer, reel, action)
        );
        CREATE INDEX IF NOT EXISTS signals_reel ON signals(reel, action);
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY, reel TEXT NOT NULL REFERENCES reels(id),
            text TEXT NOT NULL, viewer TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS platform_settings (key TEXT PRIMARY KEY);
    """)
    with database(path) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("INSERT OR IGNORE INTO platform_settings VALUES ('auto-topic-v1')").rowcount:
            posts = db.execute("SELECT id,title,description FROM reels").fetchall()
            db.executemany("UPDATE reels SET topic=? WHERE id=?",
                           ((platform_topic(row["title"], row["description"]), row["id"]) for row in posts))
    router = APIRouter(prefix="/api/reels")

    def existing(db, reel):
        row = db.execute("SELECT * FROM reels WHERE id=?", (reel,)).fetchone()
        if row is None or row["source"] in AUDIO_SAMPLES:
            raise HTTPException(404, "Rolka nie istnieje")
        return row

    @router.get("/feed")
    def feed(viewer: str = Query(min_length=1, max_length=80),
             limit: int = Query(8, ge=1, le=20),
             creator: str | None = Query(None, max_length=64),
             seen: list[str] = Query(default=[], max_length=200)):
        with database(path) as db:
            retired = ",".join("?" for _ in RETIRED_SAMPLES)
            posts = db.execute(f"""SELECT * FROM reels
                WHERE (? IS NULL OR creator=?) AND source NOT IN ({retired})
                ORDER BY created DESC,id""", (creator, creator, *RETIRED_SAMPLES)).fetchall()
            activities = db.execute("""
                SELECT reel, action, value, topic FROM signals JOIN reels ON signals.reel=reels.id
                WHERE viewer=?
            """, (viewer,)).fetchall()
            popularity = db.execute("""
                SELECT reel, action, SUM(value) AS value FROM signals
                WHERE viewer NOT LIKE 'scout-%' AND action NOT IN ('hide', 'not_interested')
                GROUP BY reel, action
            """).fetchall()
        excluded = set(seen)
        affinity, engagement = {}, {}
        for event in activities:
            action = event["action"]
            if action in {"hide", "not_interested"}:
                excluded.add(event["reel"])
            if action == "hide":
                continue
            weight = -3 if action == "not_interested" else ACTIVITY[action]
            topic = event["topic"]
            affinity[topic] = affinity.get(topic, 0) + weight * event["value"]
        for event in popularity:
            reel = event["reel"]
            engagement[reel] = engagement.get(reel, 0) + ACTIVITY[event["action"]] * event["value"]

        def score(item):
            topic_score = max(-6, min(6, affinity.get(item["topic"], 0)))
            return topic_score + min(4, engagement.get(item["id"], 0) ** 0.5)

        eligible = [item for item in posts if item["id"] not in excluded]
        ranked = sorted(eligible, key=score, reverse=True)
        # Leave one position for discovery when rendering a page of recommendations.
        if limit > 1 and len(ranked) > limit:
            ranked = [*ranked[:limit - 1], next(item for item in eligible if item not in ranked[:limit - 1])]
        return [public_post(item) for item in ranked[:limit]]

    @router.get("/posts/{reel}")
    def post(reel: str):
        with database(path) as db:
            return public_post(existing(db, reel))

    @router.get("/posts/{reel}/media")
    def media(reel: str):
        with database(path) as db:
            row = existing(db, reel)
        extension = ".mp4" if row["kind"] == "video" else ".jpg"
        return FileResponse(assets / (row["id"] + extension),
                            media_type="video/mp4" if row["kind"] == "video" else "image/jpeg",
                            headers={"X-Content-Type-Options": "nosniff"})

    @router.post("/posts", status_code=201)
    def publish(file: UploadFile = File(...), title: str = Form(min_length=1, max_length=120),
                creator: str = Form(min_length=1, max_length=64),
                description: str = Form("", max_length=4000),
                credit: str = Form("", max_length=280), source: str = Form("", max_length=300),
                rights_confirmed: bool = Form(False)):
        if not rights_confirmed or not title.strip() or not creator.strip(" @"):
            raise HTTPException(400, "Podaj tytuł, autora i potwierdź prawo do publikacji")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in VIDEO | IMAGE:
            raise HTTPException(415, "Wybierz MP4, MOV, WebM, JPG, PNG lub WebP")
        reel = uuid4().hex
        video = suffix in VIDEO
        extension = ".mp4" if video else ".jpg"
        limit = MAX_BYTES if video else 20 * 1024 * 1024
        with TemporaryDirectory(dir=root) as directory:
            incoming = Path(directory) / ("upload" + suffix)
            output = Path(directory) / ("media" + extension)
            with incoming.open("wb") as stream:
                for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
                    if stream.tell() + len(chunk) > limit:
                        raise HTTPException(413, "Plik przekracza limit publikacji")
                    stream.write(chunk)
            try:
                duration = normalize(incoming, output, video)
            except (ValueError, OSError, RuntimeError) as error:
                raise HTTPException(422, "Nie można odczytać pliku lub film przekracza 5 minut") from error
            destination = assets / (reel + extension)
            with database(path) as db:
                db.execute("BEGIN IMMEDIATE")
                output.replace(destination)
                try:
                    db.execute("""INSERT INTO reels VALUES (?,?,?,?,?,?,?,?,?,?)""",
                               (reel, title.strip(), creator.strip(" @"), description.strip(),
                                platform_topic(title, description),
                                "video" if video else "image", duration, source.strip(), credit.strip(),
                                datetime.now(timezone.utc).isoformat()))
                    db.commit()
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                return public_post(existing(db, reel))

    @router.post("/posts/{reel}/signals", status_code=204)
    def signal(reel: str, event: Signal, viewer: str = Query(min_length=1, max_length=80)):
        if event.action not in (ACTIVITY.keys() | {"hide", "not_interested"}) or event.action == "comment":
            raise HTTPException(400, "Nieznana reakcja")
        with database(path) as db:
            existing(db, reel)
            db.execute("""
                INSERT INTO signals VALUES (?,?,?,?) ON CONFLICT(viewer,reel,action) DO UPDATE SET
                value=CASE WHEN excluded.action='watch' THEN MAX(value,excluded.value) ELSE excluded.value END
            """, (viewer, reel, event.action, event.value))
            if event.action in {"hide", "not_interested"} and event.value == 0:
                db.execute("DELETE FROM signals WHERE viewer=? AND reel=? AND action=?", (viewer, reel, event.action))
            db.commit()

    @router.get("/posts/{reel}/engagement")
    def engagement(reel: str, viewer: str = Query(min_length=1, max_length=80)):
        with database(path) as db:
            existing(db, reel)
            counts = {row[0]: row[1] for row in db.execute("""
                SELECT action, CAST(SUM(value) AS INTEGER) FROM signals
                WHERE reel=? AND viewer NOT LIKE 'scout-%' AND action IN ('like','save','share') GROUP BY action
            """, (reel,))}
            mine = [row[0] for row in db.execute(
                "SELECT action FROM signals WHERE reel=? AND viewer=? AND value=1", (reel, viewer))]
            comments = [row[0] for row in db.execute(
                "SELECT text FROM comments WHERE reel=? ORDER BY id DESC LIMIT 50", (reel,))]
        return {"counts": counts, "mine": mine, "comments": comments}

    @router.post("/posts/{reel}/comments", status_code=201)
    def comment(reel: str, entry: Comment, viewer: str = Query(min_length=1, max_length=80)):
        if not entry.text.strip() or viewer.startswith("scout-"):
            raise HTTPException(400, "Wpisz tekst komentarza")
        with database(path) as db:
            existing(db, reel)
            db.execute("INSERT INTO comments(reel,text,viewer) VALUES (?,?,?)", (reel, entry.text.strip(), viewer))
            db.execute("INSERT OR IGNORE INTO signals VALUES (?,?,?,1)", (viewer, reel, "comment"))
            db.commit()
        return {"text": entry.text.strip()}

    return router


def normalize(incoming, output, video):
    """Decode only uploads and emit browser-friendly formats."""
    import subprocess

    from .media import probe

    try:
        if video:
            duration, streams = probe(incoming)
            if "video" not in streams or duration > MAX_SECONDS:
                raise ValueError("Brak obsługiwanego obrazu")
            command(["ffmpeg", "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file",
                     "-i", str(incoming), "-map", "0:v:0", "-map", "0:a:0?",
                     "-vf", "scale=w='min(1080,iw)':h='min(1920,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                     "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-threads", "2",
                     "-c:a", "aac", "-movflags", "+faststart", str(output)], timeout=240)
            return round(duration, 3)
        command(["ffmpeg", "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file",
                 "-i", str(incoming), "-frames:v", "1",
                 "-vf", "scale=w='min(1080,iw)':h='min(1920,ih)':force_original_aspect_ratio=decrease",
                 "-threads", "1", "-update", "1", str(output)])
        if not output.is_file():
            raise ValueError("Brak obrazu")
        return 0
    except (subprocess.SubprocessError, KeyError) as error:
        raise ValueError("Dekodowanie nie powiodło się") from error
