from contextlib import asynccontextmanager
import hashlib
from html import escape
import json
import os
from pathlib import Path
import shutil
import tempfile
from threading import Event, Thread
from urllib.parse import urlsplit
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .store import Store, now

WEB = Path(__file__).parent / "web"
MEDIA = {".mp4", ".mp3", ".wav", ".webm", ".m4a", ".mov"}
CAPTION = {".srt", ".vtt", ".txt"}


def valid_url(url, demo=False):
    try:
        parsed = urlsplit(url)
        return (not url or (bool(parsed.hostname) and not parsed.username
                and parsed.scheme in ({"https", "http", "demo"} if demo else {"https", "http"})))
    except ValueError:
        return False


def submit(store, meta, files=()):
    with tempfile.TemporaryDirectory(dir=store.root) as directory:
        tmp = Path(directory)
        hashes = {}
        for key, source, suffix in files:
            name = key + suffix
            digest = hashlib.sha256()
            size = 0
            with (tmp / name).open("wb") as target:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    size += len(chunk)
                    if size > (5 if key == "caption" else 150) * 1024 * 1024:
                        raise HTTPException(413, "Plik przekracza limit")
                    digest.update(chunk)
                    target.write(chunk)
            hashes[key] = digest.hexdigest()
            meta[key] = name
        meta["sha256"] = hashes
        identity = {**hashes, "url": meta["url"], "description": meta["description"]}
        if hashes:
            identity.pop("url")
        identity["is_demo"] = meta["is_demo"]
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        job = uuid.uuid4().hex
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT id,status FROM jobs WHERE fingerprint=?", (fingerprint,)).fetchone()
            if old:
                return {**dict(old), "duplicate": True}
            target = store.root / job
            shutil.copytree(tmp, target)
            try:
                db.execute("INSERT INTO jobs(id,fingerprint,status,created,metadata) VALUES(?,?,?,?,?)",
                           (job, fingerprint, "QUEUED", now(), json.dumps(meta, ensure_ascii=False)))
                db.execute("INSERT INTO events(job,status,at) VALUES (?,?,?)", (job, "QUEUED", now()))
                db.commit()
            except Exception:
                shutil.rmtree(target)
                raise
        return {"id": job, "status": "QUEUED"}


def create_app(root=None):
    store = Store(root or os.environ.get("IW_DATA", "data"))

    @asynccontextmanager
    async def lifespan(app):
        stop = Event()
        from .monitor import tick
        process = Thread(target=store.run, args=(stop, tick), daemon=True)
        process.start()
        yield
        stop.set()
        process.join()

    app = FastAPI(title="InvestWatch", lifespan=lifespan)
    app.state.store = store

    @app.get("/dashboard")
    def dashboard():
        return FileResponse(WEB / "index.html")

    @app.get("/dashboard/app.js")
    def javascript():
        return FileResponse(WEB / "app.js")

    @app.post("/import/video", status_code=202)
    def import_video(video: UploadFile | None = File(None), subtitle: UploadFile | None = File(None),
                     url: str = Form("", max_length=2048), title: str = Form("", max_length=200),
                     creator: str = Form("", max_length=200), description: str = Form("", max_length=10000),
                     rights_confirmed: bool = Form(False), captions_complete: bool = Form(False),
                     relation: str = Form("UNKNOWN"), publisher_url: str = Form("", max_length=2048)):
        if not rights_confirmed:
            raise HTTPException(400, "Potwierdź uprawnienia do przekazanego materiału")
        if not valid_url(url) or not valid_url(publisher_url):
            raise HTTPException(400, "Niepoprawny adres HTTP(S)")
        if relation not in {"FIRST_PARTY", "THIRD_PARTY", "UNKNOWN"}:
            raise HTTPException(400, "Niepoprawna relacja wydawcy")
        files = []
        for key, upload, extensions in (("media", video, MEDIA), ("caption", subtitle, CAPTION)):
            if upload:
                suffix = Path(upload.filename or "").suffix.lower()
                if suffix not in extensions:
                    raise HTTPException(400, "Nieobsługiwane rozszerzenie")
                files.append((key, upload.file, suffix))
        if not files and not url:
            raise HTTPException(400, "Podaj plik lub URL")
        return submit(store, {"url": url, "title": title, "creator": creator,
                             "description": description, "relation": relation,
                             "publisher_url": publisher_url, "captions_complete": captions_complete,
                             "source_mode": "USER_PROVIDED" if files else "MANUAL_QUEUE",
                             "rights_status": "OPERATOR_CONFIRMED", "is_demo": False}, files)

    @app.post("/import/transcript", status_code=202)
    def import_transcript(subtitle: UploadFile = File(...), url: str = Form(""),
                          title: str = Form(""), creator: str = Form(""),
                          description: str = Form(""), rights_confirmed: bool = Form(False)):
        return import_video(None, subtitle, url, title, creator, description,
                            rights_confirmed, False, "UNKNOWN", "")

    def get_item(job):
        row = store.row(job)
        if row is None:
            raise HTTPException(404, "Nie znaleziono zadania")
        return row

    @app.get("/jobs")
    @app.get("/content")
    def content():
        return store.items()

    @app.get("/jobs/{job}")
    @app.get("/content/{job}")
    def item(job: str):
        return get_item(job)

    @app.get("/reports/{job}")
    def report(job: str, format: str = "json"):
        row = get_item(job)
        if not row["report"]:
            raise HTTPException(409, "Raport jeszcze niedostępny")
        with store.db() as db:
            audit = [dict(event) for event in db.execute(
                "SELECT * FROM events WHERE job=? ORDER BY id", (job,))]
        result = {**row["report"], "review": row["review"], "audit": audit,
                  "operator": row["operator"], "note": row["note"]}
        if format == "html":
            return HTMLResponse("<!doctype html><meta charset=utf-8><title>InvestWatch</title>"
                                "<h1>Raport InvestWatch</h1><pre style='white-space:pre-wrap'>" +
                                escape(json.dumps(result, indent=2, ensure_ascii=False)) + "</pre>")
        return result

    @app.get("/artifacts/{job}/{name}")
    def artifact(job: str, name: str):
        import re
        row = get_item(job)
        if name != row["metadata"].get("media") and not re.fullmatch(r"frame-\d+\.png", name):
            raise HTTPException(404)
        path = store.root / job / name
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/health")
    def health():
        return {"status": "ok", "ffmpeg": bool(shutil.which("ffmpeg")),
                "tesseract": bool(shutil.which("tesseract")), "platform_download": "NOT_APPROVED"}

    from .monitor import attach
    attach(app, store, get_item, submit)
    site_dir = os.environ.get("IW_SITE_DIR")
    if site_dir:
        site = Path(site_dir).resolve()
        if not (site / "index.html").is_file():
            raise ValueError("IW_SITE_DIR musi wskazywać wygenerowaną stronę z plikiem index.html")
        @app.get("/admin/login", include_in_schema=False)
        @app.get("/admin/login/", include_in_schema=False)
        def demo_login():
            return FileResponse(site / "index.html")

        app.mount("/", StaticFiles(directory=site, html=True), name="project-site")
    else:
        app.add_api_route("/", dashboard, include_in_schema=False)
        app.add_api_route("/app.js", javascript, include_in_schema=False)
    return app
