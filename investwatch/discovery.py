"""Durable discovery jobs and an analyst inbox with explicit source provenance."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from hashlib import blake2b, file_digest, sha256
import http.client
import json
import logging
from math import sqrt
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Lock
from time import perf_counter
from urllib.parse import urlsplit

from . import analysis, collectors, media, reel_review, rules
from .reels import IMAGE, MAX_BYTES, VIDEO, database, initialize, normalize
from .store import now

logger = logging.getLogger(__name__)
CATALOG = {"META": "Biblioteka reklam Meta", "TIKTOK_ADS": "Biblioteka reklam TikToka",
           "TIKTOK_POSTS": "Oznaczone współprace na TikToku", "WEB": "Publiczne witryny WWW"}
VISUAL_RULES = {"R04", "R05", "R06", "R07", "R08", "R13"}
SEMANTIC_WITH_TEXT_ONLY = {rule["rule_id"] for rule in rules.catalog()} - VISUAL_RULES - rules.ABSENCE_BASED


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def text_embedding(blocks):
    """Sparse, deterministic lexical embedding; the semantic model is independent."""
    terms = re.findall(r"\b[^\W\d_]{3,}\b", reel_review.plain(" ".join(blocks)))
    if len(terms) < 8:
        return {}
    counts = Counter(str(int.from_bytes(blake2b(term.encode(), digest_size=2).digest(), "big")) for term in terms)
    norm = sqrt(sum(value * value for value in counts.values()))
    return {key: count / norm for key, count in counts.items()}


def entity_match(name, registry):
    exact = reel_review.plain(name)
    if not exact:
        return None
    choices = [entry for entry in registry if exact in
               {reel_review.plain(alias) for alias in (entry["name"], *entry.get("aliases", []))}]
    return choices[0] if len(choices) == 1 else None


def assess(item, registry, model=None, extracted=None):
    registry = [entry for entry in registry if not entry.get("is_demo")]
    blocks = list(dict.fromkeys(collectors.clean(block) for block in item.blocks if collectors.clean(block)))
    written = [media.segment("DESCRIPTION", part) for part in blocks]
    rows, coverage, limitations = extracted or (written, {"DESCRIPTION": "CHECKED" if written else "UNAVAILABLE",
                                                           "ASR": "UNAVAILABLE", "OCR": "UNAVAILABLE"},
                                                ["Zakres obejmuje pozyskany tekst i metadane. Brak pomiarów obrazu."])
    rows = [*written, *(row for row in rows if row["kind"] != "DESCRIPTION")]
    language = reel_review.market_language(rows)
    actor = entity_match(item.actor, registry)
    source_id = f"{item.source}:{item.publisher_id}" if item.publisher_id else ""
    publisher_url = collectors.safe_url(item.profile_url)
    profiles = [entry for entry in registry if entry.get("in_scope") and (
        (publisher_url and collectors.safe_url(entry.get("publisher_url")) == publisher_url)
        or (source_id and source_id in entry.get("publisher_ids", [])))]
    first_party = profiles[0] if len(profiles) == 1 else None
    declared = [entity_match(name, registry) for name in item.companies]
    registry_hits = [entry for entry in registry if any(
        len(alias) >= 3 and analysis.matches_name(alias, row["quote"]) for row in rows
        for alias in (entry["name"], *entry.get("aliases", [])))]
    candidates = {entry["name"]: entry for entry in [actor, first_party, *declared, *registry_hits]
                  if entry and entry.get("in_scope")}
    profile = first_party.get("publisher_url") if first_party else None
    # Restrict the model pass to plausible investment content. All captured rows reach the analyzer.
    financial = bool(candidates) or any(reel_review.matches(reel_review.FINANCE, row["quote"]) for row in rows)
    paid = item.kind == "PAID_AD"
    disclosed = item.kind == "DISCLOSED_POST"
    web_offer = item.kind == "WEB_PAGE" and (
        any(reel_review.matches(reel_review.PROMO, text)
            or all(reel_review.matches(pattern, text) for pattern in (reel_review.BROKER, reel_review.SERVICE_ACTION))
            for text in item.editorial_blocks)
        and any(reel_review.matches(reel_review.FINANCE, text) for text in item.editorial_blocks))
    contextual = (reel_review.classify({"creator": item.actor, "title": item.title}, rows, coverage,
                                       limitations, registry, profile or "", item.url, model=model,
                                       official_entity=first_party, known_promotion=bool(paid or disclosed or web_offer),
                                       semantic_keys=SEMANTIC_WITH_TEXT_ONLY if extracted is None else None)
                  if rows and financial else {})
    promotion = (web_offer if item.kind == "WEB_PAGE" else
                 paid or disclosed or contextual.get("content_type") == "PROMOTION")
    companies = [entry for entry in candidates.values() if not actor or entry["name"] != actor["name"]]
    modules = []
    findings = []
    polish_market = language == "pl" or (item.market == "REACHED_PL" and language != "foreign")
    if promotion and (language == "pl" or (first_party and polish_market)) and candidates:
        if first_party and first_party.get("market_presence") in {"PL_DOMESTIC", "PL_BRANCH"}:
            modules.append("M2")
            findings.append({"module": "M2", "text": "Materiał marketingowy powiązano z firmą z kartoteki.",
                             "points": 0, "quotes": []})
        elif not first_party and item.actor and companies and (not disclosed or language == "pl"):
            modules.append("M1")
            findings.append({"module": "M1", "text": "Publikujący różni się od firmy inwestycyjnej wskazanej w materiale.",
                             "points": 45, "quotes": [row["quote"] for row in rows if any(
                                 analysis.matches_name(entry["name"], row["quote"]) or
                                 any(analysis.matches_name(alias, row["quote"]) for alias in entry.get("aliases", []))
                                 for entry in companies)][:4]})
    # Missing captions for a disclosed record are missing evidence even if its creator is in Poland.
    if disclosed and companies and item.actor and not rows and item.market == "CREATOR_PL" and not first_party:
        modules.append("M1")
        findings.append({"module": "M1", "text": "Oznaczona współpraca z twórcą z Polski. Zweryfikuj język i treść rolki.",
                         "points": 0, "quotes": []})
    related = reel_review.advisory_offer(reel_review.author_claims(rows)) if language == "pl" else []
    authorization = ("MATCHED_IN_SCOPE" if first_party else "MATCH_NOT_CONFIRMED")
    if related and not (first_party and first_party.get("advisory_authorized")):
        modules.append("M3")
        findings.append({"module": "M3", "text": (
            "Oferta łączy indywidualną rekomendację z transakcją na instrumencie. Sprawdź status i zakres zezwolenia."),
            "points": 45 if first_party else 85, "quotes": [row["quote"] for row in related]})
    elif "M3" in contextual.get("modules", []) and not first_party and language == "pl":
        modules.append("M3")
        findings.append({"module": "M3", "text": "Sygnał indywidualnej rekomendacji. Sprawdź, czy podmiot oferuje usługę.",
                         "points": 45, "quotes": [proof["quote"] for reason in contextual["reasons"]
                                                 if reason["rule_id"] is None for proof in reason["evidence"]][:4]})
    evaluations = []
    if "M2" in modules:
        if contextual.get("rules"):
            evaluations = contextual["rules"]
        else:
            evaluations = rules.evaluate({"url": item.url, "is_demo": False}, rows, {
                "modules": ["M2"], "promotion": True, "partial": extracted is None,
                "financial_entities": list(candidates.values())})
        for rule in evaluations:
            key = rule["rule_id"]
            if (extracted is None and key in VISUAL_RULES) or (paid and key == "R02"):
                rule.update(points=0, status="UNASSESSED" if key != "R02" else "NOT_APPLICABLE",
                            why="Brak danych pomiarowych." if key != "R02" else "Rekord udokumentowanej kampanii płatnej.",
                            evidence=[], counter_evidence=[], human_review_required=key != "R02")
            elif key == "R02" and disclosed:
                rule.update(points=0, status="PASS", why="Źródło przekazało oznaczenie współpracy.",
                            evidence=[], counter_evidence=[], human_review_required=False)
            elif extracted is None and key in rules.ABSENCE_BASED and rule["points"]:
                rule.update(points=0, status="UNASSESSED", human_review_required=True,
                            why="Uzupełnij oryginalny materiał, by zweryfikować kompletność informacji.")
            if rule["points"]:
                findings.append({"module": "M2", "text": rule["title"] + ". " + rule["why"],
                                 "points": rule["points"], "rule_id": key,
                                 "quotes": [proof["quote"] for proof in rule["evidence"]]})
    if "M1" in modules and extracted and not (paid or disclosed) and not item.label and not any(
            analysis.has(analysis.DISCLOSURE, row["quote"]) for row in rows):
        findings.append({"module": "M1", "text": "Nie znaleziono oznaczenia współpracy w dostępnym materiale.",
                         "points": 60, "quotes": []})
    findings.sort(key=lambda reason: -reason["points"])
    score = max((reason["points"] for reason in findings), default=0)
    return {"modules": modules, "findings": findings, "score": score, "risk": rules.priority_level(score),
            "coverage": coverage, "limitations": limitations, "language": language, "authorization": authorization,
            "companies": list(candidates.values()), "rules": evaluations, "timeline": rows,
            "inference": contextual.get("inference"), "legal_conclusion": "NOT_DETERMINED"}


def simulation(item):
    score = max((reason.get("points") or 0 for reason in item["reasons"]), default=0)
    core = next((module for module in item["modules"] if module in {"M1", "M2"}), None)
    findings = [{"module": (
        "M3" if "M3" in item["modules"] and "Sygnał rekomendacji dopasowanej" in reason["text"] else core
    ), "text": reason["text"], "points": reason.get("points") or 0,
                 "rule_id": reason.get("rule_id"), "quotes": [proof["quote"] for proof in reason["evidence"]]}
                for reason in item["reasons"]]
    return {"id": f'{item["run"]}/{item["reel"]}', "mode": "SIMULATION", "source": "LOCAL_FEED",
            "kind": "SIMULATED_POST", "actor": item["creator"], "title": item["title"], "url": item["url"],
            "published": "", "last_seen": item["saved"], "modules": item["modules"], "review": "NEW",
            "score": score, "risk": item["risk"], "findings": findings, "coverage": item.get("coverage", {}),
            "companies": [{"name": name} for name in item["companies"]],
            "report_url": f'/api/scan/reports/{item["run"]}/{item["reel"]}',
            "legal_conclusion": "NOT_DETERMINED"}


class Discovery:
    def __init__(self, root, store, scanner):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = root / "discovery.sqlite3"
        self.store, self.scanner = store, scanner
        self.write_lock = Lock()
        config = Path(os.environ.get("IW_DISCOVERY_CONFIG") or root / "sources.json")
        self.settings = collectors.Settings.model_validate_json(config.read_text(encoding="utf-8-sig")) if config.is_file() else collectors.Settings()
        self.meta_token = os.environ.get("IW_META_AD_LIBRARY_TOKEN", "").strip()
        self.tiktok_token = os.environ.get("IW_TIKTOK_COMMERCIAL_TOKEN", "").strip()
        initialize(self.path, """
            CREATE TABLE IF NOT EXISTS collection_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, target TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'QUEUED', eligible_at TEXT NOT NULL, finished_at TEXT,
                attempts INTEGER NOT NULL DEFAULT 0, records INTEGER NOT NULL DEFAULT 0, error TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS active_collection ON collection_jobs(source,target)
                WHERE status IN ('QUEUED','RUNNING');
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL, external_id TEXT NOT NULL,
                first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, digest TEXT NOT NULL, body TEXT NOT NULL,
                analysis TEXT NOT NULL, media_name TEXT, review TEXT NOT NULL DEFAULT 'NEW',
                operator TEXT, note TEXT, UNIQUE(source,kind,external_id)
            );
            CREATE TABLE IF NOT EXISTS review_events (
                id INTEGER PRIMARY KEY, material TEXT NOT NULL REFERENCES materials(id),
                created TEXT NOT NULL, status TEXT NOT NULL, operator TEXT NOT NULL, note TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS text_embeddings (
                material TEXT PRIMARY KEY REFERENCES materials(id), vector TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS discovery_settings (id INTEGER PRIMARY KEY CHECK (id=1),
                threshold INTEGER NOT NULL, next_run TEXT NOT NULL);
            INSERT OR IGNORE INTO discovery_settings(id,threshold,next_run) VALUES (1,55,'');
            CREATE TABLE IF NOT EXISTS discovery_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, material TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS simulation_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT, material TEXT NOT NULL, created TEXT NOT NULL,
                status TEXT NOT NULL, operator TEXT NOT NULL, note TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS simulation_review_lookup ON simulation_reviews(material,id DESC);
        """)

    def sources(self):
        ready = {"META": bool(self.meta_token), "TIKTOK_ADS": bool(self.tiktok_token),
                 "TIKTOK_POSTS": bool(self.tiktok_token), "WEB": bool(self.settings.websites)}
        return [{"id": key, "name": label, "ready": ready[key],
                 "status": "READY" if ready[key] else "SETUP_REQUIRED" if key == "WEB" else "ACCESS_REQUIRED"}
                for key, label in CATALOG.items()]

    def enqueue(self, selected=None, db=None):
        if db is None:
            with database(self.path) as connection:
                return self.enqueue(selected, connection)
        sources = [item["id"] for item in self.sources() if item["ready"] and (not selected or item["id"] == selected)]
        batch = [(key, target, now()) for key in sources for target in (
            [source.url for source in self.settings.websites] if key == "WEB" else
            [""] if key == "TIKTOK_POSTS" else
            list(dict.fromkeys(term.strip()[:50] for term in self.settings.terms if term.strip())))]
        before = db.total_changes
        db.executemany("INSERT OR IGNORE INTO collection_jobs(source,target,eligible_at) VALUES(?,?,?)", batch)
        return db.total_changes - before

    def queue(self):
        with database(self.path) as db:
            jobs = [dict(row) for row in db.execute("SELECT * FROM collection_jobs ORDER BY id DESC LIMIT 40")]
            settings = dict(db.execute("SELECT * FROM discovery_settings WHERE id=1").fetchone())
        return {"jobs": jobs, "settings": settings, "sources": self.sources(), "scheduled": self.settings.scheduled,
                "interval_minutes": self.settings.interval_minutes}

    def fetch(self, job, stop):
        source, target = job["source"], job["target"]
        if source == "WEB":
            configured = next((item for item in self.settings.websites if item.url == target), None)
            if not configured:
                raise collectors.CollectionError("SOURCE_NOT_CONFIGURED")
            return collectors.websites(configured, stop)
        token = self.meta_token if source == "META" else self.tiktok_token
        if not token:
            raise collectors.CollectionError("ACCESS_REQUIRED")
        return (collectors.meta_ads(target, self.settings, token) if source == "META"
                else collectors.tiktok(source, target, self.settings, token))

    def run(self, stop):
        with database(self.path) as db:
            db.execute("UPDATE collection_jobs SET status='QUEUED' WHERE status='RUNNING'")
        while not stop.wait(1):
            with database(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                next_run = db.execute("SELECT next_run FROM discovery_settings WHERE id=1").fetchone()[0]
                if self.settings.scheduled and next_run <= now():
                    self.enqueue(db=db)
                    upcoming = datetime.now(timezone.utc) + timedelta(minutes=self.settings.interval_minutes)
                    db.execute("UPDATE discovery_settings SET next_run=? WHERE id=1",
                               (upcoming.isoformat(timespec="seconds"),))
                job = db.execute("""UPDATE collection_jobs SET status='RUNNING',attempts=attempts+1 WHERE id=(
                    SELECT id FROM collection_jobs WHERE status='QUEUED' AND eligible_at<=? ORDER BY id LIMIT 1)
                    RETURNING *""", (now(),)).fetchone()
            if job:
                self.collect(job, stop)

    def collect(self, job, stop):
        records = 0
        status, error, delay = "DONE", None, 0
        rate_limited = False
        try:
            for item in self.fetch(job, stop):
                if stop.is_set():
                    break
                self.store_material(item)
                records += 1
            if stop.is_set():
                status = "QUEUED"
        except collectors.CollectionError as failure:
            error = failure.code
            rate_limited = failure.status == 429 or error == "HTTP_429"
            retryable = rate_limited or (failure.status is not None and 500 <= failure.status <= 599)
            status = "QUEUED" if retryable and job["attempts"] < 3 else "BLOCKED"
            delay = max(failure.delay or 0, 60 * job["attempts"]) if retryable else 0
        except (OSError, http.client.HTTPException) as failure:
            error = type(failure).__name__
            status, delay = ("QUEUED" if job["attempts"] < 3 else "FAILED"), 60 * job["attempts"]
        except Exception as failure:
            # Vendor responses may embed request data. Persist and log the exception class only.
            error, status = type(failure).__name__, "FAILED"
            logger.error("Discovery job %s failed (%s)", job["id"], error)
        eligible = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec="seconds")
        with database(self.path) as db:
            db.execute("""UPDATE collection_jobs SET status=?,records=records+?,error=?,eligible_at=?,finished_at=?
                       WHERE id=?""", (status, records, error, eligible, None if status == "QUEUED" else now(), job["id"]))
            if rate_limited:
                db.execute("""UPDATE collection_jobs SET eligible_at=MAX(eligible_at,?)
                           WHERE status='QUEUED' AND source IN (?,?)""",
                           (eligible, job["source"], "TIKTOK_POSTS" if job["source"] == "TIKTOK_ADS"
                            else "TIKTOK_ADS" if job["source"] == "TIKTOK_POSTS" else job["source"]))

    def analyze(self, item, asset=None, work=None, registry=None):
        started = perf_counter()
        with self.scanner.analysis_lock:
            extracted = None
            if asset:
                extracted = reel_review.collect(asset, {"description": "", "kind": (
                    "video" if asset.suffix == ".mp4" else "image")}, work, lambda *_: None)
            report = assess(item, self.store.registry() if registry is None else registry,
                            model=self.scanner.model, extracted=extracted)
        report["seconds"] = round(perf_counter() - started, 2)
        return report

    def store_material(self, item):
        with self.write_lock:
            return self._store_material(item)

    def _store_material(self, item):
        observed = now()
        ident = sha256(dump([item.source, item.kind, item.external_id]).encode()).hexdigest()[:32]
        body = dump(item.data())
        registry = sorted((entry for entry in self.store.registry() if not entry.get("is_demo")), key=lambda entry: entry["name"])
        digest = sha256(dump([item.data(), registry]).encode()).hexdigest()
        with database(self.path) as db:
            existing = db.execute("SELECT * FROM materials WHERE id=?", (ident,)).fetchone()
            if existing and existing["digest"] == digest and (not item.temporary_video_url or existing["media_name"]):
                db.execute("UPDATE materials SET last_seen=? WHERE id=?", (observed, ident))
                return ident
        asset = self.asset(existing["media_name"]) if existing and existing["media_name"] else None
        failure = None
        if asset is None and item.source == "TIKTOK" and item.kind == "PAID_AD" and item.temporary_video_url:
            try:
                with TemporaryDirectory(dir=self.root) as folder:
                    incoming, output = Path(folder) / "input.mp4", Path(folder) / "normalized.mp4"
                    with incoming.open("wb") as file:
                        collectors.download_tiktok_video(item.temporary_video_url, self.settings.tiktok_video_hosts, file)
                    normalize(incoming, output, True)
                    asset = self.save_asset(output)
            except collectors.CollectionError as error:
                if error.code == "HTTP_429":
                    raise
                failure = error.code
            except (OSError, ValueError, http.client.HTTPException) as error:
                failure = type(error).__name__
        report = self.analyze(item, asset, self.evidence_dir(ident) if asset else None, registry)
        if asset and item.temporary_video_url:
            report["limitations"].append("Sprawdzono jeden wariant wideo udostępniony przez API kampanii.")
        if failure:
            report["limitations"].append(f"Plik kampanii niedostępny ({failure}).")
        with database(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO materials(id,source,kind,external_id,first_seen,last_seen,digest,body,analysis,media_name)
                       VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE
                       SET last_seen=excluded.last_seen,digest=excluded.digest,body=excluded.body,
                           analysis=excluded.analysis,media_name=excluded.media_name""",
                       (ident, item.source, item.kind, item.external_id, observed, observed, digest, body, dump(report),
                        asset.name if asset else None))
            db.execute("INSERT OR REPLACE INTO text_embeddings VALUES (?,?)", (ident, dump(text_embedding(item.blocks))))
            self.alert(db, ident, item.title or item.actor, report, existing)
        return ident

    def evidence_dir(self, ident):
        work = self.root / "evidence" / ident
        work.mkdir(parents=True, exist_ok=True)
        return work

    def asset(self, name):
        return self.root / "objects" / name

    def save_asset(self, output):
        with output.open("rb") as normalized:
            name = file_digest(normalized, "sha256").hexdigest() + output.suffix
        asset = self.asset(name)
        asset.parent.mkdir(exist_ok=True)
        if not asset.exists():
            output.replace(asset)
        return asset

    def attach(self, ident, filename, file):
        with self.write_lock:
            return self._attach(ident, filename, file)

    def _attach(self, ident, filename, file):
        row = self.get(ident)
        if row is None:
            raise LookupError
        suffix = Path(filename or "").suffix.lower()
        if suffix not in VIDEO | IMAGE:
            raise ValueError("Obsługiwane są MP4, MOV, WEBM, JPG, PNG i WEBP.")
        with TemporaryDirectory(dir=self.root) as folder:
            incoming = Path(folder) / ("input" + suffix)
            size = 0
            with incoming.open("wb") as target:
                while chunk := file.read(131072):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("Limit pliku to 150 MB.")
                    target.write(chunk)
            video = suffix in VIDEO
            output = Path(folder) / ("normalized.mp4" if video else "normalized.jpg")
            normalize(incoming, output, video)
            asset = self.save_asset(output)
            report = self.analyze(collectors.Material(**json.loads(row["body"])), asset, self.evidence_dir(ident))
        with database(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT * FROM materials WHERE id=?", (ident,)).fetchone()
            if current["digest"] != row["digest"] or current["media_name"] != row["media_name"]:
                raise RuntimeError("Materiał zmienił się w trakcie analizy. Ponów operację.")
            db.execute("UPDATE materials SET media_name=?,analysis=? WHERE id=?", (asset.name, dump(report), ident))
            self.alert(db, ident, json.loads(row["body"])["title"], report, current)
        return self.detail(ident)

    def get(self, ident):
        with database(self.path) as db:
            return db.execute("SELECT * FROM materials WHERE id=?", (ident,)).fetchone()

    def alert(self, db, ident, title, report, previous):
        if report["risk"] == "HIGH" and (previous is None or json.loads(previous["analysis"])["risk"] != "HIGH"):
            db.execute("INSERT INTO discovery_alerts(material,created,payload) VALUES (?,?,?)",
                       (ident, now(), dump({"id": ident, "title": title, "risk": "HIGH", "modules": report["modules"]})))

    @staticmethod
    def present(row, detail=False):
        report = json.loads(row["analysis"])
        body = json.loads(row["body"])
        result = {**body, **report, "id": row["id"], "mode": "REAL", "first_seen": row["first_seen"],
                  "last_seen": row["last_seen"], "review": row["review"], "operator": row["operator"],
                  "note": row["note"], "has_media": bool(row["media_name"])}
        if not detail:
            for key in ("timeline", "rules", "blocks"):
                result.pop(key, None)
        return result

    def detail(self, ident):
        row = self.get(ident)
        if row is None:
            return None
        item = self.present(row, True)
        item["related"] = self.related(item)
        with database(self.path) as db:
            item["review_history"] = [dict(event) for event in db.execute(
                "SELECT created,status,operator,note FROM review_events WHERE material=? ORDER BY id DESC LIMIT 25", (ident,))]
        return item

    def related(self, item):
        companies = {entry["name"] for entry in item["companies"]}
        if not companies:
            return []
        with database(self.path) as db:
            vector = db.execute("SELECT vector FROM text_embeddings WHERE material=?", (item["id"],)).fetchone()
            vector = json.loads(vector[0]) if vector else {}
            if not vector:
                return []
            records = db.execute("""SELECT id,source,kind,body,vector FROM text_embeddings
                JOIN materials ON materials.id=text_embeddings.material WHERE vector!='{}' AND id!=?
                AND EXISTS (SELECT 1 FROM json_each(analysis,'$.companies')
                            WHERE json_extract(value,'$.name') IN (SELECT value FROM json_each(?)))
                ORDER BY last_seen DESC LIMIT 500""", (item["id"], dump(sorted(companies)))).fetchall()
        hits = []
        for record in records:
            similarity = sum(vector.get(key, 0) * weight for key, weight in json.loads(record["vector"]).items())
            if similarity >= .82:
                body = json.loads(record["body"])
                hits.append({"id": record["id"], "source": record["source"], "kind": record["kind"],
                             "title": body["title"], "actor": body["actor"], "url": body["url"],
                             "similarity": min(100, round(similarity * 100))})
        return sorted(hits, key=lambda entry: -entry["similarity"])[:5]

    def simulation_detail(self, run, reel):
        raw = self.scanner.detail(run, reel)
        result = {**raw, **simulation(raw)}
        review = self.simulation_reviews().get(result["id"])
        if review:
            result.update(review=review["status"], operator=review["operator"], note=review["note"])
        with database(self.path) as db:
            result["review_history"] = [dict(event) for event in db.execute(
                "SELECT created,status,operator,note FROM simulation_reviews WHERE material=? ORDER BY id DESC LIMIT 25",
                (result["id"],))]
        return result

    def simulation_reviews(self):
        with database(self.path) as db:
            return {row["material"]: dict(row) for row in db.execute(
                "SELECT * FROM simulation_reviews WHERE id IN (SELECT MAX(id) FROM simulation_reviews GROUP BY material)")}

    def review_simulation(self, run, reel, status, operator, note):
        self.scanner.detail(run, reel)
        with database(self.path) as db:
            db.execute("INSERT INTO simulation_reviews(material,created,status,operator,note) VALUES (?,?,?,?,?)",
                       (f"{run}/{reel}", now(), status, operator, note))
        return self.simulation_detail(run, reel)

    def cases(self, mode, module, source, risk, since, until, min_score, offset, limit):
        with database(self.path) as db:
            threshold = db.execute("SELECT threshold FROM discovery_settings WHERE id=1").fetchone()[0]
        if mode == "REAL":
            with database(self.path) as db:
                rows = [self.present(row) for row in db.execute("""SELECT id,first_seen,last_seen,review,operator,note,media_name,
                    json_remove(body,'$.blocks','$.editorial_blocks') AS body,json_remove(analysis,'$.timeline','$.rules') AS analysis
                    FROM materials
                    WHERE (? IS NULL OR source=? OR EXISTS
                    (SELECT 1 FROM json_each(body,'$.platforms') WHERE value=?)) AND
                    (? IS NULL OR COALESCE(NULLIF(json_extract(body,'$.published'),''),substr(first_seen,1,10))>=?) AND
                    (? IS NULL OR COALESCE(NULLIF(json_extract(body,'$.published'),''),substr(first_seen,1,10))<=?) AND
                    (? IS NULL OR EXISTS (SELECT 1 FROM json_each(analysis,'$.modules') WHERE value=?))
                    ORDER BY json_extract(analysis,'$.score') DESC,first_seen DESC,id""",
                    (source, source, source, since, since, until, until, module, module))]
        else:
            candidates = []
            start = 0
            while True:
                page = self.scanner.reports(limit=100, offset=start)
                candidates.extend(simulation(item) for item in page["items"])
                start += len(page["items"])
                if not page["items"] or start >= page["total"]:
                    break
            rows = [item for item in candidates if (not source or item["source"] == source)
                    and (not module or module in item["modules"])
                    and (not since or item["last_seen"][:10] >= since)
                    and (not until or item["last_seen"][:10] <= until)]
            reviews = self.simulation_reviews()
            for row in rows:
                if review := reviews.get(row["id"]):
                    row.update(review=review["status"], operator=review["operator"], note=review["note"])
        if module:
            for row in rows:
                row["score"] = max((finding["points"] for finding in row["findings"]
                                    if finding["module"] == module), default=0)
                row["risk"] = rules.priority_level(row["score"])
        if risk:
            rows = [row for row in rows if row["risk"] == risk]
        today = datetime.now(timezone.utc).date()
        trends = {(today - timedelta(days=delta)).isoformat(): 0 for delta in range(13, -1, -1)}
        for datum, count in Counter((row["published"] or row.get("first_seen") or row["last_seen"])[:10]
                                    for row in rows if row["score"] >= threshold and row["modules"]).items():
            if datum in trends:
                trends[datum] = count
        counts = Counter(module for row in rows for module in row["modules"])
        matches = [row for row in rows if row["score"] >= (threshold if min_score else 0)]
        ranked = sorted(matches, key=lambda row: (row["score"], row["last_seen"], row["id"]), reverse=True)
        outcomes = Counter((row["review"], row["score"] >= threshold) for row in rows)
        return {"items": ranked[offset:offset + limit] if limit else ranked, "total": len(matches), "threshold": threshold,
                "above_threshold": sum(row["score"] >= threshold and bool(row["modules"]) for row in rows),
                "groups": dict(counts), "trend": [{"date": key, "count": value} for key, value in trends.items()],
                "calibration": {"tp": outcomes["CONFIRMED_EVIDENCE", True], "fn": outcomes["CONFIRMED_EVIDENCE", False],
                                "fp": outcomes["DISMISSED", True], "tn": outcomes["DISMISSED", False]}}

    def change_review(self, ident, status, operator, note):
        with database(self.path) as db:
            updated = db.execute("UPDATE materials SET review=?,operator=?,note=? WHERE id=?",
                                 (status, operator, note, ident)).rowcount
            if updated:
                db.execute("INSERT INTO review_events(material,created,status,operator,note) VALUES (?,?,?,?,?)",
                           (ident, now(), status, operator, note))
        return self.detail(ident)

    def set_threshold(self, value):
        with database(self.path) as db:
            db.execute("UPDATE discovery_settings SET threshold=? WHERE id=1", (value,))

    def alerts(self, after=0):
        with database(self.path) as db:
            return [{"sequence": row["id"], "created": row["created"], **json.loads(row["payload"])}
                    for row in db.execute("SELECT * FROM discovery_alerts WHERE id>? ORDER BY id LIMIT 50", (after,))]

    def alert_cursor(self):
        with database(self.path) as db:
            return db.execute("SELECT COALESCE(MAX(id),0) FROM discovery_alerts").fetchone()[0]
