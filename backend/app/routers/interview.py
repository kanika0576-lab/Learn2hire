import json
import random
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Course, InterviewSession, InterviewTurn, User
from app.schemas import InterviewAnswerIn, InterviewStartIn, InterviewTurnOut
from app.security import get_current_user
from app.services import llm
from app.services.index import search

router = APIRouter(prefix="/api/interview", tags=["interview"])


@router.post("/start")
def start(body: InterviewStartIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = _owned(body.course_id, user, db)
    if course.status != "ready":
        raise HTTPException(409, f"Course is '{course.status}'")

    session = InterviewSession(course_id=course.id, user_id=user.id, turn=1, state_json=json.dumps(new_state()))
    db.add(session)
    db.commit()
    db.refresh(session)

    state = json.loads(session.state_json)
    question = first_question(course.id, state, 1)
    session.state_json = json.dumps(state, ensure_ascii=False)
    db.add(InterviewTurn(session_id=session.id, role="interviewer", content=question))
    db.commit()

    return {
        "session_id": session.id,
        "turn": session.turn,
        "status": session.status,
        "current_question": question,
        "topics_covered": state.get("topics_covered", []),
        "scorecard": {},
        "history": [{"role": "interviewer", "content": question}],
    }


@router.post("/answer")
def answer(body: InterviewAnswerIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.get(InterviewSession, body.session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(404, "Interview session not found")
    if session.status != "active":
        raise HTTPException(409, "Interview already completed")

    course = db.get(Course, session.course_id)
    state = json.loads(session.state_json)
    asked = state.get("asked", [])
    question = asked[-1] if asked else "Tell me about what you learned."

    db.add(InterviewTurn(session_id=session.id, role="candidate", content=body.answer))

    evaluation, next_q = evaluate_and_next(course.id, state, session.turn, body.answer, question)
    db.add(
        InterviewTurn(
            session_id=session.id,
            role="interviewer",
            content=next_q or "Thank you — that concludes the interview.",
            evaluation_json=json.dumps(evaluation, ensure_ascii=False),
        )
    )

    session.turn += 1
    if next_q is None:
        session.status = "completed"
        card = scorecard(state)
        session.scorecard_json = json.dumps(card, ensure_ascii=False)
    else:
        card = {}
    session.state_json = json.dumps(state, ensure_ascii=False)
    db.commit()

    return {
        "session_id": session.id,
        "turn": session.turn,
        "status": session.status,
        "current_question": next_q or "",
        "evaluation": evaluation,
        "scorecard": card,
        "topics_covered": state.get("topics_covered", []),
    }


@router.get("/{session_id}")
def get_session(session_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.get(InterviewSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(404, "Interview session not found")
    turns = (
        db.query(InterviewTurn)
        .filter(InterviewTurn.session_id == session_id)
        .order_by(InterviewTurn.created_at.asc())
        .all()
    )
    state = json.loads(session.state_json)
    return {
        "session_id": session.id,
        "course_id": session.course_id,
        "turn": session.turn,
        "status": session.status,
        "current_question": "",
        "topics_covered": state.get("topics_covered", []),
        "scorecard": json.loads(session.scorecard_json or "{}"),
        "history": [
            {"role": t.role, "content": t.content, "evaluation": json.loads(t.evaluation_json or "{}")}
            for t in turns
        ],
    }


def _owned(course_id: str, user: User, db: Session) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.owner_id != user.id:
        raise HTTPException(404, "Course not found")
    return course


# ============================ interview engine ============================

MAX_TURNS = 6

_bedrock_client = None

FALLBACK_QUESTIONS = [
    "In your own words, what problem does this course's main topic solve?",
    "Walk me through the core concept you learned most recently, step by step.",
    "Can you give a practical example of where you would apply this concept?",
    "What is a common mistake beginners make here, and how would you avoid it?",
    "If I asked you to explain this topic to a non-technical teammate, how would you?",
    "How would you debug a problem in something built with this concept?",
]



def _bedrock():
    global _bedrock_client
    if _bedrock_client is None:
        import boto3

        _bedrock_client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    return _bedrock_client


def new_state() -> dict:
    return {
        "topics_covered": [],
        "strengths": [],
        "weaknesses": [],
        "last_answer": "",
        "asked": [],
    }


def first_question(course_id: str, state: dict, turn: int) -> str:
    chunks = search(course_id, "introduction overview key concept summary", None, top_k=5, time_gate=False)
    provider = llm.active_provider()
    try:
        if provider == "gemini":
            q = _gemini_opening(chunks)
        elif provider == "bedrock":
            q = _bedrock_opening(chunks)
        else:
            q = FALLBACK_QUESTIONS[0]
        if q:
            state["asked"].append(q)
            return q
    except Exception:
        pass
    state["asked"].append(FALLBACK_QUESTIONS[0])
    return FALLBACK_QUESTIONS[0]


def evaluate_and_next(
    course_id: str, state: dict, turn: int, answer: str, question: str
) -> tuple[dict, str | None]:
    """Evaluate the candidate's answer, update agent memory, return (evaluation, next_question|None)."""
    chunks = search(course_id, answer[:400], None, top_k=4, time_gate=False)
    evaluation = None
    provider = llm.active_provider()
    try:
        if provider == "gemini":
            evaluation = _gemini_evaluate(answer, question, chunks)
        elif provider == "bedrock":
            evaluation = _bedrock_evaluate(answer, question, chunks)
    except Exception:
        evaluation = None
    if evaluation is None:
        evaluation = _heuristic_evaluate(answer, question, chunks)

    _update_memory(state, answer, evaluation)
    if turn + 1 >= MAX_TURNS:
        return evaluation, None
    nxt = _next_question(state, chunks)
    state["asked"].append(nxt)
    return evaluation, nxt


def scorecard(state: dict) -> dict:
    strengths = state.get("strengths", [])[:3]
    weaknesses = state.get("weaknesses", [])[:3]
    evals = state.get("evals", [])
    if evals:
        tech = round(sum(e.get("technical_accuracy", 6) for e in evals) / len(evals), 1)
        comm = round(sum(e.get("communication", 6) for e in evals) / len(evals), 1)
        rel = round(sum(e.get("relevance", 6) for e in evals) / len(evals), 1)
    else:
        tech = comm = rel = 6.0
    overall = round(0.45 * tech + 0.3 * comm + 0.25 * rel, 1)
    return {
        "technical_accuracy": tech,
        "communication": comm,
        "relevance": rel,
        "overall": overall,
        "grade": _grade(overall),
        "strengths": strengths or ["Showed up and engaged with every question."],
        "improvements": weaknesses or ["Add more concrete examples in your answers."],
        "topics_covered": state.get("topics_covered", []),
        "questions_asked": state.get("asked", []),
        "explanation": (
            f"Scored from {len(evals)} answers. Technical {tech}/10 (facts & correctness), "
            f"Communication {comm}/10 (clarity & structure), Relevance {rel}/10 (staying on topic)."
        ),
    }


def _grade(overall: float) -> str:
    if overall >= 8.5:
        return "Excellent"
    if overall >= 7.0:
        return "Strong"
    if overall >= 5.5:
        return "Developing"
    return "Needs practice"


def _heuristic_evaluate(answer: str, question: str, chunks: list[dict]) -> dict:
    words = re.findall(r"[a-z0-9]+", answer.lower())
    q_terms = set(re.findall(r"[a-z0-9]+", question.lower())) - {
        "what", "is", "the", "a", "an", "how", "why", "in", "of", "to", "and", "you", "your", "explain", "walk", "me"
    }
    overlap = len(q_terms & set(words))
    length_score = min(len(words) / 40.0, 1.0) * 10
    structure = 6.0 + (1.5 if any(w in words for w in ["because", "first", "then", "example", "step"]) else 0)
    chunk_terms = set()
    for c in chunks[:3]:
        chunk_terms |= set(re.findall(r"[a-z0-9]+", c["text"].lower()))
    grounded = len(set(words) & chunk_terms)
    tech = max(3.0, min(9.5, 4.0 + overlap * 0.9 + min(grounded, 12) * 0.25))
    comm = max(3.0, min(9.5, structure + length_score * 0.4))
    rel = max(3.0, min(9.5, 5.0 + overlap * 1.1))
    return {
        "technical_accuracy": round(tech, 1),
        "communication": round(comm, 1),
        "relevance": round(rel, 1),
        "feedback": _feedback(tech, comm, rel, answer),
        "topic": _topic_of(answer, question, chunks),
    }


def _feedback(tech: float, comm: float, rel: float, answer: str) -> str:
    bits = []
    if tech >= 7:
        bits.append("Good grounding in the material")
    else:
        bits.append("Add specific facts from the course")
    if comm >= 7:
        bits.append("clear structure")
    else:
        bits.append("use step-by-step structure")
    if len(answer.split()) < 15:
        bits.append("expand your answers with examples")
    return "; ".join(bits) + "."


def _topic_of(answer: str, question: str, chunks: list[dict]) -> str:
    if chunks:
        return chunks[0].get("source_name", "course material")
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]{4,}", question) if w.lower() not in {"explain", "walk"}]
    return " ".join(words[:3]) or "general"


def _update_memory(state: dict, answer: str, evaluation: dict) -> None:
    state["last_answer"] = answer
    state.setdefault("evals", []).append(evaluation)
    topic = evaluation.get("topic", "general")
    if topic not in state["topics_covered"]:
        state["topics_covered"].append(topic)
    if evaluation.get("technical_accuracy", 0) >= 7:
        if topic not in state["strengths"]:
            state["strengths"].append(topic)
    else:
        if topic not in state["weaknesses"]:
            state["weaknesses"].append(topic)


def _next_question(state: dict, chunks: list[dict]) -> str:
    weak = state.get("weaknesses", [])
    asked = set(state.get("asked", []))
    if weak:
        probe = f"You mentioned {weak[-1]} — can you go deeper on that with a concrete example?"
        if probe not in asked:
            return probe
    topic = state.get("topics_covered", [])
    if topic:
        follow = f"How would you apply {topic[-1]} in a real project you have worked on?"
        if follow not in asked:
            return follow
    for q in FALLBACK_QUESTIONS:
        if q not in asked:
            return q
    return "Is there anything about this course you would like to test yourself on before we finish?"


INTERVIEWER_PROMPT = (
    "You are a friendly but rigorous technical interviewer. "
    "Ask ONE question at a time, based on the course material provided. "
    "First question should establish baseline understanding. Output only the question text."
)

EVALUATOR_PROMPT = (
    "You are an interview evaluator. Score the candidate's answer 0-10 on "
    "technical_accuracy, communication and relevance. Give one short feedback "
    "sentence and a short topic label. Output only valid JSON with keys "
    "{technical_accuracy, communication, relevance, feedback, topic}."
)


def _gemini():
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(settings.gemini_model, system_instruction=INTERVIEWER_PROMPT)


def _gemini_opening(chunks: list[dict]) -> str:
    context = llm.build_context(chunks)
    resp = llm.call_gemini(
        _gemini(),
        f"Course material:\n{context}\n\nAsk your opening interview question.",
        generation_config={"temperature": 0.5, "max_output_tokens": 200},
    )
    return resp.text.strip()


def _gemini_evaluate(answer: str, question: str, chunks: list[dict]) -> dict:
    context = llm.build_context(chunks)
    prompt = (
        f"Interviewer asked: {question}\nCandidate answered: {answer[:1500]}\n"
        f"Course context (for grounding):\n{context[:2500]}\n\n" + EVALUATOR_PROMPT
    )
    model = _gemini()
    resp = llm.call_gemini(
        model,
        prompt,
        generation_config={"response_mime_type": "application/json", "temperature": 0.2, "max_output_tokens": 500},
    )
    data = llm._parse_json(resp.text)
    base = _heuristic_evaluate(answer, question, chunks)
    if not data:
        return base
    for k in ("technical_accuracy", "communication", "relevance"):
        try:
            v = float(data.get(k, base[k]))
            base[k] = max(0.0, min(10.0, v))
        except (TypeError, ValueError):
            pass
    base["feedback"] = str(data.get("feedback", base["feedback"]))
    base["topic"] = str(data.get("topic", base["topic"]))[:60]
    return base


def _bedrock_opening(chunks: list[dict]) -> str:
    context = llm.build_context(chunks)
    resp = _bedrock().converse(
        modelId=settings.bedrock_model_id,
        system=[
            {
                "text": (
                    "You are a friendly but rigorous technical interviewer. "
                    "Ask ONE question at a time, based on the course material provided. "
                    "First question should establish baseline understanding. Output only the question text."
                )
            }
        ],
        messages=[{"role": "user", "content": f"Course material:\n{context}\n\nAsk your opening interview question."}],
        inferenceConfig={"maxTokens": 200, "temperature": 0.5},
    )
    return resp["output"]["message"]["content"][0]["text"].strip()


def _bedrock_evaluate(answer: str, question: str, chunks: list[dict]) -> dict:
    context = llm.build_context(chunks)
    prompt = (
        f"Interviewer asked: {question}\nCandidate answered: {answer[:1500]}\n"
        f"Course context (for grounding):\n{context[:2500]}\n\n"
        "Score the answer 0-10 on technical_accuracy, communication, relevance. "
        "Give one short feedback sentence and a short topic label. "
        "Output JSON: {technical_accuracy, communication, relevance, feedback, topic}"
    )
    resp = _bedrock().converse(
        modelId=settings.bedrock_model_id,
        system=[{"text": "You are an interview evaluator. Output only valid JSON."}],
        messages=[{"role": "user", "content": prompt}],
        inferenceConfig={"maxTokens": 500, "temperature": 0.2},
    )
    text = resp["output"]["message"]["content"][0]["text"]
    data = llm._parse_json(text)
    base = _heuristic_evaluate(answer, question, chunks)
    if not data:
        return base
    for k in ("technical_accuracy", "communication", "relevance"):
        try:
            v = float(data.get(k, base[k]))
            base[k] = max(0.0, min(10.0, v))
        except (TypeError, ValueError):
            pass
    base["feedback"] = str(data.get("feedback", base["feedback"]))
    base["topic"] = str(data.get("topic", base["topic"]))[:60]
    return base