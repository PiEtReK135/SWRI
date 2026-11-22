"""Publish and analyze fictional module fixtures using the local SWRI feed."""

from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import textwrap
from threading import Event
from time import perf_counter
from urllib.parse import quote
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from investwatch.collectors import WebSource, websites
from investwatch.discovery import Discovery
from investwatch.media import command, drawtext_font
from investwatch.reel_scan import FeedClient, Scanner, stamp
from investwatch.reels import database
from investwatch.scan_history import store_report
from investwatch.store import Store

ORIGIN = "http://127.0.0.1:8000"
ROOT = Path("data").resolve()
WORK = Path("data/validation/module-examples")
BRAND = "Dom Inwestycyjny Latarnia Demo"
OFFICIAL = "sym_latarnia_demo"

# The first field is the expected test category. The analyzer never receives it.
SCENES = (
    ("M1", "Jak ustawiam aplikacje", "sym_mila",
     "Telefon po porządkach wygląda inaczej. Na końcu zostawiłam polecenie.",
     "Załóż konto maklerskie w Latarni Demo. Użyj mojego kodu MILA, żeby dostać 100 zł bonusu."),
    ("M1", "Rachunek w podróży", "sym_pod_pociagiem",
     "Materiał sponsorowany. Płatna współpraca z Domem Inwestycyjnym Latarnia Demo.",
     "Zarejestruj się u brokera Latarnia Demo przez mój link i wypróbuj rachunek maklerski."),
    ("M1", "Moja lista na koniec miesiąca", "sym_agata",
     "Pytaliście, gdzie sprawdzam kursy. Tu pokazuję moją aplikację.",
     "To jest broker Latarnia Demo. Otwórz konto maklerskie, mój kod polecający MAJ daje bonus."),
    ("M2", "Rachunek bez prowizji", OFFICIAL,
     "Dom Inwestycyjny Latarnia Demo. Otwórz rachunek maklerski i odbierz 120 zł bonusu.",
     "Najlepsza oferta inwestycyjna. Otwórz rachunek u nas. Akcje i ETF-y w aplikacji."),
    ("M2", "Wynik strategii na wykresie", OFFICIAL,
     "Dom Inwestycyjny Latarnia Demo. Załóż konto maklerskie, skorzystaj z kodu PORTFEL.",
     "W 2025 roku uzyskaliśmy 22 procent zysku. Otwórz konto i wybierz nasz fundusz akcji."),
    ("M2", "Bezpieczeństwo rachunku CFD", OFFICIAL,
     "Dom Inwestycyjny Latarnia Demo. Rachunek CFD i bonus na start. Otwórz konto maklerskie.",
     "Podlegamy nadzorowi KNF, dlatego ta inwestycja jest bezpieczna. Użyj kodu LATARNIA."),
    ("M2", "Porównujemy opłaty", OFFICIAL,
     "Dom Inwestycyjny Latarnia Demo. Otwórz konto maklerskie z kodem TANIEJ.",
     "Nasza platforma maklerska tańsza niż inne oferty na rynku. Możesz stracić część kapitału."),
    ("M2", "Prognoza na kolejny kwartał", OFFICIAL,
     "Dom Inwestycyjny Latarnia Demo. Otwórz rachunek maklerski z kodem JESIEN.",
     "Nasza prognoza cen: akcje będą warte o 20 procent więcej. Otwórz konto maklerskie."),
    ("M3", "Terminy na indywidualną konsultację", "sym_portfel_po_pracy",
     "Oferuję indywidualne rekomendacje. Na podstawie twojej sytuacji wskażę, które akcje kupić.",
     "Zapisz się na konsultację. Dobiorę akcje do twojego portfela i powiem, kiedy je kupić."),
    ("M3", "Porządkowanie portfela po zmianie pracy", "sym_analiza_wieczorem",
     "Oferuję doradztwo inwestycyjne. Na podstawie twojej sytuacji powiem, które obligacje sprzedać.",
     "Na sesji jeden na jeden dostaniesz indywidualne rekomendacje dotyczące konkretnych obligacji."),
    ("M3", "Plan na środki po sprzedaży mieszkania", "sym_spokojny_kapital",
     "Oferuję doradztwo inwestycyjne. Na podstawie twojej sytuacji wskażę, które ETF-y kupić.",
     "Otrzymasz osobistą listę instrumentów, kwoty zakupu i terminy transakcji po konsultacji."),
    ("M3", "Twoja lista transakcji na kwartał", "sym_warsztat_portfela",
     "Oferuję indywidualne rekomendacje. Na podstawie twojej sytuacji powiem, które fundusze sprzedać.",
     "Prześlij swój portfel. Na podstawie twoich potrzeb ustalimy, które fundusze trzymać i które sprzedać."),
    ("M3", "Konsultacje dla rodzin", "sym_klub_kapitalowy",
     "Family office. Na podstawie twojej sytuacji wskażę, które akcje kupić i które obligacje sprzedać.",
     "Doradztwo inwestycyjne po rozmowie o potrzebach rodziny. Dostaniesz indywidualne rekomendacje."),
    ("M1", "Moje trzy skróty w telefonie", "sym_dziennik_notatek",
     "Porównuję widżety, które mam teraz na ekranie. Numer trzy to nowość.",
     "Jeśli chcesz bonus od brokera Latarnia Demo, załóż konto maklerskie. Użyj mojego kodu SKROTY."),
    ("M1", "Konto z newslettera", "sym_czytam_rynek",
     "Współpraca reklamowa z Domem Inwestycyjnym Latarnia Demo. Poniżej szczegóły akcji partnerskiej.",
     "Otwórz rachunek maklerski u brokera Latarnia Demo. Wpisz mój kod polecający LIST, żeby dostać bonus."),
    ("M1", "Rynkowa kawa przed pracą", "sym_kawa_na_gieldzie",
     "Płatna współpraca z Domem Inwestycyjnym Latarnia Demo. Mój kod RANO daje 100 zł bonusu. Załóż konto maklerskie przez link.",
     "Jeśli zakładasz rachunek u brokera Latarnia Demo, wpisz kod RANO w formularzu."),
    ("M2", "Dwie waluty, jedna stawka", OFFICIAL,
     "Dom Inwestycyjny Latarnia Demo. Załóż konto maklerskie i użyj kodu WALUTA. Kod polecający daje bonus.",
     "Handluj akcjami USA bez prowizji. Sprawdź porównanie z konkurencją w komentarzu pod filmem."),
    ("M2", "Oferta dla nowego portfela", OFFICIAL,
     "Dom Inwestycyjny Latarnia Demo. Otwórz rachunek maklerski i użyj kodu AKCJE, żeby dostać 150 zł bonusu.",
     "Nasza prognoza cen: wartość akcji wzrośnie o 18 procent. Dostęp do funduszu po otwarciu konta."),
    ("M2", "Sesja w aplikacji", OFFICIAL,
     "Dom Inwestycyjny Latarnia Demo. Załóż konto maklerskie. Użyj kodu SESJA i dostań bonus na start.",
     "Pokażemy ranking wyników historycznych. W ostatnim roku najlepsi inwestorzy osiągnęli zysk 24 procent."),
    ("M1", "Przegląd finansów w niedzielę", "sym_niedzielny_przeglad",
     "Polecam rachunek maklerski w Domu Inwestycyjnym Latarnia Demo. Użyj kodu START, żeby dostać 100 zł bonusu.",
     "Pokażę, jak wygląda aplikacja. Rachunek maklerski zakładam z kodem START."),
    ("M1", "Poranna poczta i rachunki", "sym_poranna_poczta",
     "Załóż konto maklerskie przez mój link afiliacyjny do brokera Latarnia Demo. Użyj kodu PLAN.",
     "Materiał sponsorowany przez Dom Inwestycyjny Latarnia Demo. Otwórz rachunek przez mój link."),
)


def image(directory, title, speech, index):
    palette = ("164C61", "6F3842", "273D65", "39416F", "174E42")
    accent = palette[index % len(palette)]
    (directory / "title.txt").write_text("\n".join(textwrap.wrap(title, 21)), encoding="utf-8")
    (directory / "message.txt").write_text("\n".join(textwrap.wrap(speech, 30)), encoding="utf-8")
    filters = [
        f"drawbox=x=0:y=0:w=iw:h=270:color=0x{accent}:t=fill",
        f"drawbox=x=35:y=312:w=650:h=555:color=0x{accent}:t=2",
        f"drawtext={drawtext_font()}text=SWRI / SYMULACJA:x=53:y=44:fontsize=30:fontcolor=white",
        f"drawtext={drawtext_font()}textfile={directory.as_posix()}/title.txt:expansion=none:"
        "x=53:y=95:fontsize=47:line_spacing=8:fontcolor=white",
        f"drawtext={drawtext_font()}textfile={directory.as_posix()}/message.txt:expansion=none:"
        "x=68:y=376:fontsize=37:line_spacing=15:fontcolor=0x172537",
        f"drawtext={drawtext_font()}text=Material testowy SWRI:x=54:y=1138:fontsize=30:fontcolor=0x32465F",
    ]
    output = directory / "card.png"
    command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
             "color=c=0xEFF4FF:s=720x1200", "-vf", ",".join(filters), "-frames:v", "1", "-threads", "1", str(output)])
    return output


def clip(directory, card, speech):
    text = directory / "voice.txt"
    text.write_text(speech, encoding="utf-8")
    audio = directory / "voice.wav"
    powershell = (
        "Add-Type -AssemblyName System.Speech\n"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$s.SelectVoice('Microsoft Paulina Desktop')\n"
        f"$s.SetOutputToWaveFile((Join-Path (Get-Location) '{audio.as_posix()}'))\n"
        f"$s.Speak([IO.File]::ReadAllText((Join-Path (Get-Location) '{text.as_posix()}')))\n"
        "$s.Dispose()"
    )
    import base64
    command(["powershell.exe", "-NoProfile", "-EncodedCommand",
             base64.b64encode(powershell.encode("utf-16le")).decode("ascii")])
    output = directory / "clip.mp4"
    command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", "12",
             "-i", str(card), "-i", str(audio), "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
             "-threads", "2", "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(output)])
    return output


def bdm(store, scanner):
    workspace = Discovery(ROOT / "discovery", store, scanner)
    company = "Dom Maklerski BDM S.A."
    for url in ("https://www.bdm.pl/bdm-podstawowy", "https://www.bdm.pl/rachunek-inwestycyjny"):
        source = WebSource(url=url, publisher=company, pages=1)
        record = next(websites(source, Event()))
        ident = workspace.store_material(record)
        actual = workspace.detail(ident)
        print("REAL", actual["modules"], ident, url, flush=True)
        if "M2" in actual["modules"]:
            return


def run():
    WORK.mkdir(parents=True, exist_ok=True)
    store = Store(ROOT)
    # This identity exists only inside the fixture analysis, never in the live company register.
    synthetic_entity = {"name": BRAND, "aliases": ["Latarnia Demo"], "in_scope": True, "registry_status": "FICTION",
                        "publisher_url": ORIGIN + "/rolki?autor=" + quote(OFFICIAL, safe="")}
    scanner = Scanner(ROOT / "reel-scan", ORIGIN, lambda: [synthetic_entity])
    resume = WORK / "posts.json"
    posts = json.loads(resume.read_text(encoding="utf-8")) if resume.exists() else {}
    existing = {item["reel"]: item for item in scanner.reports(limit=-1)["items"]}
    totals = Counter(module for asset in posts.values() if asset in existing for module in existing[asset]["modules"])
    run_id = uuid4().hex
    failed = False
    with database(scanner.path) as db:
        # Manual in-process batch. A separate run preserves the viewer's existing recommendation profile.
        db.execute("INSERT INTO scan_runs(id,status,started) VALUES (?,?,?)", (run_id, "WAITING", stamp()))
    print("RUN", run_id, flush=True)
    try:
        client = FeedClient(ORIGIN, "swri-module-fixtures")
        with httpx.Client(timeout=75, trust_env=False) as http:
            for index, (expected, title, creator, caption, spoken) in enumerate(SCENES):
                if totals[expected] >= 5:
                    continue
                key = sha256(title.encode()).hexdigest()[:12]
                directory = WORK / key
                directory.mkdir(exist_ok=True)
                asset = posts.get(key)
                if asset in existing:
                    continue
                if not asset:
                    card = image(directory, title, spoken, index)
                    file = clip(directory, card, spoken) if index in (0, 3, 8) else card
                    with file.open("rb") as stream:
                        response = http.post(ORIGIN + "/api/reels/posts", files={"file": (file.name, stream)}, data={
                            "title": title + " · symulacja", "creator": creator, "description": caption,
                            "credit": "Autorski materiał ćwiczeniowy SWRI. Postacie, oferty i firma są fikcyjne.",
                            "rights_confirmed": "true",
                        })
                    response.raise_for_status()
                    asset = response.json()["id"]
                    posts[key] = asset
                    resume.write_text(json.dumps(posts, ensure_ascii=False), encoding="utf-8")
                item = client.item(asset)
                before = perf_counter()
                scanner.progress(run_id, "SCANNING", item["title"])
                report = scanner.analyze(client, run_id, item)
                report["feedback"] = "Autorski materiał ćwiczeniowy. Preferencje feedu nie były zmieniane."
                with database(scanner.path) as db:
                    store_report(db, run_id, asset, stamp(), round(perf_counter() - before, 2),
                                 {"title": item["title"], "kind": item["kind"], "scenario": True, **report})
                totals.update(report["modules"])
                print(expected, report["modules"], report["decision"], asset, report.get("inference", {}).get("uknf"),
                      round(perf_counter() - before, 2), flush=True)
        bdm(store, scanner)
    except BaseException:
        failed = True
        raise
    finally:
        with database(scanner.path) as db:
            db.execute("UPDATE scan_runs SET status=?,ended=?,current=NULL,stage=NULL,progress_percent=NULL WHERE id=?",
                       ("FAILED" if failed else "COMPLETED", stamp(), run_id))
        scanner.model.close()


if __name__ == "__main__":
    os.environ.setdefault("IW_WHISPER_MODEL", str(ROOT / "models/whisper-medium"))
    run()
