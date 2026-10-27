"""Sniff uploaded media and convert anything the browser cannot play into H.264 MP4."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess

log = logging.getLogger("learn2hire.convert")

IMAGE_CONTAINERS = {"avif", "gif", "webp", "apng"}
ALWAYS_CONVERT = {
    "mkv", "avi", "flv", "wmv", "ts", "m4v", "mov", "mts", "m2ts",
    "avif", "gif", "webp", "3gp", "webm",
}
PLAYABLE_VIDEO = {"h264", "avc1"}
PLAYABLE_AUDIO = {"aac", "mp3", "opus"}  # aac preferred; we still re-encode others


def sniff_ext(path: str, filename: str = "") -> str:
    """Guess the real container from magic bytes, not the download's filename."""
    fallback = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
    except OSError:
        return fallback
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"avif", b"avis", b"mif1", b"miaf"):
            return "avif"
        return "mp4"
    if head[:4] == b"\x1aE\xdf\xa3":
        # EBML: Matroska / WebM
        if b"webm" in head.lower() or filename.lower().endswith(".webm"):
            return "webm"
        return "mkv"
    if head[:3] == b"GIF":
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return fallback


def probe_codecs(path: str) -> dict:
    """Return duration, codec names, and stream presence. Empty dict if unreadable."""
    probe = shutil.which("ffprobe")
    if not probe or not os.path.exists(path):
        return {}
    try:
        proc = subprocess.run(
            [
                probe, "-v", "error",
                "-show_entries", "format=duration:stream=codec_type,codec_name",
                "-of", "json", path,
            ],
            capture_output=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        data = json.loads(proc.stdout or "{}")
    except Exception:
        return {}
    streams = data.get("streams") or []
    types = {s.get("codec_type") for s in streams}
    vcodec = next((s.get("codec_name") for s in streams if s.get("codec_type") == "video"), "")
    acodec = next((s.get("codec_name") for s in streams if s.get("codec_type") == "audio"), "")
    try:
        duration = float((data.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration": duration,
        "has_video": "video" in types,
        "has_audio": "audio" in types,
        "vcodec": vcodec or "",
        "acodec": acodec or "",
        "ok": bool(types),
    }


def needs_mp4(filename: str, info: dict | None = None) -> bool:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in ALWAYS_CONVERT or ext in IMAGE_CONTAINERS:
        return True
    if not info:
        return ext not in {"mp4"}
    if info.get("vcodec") and info["vcodec"] not in PLAYABLE_VIDEO:
        return True
    if info.get("has_audio") and info.get("acodec") and info["acodec"] not in PLAYABLE_AUDIO:
        return True
    return ext != "mp4"


def convert_to_mp4(src: str, ext: str, has_audio: bool) -> str | None:
    """Write sibling .mp4. Returns destination path or None."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        log.warning("ffmpeg not found; cannot convert %s", src)
        return None
    dst = os.path.splitext(src)[0] + ".mp4"
    # Image/animated containers and exotic codecs cannot be stream-copied.
    attempts: list[list[str]] = []
    if ext not in IMAGE_CONTAINERS:
        copy = ["-c:v", "copy"]
        if has_audio:
            copy += ["-c:a", "aac", "-b:a", "128k"]
        attempts.append(copy)
    encode = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    if has_audio:
        encode += ["-c:a", "aac", "-b:a", "128k"]
    else:
        encode += ["-an"]
    attempts.append(encode)

    for args in attempts:
        try:
            proc = subprocess.run(
                [ffmpeg, "-y", "-i", src, *args, "-movflags", "+faststart", dst],
                capture_output=True,
                timeout=1800,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
                return dst
        except Exception:
            log.exception("convert attempt failed for %s", src)
    return None


def ensure_playable(video) -> None:
    """Rewrite a Material row so the stored file is a browser-playable H.264 MP4."""
    src = video.storage_key
    if not (os.path.isabs(src) and os.path.exists(src)):
        return
    real_ext = sniff_ext(src, video.filename)
    info = probe_codecs(src)
    if info.get("ok"):
        video.duration_seconds = info["duration"]
    # A YouTube download often keeps the wrong extension (.avif for an mp4).
    # Rename so the player sends video/mp4 even when no re-encode is needed.
    if real_ext == "mp4" and not video.filename.lower().endswith(".mp4"):
        dst = os.path.splitext(src)[0] + ".mp4"
        if dst != src:
            try:
                os.replace(src, dst)
                src = dst
                video.storage_key = dst
            except OSError:
                pass
        video.filename = os.path.splitext(video.filename)[0] + ".mp4"
    if not needs_mp4(video.filename if not real_ext else f"file.{real_ext}", info or None):
        return
    dst = convert_to_mp4(src, real_ext, bool(info.get("has_audio", True)))
    if not dst:
        log.warning("could not convert %s; keeping original", video.filename)
        return
    old = src
    video.storage_key = dst
    base = os.path.splitext(video.filename)[0]
    video.filename = base + ".mp4"
    try:
        if old != dst:
            os.remove(old)
    except OSError:
        pass
    log.info("converted %s -> %s", old, dst)


def segments_to_vtt(segments: list[dict]) -> str:
    """Timestamped segments -> WebVTT text the <track> tag can load."""
    def fmt(t: float) -> str:
        t = max(0.0, float(t))
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}"

    lines = ["WEBVTT", ""]
    for i, seg in enumerate(segments, start=1):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = seg.get("start_time", 0)
        end = seg.get("end_time", start + 3)
        if end <= start:
            end = start + 1.5
        lines.append(str(i))
        lines.append(f"{fmt(start)} --> {fmt(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)
