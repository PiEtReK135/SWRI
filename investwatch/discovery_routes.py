"""HTTP and WebSocket endpoints for the analyst workspace."""

import asyncio
import csv
from datetime import date
from io import StringIO
import re
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

from .discovery import CATALOG
from .monitor import CaseUpdate, REVIEW, Threshold
from .reel_scan import REEL_ID

Mode = Literal["REAL", "SIMULATION"]
Module = Literal["M1", "M2", "M3"]
Risk = Literal["HIGH", "MEDIUM", "LOW"]
Source = Literal["META", "FACEBOOK", "INSTAGRAM", "TIKTOK", "WEB", "LOCAL_FEED"]


def same_origin(connection):
    if connection.url.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
        return False
    origin = connection.headers.get("origin")
    if not origin:
        return True
    expected = "https" if connection.url.scheme in {"https", "wss"} else "http"
    return urlsplit(origin).scheme == expected and urlsplit(origin).netloc == connection.headers.get("host")


def local_request(request: Request):
    if not same_origin(request) or request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Panel wymaga żądania z tej samej aplikacji.")


def attach(app, workspace):
    router = APIRouter(prefix="/api/workspace", dependencies=[Depends(local_request)])

    @router.get("/sources")
    def sources():
        return workspace.queue()

    @router.post("/collect", status_code=202)
    def collect(source: str | None = None):
        if source and source not in CATALOG:
            raise HTTPException(422, "Nieznane źródło.")
        return {"queued": workspace.enqueue(source)}

    @router.get("/cases")
    def cases(mode: Mode = "REAL", module: Module | None = None, source: Source | None = None,
              risk: Risk | None = None, since: date | None = None, until: date | None = None,
              above_threshold: bool = False, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
        if since and until and since > until:
            raise HTTPException(422, "Data początkowa musi poprzedzać datę końcową.")
        return workspace.cases(mode, module, source, risk, since.isoformat() if since else None,
                               until.isoformat() if until else None, above_threshold, offset, limit)

    @router.get("/cases.csv")
    def export(mode: Mode = "REAL", module: Module | None = None, source: Source | None = None,
               risk: Risk | None = None, since: date | None = None, until: date | None = None,
               above_threshold: bool = False):
        data = cases(mode, module, source, risk, since, until, above_threshold, 0, None)
        output = StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["Tryb", "Źródło", "Rodzaj", "Moduły", "Firma", "Publikujący", "Materiał",
                         "URL", "Data publikacji", "Ostatnio pozyskany", "Waga", "Priorytet", "Status", "Główny powód"])
        for item in data["items"]:
            fields = [mode, item["source"], item["kind"], ", ".join(item["modules"]),
                      ", ".join(entry["name"] for entry in item["companies"]), item["actor"],
                      item["title"], item["url"], item["published"], item["last_seen"], item["score"],
                      item["risk"] or "", item["review"], next((finding["text"] for finding in item["findings"]), "")]
            writer.writerow([("'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value)
                             if isinstance(value, str) else value for value in fields])
        return Response("\ufeff" + output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=swri-" + mode.lower() + ".csv"})

    def material(ident):
        if not REEL_ID.fullmatch(ident) or (result := workspace.detail(ident)) is None:
            raise HTTPException(404, "Brak materiału.")
        return result

    @router.get("/cases/{ident}")
    def detail(ident: str):
        return material(ident)

    @router.get("/simulation/{run}/{reel}")
    def simulation(run: str, reel: str):
        return workspace.simulation_detail(run, reel)

    @router.patch("/simulation/{run}/{reel}")
    def review_simulation(run: str, reel: str, change: CaseUpdate):
        if change.review not in REVIEW or not change.operator.strip():
            raise HTTPException(422, "Podaj właściwy status i identyfikator analityka.")
        return workspace.review_simulation(run, reel, change.review, change.operator.strip(), change.note.strip())

    @router.patch("/cases/{ident}")
    def review(ident: str, change: CaseUpdate):
        material(ident)
        if change.review not in REVIEW or not change.operator.strip():
            raise HTTPException(422, "Podaj właściwy status i identyfikator analityka.")
        return workspace.change_review(ident, change.review, change.operator.strip(), change.note.strip())

    @router.patch("/threshold")
    def threshold(change: Threshold):
        workspace.set_threshold(change.threshold)
        return change

    @router.post("/cases/{ident}/media")
    def media(ident: str, file: UploadFile = File(...), rights_confirmed: bool = Form(False)):
        material(ident)
        if not rights_confirmed:
            raise HTTPException(422, "Potwierdź uprawnienie do wykorzystania materiału.")
        try:
            return workspace.attach(ident, file.filename, file.file)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(409, "Nie udało się ukończyć analizy pliku.") from error

    @router.get("/evidence/{ident}/{name}")
    def evidence(ident: str, name: str):
        material(ident)
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}\.jpg", name):
            raise HTTPException(404)
        path = workspace.root / "evidence" / ident / name
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"})

    app.include_router(router)

    @app.websocket("/api/workspace/alerts")
    async def live_alerts(socket: WebSocket, after: int | None = None):
        if not same_origin(socket):
            await socket.close(code=1008)
            return
        await socket.accept()
        if after is None:
            after = await asyncio.to_thread(workspace.alert_cursor)
        await socket.send_json({"type": "ready", "cursor": after})
        try:
            while True:
                for item in await asyncio.to_thread(workspace.alerts, after):
                    await socket.send_json({"type": "high_risk", **item})
                    after = item["sequence"]
                try:
                    message = await asyncio.wait_for(socket.receive(), timeout=1)
                    if message["type"] == "websocket.disconnect":
                        break
                except TimeoutError:
                    continue
        except WebSocketDisconnect:
            pass
