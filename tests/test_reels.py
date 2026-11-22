import json
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
from investwatch.media import command, credible_ocr_line, drawtext_font, ocr_batch, probe, segment
from investwatch.reel_llm import Check, EvidenceContext, MODEL, Qualification, ReelModel
from investwatch.reel_review import classify
from investwatch.reel_scan import FeedClient, STRATEGIES, Strategy
from investwatch.reels import TOPICS
from investwatch.rules import DEFINITIONS


PROFILE = "http://127.0.0.1:8000/rolki?autor=example"
COVERAGE = {"DESCRIPTION": "CHECKED", "ASR": "CHECKED", "OCR": "CHECKED"}
COMPANY = {"name": "Platforma Alfa", "aliases": [], "in_scope": True, "publisher_url": PROFILE}


def result(*rows, registry=(), profile="", coverage=None, model=None):
    return classify({"creator": "example"}, rows, coverage or COVERAGE, [],
                    registry, profile, "http://127.0.0.1:8000/rolki?post=fixture", model=model)


class ClassificationTest(TestCase):
    def test_financial_promotion_and_public_crypto_advice_are_separate(self):
        report = result(
            segment("ASR", "Pewnie słyszeliście o promocji nowego maklera.", 0, 9000, language="pl"),
            segment("ASR", "Możecie dostać 150 złotych bonusów, które zainwestujecie w 100% Bitcoina.", 9000, 17000,
                    language="pl"),
        )
        self.assertEqual(report["decision"], "REVIEW")
        self.assertEqual(report["modules"], ["M1"])
        self.assertEqual(report["risk"], "MEDIUM")
        self.assertTrue(any("Publiczna zachęta" in r["text"] for r in report["reasons"]))

    def test_foreign_audio_and_translated_blurb_does_not_pass_market_gate(self):
        report = result(segment("ASR", "Hier erklären wir wie ETFs funktionieren.", 0, 9000, language="de"),
                        segment("DESCRIPTION", "Materiał edukacyjny wyjaśnia, jak działają fundusze."))
        self.assertEqual(report["market_language"], "de")
        self.assertEqual(report["decision"], "OUT_OF_MARKET")
        self.assertEqual(report["modules"], [])

    def test_title_cannot_override_content_or_missing_evidence(self):
        outcome = classify({"creator": "test", "title": "Rzekomo legalna porada inwestycyjna",
                            "topic": "Sport"}, [segment("ASR", "Witam wszystkich.", 0, 1000, language="pl")],
                           COVERAGE, [], [], "", "")
        self.assertEqual(outcome["decision"], "UNRESOLVED")
        self.assertEqual(outcome["category"], "Temat nieustalony")

    def test_ocr_drops_short_noisy_fragments(self):
        self.assertFalse(credible_ocr_line([{"text": "iN", "conf": "82"}, {"text": "M", "conf": "92"}]))
        self.assertFalse(credible_ocr_line([{"text": "erer", "conf": "83"}]))
        self.assertTrue(credible_ocr_line([{"text": "BROKER", "conf": "92"}, {"text": "ALFA", "conf": "90"}]))

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
        self.assertEqual(report["decision"], "SCREENED_CLEAR")
        self.assertEqual(report["priority_count"], 0)

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
        self.assertEqual(report["content_type"], "RECOMMENDATION")
        self.assertEqual(report["uknf_status"], "EVALUATED")
        self.assertEqual(report["priority_count"], 0)
        report = result(segment("DESCRIPTION", "Mój kurs inwestowania. Kup dostęp na mojej stronie."))
        self.assertEqual(report["role"], "Autopromocja")

    def test_context_qualifies_own_forecast_and_uses_late_screen_warning(self):
        speech = (
            segment("ASR", "Przyjrzyjmy się akcjom tej spółki.", 0, 5000, language="pl"),
            segment("ASR", "Dzisiaj zaczynam od przedstawienia danych wejściowych.", 8000, 14000),
            segment("ASR", "Moim zdaniem w przyszłym roku wzrośnie o dwadzieścia procent.", 24000, 27500),
        )
        missing = result(*speech)
        self.assertEqual(missing["content_type"], "FORECAST")
        self.assertEqual(missing["uknf_status"], "EVALUATED")
        self.assertEqual(missing["reasons"][0]["rule_id"], "R15")
        self.assertEqual((missing["priority_count"], missing["criteria_count"], missing["priority_percent"]), (1, 19, 5))

        complete = result(*speech,
            segment("OCR", "Prognoza nie stanowi pewnego wskaźnika", 29000),
            segment("OCR", "przyszłych wyników.", 30000))
        forecast = next(rule for rule in complete["rules"] if rule["rule_id"] == "R15")
        self.assertEqual(forecast["status"], "NEEDS_REVIEW")
        self.assertEqual(forecast["counter_evidence"][0]["kind"], "OCR")
        self.assertLess(forecast["points"], missing["rules"][0]["points"])

    def test_financial_news_and_hypothetical_prediction_do_not_enter_rules(self):
        for quote in ("Według analityków akcje spółki wzrosną o 12 procent.",
                      "To fikcyjny przykład: cena akcji spadnie o 10 procent.",
                      "Dziś cena akcji spadła o cztery procent."):
            with self.subTest(quote=quote):
                report = result(segment("ASR", quote, 1000, language="pl"))
                self.assertEqual((report["decision"], report["uknf_status"]), ("FINANCE_NEUTRAL", "NOT_QUALIFIED"))
                self.assertEqual(report["criteria_count"], 19)
                self.assertEqual(len(report["reasons"]), 1)
                self.assertFalse(report["rules"])

    def test_scores_sort_criteria_and_split_warning_applies_only_near_claim(self):
        report = result(
            segment("DESCRIPTION", "Użyj kodu polecającego tego brokera."),
            segment("ASR", "Gwarantowany zysk, bo produkt został zatwierdzony przez", 1000, 3000, language="pl"),
            segment("ASR", "KNF.", 3100, 4000),
            segment("OCR", "Możesz stracić kapitał.", 15000),
        )
        points = [rule["points"] for rule in report["rules"]]
        self.assertEqual(points, sorted(points, reverse=True))
        self.assertEqual([reason["rule_id"] for reason in report["reasons"][:2]], ["R03", "R17"])
        self.assertEqual(report["risk"], "HIGH")
        self.assertLessEqual(report["priority_count"], report["criteria_count"])

    def test_semantic_gate_and_criterion_use_indexed_evidence(self):
        context = EvidenceContext.from_timeline([
            segment("DESCRIPTION", "Wynik tego portfela może być gorszy.", None),
            segment("ASR", "Moim zdaniem ta spółka za rok będzie dwa razy droższa.", 2000, language="pl"),
            segment("OCR", "Prognoza nie daje pewności przyszłych wyników.", 20000),
            segment("OCR", "Prognoza nie daje pewności przyszłych wyników.", 21000),
        ])
        self.assertEqual(len(context.rows), 4)
        with self.assertRaises(ValueError):
            context.resolve([999])
        with patch("investwatch.reel_llm.ReelModel", autospec=True) as model_class:
            model = model_class.return_value
            model.available = True
            model.qualify.return_value = Qualification(category="FORECAST", evidence=[1], reason="Autor stawia własną prognozę.")
            model.review.return_value = [Check(rule="R15", status="ok", evidence=[1], counter=[2],
                                              reason="Ostrzeżenie na ekranie dotyczy przewidywanych wyników.")]
            report = result(*context.rows, model=model)
            self.assertEqual(report["inference"]["uknf"], MODEL)
            forecast = next(rule for rule in report["rules"] if rule["rule_id"] == "R15")
            self.assertEqual(forecast["counter_evidence"], [context.rows[2]])
            self.assertEqual(forecast["status"], "PASS")
            self.assertEqual(report["priority_count"], 0)
            model.review.reset_mock()
            model.qualify.return_value = Qualification(category="OTHER", evidence=[0], reason="Słowa padły w innym kontekście.")
            rejected = result(*context.rows, model=model)
            model.review.assert_not_called()
            self.assertEqual(rejected["uknf_status"], "NOT_QUALIFIED")
            self.assertIsNone(rejected["priority_count"])
            self.assertEqual(rejected["timeline"], context.rows)

    def test_broker_endorsement_far_from_trade_survives_wrong_neutral_vote(self):
        data = (
            segment("DESCRIPTION", "Film z wyjazdu w góry."),
            segment("ASR", "Sprzedajcie obligacje funduszu i przejdźcie na akcje.", 2000, 5000, language="pl"),
            segment("ASR", "Przejdźmy przez historię tego rynku.", 13000, 20000),
            segment("ASR", "Wybierzcie tego brokera, bo jest najlepszy na rynku.", 35000, 40000),
        )
        with patch("investwatch.reel_llm.ReelModel", autospec=True) as model_class:
            model = model_class.return_value
            model.available = True
            model.qualify.return_value = Qualification(category="FINANCE_INFORMATION", evidence=[0, 2],
                                                        reason="Opis brzmi jak relacja z wyjazdu.")
            model.review.return_value = []
            report = result(*data, model=model)
        self.assertEqual(report["content_type"], "PROMOTION")
        self.assertEqual(report["decision"], "REVIEW")
        trade = next(reason for reason in report["reasons"] if "Publiczna zachęta" in reason["text"])
        promotion = next(reason for reason in report["reasons"] if "zachętę promocyjną" in reason["text"])
        self.assertIn(data[1], trade["evidence"])
        self.assertIn(data[-1], promotion["evidence"])
        self.assertEqual(next(rule["status"] for rule in report["rules"] if rule["rule_id"] == "R11"), "NEEDS_REVIEW")

    def test_quote_context_persists_across_distant_fragments(self):
        speech = (
            segment("ASR", "Przytoczę hasło, które pojawiało się w cudzej reklamie.", 0, 4500, language="pl"),
            segment("ASR", "W materiale występowały dwie osoby i plansza.", 8500, 11000),
            segment("ASR", "Kupcie akcje i wybierzcie tego brokera.", 20000, 24000),
        )
        with patch("investwatch.reel_llm.ReelModel", autospec=True) as model_class:
            model = model_class.return_value
            model.available = True
            model.qualify.return_value = Qualification(category="PROMOTION", evidence=[2],
                                                        reason="W materiale występuje zachęta.")
            rejected = result(*speech, model=model)
        self.assertEqual(rejected["decision"], "FINANCE_NEUTRAL")
        self.assertEqual(rejected["timeline"], list(speech))
        model.review.assert_not_called()

    def test_every_check_sees_every_page_without_truncating_tail(self):
        speech = [segment("ASR", ("Wyjaśnienie. " * 160) + str(index), index * 5000)
                  for index in range(8)]
        context = EvidenceContext.from_timeline(speech)
        pages = list(context.pages())
        self.assertGreater(len(pages), 1)
        self.assertEqual(set().union(*pages), set(range(len(speech))))
        model = ReelModel(Path("data"))
        per_rule = {}
        def infer(prompt, schema, tokens, constraints):
            indices = {row[0] for row in json.loads(prompt.split("\n", 1)[0])}
            for key in constraints["required"]:
                per_rule.setdefault(key, set()).update(indices)
            return {key: [-1, -1] for key in constraints["required"]}
        with patch.object(model, "_infer", side_effect=infer):
            review = model.review(context, "RECOMMENDATION")
        self.assertEqual(review.complete, {definition[0] for definition in DEFINITIONS})
        self.assertEqual({frozenset(indices) for indices in per_rule.values()}, {frozenset(range(len(speech)))})

    def test_real_broker_offer_is_reviewed_on_gate_disagreement(self):
        speech = segment("ASR", "Polecam ofertę brokera. Możecie dostać 150 złotych bonusów na zakup Bitcoina.",
                         0, 7000, language="pl")
        with patch("investwatch.reel_llm.ReelModel", autospec=True) as model_class:
            model = model_class.return_value
            model.available = True
            model.qualify.return_value = Qualification(category="FINANCE_INFORMATION", evidence=[0],
                                                        reason="Materiał przekazuje wiadomość finansową.")
            model.review.return_value = [Check(rule="R03", status="ok", evidence=[0], counter=[],
                                              reason="Brak przestrogi w nagraniu.")]
            checked = result(speech, model=model)
            self.assertEqual(checked["content_type"], "PROMOTION")
            self.assertEqual(checked["inference"]["accepted_criteria"], ["R03"])
            self.assertEqual(checked["rules"][0]["status"], "POTENTIAL_ISSUE")
            training = {**speech, "quote": "Fikcyjny przykład: " + speech["quote"]}
            clipped = result(training, model=model)
            self.assertEqual(clipped["uknf_status"], "NOT_QUALIFIED")
            model.review.assert_called_once()


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
            self.assertEqual(client.get(f"/api/reels/posts/{first}").json()["topic"], TOPICS[0])
            misleading = publish("Desery w domu", TOPICS[0])
            self.assertEqual(client.get(f"/api/reels/posts/{misleading}").json()["topic"], "Kuchnia")

            def top(viewer, seen=()):
                response = client.get("/api/reels/feed", params=[
                    ("viewer", viewer), ("limit", 1), *(("seen", item) for item in seen)])
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()[0]["id"]

            def react(reel, viewer, action, value=1):
                response = client.post(f"/api/reels/posts/{reel}/signals?viewer={viewer}",
                                       json={"action": action, "value": value})
                self.assertEqual(response.status_code, 204, response.text)

            self.assertEqual(top("scout-test", (misleading,)), third)
            react(first, "scout-test", "watch", 0.9)
            self.assertEqual(top("scout-test", (first,)), second)
            self.assertEqual(top("different-viewer", (misleading,)), third)
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
                    self.assertEqual(client.post("/api/scan/reset").status_code, 409)
                    client.post("/api/scan/stop").raise_for_status()
                    deadline = monotonic() + 10
                    while monotonic() < deadline:
                        if client.get("/api/scan/status").json()["status"] == "STOPPED":
                            break
                        sleep(.1)
                    preview = client.get(f"/api/scan/sessions/{run}/preview?download=true")
                    self.assertEqual(preview.status_code, 200, preview.text)
                    self.assertIn("Rolka testowa", preview.text)
                    self.assertIn("Analiza wykonana lokalnie", preview.text)
                    self.assertIn("attachment", preview.headers["content-disposition"])
                    self.assertEqual(client.post("/api/scan/reset").json()["status"], "IDLE")
                    self.assertEqual(client.get("/api/scan/sessions").json(), [])
                    self.assertEqual(client.get(f"/api/scan/sessions/{run}/preview").status_code, 404)
                    self.assertEqual(client.get(f"/api/reels/posts/{reel}").status_code, 200)
            finally:
                server.should_exit = True
                thread.join(12)
