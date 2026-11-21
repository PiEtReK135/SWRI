from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from investwatch.api import create_app
from tests.test_pipeline import await_report


class MonitorTest(unittest.TestCase):
    def test_synthetic_demo_m1_m2_m3_and_ocr_only(self):
        with tempfile.TemporaryDirectory() as temp, TestClient(create_app(temp)) as client:
            response = client.post("/demo/run")
            self.assertEqual(response.status_code, 202, response.text)
            ids = [item["id"] for item in response.json()]
            reports = [await_report(client, job)["report"] for job in ids]
            self.assertEqual([report["modules"] for report in reports], [["M1"], ["M2"], ["M3"], ["M1"]])
            self.assertTrue(all(report["is_demo"] for report in reports))
            self.assertEqual({item["kind"] for item in reports[3]["evidence"]}, {"OCR"})
            self.assertEqual(reports[3]["evidence"][0]["start_ms"], 18000)
            self.assertTrue(reports[3]["evidence"][0]["frame_sha256"])
            rules = {item["rule_id"]: item for item in reports[1]["rule_evaluations"]}
            self.assertEqual(len(rules), 19)
            self.assertEqual(rules["R17"]["status"], "POTENTIAL_ISSUE")
            self.assertEqual(rules["R08"]["status"], "UNASSESSED")
            self.assertEqual(reports[0]["rule_evaluations"][0]["scope"], "M1_AUXILIARY")
            old_alerts = client.get("/metrics").json()["alerts"]
            self.assertGreater(old_alerts, 0)
            client.patch("/settings/threshold", json={"threshold": 99}).raise_for_status()
            self.assertEqual(client.get("/metrics").json()["alerts"], 0)
            job = ids[0]
            client.patch(f"/cases/{job}", json={"review": "IN_REVIEW", "operator": "Operator",
                                               "note": "Ręczny przegląd"}).raise_for_status()
            self.assertIn("IN_REVIEW", client.get(f"/reports/{job}").text)
            self.assertTrue(client.get("/reports.csv").text.startswith("id,demo"))

    def test_source_policy_persists_and_does_not_retry_block(self):
        with tempfile.TemporaryDirectory() as temp:
            app = create_app(temp)
            with TestClient(app) as client:
                payload = {"rights_confirmed": "true"}
                files = {"file": ("urls.json", b'["https://example.test/vlog"]')}
                first = client.post("/import/urls", data=payload, files=files)
                self.assertEqual(first.status_code, 202)
                job = first.json()[0]["id"]
                self.assertEqual(await_report(client, job)["status"], "ACTION_REQUIRED")
                duplicate = client.post("/import/urls", data=payload, files=files).json()[0]
                self.assertEqual(duplicate["id"], job)
                self.assertTrue(duplicate["duplicate"])
                client.post(f"/content/{job}/source-observation", json={"status": "CAPTCHA"}).raise_for_status()
                self.assertEqual(client.post(f"/jobs/{job}/retry").status_code, 409)
                self.assertEqual(client.get("/alerts").json()[0]["job"], job)
                self.assertFalse(client.get("/sources").json()["media_download"])
                self.assertEqual(client.post("/import/urls", data=payload, files={
                    "file": ("urls.json", b'["file:///etc/passwd"]')}).status_code, 400)
                client.post("/watchlist", json={"kind": "CREATORS", "name": "@vlog",
                                                "reason": "Zweryfikowany zakres"}).raise_for_status()
                plans = client.post("/discovery/run").json()
                self.assertTrue({"FINANCIAL_TOPICS", "NON_FINANCIAL_CONTEXT", "WATCHLIST_CREATORS"} <=
                                {query["sampling_stratum"] for query in plans})
                self.assertEqual(client.post("/import/video", data={"url": "https://example.test"}).status_code, 400)
            with TestClient(create_app(temp)) as client:
                self.assertEqual(client.get(f"/jobs/{job}").json()["status"], "ACTION_REQUIRED")
                self.assertEqual(client.post(f"/jobs/{job}/retry").status_code, 409)
                client.post(f"/content/{job}/source-observation", json={"status": "AVAILABLE"}).raise_for_status()
                self.assertEqual(client.post(f"/jobs/{job}/retry").status_code, 200)

    def test_corrupt_media(self):
        with tempfile.TemporaryDirectory() as temp, TestClient(create_app(temp)) as client:
            response = client.post("/import/video", data={"rights_confirmed": "true"},
                                   files={"video": ("bad.mp4", b"invalid")})
            item = await_report(client, response.json()["id"])
            self.assertEqual(item["status"], "ACTION_REQUIRED")
            self.assertEqual(item["report"]["coverage"], [])
