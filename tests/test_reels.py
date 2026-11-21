from pathlib import Path
from socket import socket
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
import uvicorn

from investwatch.api import create_app
from investwatch.media import command, drawtext_font, ocr_batch, probe, segment
from investwatch.reel_review import classify
from investwatch.reel_scan import FeedClient, STRATEGIES, Strategy
from investwatch.reels import TOPICS


PROFILE = "http://127.0.0.1:8000/rolki?autor=example"
COVERAGE = {"DESCRIPTION": "CHECKED", "ASR": "CHECKED", "OCR": "CHECKED"}
COMPANY = {"name": "Platforma Alfa", "aliases": [], "in_scope": True, "publisher_url": PROFILE}


def result(*rows, registry=(), profile="", coverage=None):
    return classify({"creator": "example"}, rows, coverage or COVERAGE, [],
                    registry, profile, "http://127.0.0.1:8000/rolki?post=fixture")


class ClassificationTest(TestCase):
    def test_only_promotional_evidence_can_appear_in_any_channel(self):
        for channel in COVERAGE:
            with self.subTest(channel=channel):
                report = result(segment(channel, "Otwórz rachunek maklerski. Użyj kodu polecającego.", 3200))
                self.assertEqual(report["decision"], "REVIEW")
                self.assertEqual(report["modules"], ["M1"])
                self.assertEqual(report["reasons"][-1]["evidence"][0]["kind"], channel)

    def test_cross_channel_finance_and_promotional_action(self):
        report = result(segment("ASR", "Porównujemy rachunki maklerskie.", 2000),
                        segment("OCR", "Użyj kodu polecającego", 2100),
                        segment("DESCRIPTION", "Materiał sponsorowany przez Platforma Alfa."),
                        registry=[COMPANY], profile=PROFILE)
        self.assertEqual(report["modules"], ["M2"])
        self.assertEqual(report["companies"], [COMPANY["name"]])
        self.assertEqual(report["role"], "Firma")
        self.assertEqual(len(report["rules"]), 19)
        self.assertEqual(report["risk"], "LOW")

    def test_neutral_and_rejected_and_incomplete(self):
        fixtures = (
            (segment("DESCRIPTION", "Złotówka się umacnia, a bitcoin traci."), "FINANCE_NEUTRAL"),
            (segment("ASR", "Jak działają ETF-y i z czego wynika ryzyko?", 1000), "FINANCE_NEUTRAL"),
            (segment("ASR", "Ostrzegam: nie zakładaj konta u tego brokera.", 1000), "FINANCE_NEUTRAL"),
            (segment("DESCRIPTION", "Kup mój kurs robienia deserów. Gwarantowane efekty."), "OUT_OF_SCOPE"),
            (segment("OCR", "Spacer po Tatrach", 0), "OUT_OF_SCOPE"),
        )
        for row, decision in fixtures:
            with self.subTest(decision=decision, text=row["quote"]):
                self.assertEqual(result(row)["decision"], decision)
        self.assertEqual(result(segment("DESCRIPTION", "Spacer"), coverage={**COVERAGE, "ASR": "ERROR"})["decision"],
                         "UNRESOLVED")

    def test_advice_and_own_promotion_are_distinct(self):
        report = result(segment("ASR", "Na podstawie Twojej sytuacji kup akcje spółki Alfa.", 1000))
        self.assertEqual(report["modules"], ["M3"])
        self.assertEqual(report["risk"], "HIGH")
        report = result(segment("DESCRIPTION", "Mój kurs inwestowania. Kup dostęp na mojej stronie."))
        self.assertEqual(report["role"], "Autopromocja")


class RecommendationTest(TestCase):
    def test_strategy_adapts_when_reward_changes(self):
        for best in STRATEGIES:
            with self.subTest(best=best):
                strategy = Strategy()
                for _ in range(100):
                    arm = strategy.choose()
                    strategy.observe(arm, arm == best)
                self.assertGreater(strategy.trials[best], 70)
                self.assertTrue(all(strategy.trials[arm] > 0 for arm in STRATEGIES))

    def test_viewer_signals_are_isolated_and_topic_affinity_changes_feed(self):
        def normalization(_incoming, output, _video):
            output.write_bytes(b"test image")
            return 0

        with TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp))) as client, patch(
            "investwatch.reels.normalize", side_effect=normalization
        ):
            def publish(title, topic):
                response = client.post("/api/reels/posts", files={"file": ("frame.jpg", b"image")},
                                       data={"title": title, "creator": "test", "topic": topic,
                                             "rights_confirmed": "true"})
                self.assertEqual(response.status_code, 201, response.text)
                return response.json()["id"]

            first = publish("Finanse A", TOPICS[0])
            second = publish("Finanse B", TOPICS[0])
            third = publish("Kultura A", TOPICS[2])

            def top(viewer, seen=()):
                response = client.get("/api/reels/feed", params=[
                    ("viewer", viewer), ("limit", 1), *(("seen", item) for item in seen)])
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()[0]["id"]

            def react(reel, viewer, action, value=1):
                response = client.post(f"/api/reels/posts/{reel}/signals?viewer={viewer}",
                                       json={"action": action, "value": value})
                self.assertEqual(response.status_code, 204, response.text)

            self.assertEqual(top("scout-test"), third)
            react(first, "scout-test", "watch", 0.9)
            self.assertEqual(top("scout-test", (first,)), second)
            self.assertEqual(top("different-viewer"), third)
            react(third, "scout-test", "not_interested")
            self.assertNotEqual(top("scout-test"), third)
            response = client.get(f"/api/reels/posts/{first}/media", headers={"Range": "bytes=0-3"})
            self.assertEqual((response.status_code, response.content), (206, b"test"))
            self.assertEqual(client.get("/api/scan/status").json()["status"], "IDLE")

    def test_scanner_does_not_accept_external_source(self):
        with self.assertRaises(ValueError):
            FeedClient("https://example.com", "test")

    def test_batched_ocr_preserves_second_and_frame(self):
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            clip = work / "clip.mp4"
            command(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=white:s=640x360:r=12:d=4.5",
                     "-f", "lavfi", "-i", "anullsrc=duration=6.1",
                     "-vf", f"drawtext={drawtext_font()}text='BROKER ALFA':x=30:y=120:fontsize=50:"
                            "fontcolor=black:enable='between(t,2,3.5)'",
                     "-c:v", "libx264", "-c:a", "aac", "-threads", "2", str(clip)])
            duration, _ = probe(clip)
            rows = list(ocr_batch(clip, duration, [], work, 2))
            self.assertEqual([(row["start_ms"], row["quote"]) for row in rows], [(2000, "BROKER ALFA")])
            self.assertTrue((work / rows[0]["artifact"]).is_file())

    def test_published_image_reaches_scanner_via_http_with_ocr_evidence(self):
        with TemporaryDirectory() as tmp, socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(32)
            origin = "http://127.0.0.1:" + str(listener.getsockname()[1])
            root = Path(tmp)
            picture = root / "poster.jpg"
            command(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=white:s=640x360:d=1",
                     "-vf", f"drawtext={drawtext_font()}text='ZYSK BEZ RYZYKA':x=30:y=120:fontsize=50:fontcolor=black",
                     "-frames:v", "1", "-threads", "1", "-update", "1", str(picture)])
            with patch.dict("os.environ", {"IW_REELS_ORIGIN": origin}):
                application = create_app(root / "data")
            server = uvicorn.Server(uvicorn.Config(application, log_level="error"))
            thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            thread.start()
            try:
                deadline = monotonic() + 10
                while not server.started and monotonic() < deadline and thread.is_alive():
                    sleep(.05)
                self.assertTrue(server.started)
                with httpx.Client(base_url=origin, timeout=10, trust_env=False) as client:
                    published = client.post("/api/reels/posts", files={"file": ("poster.jpg", picture.read_bytes())},
                                            data={"title": "Rolka testowa", "creator": "test_e2e",
                                                  "description": "Otwórz konto u brokera Alfa.",
                                                  "rights_confirmed": "true"})
                    self.assertEqual(published.status_code, 201, published.text)
                    reel = published.json()["id"]
                    scan = client.post("/api/scan/start")
                    self.assertEqual(scan.status_code, 202, scan.text)
                    run = scan.json()["id"]
                    deadline = monotonic() + 20
                    while monotonic() < deadline:
                        response = client.get(f"/api/scan/reports/{run}/{reel}")
                        if response.status_code == 200:
                            break
                        sleep(.1)
                    else:
                        self.fail(client.get("/api/scan/status").text)
                    report = response.json()
                    self.assertEqual((report["decision"], report["risk"]), ("REVIEW", "HIGH"))
                    self.assertEqual(report["modules"], ["M1"])
                    self.assertEqual(report["coverage"]["OCR"], "CHECKED")
                    proof = report["reasons"][0]["evidence"][0]
                    self.assertEqual(proof["kind"], "OCR")
                    self.assertEqual(client.get(f"/api/scan/evidence/{run}/{reel}/{proof['artifact']}").status_code, 200)
                    self.assertEqual(client.get("/api/scan/reports?decision=REVIEW&risk=HIGH").json()["total"], 1)
                    self.assertTrue(client.get("/api/scan/ratings").json())
            finally:
                server.should_exit = True
                thread.join(12)
