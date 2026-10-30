
import json
import random
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Course, QuizAttempt, User
from app.schemas import QuizGenerateIn, QuizGenerateOut, QuizResultOut, QuizSubmitIn
from app.security import get_current_user
from app.services import llm
from app.services.index import search

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


@router.post("/generate", response_model=QuizGenerateOut)
def generate(body: QuizGenerateIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = _owned(body.course_id, user, db)
    if course.status != "ready":
        raise HTTPException(409, f"Course is '{course.status}'")
    questions = build_questions(course.id, body.video_time, body.n_questions)
    if not questions:
        raise HTTPException(422, "Not enough indexed material to build a quiz yet")
    _store_attempt(db, course.id, user.id, questions)
    return QuizGenerateOut(questions=questions)


@router.post("/submit", response_model=QuizResultOut)
def submit(body: QuizSubmitIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = _owned(body.course_id, user, db)
    attempt = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.course_id == course.id, QuizAttempt.user_id == user.id)
        .order_by(QuizAttempt.created_at.desc())
        .first()
    )
    if attempt is None:
        raise HTTPException(404, "No quiz attempt found for this course")
    questions = json.loads(attempt.questions_json)
    detail = grade(questions, {str(k): int(v) for k, v in body.answers.items()})
    score = sum(1 for d in detail if d["correct"])
    attempt.score = score
    attempt.total = len(questions)
    attempt.answers_json = json.dumps(body.answers, ensure_ascii=False)
    db.commit()
    return QuizResultOut(
        score=score,
        total=len(questions),
        detail=[{**d, "question": next(q["question"] for q in questions if q["id"] == d["id"])} for d in detail],
    )


def _store_attempt(db: Session, course_id: str, user_id: str, questions: list[dict]) -> None:
    db.add(
        QuizAttempt(
            course_id=course_id,
            user_id=user_id,
            total=len(questions),
            questions_json=json.dumps(questions, ensure_ascii=False),
        )
    )
    db.commit()


def _owned(course_id: str, user: User, db: Session) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.owner_id != user.id:
        raise HTTPException(404, "Course not found")
    return course


# ============================ generation + grading ============================

_bedrock_client = None


def _bedrock():
    global _bedrock_client
    if _bedrock_client is None:
        import boto3

        _bedrock_client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    return _bedrock_client


def build_questions(course_id: str, video_time: float | None, n: int, history: list[dict] | None = None) -> list[dict]:
    seed_chunks = search(course_id, "key concepts definitions examples steps why how", video_time, top_k=12)
    if not seed_chunks:
        seed_chunks = search(course_id, "introduction basics summary", None, top_k=12, time_gate=False)
    if not seed_chunks:
        seed_chunks = search(course_id, "overview", None, top_k=12, time_gate=False)
    if not seed_chunks:
        return []
    provider = llm.active_provider()
    questions: list[dict] = []
    try:
        if provider == "gemini":
            questions = _gemini_questions(seed_chunks, n)
        elif provider == "bedrock":
            questions = _bedrock_questions(seed_chunks, n)
    except Exception:
        questions = []
    if len(questions) < max(2, n // 2):
        questions = _template_questions(seed_chunks, n)
    return questions[:n]


def grade(questions: list[dict], answers: dict[str, int]) -> list[dict]:
    detail = []
    for q in questions:
        given = answers.get(q["id"])
        correct = given is not None and int(given) == int(q["correct_index"])
        detail.append(
            {
                "id": q["id"],
                "correct": correct,
                "given": given,
                "correct_index": q["correct_index"],
                "explanation": q.get("explanation", ""),
            }
        )
    return detail


def _template_questions(chunks: list[dict], n: int) -> list[dict]:
    """Deterministic offline quiz: build cloze-style MCQs from real sentences."""
    rng = random.Random(sum(ord(c) for c in "".join(c["text"][:40] for c in chunks)))
    pool: list[tuple[dict, list[str]]] = []
    stop = {"the", "a", "an", "of", "in", "to", "and", "is", "are", "for", "on", "with"}
    for c in chunks:
        for sent in re.split(r"(?<=[.!?])\s+", c["text"]):
            words = sent.split()
            content = [w for w in words if w.strip(".,()").lower() not in stop and len(w.strip(".,()")) > 3]
            if len(words) < 8 or len(content) < 3:
                continue
            target = content[min(len(content) // 2, len(content) - 1)].strip(".,()")
            if not target:
                continue
            distractors = _distractors(target, chunks, rng)
            if not distractors:
                continue
            options = distractors + [target]
            rng.shuffle(options)
            pool.append(
                (
                    {
                        "sentence": sent.strip(),
                        "target": target,
                        "options": options,
                        "correct_index": options.index(target),
                        "chunk": c,
                    },
                    options,
                )
            )
        if len(pool) >= n * 3:
            break

    seen_targets: set[str] = set()
    questions = []
    for (item, _) in pool:
        tkey = item["target"].lower()
        if tkey in seen_targets:
            continue
        seen_targets.add(tkey)
        masked = item["sentence"].replace(item["target"], "_____", 1)
        questions.append(
            {
                "id": uuid.uuid4().hex[:10],
                "question": f"Fill in the blank: {masked}",
                "options": item["options"],
                "correct_index": item["correct_index"],
                "explanation": f"The source sentence is: “{item['sentence']}”",
                "source": llm.to_source(item["chunk"]),
            }
        )
        if len(questions) >= n:
            break
    return questions


def _distractors(target: str, chunks: list[dict], rng: random.Random) -> list[str]:
    vocab = set()
    for c in chunks:
        for w in re.findall(r"[A-Za-z][A-Za-z-]{4,}", c["text"]):
            if w.lower() != target.lower():
                vocab.add(w)
    pool = sorted(vocab - {target})
    rng.shuffle(pool)
    picks = [w for w in pool if w.lower() != target.lower()][:3]
    while len(picks) < 3:
        picks.append(["concept", "variable", "function", "method"][len(picks)])
    return picks


QUIZ_PROMPT = """You write quiz questions for a student who just watched this lecture.

Write {n} multiple-choice questions (exactly 4 options each) from CONTEXT only.
Rules:
- Test understanding, not trivia: "why", "what happens if", "which is true", trade-offs, definitions, how it works.
- Easy English only. Never use Hindi/Hinglish/Devanagari or any non-English words.
- One clearly correct option. Wrong options must be plausible but wrong.
- Include a 1-sentence explanation that teaches the idea.
- chunk_tag must be one of: {tags}

Output JSON: {{"questions": [{{"question": str, "options": [str,str,str,str], "correct_index": 0-3, "explanation": str, "chunk_tag": str}}]}}"""


def _gemini_questions(chunks: list[dict], n: int) -> list[dict]:
    context = llm.build_context(chunks[:10])
    tags = ", ".join(llm.chunk_tag(c) for c in chunks[:10])
    model = llm._gemini(QUIZ_PROMPT.format(n=n, tags=tags))
    resp = llm.call_gemini(
        model,
        f"CONTEXT:\n{context}\n\nWrite {n} quiz questions. JSON only.",
        generation_config={"response_mime_type": "application/json", "temperature": 0.4, "max_output_tokens": 2200},
    )
    return _normalize_questions(llm._parse_json(resp.text), chunks)


def _normalize_questions(raw, chunks: list[dict]) -> list[dict]:
    items = raw if isinstance(raw, list) else (raw or {}).get("questions", [])
    out = []
    tag_map = {llm.chunk_tag(c): c for c in chunks}
    for it in items:
        if not isinstance(it, dict) or not it.get("question") or not it.get("options"):
            continue
        opts = [str(o) for o in it["options"][:4]]
        if len(opts) < 2:
            continue
        while len(opts) < 4:
            opts.append("None of these")
        try:
            idx = int(it.get("correct_index", 0))
        except (TypeError, ValueError):
            idx = 0
        idx = max(0, min(idx, len(opts) - 1))
        c = tag_map.get(it.get("chunk_tag", ""), chunks[0])
        out.append(
            {
                "id": uuid.uuid4().hex[:10],
                "question": str(it["question"]).strip(),
                "options": opts,
                "correct_index": idx,
                "explanation": str(it.get("explanation") or ""),
                "source": llm.to_source(c),
            }
        )
    return out


def _bedrock_questions(chunks: list[dict], n: int) -> list[dict]:
    context = llm.build_context(chunks[:6])
    prompt = (
        f"Create {n} multiple-choice questions (4 options each) from the CONTEXT. "
        "Only facts present in CONTEXT. Output JSON array with keys: question, options, correct_index, explanation, chunk_tag "
        f"(one of: {', '.join(llm.chunk_tag(c) for c in chunks[:6])}).\n\nCONTEXT:\n{context}"
    )
    resp = _bedrock().converse(
        modelId=settings.bedrock_model_id,
        system=[{"text": "You are a course quiz writer. Output only valid JSON."}],
        messages=[{"role": "user", "content": prompt}],
        inferenceConfig={"maxTokens": 1800, "temperature": 0.3},
    )
    text = resp["output"]["message"]["content"][0]["text"]
    return _normalize_questions(llm._parse_json(text), chunks)