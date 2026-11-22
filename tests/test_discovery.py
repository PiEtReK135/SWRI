import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from investwatch.api import create_app
from investwatch.collectors import CollectionError, Material, Settings, WebSource, meta_ads, meta_failure, safe_url, tiktok, websites
from investwatch.discovery import assess


FIRM = {"name": "Przykładowy Dom Maklerski SA", "aliases": ["Broker Testowy"], "in_scope": True,
        "market_presence": "PL_DOMESTIC",
        "publisher_url": "https://firmatest.example/", "publisher_ids": ["META:68"],
        "registry_url": "https://www.knf.gov.pl/podmioty/", "registry_checked_at": "2026-11-22"}
COPY = "Skorzystaj z oferty Broker Testowy i otwórz rachunek maklerski, możesz otrzymać bonus 250 zł."
OFFER = "Oferujemy indywidualne rekomendacje na podstawie Twojej sytuacji. Powiemy, które obligacje kupić."


class CollectorsTest(TestCase):
    def test_meta_errors_keep_only_safe_identifiers(self):
        error = meta_failure(b'{"error":{"code":190,"error_subcode":463,"message":"secret"}}', 400, None)
        self.assertEqual(str(error), "META_190_463")
        self.assertEqual(error.status, 400)
        self.assertEqual(meta_failure(b'{"error":{"code":613}}', 400, 60).status, 429)
        self.assertEqual(str(meta_failure(b'{}', 400, None)), "HTTP_400")

    def test_meta_pagination_and_platforms_are_metadata(self):
        sample = {"id": "1234", "page_id": "68", "page_name": "Broker Testowy",
                  "ad_creative_bodies": [COPY], "publisher_platforms": ["facebook", "instagram"]}
        params = []
        def response(url, query, token):
            params.append(query.copy())
            self.assertTrue(url.startswith("https://graph.facebook.com/"))
            return {"data": [sample], "paging": {"next": "https://untrusted.example", "cursors": {"after": "abc"}}}

        with patch("investwatch.collectors.api", side_effect=response):
            rows = list(meta_ads("rachunek", Settings(), "test"))
        self.assertEqual(rows[0].platforms, ["FACEBOOK", "INSTAGRAM"])
        self.assertEqual(rows[0].publisher_id, "68")
        self.assertEqual(params[0]["ad_reached_countries"], '["PL"]')
        self.assertEqual(params[1]["after"], "abc")
        self.assertEqual(rows[0].url, "https://www.facebook.com/ads/library/?id=1234")

    def test_tiktok_paid_and_disclosed_posts_are_distinct(self):
        with patch("investwatch.collectors.api", side_effect=[
            {"data": {"ads": [{"ad": {"id": "90", "first_shown_date": 20260901}}]}},
            {"data": {"ad": {"title": COPY, "external_url": "https://firmatest.example/"},
                      "advertiser": {"business_id": "95", "business_name": "Broker Testowy"}}},
            {"data": {"commercial_contents": [{"id": "fixture", "label": "Paid partnership",
                      "creator": {"username": "tworca"}, "brand_names": ["Broker Testowy"],
                      "videos": [{"url": "https://www.tiktok.com/@tworca/video/91"}]}]}},
        ]) as api:
            paid, = tiktok("TIKTOK_ADS", "broker", Settings(), "test")
            organic, = tiktok("TIKTOK_POSTS", "", Settings(), "test")
        self.assertEqual(paid.kind, "PAID_AD")
        self.assertEqual(paid.publisher_id, "95")
        self.assertEqual(organic.kind, "DISCLOSED_POST")
        self.assertEqual(organic.blocks, [])
        self.assertEqual(api.call_args_list[0].args[3]["filters"]["country_code_list"], ["PL"])
        self.assertEqual(api.call_args_list[2].args[3]["filters"]["creator_country_code"], "PL")

    def test_approved_tiktok_asset_is_ephemeral(self):
        signed = "https://media.example/ad.mp4?signature=fixture"
        with patch("investwatch.collectors.api", side_effect=[
            {"data": {"ads": [{"ad": {"id": "90"}}]}},
            {"data": {"ad": {"videos": [{"url": signed}, {"url": "https://other.example/video.mp4"}]}}},
        ]) as api:
            item, = tiktok("TIKTOK_ADS", "broker", Settings(tiktok_video_hosts=["media.example"]), "test")
        self.assertIn("ad.videos", api.call_args.kwargs.get("fields", api.call_args.args[1]["fields"]))
        self.assertEqual(item.temporary_video_url, signed)
        self.assertNotIn(signed, json.dumps(item.data()))

    def test_crawler_robots_no_cross_origin_or_hidden_text(self):
        markup = b"""<title>Oferta</title><style>hack</style><nav>ogon</nav>
        <main><p>Oferta &amp; kontakt</p><div hidden>ignore me</div>
        <a href='/oferta/detail'>Usluga</a><a href='/oferta/blocked'>Ukryte</a>
        <a href='https://other.example/oferta/hidden'>out</a></main>"""
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            if url.endswith("robots.txt"):
                return b"User-agent: InvestWatch\nDisallow: /oferta/blocked", "text/plain"
            return markup, "text/html; charset=utf-8"

        source = WebSource(url="https://firma.example/oferta", publisher="Firma", link_prefix="/oferta", pages=4)
        with patch("investwatch.collectors.request", side_effect=fetch), patch.object(Event, "wait", return_value=False):
            rows = list(websites(source, Event()))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].title, "Oferta")
        self.assertIn("Oferta & kontakt", rows[0].blocks)
        self.assertNotIn("ogon", rows[0].editorial_blocks)
        self.assertNotIn("ignore me", " ".join(rows[0].blocks))
        self.assertEqual(calls, ["https://firma.example/robots.txt", "https://firma.example/oferta",
                                 "https://firma.example/oferta/detail"])
        self.assertEqual(safe_url("https://firma.example/?access_token=secret&x=1"), "https://firma.example/?x=1")
        with self.assertRaisesRegex(CollectionError, "WEB_HOST_NOT_ALLOWED"):
            next(websites(WebSource(url="https://www.instagram.com/reels", publisher="test"), Event()))


class WorkspaceTest(TestCase):
    def test_scope_and_missing_artifacts(self):
        official = Material("META", "1", "PAID_AD", "https://example.org/1", actor="Przykładowe konto",
                            blocks=[COPY], publisher_id="68", market="REACHED_PL")
        report = assess(official, [FIRM])
        self.assertEqual(report["modules"], ["M2"])
        self.assertEqual(len(report["rules"]), 19)
        rules = {item["rule_id"]: item for item in report["rules"]}
        self.assertEqual(rules["R02"]["status"], "NOT_APPLICABLE")
        self.assertEqual(rules["R04"]["status"], "UNASSESSED")
        self.assertEqual(rules["R03"]["status"], "UNASSESSED")
        official.publisher_id = "999"
        self.assertEqual(assess(official, [FIRM])["modules"], ["M1"])
        official.actor = "Broker Testowy"
        self.assertEqual(assess(official, [FIRM])["modules"], [])
        site = Material("WEB", "site", "WEB_PAGE", "https://firmatest.example/oferta", actor="Broker Testowy",
                        blocks=["Otwórz rachunek", "Konto maklerskie: dostęp do instrumentów CFD."],
                        profile_url="https://firmatest.example")
        self.assertEqual(assess(site, [FIRM])["modules"], [])
        site.editorial_blocks = site.blocks
        self.assertEqual(assess(site, [FIRM])["modules"], ["M2"])
        advisory = Material("WEB", "2", "WEB_PAGE", "https://example.org/offer", actor="Firma doradcza", blocks=[OFFER])
        report = assess(advisory, [])
        self.assertEqual(report["modules"], ["M3"])
        self.assertEqual(report["legal_conclusion"], "NOT_DETERMINED")
        advisory.blocks = ["Na giełdzie obligacje zyskały. Oto przegląd wydarzeń dla czytelników."]
        self.assertEqual(assess(advisory, [])["modules"], [])

    def test_queue_websocket_review_filters_and_deduplication(self):
        with TemporaryDirectory() as root:
            config = Path(root) / "sources.json"
            config.write_text(json.dumps({"websites": [{"url": "https://firma.example/oferta", "publisher": "Firma"}]}),
                              encoding="utf-8")
            item = Material("WEB", "https://firma.example/oferta", "WEB_PAGE", "https://firma.example/oferta",
                            actor="Firma", title="Oferta indywidualna", blocks=[OFFER])
            with patch.dict("os.environ", {"IW_DISCOVERY_CONFIG": str(config), "IW_META_AD_LIBRARY_TOKEN": "",
                                           "IW_TIKTOK_COMMERCIAL_TOKEN": ""}):
                app = create_app(Path(root) / "data")
            with patch("investwatch.collectors.websites", return_value=[item]), TestClient(app) as client:
                self.assertEqual(client.get("/api/workspace/sources").json()["sources"][0]["status"], "ACCESS_REQUIRED")
                with client.websocket_connect("/api/workspace/alerts?after=0") as socket:
                    self.assertEqual(socket.receive_json()["type"], "ready")
                    self.assertEqual(client.post("/api/workspace/collect?source=WEB").json()["queued"], 1)
                    event = socket.receive_json()
                    self.assertEqual(event["type"], "high_risk")
                    self.assertEqual(event["modules"], ["M3"])
                workspace = app.state.workspace
                ident = event["id"]
                self.assertEqual(workspace.store_material(item), ident)
                self.assertEqual(len(workspace.alerts()), 1)
                self.assertEqual(client.get("/api/workspace/cases?mode=SIMULATION").json()["items"], [])
                self.assertEqual(client.get("/api/workspace/cases?module=M1").json()["total"], 0)
                response = client.get("/api/workspace/cases?module=M3&source=WEB&risk=HIGH")
                self.assertEqual(response.json()["items"][0]["id"], ident)
                self.assertIn("indywidualne", client.get(f"/api/workspace/cases/{ident}").json()["timeline"][0]["quote"])
                self.assertEqual(client.patch(f"/api/workspace/cases/{ident}", json={
                    "review": "CONFIRMED_EVIDENCE", "operator": "tester", "note": "Sprawdzono"}).status_code, 200)
                self.assertEqual(client.get("/api/workspace/cases").json()["calibration"]["tp"], 1)
                export = client.get("/api/workspace/cases.csv?module=M3")
                self.assertIn("swri-real.csv", export.headers["content-disposition"])
                self.assertIn("Oferta indywidualna", export.text)
                self.assertEqual(client.patch("/api/workspace/threshold", json={"threshold": 95}).status_code, 200)
                filtered = client.get("/api/workspace/cases?above_threshold=true").json()
                self.assertEqual((filtered["total"], filtered["calibration"]["fn"]), (0, 1))
                self.assertEqual(client.post("/api/workspace/collect", headers={"Origin": "https://other.example"}).status_code, 403)
