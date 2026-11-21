"""Local, bounded media extraction. Timings are milliseconds."""
import csv
import hashlib
import io
import json
import os
import re
import subprocess

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


def asr(path, work):
    from faster_whisper import WhisperModel

    wav = work / "audio.wav"
    command(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-threads", "2",
             *local_format(path), "-i", str(path), "-vn", "-ac", "1",
             "-ar", "16000", str(wav)])
    try:
        model = WhisperModel(os.environ.get("IW_WHISPER_MODEL", "base"),
                             device="cpu", compute_type="int8", cpu_threads=4,
                             num_workers=1, local_files_only=True)
        chunks, info = model.transcribe(str(wav), beam_size=1, vad_filter=True)
        return [segment("ASR", chunk.text.strip(), round(chunk.start * 1000),
                        round(chunk.end * 1000), language=info.language,
                        avg_logprob=chunk.avg_logprob, model="faster-whisper/" +
                        os.environ.get("IW_WHISPER_MODEL", "base")) for chunk in chunks]
    finally:
        wav.unlink(missing_ok=True)


def ocr(path, duration, clips, work):
    reasons = command(["tesseract", "--list-langs"]).decode().splitlines()[1:]
    languages = "+".join(lang for lang in ("pol", "eng") if lang in reasons)
    if not languages:
        raise RuntimeError("Brak języków OCR pol/eng")
    times = set(range(0, int(duration) + 1, 3))
    times.update(s["start_ms"] // 1000 for s in clips
                 if s["start_ms"] is not None and 0 <= s["start_ms"] < duration * 1000)
    for second in sorted(t for t in times if t < duration)[:130]:
        frame = work / f"frame-{second}.png"
        command(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-threads", "2",
                 *local_format(path), "-ss", str(second), "-i", str(path),
                 "-frames:v", "1", "-vf", "scale=960:-2", "-threads", "1", str(frame)])
        if not frame.exists():
            continue
        output = command(["tesseract", str(frame), "stdout", "-l", languages, "--psm", "11", "-c", "tessedit_create_tsv=1"])
        lines = {}
        for word in csv.DictReader(io.StringIO(output.decode()), delimiter="\t", quoting=csv.QUOTE_NONE):
            if word["text"] and float(word["conf"]) >= 35:
                key = (word["block_num"], word["par_num"], word["line_num"])
                lines.setdefault(key, []).append(word)
        if not lines:
            frame.unlink()
            continue
        digest = hashlib.sha256(frame.read_bytes()).hexdigest()
        for words in lines.values():
            x, y = min(int(w["left"]) for w in words), min(int(w["top"]) for w in words)
            yield segment("OCR", " ".join(w["text"] for w in words), second * 1000,
                          bbox=[x, y, max(int(w["left"]) + int(w["width"]) for w in words) - x,
                                max(int(w["top"]) + int(w["height"]) for w in words) - y],
                          frame_sha256=digest, artifact=frame.name, language=languages)
