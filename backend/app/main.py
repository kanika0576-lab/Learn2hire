from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import ask, auth, courses, files, interview, quiz

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Learn2Hire API",
    version="1.0.0",
    description="Timestamp-aware AI tutor + AI mock interviewer (AHGV BuildVerse 2026, Team codeflux)",
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
