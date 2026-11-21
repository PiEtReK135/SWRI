from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from investwatch.api import create_app


class SiteTest(TestCase):
    def test_project_site_dashboard_and_api_share_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "dist"
            site.mkdir()
            (site / "index.html").write_text("<a href='/dashboard'>SWRI</a>", encoding="utf-8")
            (site / "app.js").write_text("console.log('project-site');", encoding="utf-8")
            with patch.dict("os.environ", {"IW_SITE_DIR": str(site)}):
                app = create_app(root / "data")
            with TestClient(app) as client:
                self.assertIn("SWRI", client.get("/").text)
                self.assertIn("project-site", client.get("/app.js").text)
                self.assertIn("Import materiału", client.get("/dashboard").text)
                self.assertIn("openItem", client.get("/dashboard/app.js").text)
                self.assertEqual(client.get("/health").json()["status"], "ok")
                self.assertEqual(client.get("/content").json(), [])
