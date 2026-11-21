"""Deterministic, fictional organic samples using local video and caption input."""
import io
import json
from pathlib import Path
import tempfile

from .media import command, drawtext_font


DEMO = (
    ("Jesienna wędrówka", "@demo_szlak", "THIRD_PARTY", "Dzis idziemy w Tatry.",
     "Załóż konto u brokera Szlak Finance, mój kod SZLAK.",
     "Tatry o świcie. Widoki z trasy."),
    ("Szlak Finance – oferta", "@demo_szlak_finance", "FIRST_PARTY", "Oferta Szlak Finance.",
     "Załóż konto maklerskie w Szlak Finance. Zysk 15%. Produkt zatwierdzony przez KNF.",
     "Demo oficjalnej publikacji."),
    ("Konsultacja portfela", "@demo_portfel", "UNKNOWN", "Pytania i odpowiedzi.",
     "Na podstawie twojej sytuacji kup akcje spółki ABC. Oferuję indywidualną konsultację.",
     "Pytania od widzów."),
    ("Rowerem przez las", "@demo_rower", "THIRD_PARTY", "Dzis jedziemy przez las.",
     "", "Leśny szlak rowerowy."),
)


def seed(store, submit):
    official = {"name": "Szlak Finance", "aliases": [], "in_scope": True,
                "publisher_url": "demo://profiles/szlak-finance",
                "registry_status": "DEMO", "is_demo": True}
    with store.db() as db:
        db.execute("INSERT OR IGNORE INTO registry VALUES (?,?)",
                   ("demo:Szlak Finance", json.dumps(official)))
    results = []
    with tempfile.TemporaryDirectory(dir=store.root) as temp:
        for title, creator, relation, opening, promo, description in DEMO:
            clip = Path(temp) / "clip.mp4"
            overlay = ("BROKER SZLAK FINANCE - ZALOZ KONTO" if creator == "@demo_rower"
                       else "INVESTWATCH - DEMO")
            command(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                     "color=c=0x153744:s=640x360:r=12:d=24", "-vf",
                     f"drawtext={drawtext_font()}text={overlay}:x=22:y=160:fontsize=26:fontcolor=white:"
                     "enable='between(t,18,22)'", "-threads", "2", "-c:v", "libx264", str(clip)])
            caption = f"1\n00:00:00,000 --> 00:00:04,000\n{opening}\n"
            if promo:
                caption += f"\n2\n00:00:18,000 --> 00:00:22,000\n{promo}\n"
            meta = {"title": title, "creator": creator, "relation": relation, "description": description,
                    "url": "demo://organic/" + creator[1:], "source_mode": "DEMO_ORGANIC_FEED",
                    "publisher_url": official["publisher_url"] if relation == "FIRST_PARTY" else "",
                    "rights_status": "SYNTHETIC", "captions_complete": True, "is_demo": True}
            with clip.open("rb") as stream:
                results.append(submit(store, meta, [("media", stream, ".mp4"),
                                                   ("caption", io.BytesIO(caption.encode()), ".srt")]))
    return results
