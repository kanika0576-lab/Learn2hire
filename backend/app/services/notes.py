"""Study notes generated from the indexed material, plus a tiny on-disk cache so
notes exist the moment a build finishes."""

from __future__ import annotations

import json
import os
import re
import tempfile

from app.config import settings
from app.services import llm
from app.services.index import retrieve_for_question, search

NOTES_PROMPT = """You are writing revision notes for a student who just finished a lecture.

LANGUAGE RULES (critical):
- Write ONLY in plain, simple English. NEVER use any non-English script (no Hindi, no Devanagari, no other languages).
- Use short everyday words, the way a student would write them: "we store", "it takes time", "you can do this", not heavy academic phrasing. Keep it easy to read for a beginner.

Use the lecture transcript AND any notes/PDF/slides in the context. Produce:
1. A 4-6 sentence summary of what was taught, in easy English a beginner can follow.
2. 6-10 key points covering every main idea, each a short bullet, each ending with its source tag like [video@2:10] or [pdf p.1].
3. 4-6 likely exam questions with one-line answers.
4. 5 terms the student must memorise, each defined in one easy line.

Output ONLY valid JSON:
{"summary": str, "key_points": [str], "exam_questions": [{"q": str, "a": str}], "terms": [{"term": str, "definition": str}]}"""


def _gemini_notes(chunks: list[dict], title: str) -> dict | None:
    if not settings.gemini_api_key:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model, system_instruction=NOTES_PROMPT)
        context = llm.build_context(chunks)
        resp = llm.call_gemini(
            model,
            f"LECTURE: {title}\n\nCONTEXT:\n{context}\n\nReply with JSON only.",
            generation_config={"response_mime_type": "application/json", "temperature": 0.3},
        )
        data = llm._parse_json(resp.text)
        if data.get("summary"):
            return data
    except Exception:
        return None
    return None


def _fallback_notes(chunks: list[dict], title: str) -> dict:
    """Deterministic notes from the material itself (works offline)."""
    points: list[str] = []
    for c in chunks:
        text = re.sub(r"\s+", " ", c.get("text") or "").strip()
        if not text:
            continue
        first = re.split(r"(?<=[.!?])\s+", text)[0].strip()
        if len(first) < 25:
            first = text[:180].strip()
        points.append(f"{first} {llm.chunk_tag(c)}")
        if len(points) >= 6:
            break

    # overview-only courses (single short chunk) still deserve a usable bullet
    if not points:
        for c in chunks:
            text = re.sub(r"\s+", " ", c.get("text") or "").strip()
            if text:
                points.append(f"{text[:240]} {llm.chunk_tag(c)}")
                break

    terms = []
    for c in chunks:
        for m in re.finditer(r"\b([A-Z][a-zA-Z\-]{3,})\b", c.get("text") or ""):
            t = m.group(1)
            if t not in [x["term"] for x in terms] and len(t) > 4:
                terms.append({"term": t, "definition": f"Discussed in {llm.chunk_tag(c)}."})
            if len(terms) >= 5:
                break
        if len(terms) >= 5:
            break

    summary_bits = []
    for c in chunks[:2]:
        t = re.sub(r"\s+", " ", c.get("text") or "").strip()
        if t:
            summary_bits.append(t[:220])
    summary = " ".join(summary_bits) if summary_bits else f"No summary could be generated for {title}."

    exam = [{"q": f"Explain the main idea of {title}.", "a": points[0] if points else summary[:180]}]
    for p in points[1:4]:
        exam.append({"q": p.split(" [")[0][:120] + "?", "a": p})

    return {
        "summary": summary,
        "key_points": points,
        "exam_questions": exam,
        "terms": terms,
    }


def build(course_id: str, title: str, video_time: float | None = None) -> dict:
    chunks = search(course_id, "summary key concepts definitions examples steps", None, top_k=16, time_gate=False)
    if not chunks:
        chunks = search(course_id, "overview lecture notes", video_time, top_k=16, time_gate=False)
    if not chunks:
        return {
            "summary": f"No indexed material yet for {title}. Build the knowledge base first.",
            "key_points": [],
            "exam_questions": [],
            "terms": [],
            "generated_by": "none",
        }
    notes = _gemini_notes(chunks, title) or _fallback_notes(chunks, title)
    notes["generated_by"] = "gemini" if _gemini_available() else "offline-extractive"
    return notes


def _gemini_available() -> bool:
    return bool(settings.gemini_api_key)


# ------------------------------- cache -------------------------------

def _cache_path(course_id: str) -> str:
    d = os.path.join(tempfile.gettempdir(), "learn2hire", "notes")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{course_id}.json")


def cache_notes(course_id: str, notes: dict) -> None:
    try:
        with open(_cache_path(course_id), "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False)
    except OSError:
        pass


def get_notes(course_id: str) -> dict | None:
    p = _cache_path(course_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def clear_notes(course_id: str) -> None:
    try:
        os.remove(_cache_path(course_id))
    except OSError:
        pass
