from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.ingestion import ingest_course
from app.models import Course, Material, User
from app.security import hash_password
from app.services import storage
import os

EMAIL = "demo@learn2hire.dev"
PASSWORD = "demo1234"


def _seed_on_startup():
    """Ensure demo account + course exist on Render startup (idempotent)."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == EMAIL).first()
        if user is None:
            user = User(name="Demo Learner", email=EMAIL, password_hash=hash_password(PASSWORD))
            db.add(user)
            db.commit()
            db.refresh(user)
        existing = (
            db.query(Course)
            .filter(Course.owner_id == user.id, Course.title.like("Intro to Data Structures%"))
            .first()
        )
        if existing and existing.status == "ready":
            return
        course = existing or Course(
            owner_id=user.id,
            title="Intro to Data Structures — Lecture 1",
            description="Sample lecture: arrays, linked lists, stacks, queues, hash maps, trees, heaps, graphs and DP.",
        )
        if existing is None:
            db.add(course)
            db.commit()
            db.refresh(course)
        for filename, kind in [
            ("lecture1.mp4", "video"),
            ("lecture1.vtt", "transcript"),
            ("notes.pdf", "pdf"),
        ]:
            already = (
                db.query(Material)
                .filter(Material.course_id == course.id, Material.filename == filename)
                .first()
            )
            if already:
                continue
            sample_path = os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                ),
                "sample",
                filename,
            )
            if not os.path.exists(sample_path):
                continue
            with open(sample_path, "rb") as fh:
                data = fh.read()
            key = storage.save_upload(course.id, filename, data)
            db.add(Material(course_id=course.id, kind=kind, filename=filename, storage_key=key))
        db.commit()
        try:
            result = ingest_course(db, course)
            print(f"seed: status={result['status']} chunks={result.get('chunks')}")
        except Exception as exc:  # noqa: BLE001
            print(f"seed: ingestion deferred: {exc}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: seed database once on startup (idempotent)."""
    _seed_on_startup()
    yield


from app.routers import ask, auth, courses, files, interview, quiz

app = FastAPI(
    title="Learn2Hire API",
    version="1.0.0",
    description="Timestamp-aware AI tutor + AI mock interviewer (AHGV BuildVerse 2026, Team codeflux)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(files.router)
app.include_router(ask.router)
app.include_router(quiz.router)
app.include_router(interview.router)


@app.get("/api/health")
def health():
    from app.services.llm import active_provider, last_provider_error

    provider = active_provider()
    return {
        "status": "ok",
        "app": settings.app_name,
        "mode": "demo-offline" if settings.demo_mode else "aws",
        "provider": provider,
        "model": settings.gemini_model if provider == "gemini" else settings.bedrock_model_id,
        "provider_error": last_provider_error(),
    }
