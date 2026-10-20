"""Ingestion pipeline: upload -> transcribe -> chunk -> embed -> index.
(Video: AWS Transcribe or an uploaded .vtt/.srt/.txt transcript.)

Statuses are written back to Course/Material rows so the UI can show progress.
"""

import json
import logging
import os
import shutil
import subprocess

from sqlalchemy.orm import Session

from app.models import Course, Material
from app.services import chunking, storage, transcription
from app.services.index import get_index

log = logging.getLogger("learn2hire.ingest")

# formats browsers cannot play in <video> — remuxed/converted to mp4 during ingestion
# (avif is an image/animated-image container: always re-encoded, never stream-copied)
NEEDS_REMUX = {"mkv", "avi", "flv", "wmv", "ts", "m4v", "mov", "mts", "m2ts", "avif", "gif", "webp", "3gp"}

# image containers that can hold animation — never stream-copied, always re-encoded
IMAGE_CONTAINERS = {"avif", "gif", "webp", "apng"}


def ensure_playable(video: Material) -> None:
    """Remux browser-hostile containers (mkv/avi/mov/…) to mp4 with ffmpeg if available.

    Stream-copy first (instant, lossless); falls back to h264/aac re-encode.
    Rewrites the material row to point at the playable file. No-op for mp4/webm.
    """
    ext = video.filename.lower().rsplit(".", 1)[-1] if "." in video.filename else ""
    if ext not in NEEDS_REMUX:
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        log.warning("ffmpeg not found; %s left as-is (may not play in the browser)", video.filename)
        return

    src = video.storage_key
    if not (os.path.isabs(src) and os.path.exists(src)):
        return  # remote (S3) files are streamed as uploaded; remux is a local convenience
    dst = os.path.splitext(src)[0] + ".mp4"

    has_audio = _has_audio(src)
    # 1) copy video, normalise audio to AAC (plays everywhere, clear voice)
    # 2) full re-encode fallback (avif/image, exotic codecs, ...)
    attempts = [["-c:v", "copy"]]
    if has_audio:
        attempts[0] += ["-c:a", "aac", "-b:a", "128k"]
    attempts.append(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"])

    # Animated image containers (avif/gif/webp) must always be re-encoded: stream-copying
    # them into mp4 silently keeps only the first frame and truncates the video to ~1s.
    if ext in IMAGE_CONTAINERS:
        attempts = attempts[1:]

    for args in attempts:
        try:
            proc = subprocess.run(
                [ffmpeg, "-y", "-i", src, *args, "-movflags", "+faststart", dst],
                capture_output=True,
                timeout=1800,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
                old = src
                video.storage_key = dst
                video.filename = os.path.splitext(video.filename)[0] + ".mp4"
                try:
                    os.remove(old)
                except OSError:
                    pass
                log.info("remuxed %s -> %s", old, dst)
                return
        except Exception:
            log.exception("remux attempt failed for %s", video.filename)
    log.warning("could not remux %s; keeping original", video.filename)


def _has_audio(path: str) -> bool:
    """True when the file carries an audio stream (so we keep the voice)."""
    probe = shutil.which("ffprobe")
    if not probe:
        return True  # assume yes; the AAC copy attempt fails safely otherwise
    try:
        proc = subprocess.run(
            [probe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return b"audio" in proc.stdout
    except Exception:
        return True


def ingest_course(db: Session, course: Course) -> dict:
    course.status = "ingesting"
    course.error = ""
    db.commit()

    # Rebuilding must be idempotent: drop the previous index (and cached notes) first,
    # otherwise every "Build knowledge base" click appends a duplicate copy of each chunk.
    delete_course_data(course.id)
    try:
        from app.services.notes import clear_notes

        clear_notes(course.id)
    except Exception:
        log.exception("notes cache clear failed for %s", course.id)

    try:
        materials = list(course.materials)
        total_chunks = 0

        video = next((m for m in materials if m.kind == "video"), None)
        transcript_mat = next((m for m in materials if m.kind == "transcript"), None)

        video_blocked = False

        if video is not None:
            chunks, note, blocked = _ingest_video(db, course, video, transcript_mat, materials)
            video_blocked = blocked
            total_chunks += len(chunks)
            if chunks:
                get_index().add_chunks(chunks)
            if not blocked:
                video.status = "indexed"
            db.commit()
            if note:
                course.error = note  # surfaced as a warning in the UI

        for m in materials:
            if m.kind in ("pdf", "slides"):
                try:
                    chunks = chunking.build_for_material(course.id, m, m.storage_key)
                    if chunks:
                        get_index().add_chunks(chunks)
                    m.status = "indexed"
                except Exception as exc:  # keep going: one bad file shouldn't kill the course
                    m.status = "error"
                    course.error = f"{m.filename}: {exc}"[:400]
                    log.exception("chunk failed for %s", m.filename)
                db.commit()

        # Demo fallback: build the KB from the course title/description when there is a
        # video but no transcript / PDF / slides. Time-gated answers need a transcript;
        # this keeps the demo flow working from video alone.
        # Skip it when the video itself is unusable (e.g. a still image) — never paper
        # over a broken upload by declaring the course ready.
        if video is not None and not video_blocked and get_index().count(course.id) == 0:
            duration = float(video.duration_seconds or 0.0)
            end = duration if duration > 0 else 300.0
            text = f"{course.title}. {course.description}".strip(" .")
            if text:
                overview = chunking.chunk_video_overview(
                    course.id, video.id, video.filename, 0.0, end, text
                )
                if overview:
                    get_index().add_chunks(overview)
                    video.status = "indexed"
                    course.error = ""
                    db.commit()

        idx_count = get_index().count(course.id)
        if idx_count == 0:
            course.status = "error"
            course.error = course.error or "No text could be extracted. Upload a transcript (.vtt/.srt/.txt) with the video, or a PDF/slides."
        else:
            course.status = "ready"
        db.commit()

        # Build the revision notes straight away so the learner has something to read
        # the moment the knowledge base is ready (cached for the Notes tab).
        if course.status == "ready":
            try:
                from app.services.notes import build as build_notes, cache_notes

                built = build_notes(course.id, course.title)
                cache_notes(course.id, built)
            except Exception:
                log.exception("notes generation failed for %s", course.id)

        return {"status": course.status, "chunks": idx_count, "message": course.error}
    except Exception as exc:
        course.status = "error"
        course.error = str(exc)[:600]
        db.commit()
        log.exception("ingestion failed")
        return {"status": "error", "chunks": 0, "message": course.error}


def _ingest_video(
    db: Session, course: Course, video: Material, transcript_mat: Material | None, materials: list[Material]
) -> tuple[list[dict], str, bool]:
    """Return (chunks, warning, blocked). blocked=True means the upload is unusable."""
    segments: list[dict] = []
    warning = ""

    ensure_playable(video)

    # A still image (e.g. an .avif thumbnail) converts to a ~1s "video" that can never be
    # a lecture. Detect it up front and say so plainly instead of pretending it indexed.
    src_path = video.storage_key
    if os.path.isabs(src_path) and os.path.exists(src_path):
        dur, has_video, has_audio, probe_ok = _probe(src_path)
        if probe_ok:
            video.duration_seconds = dur
            if not has_video or dur < 2.0:
                video.status = "error"
                db.commit()
                return [], (
                    f"“{video.filename}” is only {dur:.0f}s long — it looks like a still image, "
                    "not a lecture video. Upload the real video file "
                    "(.mp4/.mkv/.webm downloaded from YouTube) and build again."
                ), True
            if not has_audio:
                warning = (
                    f"“{video.filename}” has no audio track, so it cannot be transcribed automatically — "
                    "add a .vtt/.srt caption file to get a full transcript."
                )

    if transcript_mat is not None:
        data = storage.read_file(transcript_mat.storage_key)
        segments = transcription.parse_transcript_bytes(data, transcript_mat.filename)
        transcript_mat.status = "transcribed"
        db.commit()

    if not segments and not _demo_mode():
        try:
            job = transcription.start_transcription(video.storage_key)
            segments = transcription.wait_for_transcription(job)
            video.status = "transcribed"
            db.commit()
        except Exception as exc:
            warning = (
                "AWS Transcribe could not run ("
                + transcription.readable_error(exc)
                + "). Add a .vtt/.srt/.txt transcript file for this video."
            )

    # No captions uploaded -> run speech-to-text on the audio ourselves, so a plain
    # video download still gets a full, timestamped knowledge base.
    if not segments:
        segments, stt_note = _auto_transcribe(video)
        if stt_note:
            warning = stt_note

    if not segments:
        return [], warning or (
            "No transcript for the video yet. Drop the video together with its caption file "
            "(.vtt/.srt — YouTube downloads include one, e.g. 'video.en.vtt'), or upload a .txt transcript."
        ), False

    video.duration_seconds = transcription.extract_duration(segments)
    db.commit()
    chunks = chunking.chunk_video_transcript(course.id, video.id, video.filename, segments)
    return chunks, warning, False


def _probe(path: str) -> tuple[float, bool, bool, bool]:
    """Return (duration_seconds, has_video, has_audio, probe_ok).

    probe_ok=False means we could not measure the file at all (not a decodable
    container) — callers must not treat that as "too short".
    """
    probe = shutil.which("ffprobe")
    if not probe:
        return 0.0, True, True, False
    try:
        proc = subprocess.run(
            [
                probe, "-v", "error",
                "-show_entries", "format=duration:stream=codec_type",
                "-of", "json", path,
            ],
            capture_output=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        data = json.loads(proc.stdout or "{}")
        types = {s.get("codec_type") for s in data.get("streams", [])}
        if not types:
            return 0.0, True, True, False
        dur = float(data.get("format", {}).get("duration") or 0.0)
        return dur, "video" in types, "audio" in types, True
    except Exception:
        return 0.0, True, True, False


def _auto_transcribe(video: Material) -> tuple[list[dict], str]:
    """Speech-to-text the video when no caption file was supplied.

    Uses Gemini's audio understanding (needs GEMINI_API_KEY). Returns (segments, note).
    """
    from app.config import settings

    if not settings.gemini_api_key:
        return [], ""
    path = video.storage_key
    if not (os.path.isabs(path) and os.path.exists(path)):
        return [], ""

    audio = transcription.extract_audio_for_stt(path)
    if not audio:
        return [], "Could not extract audio from this video for speech-to-text."
    try:
        segments = transcription.gemini_transcribe(audio)
    except Exception as exc:
        log.warning("gemini stt failed: %s", exc)
        return [], f"Speech-to-text failed ({transcription.readable_error(exc)})."
    finally:
        try:
            os.remove(audio)
        except OSError:
            pass

    if segments:
        video.status = "transcribed"
        log.info("speech-to-text produced %d segments for %s", len(segments), video.filename)
        return segments, ""
    return [], "Speech-to-text found no speech in this video — it may be silent."


def _demo_mode() -> bool:
    from app.config import settings

    return settings.demo_mode


def delete_course_data(course_id: str) -> None:
    try:
        get_index().delete_course(course_id)
    except Exception:
        log.exception("index delete failed")
