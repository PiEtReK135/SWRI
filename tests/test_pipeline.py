import io
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from fastapi.testclient import TestClient
from investwatch.api import create_app
from investwatch.media import drawtext_font


def await_report(client, job):
    deadline = time.monotonic() + 50
    while time.monotonic() < deadline:
        item = client.get("/jobs/" + job).json()
        if item["status"] in {"COMPLETED", "FAILED", "ACTION_REQUIRED"}:
            return item
        time.sleep(.15)
    raise AssertionError("Worker did not complete")


def create_clip(path, text="Tatry w listopadzie"):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=0x182932:s=640x360:r=12:d=24", "-vf",
                    f"drawtext={drawtext_font()}text='{text}':x=25:y=150:fontsize=24:fontcolor=white:"
                    "enable='between(t,18,22)'", "-c:v", "libx264", "-threads", "2", str(path)],
                   check=True)


class PipelineTest(unittest.TestCase):
    def test_ordinary_clip_with_timed_caption(self):
        with tempfile.TemporaryDirectory() as temp:
            clip = Path(temp) / "vlog.mp4"
            create_clip(clip)
            caption = ("1\n00:00:00,000 --> 00:00:04,000\nDziś idziemy w Tatry.\n\n"
                       "2\n00:00:18,000 --> 00:00:22,000\nZałóż konto u brokera DemoFin.\n")
            with TestClient(create_app(Path(temp) / "data")) as client, clip.open("rb") as file:
                started = time.perf_counter()
                request = client.post("/import/video",
                                      data={"description": "Jesienna wędrówka", "creator": "@gory",
                                            "rights_confirmed": "true", "captions_complete": "true",
                                            "relation": "THIRD_PARTY"},
                                      files={"video": ("vlog.mp4", file, "video/mp4"),
                                             "subtitle": ("vlog.srt", io.BytesIO(caption.encode()))})
                self.assertEqual(request.status_code, 202, request.text)
                job = request.json()["id"]
                item = await_report(client, job)
                self.assertEqual(item["status"], "COMPLETED", item)
                self.assertLess(time.perf_counter() - started, 50)
                print(f"24 s MP4 + SRT + OCR + raport: {time.perf_counter() - started:.2f} s")
                report = client.get("/reports/" + job).json()
                self.assertEqual(report["modules"], ["M1"])
                self.assertEqual(report["evidence"][0]["start_ms"], 18000)
                self.assertEqual(report["evidence"][0]["quote"], "Załóż konto u brokera DemoFin.")
                self.assertIn("OCR", report["coverage"])
                self.assertIn("Raport InvestWatch", client.get(f"/reports/{job}?format=html").text)
                self.assertIn("Import materiału", client.get("/").text)
                self.assertEqual(client.get(f"/artifacts/{job}/frame-18.png").status_code, 200)
                self.assertEqual(client.get(f"/artifacts/{job}/frame-18.png").content[:4], b"\x89PNG")
