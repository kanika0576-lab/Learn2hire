"""Video -> timestamped transcript via AWS Transcribe.

Fallback for offline demos: a .vtt / .srt / .txt transcript uploaded next to the
video, or None when no transcript exists (the API then reports honestly).
"""

import json
import os
import re
import time
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings
from app.services import llm as llm_service

VTT_TIME = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})"
)


def _to_seconds(h, m, s, ms) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_transcript_bytes(data: bytes, filename: str) -> list[dict]:
    """Parse .vtt/.srt/.txt into [{start_time, end_time, text}]."""
    text = data.decode("utf-8", errors="replace")
    name = filename.lower()
    segments: list[dict] = []

    if name.endswith(".vtt") or name.endswith(".srt"):
        blocks = re.split(r"\n\s*\n", text.strip())
        for block in blocks:
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            for i, ln in enumerate(lines):
                m = VTT_TIME.search(ln)
                if m:
                    start = _to_seconds(m.group(1), m.group(2), m.group(3), m.group(4))
                    end = _to_seconds(m.group(5), m.group(6), m.group(7), m.group(8))
                    body = " ".join(lines[i + 1 :]).strip()
                    if body and not body.isdigit():
                        segments.append({"start_time": start, "end_time": end, "text": body})
                    break
    else:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        per_line = 8.0
        for idx, ln in enumerate(lines):
            if ln.lower().startswith(("[music]", "[applause]")):
                continue
            segments.append(
                {"start_time": idx * per_line, "end_time": (idx + 1) * per_line, "text": ln}
            )

    return segments


def start_transcription(s3_key: str, language: str = "en-US") -> str:
    """Start an AWS Transcribe job; returns the job name. Raises RuntimeError offline."""
    if settings.demo_mode:
        raise RuntimeError("Transcription via AWS Transcribe is disabled in demo mode")
    client = boto3.client("transcribe", region_name=settings.aws_region)
    job_name = f"l2h-{uuid.uuid4().hex[:12]}"
    uri = f"s3://{settings.s3_bucket}/{s3_key}"
    kwargs = {
        "TranscriptionJobName": job_name,
        "MediaFormat": _media_format(s3_key),
        "LanguageCode": language,
        "Media": {"MediaFileUri": uri},
        "OutputBucketName": settings.s3_bucket,
    }
    if settings.transcribe_role_arn:
        kwargs["Settings"] = {"ShowSpeakerLabels": False}
    client.start_transcription_job(**kwargs)
    return job_name


def wait_for_transcription(job_name: str, timeout_s: int = 900, poll_s: float = 5.0) -> list[dict]:
    client = boto3.client("transcribe", region_name=settings.aws_region)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get_transcription_job(TranscriptionJobName=job_name)
        status_name = resp["TranscriptionJob"]["TranscriptionJobStatus"]
        if status_name == "COMPLETED":
            uri = resp["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
            raw = _read_uri(uri)
            return _segments_from_transcribe(raw)
        if status_name == "FAILED":
            raise RuntimeError(f"Transcribe job {job_name} failed")
        time.sleep(poll_s)
    raise TimeoutError(f"Transcribe job {job_name} timed out")


def _media_format(key: str) -> str:
    ext = key.rsplit(".", 1)[-1].lower()
    return {"mp4": "mp4", "mov": "mp4", "mkv": "mkv", "webm": "webm", "m4v": "mp4", "avi": "avi"}.get(ext, "mp4")


# ---------- Gemini speech-to-text (used when no .vtt/.srt caption was uploaded) ----------

GEMINI_STT_PROMPT = """Transcribe the spoken audio in this lecture.

Return ONLY a JSON array, no prose and no markdown fence. Each element:
{"start": <seconds, number>, "end": <seconds, number>, "text": "<what is said>"}

Rules:
- One object per spoken sentence or clause, in chronological order.
- start/end are seconds from the beginning of the recording, and end > start.
- text is the exact spoken wording, cleaned of filler only.
- If the audio is silent or has no speech, return []."""


def gemini_transcribe(local_path: str, language: str = "en-US") -> list[dict]:
    """Speech-to-text via Gemini (video/audio understanding). Returns timestamped segments."""
    if not settings.gemini_api_key:
        raise RuntimeError("Gemini API key not configured")

    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)

    uploaded = genai.upload_file(local_path)
    try:
        resp = llm_service.call_gemini(
            model,
            [uploaded, GEMINI_STT_PROMPT],
            generation_config={"temperature": 0.0, "response_mime_type": "application/json"},
        )
    finally:
        try:
            uploaded.delete()
        except Exception:
            pass

    return _parse_stt_payload(resp.text)


def _parse_stt_payload(text: str) -> list[dict]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return []
        try:
            raw = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []

    segments: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = str(item.get("text") or "").strip()
        if not content:
            continue
        try:
            start = float(item.get("start", 0))
            end = float(item.get("end", start + 4))
        except (TypeError, ValueError):
            continue
        end = max(end, start + 0.5)
        segments.append({"start_time": start, "end_time": end, "text": content})
    segments.sort(key=lambda s: s["start_time"])
    return segments


def extract_audio_for_stt(local_path: str, workdir: str | None = None) -> str | None:
    """Pull a compact mono 16 kHz wav out of a video so speech-to-text stays fast."""
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not os.path.exists(local_path):
        return None
    out_dir = workdir or os.path.dirname(local_path)
    dst = os.path.join(out_dir, os.path.splitext(os.path.basename(local_path))[0] + ".stt.wav")
    try:
        proc = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", local_path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst],
            capture_output=True,
            timeout=1800,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    if proc.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst
    return None


def _read_uri(uri: str) -> str:
    if uri.startswith("s3://"):
        bucket, _, key = uri[len("s3://") :].partition("/")
        s3 = boto3.client("s3", region_name=settings.aws_region)
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    import urllib.request

    with urllib.request.urlopen(uri) as r:  # noqa: S310 - AWS-signed URL
        return r.read().decode("utf-8")


def _segments_from_transcribe(raw: str) -> list[dict]:
    payload = json.loads(raw)
    alt = payload["results"]["audio_segments"]
    return [
        {
            "start_time": float(s.get("start_time", 0)),
            "end_time": float(s.get("end_time", 0)),
            "text": s.get("transcript", "").strip(),
        }
        for s in alt
        if s.get("transcript", "").strip()
    ]


def extract_duration(segments: list[dict]) -> float:
    return max((s["end_time"] for s in segments), default=0.0)


def transcript_file_for(course_materials: list) -> tuple | None:
    """Find an uploaded transcript material belonging to the same course."""
    for m in course_materials:
        if m.kind == "transcript":
            return m, None
    return None, None


def readable_error(exc: Exception) -> str:
    if isinstance(exc, (ClientError, BotoCoreError)):
        return "AWS Transcribe error: " + str(exc)[:300]
    return str(exc)[:300]
