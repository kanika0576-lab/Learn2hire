"""Unit tests for media sniffing, VTT generation, and quiz/notes helpers.
Run from backend/:  python tests/test_media.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.convert import needs_mp4, segments_to_vtt, sniff_ext
from app.routers.quiz import _template_questions
from app.services.notes import _fallback_notes

ok = True


def check(label, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {label}{(' :: ' + detail) if detail else ''}")
    if not cond:
        ok = False


def test_sniff():
    with tempfile.TemporaryDirectory() as d:
        mp4 = os.path.join(d, "lecture.avif")  # misnamed YouTube-style file
        with open(mp4, "wb") as f:
            f.write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
        check("sniff misnamed avif that is mp4", sniff_ext(mp4, "lecture.avif") == "mp4")

        still = os.path.join(d, "thumb.avif")
        with open(still, "wb") as f:
            f.write(b"\x00\x00\x00\x1cftypavif" + b"\x00" * 32)
        check("sniff real avif still", sniff_ext(still, "thumb.avif") == "avif")

        webm = os.path.join(d, "clip.webm")
        with open(webm, "wb") as f:
            f.write(b"\x1aE\xdf\xa3" + b"webm" + b"\x00" * 20)
        check("sniff webm", sniff_ext(webm, "clip.webm") == "webm")


def test_needs_mp4():
    check("mkv needs convert", needs_mp4("talk.mkv") is True)
    check("avif needs convert", needs_mp4("clip.avif") is True)
    check("webm needs convert", needs_mp4("clip.webm") is True)
    check("h264 mp4 can skip", needs_mp4("talk.mp4", {"vcodec": "h264", "has_audio": True, "acodec": "aac"}) is False)
    check("av1 mp4 needs convert", needs_mp4("talk.mp4", {"vcodec": "av1", "has_audio": True, "acodec": "aac"}) is True)


def test_vtt():
    vtt = segments_to_vtt(
        [
            {"start_time": 0, "end_time": 2.5, "text": "Hello class"},
            {"start_time": 2.5, "end_time": 6, "text": "Today we learn stacks"},
        ]
    )
    check("vtt header", vtt.startswith("WEBVTT"))
    check("vtt has cue text", "Hello class" in vtt and "stacks" in vtt)
    check("vtt timestamps", "00:00:00.000 --> 00:00:02.500" in vtt)


def test_quiz_and_notes():
    chunks = [
        {
            "text": "A stack is a LIFO structure. Push adds to the top, pop removes from the top.",
            "source_type": "video",
            "source_name": "lecture.mp4",
            "start_time": 60,
            "page": None,
            "slide": None,
        },
        {
            "text": "A queue is FIFO. Enqueue adds at the rear, dequeue removes from the front.",
            "source_type": "pdf",
            "source_name": "notes.pdf",
            "start_time": None,
            "page": 2,
            "slide": None,
        },
    ]
    qs = _template_questions(chunks, 3)
    check("template quiz from lecture sentences", len(qs) >= 1, f"n={len(qs)}")
    if qs:
        check("quiz has 4 options", len(qs[0]["options"]) == 4)
        check("quiz grounded in material", "LIFO" in qs[0]["question"] or "stack" in qs[0]["question"].lower() or "_____ " in qs[0]["question"])
    notes = _fallback_notes(chunks, "Intro to DSA")
    check("notes summary nonempty", len(notes["summary"]) > 20)
    check("notes key points from lecture", len(notes["key_points"]) >= 1)


if __name__ == "__main__":
    test_sniff()
    test_needs_mp4()
    test_vtt()
    test_quiz_and_notes()
    print("\nDONE" + (" (ok)" if ok else " (FAILURES)"))
    sys.exit(0 if ok else 1)
