"""Local, bounded media extraction. Timings are milliseconds."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from statistics import median

from .rules import RISK

MAX_SECONDS = 300
STAMP = r"(?:\d{2}:)?\d{2}:\d{2}[,.]\d{3}"
CUE = re.compile(rf"^({STAMP})\s+-->\s+({STAMP})(?:\s.*)?$")


def milliseconds(stamp):
    parts = re.split(r"[:,.]", stamp)
    return sum(value * int(part) for value, part in zip(
        (1, 1000, 60000, 3600000), reversed(parts)))


def segment(kind, quote, start=None, end=None, **details):
    return {"kind": kind, "quote": quote, "start_ms": start, "end_ms": end,
            "speaker_or_screen": "screen" if kind == "OCR" else None, **details}


def captions(text, suffix):
    if suffix == ".txt":
        return [segment("TRANSCRIPT", line.strip()) for line in text.splitlines() if line.strip()]
    result = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = block.splitlines()
        for index, line in enumerate(lines):
            match = CUE.fullmatch(line.strip())
            if match:
                start, end = map(milliseconds, match.groups())
                quote = "\n".join(lines[index + 1:]).strip()
                if quote and end > start:
                    result.append(segment("CAPTION", quote, start, end))
                break
    if not result:
        raise ValueError("Brak poprawnych segmentów SRT/VTT")
    return sorted(result, key=lambda row: row["start_ms"])


FORMAT = {".mp4": "mov", ".mov": "mov", ".m4a": "mov", ".webm": "matroska",
          ".mp3": "mp3", ".wav": "wav"}


def local_format(path):
    return ["-protocol_whitelist", "file", "-f", FORMAT[path.suffix]]


def command(args, timeout=60):
    return subprocess.run(args, check=True, capture_output=True, timeout=timeout,
                          env={**os.environ, "OMP_THREAD_LIMIT": "2"}).stdout


def probe(path):
    raw = command(["ffprobe", "-v", "error", *local_format(path),
                   "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)])
    info = json.loads(raw)
    duration = float(info["format"]["duration"])
    if not 0 < duration <= MAX_SECONDS:
        raise ValueError("Obsługiwane są klipy o długości do 300 sekund")
    return duration, {row["codec_type"] for row in info["streams"]}


def drawtext_font():
    if os.name == "nt":
        font = Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf"
        if font.is_file():
            escaped = font.as_posix().replace(":", r"\:")
            return f"fontfile='{escaped}':"
    return ""


def asr(path, *, model_path=None, beam_size=5, progress=None):
    from faster_whisper import WhisperModel
    import numpy as np

    pcm = command(["ffmpeg", "-nostdin", "-loglevel", "error", "-threads", "2",
                   *local_format(path), "-i", str(path), "-vn", "-ac", "1",
                   "-ar", "16000", "-f", "f32le", "pipe:1"])
    audio = np.frombuffer(pcm, dtype="<f4")
    model_path = model_path or os.environ.get("IW_WHISPER_MODEL", "base")
    model = WhisperModel(model_path, device="cpu", compute_type="int8", cpu_threads=4,
                         num_workers=1, local_files_only=True)
    chunks, info = model.transcribe(
        audio, beam_size=beam_size, vad_filter=True, condition_on_previous_text=False,
        language_detection_segments=3, vad_parameters={"min_silence_duration_ms": 450},
    )
    rows = []
    for chunk in chunks:
        if chunk.text.strip():
            rows.append(segment("ASR", chunk.text.strip(), round(chunk.start * 1000), round(chunk.end * 1000),
                                language=info.language, avg_logprob=chunk.avg_logprob,
                                language_probability=info.language_probability,
                                model="faster-whisper/" + Path(model_path).name))
        if progress:
            progress(min(1, chunk.end / max(info.duration, 1)))
    return rows


def ocr_languages():
    reasons = command(["tesseract", "--list-langs"]).decode().splitlines()[1:]
    languages = "+".join(lang for lang in ("pol", "eng") if lang in reasons)
    if not languages:
        raise RuntimeError("Brak języków OCR pol/eng")
    return languages


def read_ocr(source, languages):
    output = command(["tesseract", str(source), "stdout", "-l", languages, "--psm", "11",
                      "-c", "tessedit_create_tsv=1"], timeout=120)
    pages = {}
    lines = {}
    sizes = {}
    for word in csv.DictReader(io.StringIO(output.decode()), delimiter="\t", quoting=csv.QUOTE_NONE):
        if word["level"] == "1":
            sizes[word["page_num"]] = [int(word["width"]), int(word["height"])]
        if word["text"] and float(word["conf"]) >= 55:
            key = (word["page_num"], word["block_num"], word["par_num"], word["line_num"])
            if key not in lines:
                lines[key] = []
                pages.setdefault(int(word["page_num"]), []).append(lines[key])
            lines[key].append({**word, "frame_size": sizes.get(word["page_num"])})
    return pages


def ocr_segments(frame, languages, lines, start):
    lines = [words for words in lines if credible_ocr_line(words)]
    if not lines:
        return
    digest = hashlib.sha256(frame.read_bytes()).hexdigest()
    gray = None
    for words in lines:
        x, y = min(int(w["left"]) for w in words), min(int(w["top"]) for w in words)
        quote = " ".join(w["text"] for w in words)
        size = words[0].get("frame_size")
        box = [x, y, max(int(w["left"]) + int(w["width"]) for w in words) - x,
               max(int(w["top"]) + int(w["height"]) for w in words) - y]
        contrast = None
        if size and re.search(RISK, quote, re.I):
            if gray is None:
                try:
                    gray = command(["ffmpeg", "-v", "error", "-threads", "1", "-i", str(frame),
                                    "-frames:v", "1", "-pix_fmt", "gray", "-threads", "1", "-f", "rawvideo", "pipe:1"])
                except (OSError, subprocess.SubprocessError):
                    gray = b""
            if len(gray) == size[0] * size[1]:
                contrast = luminance_span(gray, size[0], box)
        yield segment("OCR", quote, start, bbox=box, frame_size=size, luminance_span=contrast,
                      frame_sha256=digest, artifact=frame.name, language=languages,
                      confidence=round(median(float(w["conf"]) for w in words), 1))


def luminance_span(gray, stride, box):
    x, y, width, height = box
    values = sorted(gray[row * stride + column] for row in range(y, y + height, 2)
                    for column in range(x, x + width, 2))
    if values:
        return values[(len(values) - 1) * 9 // 10] - values[(len(values) - 1) // 10]
    return None


def credible_ocr_line(words):
    tokens = [re.sub(r"[^\w%]", "", word["text"], flags=re.UNICODE).strip("_") for word in words]
    confidence = median(float(word["conf"]) for word in words)
    useful = [token for token in tokens if len(token) >= 3 and any(char.isalpha() for char in token)]
    if len(useful) >= 2:
        return confidence >= 79 and sum(map(len, useful)) >= 7 and len(useful) * 2 >= len(tokens)
    text = " ".join(tokens).strip().casefold()
    # Keep explicit short financial labels and disclosure marks at high confidence.
    return confidence >= 90 and bool(re.fullmatch(r"reklama|cfd|etf(?:y)?|knf|bitcoin|[0-9]{1,3}%", text))


def ocr_frame(frame, languages, start=None):
    return ocr_segments(frame, languages, read_ocr(frame, languages).get(1, []), start)


def ocr_batch(path, duration, clips, work, interval, progress=None):
    """Decode once and run OCR on bounded batches of sampled frames."""
    seconds = set(range(0, int(duration) + 1, interval))
    seconds.update(row["start_ms"] // 1000 for row in clips if row["start_ms"] is not None)
    times = sorted(second for second in seconds if 0 <= second < duration)
    filters = "+".join(f"eq(n,{second})" for second in times)
    with tempfile.TemporaryDirectory(dir=work) as temporary:
        folder = Path(temporary)
        command(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-threads", "2", *local_format(path),
                 "-i", str(path), "-an", "-vf", f"fps=1:start_time=0:round=up,select='{filters}',scale=960:-2",
                 "-fps_mode", "vfr", "-threads", "1", str(folder / "sample-%03d.png")], timeout=120)
        frames = sorted(folder.glob("sample-*.png"))
        # Container duration can include a final audio tail after the last video frame.
        if not frames or not 0 <= len(times) - len(frames) <= 1:
            raise RuntimeError("Niepełna ekstrakcja klatek OCR")
        languages = ocr_languages()
        manifest = folder / "frames.txt"
        batch_size = 10 if progress else len(frames)
        for begin in range(0, len(frames), batch_size):
            batch = frames[begin:begin + batch_size]
            manifest.write_text("\n".join(str(frame.resolve()) for frame in batch) + "\n", encoding="utf-8")
            pages = read_ocr(manifest, languages)
            for page, frame in enumerate(batch, 1):
                second = times[begin + page - 1]
                accepted = list(ocr_segments(frame, languages, pages.get(page, []), second * 1000))
                if not accepted:
                    continue
                published = work / f"frame-{second}.png"
                frame.replace(published)
                yield from ({**row, "artifact": published.name} for row in accepted)
            if progress:
                progress((begin + len(batch)) / len(frames))


def ocr(path, duration, clips, work, interval=3):
    languages = ocr_languages()
    times = set(range(0, int(duration) + 1, interval))
    times.update(s["start_ms"] // 1000 for s in clips
                 if s["start_ms"] is not None and 0 <= s["start_ms"] < duration * 1000)
    for second in sorted(t for t in times if t < duration)[:130]:
        frame = work / f"frame-{second}.png"
        command(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-threads", "2",
                 *local_format(path), "-ss", str(second), "-i", str(path),
                 "-frames:v", "1", "-vf", "scale=960:-2", "-threads", "1", str(frame)])
        if not frame.exists():
            continue
        rows = list(ocr_frame(frame, languages, second * 1000))
        if not rows:
            frame.unlink()
        yield from rows
