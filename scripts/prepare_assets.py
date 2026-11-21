"""Download optional local runtime assets before starting InvestWatch."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.request import urlopen

TESSDATA = {
    "eng": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
    "pol": "c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2",
}


def prepare_ocr(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for lang, expected in TESSDATA.items():
        filename = f"{lang}.traineddata"
        target = directory / filename
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
            continue
        url = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/" + filename
        with urlopen(url, timeout=30) as response:
            payload = response.read(8 * 1024 * 1024 + 1)
        if hashlib.sha256(payload).hexdigest() != expected:
            raise RuntimeError(f"Niezgodna suma SHA-256 pakietu {filename}")
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as temporary:
            temporary.write(payload)
        try:
            os.replace(temporary.name, target)
        finally:
            Path(temporary.name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("IW_DATA", "data")))
    parser.add_argument("--models", action="store_true", help="Prepare faster-whisper base")
    args = parser.parse_args()
    prepare_ocr(args.data / "tessdata")
    if args.models:
        os.environ.setdefault("HF_HOME", str((args.data / "hf").resolve()))
        from faster_whisper.utils import download_model

        target = args.data / "models" / "whisper-base"
        download_model("base", output_dir=str(target))
        print(f"Model ASR: {target.resolve()}")


if __name__ == "__main__":
    main()
