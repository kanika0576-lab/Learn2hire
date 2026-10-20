"""Chunking: every chunk is tagged with its source position
(video time / pdf page / slide) so retrieval can be time-gated."""

import io
import re
import uuid

from app.services import storage

MAX_VIDEO_SECONDS = 45.0
MAX_DOC_CHARS = 900


def _cid() -> str:
    return uuid.uuid4().hex[:12]


def chunk_video_transcript(course_id: str, material_id: str, source_name: str, segments: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    bucket: list[dict] = []

    def flush():
        if not bucket:
            return
        start = bucket[0]["start_time"]
        end = bucket[-1]["end_time"]
        text = " ".join(s["text"] for s in bucket).strip()
        if text:
            chunks.append(
                {
                    "chunk_id": _cid(),
                    "course_id": course_id,
                    "material_id": material_id,
                    "source_type": "video",
                    "source_name": source_name,
                    "start_time": round(start, 2),
                    "end_time": round(end, 2),
                    "page": None,
                    "slide": None,
                    "text": text,
                }
            )
        bucket.clear()

    for seg in segments:
        if bucket and (
            seg["end_time"] - bucket[0]["start_time"] > MAX_VIDEO_SECONDS
            or sum(len(s["text"]) for s in bucket) > MAX_DOC_CHARS
        ):
            flush()
        bucket.append(seg)
    flush()
    return chunks


def chunk_pdf(course_id: str, material_id: str, source_name: str, data: bytes) -> list[dict]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    chunks: list[dict] = []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = re.sub(r"[ \t]+", " ", text).strip()
        if not text:
            continue
        for piece in _split_text(text, MAX_DOC_CHARS):
            chunks.append(
                {
                    "chunk_id": _cid(),
                    "course_id": course_id,
                    "material_id": material_id,
                    "source_type": "pdf",
                    "source_name": source_name,
                    "start_time": None,
                    "end_time": None,
                    "page": page_no,
                    "slide": None,
                    "text": piece,
                }
            )
    return chunks


def chunk_slides(course_id: str, material_id: str, source_name: str, data: bytes) -> list[dict]:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    chunks: list[dict] = []
    for slide_no, slide in enumerate(prs.slides, start=1):
        parts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in para.runs).strip()
                    if t:
                        parts.append(t)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
        text = "\n".join(parts).strip()
        if not text:
            continue
        for piece in _split_text(text, MAX_DOC_CHARS):
            chunks.append(
                {
                    "chunk_id": _cid(),
                    "course_id": course_id,
                    "material_id": material_id,
                    "source_type": "slides",
                    "source_name": source_name,
                    "start_time": None,
                    "end_time": None,
                    "page": None,
                    "slide": slide_no,
                    "text": piece,
                }
            )
    return chunks


def _split_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            nl = text.rfind("\n", start, end)
            para = text.rfind(". ", start, end)
            cut = max(nl, para)
            if cut > start + max_chars // 2:
                end = cut + 1
        pieces.append(text[start:end].strip())
        start = end
    return [p for p in pieces if p]


def build_for_material(course_id: str, material, storage_key: str) -> list[dict]:
    """Dispatch chunking by material kind. For video, requires a transcript material too."""
    if material.kind == "pdf":
        return chunk_pdf(course_id, material.id, material.filename, storage.read_file(storage_key))
    if material.kind == "slides":
        return chunk_slides(course_id, material.id, material.filename, storage.read_file(storage_key))
    return []


def chunk_video_overview(
    course_id: str, material_id: str, source_name: str, start_time: float, end_time: float, text: str
) -> list[dict]:
    """Single chunk spanning a video range, used when no transcript is available."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    return [
        {
            "chunk_id": _cid(),
            "course_id": course_id,
            "material_id": material_id,
            "source_type": "video",
            "source_name": source_name,
            "start_time": round(start_time, 2),
            "end_time": round(end_time, 2),
            "page": None,
            "slide": None,
            "text": text,
        }
    ]
