"""Answer generation: Claude on Amazon Bedrock (real path) with a deterministic
extractive fallback used in DEMO_MODE, so the prototype always demonstrates."""

import json
import re
from typing import Any

from app.config import settings, GEMINI_TIMEOUT

_client = None
_gemini_client = None

# Last provider failure (bad model name, quota, bad key…). Kept so a silent fallback
# to the offline extractor is visible in /api/health instead of looking like success.
_last_error: str = ""


def last_provider_error() -> str:
    return _last_error


def _note_error(exc: Exception) -> None:
    global _last_error
    _last_error = f"{type(exc).__name__}: {str(exc)[:220]}"


def _clear_error() -> None:
    global _last_error
    _last_error = ""


def call_gemini(model, contents, generation_config=None, attempts: int = 3):
    """generate_content with backoff on 429/quota and transient 5xx.

    Free-tier Gemini keys are rate limited; one retry keeps a burst of demo clicks
    from silently degrading into the offline extractor.
    """
    import time

    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return model.generate_content(
                contents,
                generation_config=generation_config,
                request_options=GEMINI_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 - inspect and decide
            last_exc = exc
            msg = str(exc).lower()
            transient = (
                "429" in msg
                or "resource_exhausted" in msg
                or "quota" in msg
                or "500" in msg
                or "503" in msg
                or "not found" in msg
                or "404" in msg
            )
            if not transient or i == attempts - 1:
                raise
            time.sleep(1.5 * (i + 1) ** 2)  # 1.5s, 6s
    raise last_exc  # pragma: no cover


def active_provider() -> str:
    """Which answer engine is actually in use right now."""
    pref = (settings.llm_provider or "auto").lower()
    if pref == "gemini":
        return "gemini" if settings.gemini_api_key else "demo"
    if pref == "bedrock":
        return "bedrock"
    if pref == "demo":
        return "demo"
    if settings.gemini_api_key:
        return "gemini"
    return "demo-offline" if settings.demo_mode else "bedrock"


_GEMINI_FALLBACKS = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-1.5-flash")


def _gemini(system_instruction: str | None = None):
    global _gemini_client
    instruction = system_instruction or SYSTEM_PROMPT
    if _gemini_client is None or getattr(_gemini_client, "_l2h_instruction", None) != instruction:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model_name = settings.gemini_model or _GEMINI_FALLBACKS[0]
        last_exc: Exception | None = None
        for name in (model_name, *_GEMINI_FALLBACKS):
            try:
                client = genai.GenerativeModel(name, system_instruction=instruction)
                client._l2h_instruction = instruction  # type: ignore[attr-defined]
                _gemini_client = client
                return _gemini_client
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        if last_exc:
            raise last_exc
    return _gemini_client

SYSTEM_PROMPT = """You are Learn2Hire, a timestamp-aware course tutor inside a video player.
You receive ONLY the course material that the learner has already reached (video time gate applied upstream).

Rules:
0. LANGUAGE: answer only in plain, simple English. Never use Devanagari/Hindi script or any non-English language.
1. Answer the student's doubt clearly. Teach the idea, then give a short example, using ONLY the CONTEXT chunks. Never invent facts.
2. Cite every claim inline using the chunk tags given: [video@seconds], [pdf p.N], [slides s.N].
3. If the CONTEXT does not contain the answer, reply with exactly: NOT_IN_MATERIAL: <short reason>
4. If the question is about content that seems to come later in the course, reply with exactly: COVERED_LATER: <short hint>
5. Be friendly and tutorial-like. Prefer 80–160 words when explaining a concept. Do not refuse a question that is clearly covered in CONTEXT.
6. Output ONLY valid JSON with keys: answer (string), in_material (bool), covered_later (bool).
"""


def _bedrock():
    global _client
    if _client is None:
        import boto3

        _client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    return _client


def fmt_seconds(t: float | None) -> str:
    if t is None:
        return "0:00"
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"


def chunk_tag(c: dict) -> str:
    if c.get("source_type") == "video":
        return f"[video@{fmt_seconds(c.get('start_time'))}]"
    if c.get("source_type") == "pdf":
        return f"[pdf p.{c.get('page')}]"
    return f"[slides s.{c.get('slide')}]"


def build_context(chunks: list[dict]) -> str:
    parts = []
    used = 0
    for i, c in enumerate(chunks, start=1):
        block = f"<chunk id={i} tag={chunk_tag(c)} source={c.get('source_name','')}>\n{c['text']}\n</chunk>"
        if used + len(block) > settings.max_context_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def source_label(c: dict) -> str:
    name = c.get("source_name", "material")
    if c.get("source_type") == "video":
        return f"{name} @ {fmt_seconds(c.get('start_time'))}"
    if c.get("source_type") == "pdf":
        return f"{name} p.{c.get('page')}"
    return f"{name} s.{c.get('slide')}"


def to_source(c: dict) -> dict:
    return {
        "type": c.get("source_type", "video"),
        "label": source_label(c),
        "start_time": c.get("start_time"),
        "page": c.get("page"),
        "slide": c.get("slide"),
        "quote": (c.get("text") or "")[:220],
    }


def generate_answer(
    question: str,
    chunks: list[dict],
    covered_later: bool,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    if covered_later and not chunks:
        return {
            "answer": (
                "COVERED_LATER: This topic is covered later in the lecture — you haven't reached it yet. "
                "Please watch more of the video first, then I'll be able to answer."
            ),
            "sources": [],
            "in_material": False,
            "covered_later": True,
        }
    if not chunks:
        return {
            "answer": (
                "NOT_IN_MATERIAL: I couldn't find this in the material you've watched so far. "
                "Try rephrasing your question, or check the PDF/slides attached to this course."
            ),
            "sources": [],
            "in_material": False,
            "covered_later": False,
        }
    provider = active_provider()
    overview_only = len(chunks) == 1
    if provider == "gemini":
        try:
            result = _gemini_answer(question, chunks, history or [])
            _clear_error()
            return result
        except Exception as exc:
            _note_error(exc)
            return _extractive_answer(question, chunks, overview_only)
    if provider == "bedrock":
        try:
            result = _bedrock_answer(question, chunks, history or [])
            _clear_error()
            return result
        except Exception as exc:
            _note_error(exc)
            return _extractive_answer(question, chunks, overview_only)
    return _extractive_answer(question, chunks, overview_only)


def _gemini_answer(question: str, chunks: list[dict], history: list[dict]) -> dict[str, Any]:
    context = build_context(chunks)
    convo = [
        {"role": ("model" if m["role"] == "assistant" else "user"), "parts": [m["content"]]}
        for m in history[-6:]
    ]
    convo.append(
        {
            "role": "user",
            "parts": [f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nReply with JSON only."],
        }
    )
    resp = call_gemini(
        _gemini(),
        convo,
        generation_config={"response_mime_type": "application/json", "temperature": 0.2, "max_output_tokens": 700},
    )
    text = resp.text
    data = _parse_json(text)
    answer = data.get("answer", text)
    in_material = bool(data.get("in_material", not answer.startswith(("NOT_IN_MATERIAL", "COVERED_LATER"))))
    covered = bool(data.get("covered_later", answer.startswith("COVERED_LATER")))
    sources = [to_source(c) for c in chunks[:4]]
    return {
        "answer": answer,
        "sources": sources if in_material else sources,
        "in_material": in_material,
        "covered_later": covered,
    }


def _bedrock_answer(question: str, chunks: list[dict], history: list[dict]) -> dict[str, Any]:
    context = build_context(chunks)
    turns = [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
    messages = turns + [
        {
            "role": "user",
            "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nReply with JSON only.",
        }
    ]
    resp = _bedrock().converse(
        modelId=settings.bedrock_model_id,
        system=[{"text": SYSTEM_PROMPT}],
        messages=messages,
        inferenceConfig={"maxTokens": 700, "temperature": 0.2},
    )
    text = resp["output"]["message"]["content"][0]["text"]
    data = _parse_json(text)
    answer = data.get("answer", text)
    in_material = bool(data.get("in_material", not answer.startswith(("NOT_IN_MATERIAL", "COVERED_LATER"))))
    covered = bool(data.get("covered_later", answer.startswith("COVERED_LATER")))
    cited = set(re.findall(r"\[video@(\d+:\d{2})\]|\[pdf p\.(\d+)\]|\[slides s\.(\d+)\]", answer))
    sources = [to_source(c) for c in chunks[:4]]
    return {
        "answer": answer,
        "sources": sources if in_material else ([] if not cited else sources),
        "in_material": in_material,
        "covered_later": covered,
    }


def _extractive_answer(question: str, chunks: list[dict], overview_only: bool = False) -> dict[str, Any]:
    """Deterministic offline answer: rank chunks against the question, quote the best."""
    from app.services.embeddings import tokenize

    q_terms = set(tokenize(question)) - {
        "what", "is", "the", "a", "an", "of", "in", "to", "how", "why", "and", "or",
        "do", "does", "did", "explain", "tell", "me", "about", "this", "that", "it",
        "when", "where", "who", "which", "are", "was", "were", "there", "any", "you",
    }
    scored: list[tuple[float, dict]] = []
    for c in chunks:
        t_terms = set(tokenize(c["text"]))
        overlap = len(q_terms & t_terms)
        if overlap == 0:
            continue
        coverage = overlap / max(len(q_terms), 1)
        scored.append((coverage + 0.15 * overlap, c))
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        # Course has only an overview chunk (no transcript yet): answer from it instead of
        # bouncing the learner to "not in the material", but say what is limited.
        if overview_only and chunks:
            c = chunks[0]
            return {
                "answer": (
                    f"This course doesn't have a transcript yet, so I can only share the course overview: "
                    f"\"{(c.get('text') or '').strip()}\" {chunk_tag(c)}. "
                    "Add a .vtt/.srt caption file (or a transcript) to the course and I'll answer with "
                    "exact quotes and timestamps."
                ),
                "sources": [to_source(c)],
                "in_material": True,
                "covered_later": False,
            }
        return {
            "answer": (
                "NOT_IN_MATERIAL: I couldn't find that in the material you've watched so far. "
                "Try rephrasing, or check the PDF/slides attached to this course."
            ),
            "sources": [],
            "in_material": False,
            "covered_later": False,
        }

    top = [c for _, c in scored[:3]]
    sentences: list[tuple[dict, str]] = []
    seen_text: set[str] = set()
    for c in top:
        c_terms = set(tokenize(c["text"]))
        picked = ""
        for s in re.split(r"(?<=[.!?])\s+", c["text"]):
            if (q_terms & set(tokenize(s))) and 40 <= len(s) <= 400:
                picked = s.strip()
                break
        if not picked:
            picked = c["text"][:260].strip()
        # de-duplicate: overlapping chunks often restate the same sentence
        key = re.sub(r"[^a-z0-9 ]", "", picked.lower())[:90]
        if key and key in seen_text:
            continue
        seen_text.add(key)
        sentences.append((c, picked))

    if not sentences:
        return {
            "answer": (
                "NOT_IN_MATERIAL: I couldn't find that in the material you've watched so far. "
                "Try rephrasing, or check the PDF/slides attached to this course."
            ),
            "sources": [],
            "in_material": False,
            "covered_later": False,
        }

    lines = [f"Based on the material you've watched: {sent[1]} {chunk_tag(sent[0])}" for sent in sentences[:3]]
    answer = " ".join(lines)
    return {
        "answer": answer,
        "sources": [to_source(c) for c, _ in sentences[:3]],
        "in_material": True,
        "covered_later": False,
    }


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}
