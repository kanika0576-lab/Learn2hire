import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChatMessage, Course, User
from app.schemas import AskIn, AskOut
from app.security import get_current_user
from app.services import llm
from app.services.index import retrieve_for_question, search

router = APIRouter(prefix="/api", tags=["ask"])


@router.post("/ask", response_model=AskOut)
def ask(body: AskIn, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = db.get(Course, body.course_id)
    if course is None or course.owner_id != user.id:
        raise HTTPException(404, "Course not found")
    if course.status != "ready":
        raise HTTPException(409, f"Course is '{course.status}' — wait for ingestion to finish")

    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.course_id == course.id, ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]

    evidence = retrieve_for_question(course.id, body.question, body.video_time, history)
    result = llm.generate_answer(body.question, evidence["chunks"], evidence["covered_later"], history)

    db.add(
        ChatMessage(
            course_id=course.id,
            user_id=user.id,
            role="user",
            content=body.question,
            video_time=body.video_time,
        )
    )
    db.add(
        ChatMessage(
            course_id=course.id,
            user_id=user.id,
            role="assistant",
            content=result["answer"],
            video_time=body.video_time,
            sources_json=json.dumps(result["sources"], ensure_ascii=False),
        )
    )
    db.commit()

    return AskOut(
        answer=result["answer"],
        sources=result["sources"],
        in_material=result["in_material"],
        covered_later=result["covered_later"],
        retrieved_count=len(evidence["chunks"]),
    )


@router.get("/courses/{course_id}/chat")
def history(course_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None or course.owner_id != user.id:
        raise HTTPException(404, "Course not found")
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.course_id == course_id, ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(200)
        .all()
    )
    return [
        {
            "role": m.role,
            "content": m.content,
            "video_time": m.video_time,
            "sources": json.loads(m.sources_json or "[]"),
        }
        for m in rows
    ]
