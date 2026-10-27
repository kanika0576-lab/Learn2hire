"""Ingestion pipeline: upload -> transcribe -> chunk -> embed -> index.
(Video: AWS Transcribe or an uploaded .vtt/.srt/.txt transcript.)

Statuses are written back to Course/Material rows so the UI can show progress.
"""

import logging
import os

from sqlalchemy.orm import Session

from app.models import Course, Material
from app.services import chunking, storage, transcription
from app.services.convert import ensure_playable, probe_codecs, segments_to_vtt
from app.services.index import get_index

log = logging.getLogger("learn2hire.ingest")


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
        info = probe_codecs(src_path)
        if info.get("ok"):
            dur = info["duration"]
            video.duration_seconds = dur
            if not info["has_video"] or dur < 2.0:
                video.status = "error"
                db.commit()
                return [], (
                    f"“{video.filename}” is only {dur:.0f}s long — it looks like a still image "
                    "(YouTube thumbnails are often .avif pictures), not a lecture. "
                    "Upload the real video (.mp4 / .mkv / .webm) and build again."
                ), True
            if not info["has_audio"]:
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
    if transcript_mat is None:
        try:
            _save_generated_captions(db, course, video, segments)
        except Exception:
            log.exception("could not persist generated captions")
    db.commit()
    chunks = chunking.chunk_video_transcript(course.id, video.id, video.filename, segments)
    return chunks, warning, False


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


def _save_generated_captions(db: Session, course: Course, video: Material, segments: list[dict]) -> None:
    """Persist auto-generated captions as a .vtt so the player can show CC and notes stay timestamped."""
    already = next((m for m in course.materials if m.kind == "transcript"), None)
    if already:
        return
    vtt = segments_to_vtt(segments)
    name = os.path.splitext(video.filename)[0] + ".generated.vtt"
    key = storage.save_upload(course.id, name, vtt.encode("utf-8"))
    db.add(
        Material(
            course_id=course.id,
            kind="transcript",
            filename=name,
            storage_key=key,
            status="transcribed",
        )
    )
    db.commit()


def _demo_mode() -> bool:
    from app.config import settings

    return settings.demo_mode


def delete_course_data(course_id: str) -> None:
    try:
        get_index().delete_course(course_id)
    except Exception:
        log.exception("index delete failed")
