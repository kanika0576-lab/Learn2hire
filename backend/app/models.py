import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def uid() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=uid)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=now)

    courses = relationship("Course", back_populates="owner")


class Course(Base):
    __tablename__ = "courses"

    id = Column(String, primary_key=True, default=uid)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="created")  # created | ingesting | ready | error
    error = Column(Text, default="")
    created_at = Column(DateTime, default=now)

    owner = relationship("User", back_populates="courses")
    materials = relationship("Material", back_populates="course", cascade="all, delete-orphan")


class Material(Base):
    __tablename__ = "materials"

    id = Column(String, primary_key=True, default=uid)
    course_id = Column(String, ForeignKey("courses.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)  # video | pdf | slides | transcript
    filename = Column(String, nullable=False)
    storage_key = Column(String, nullable=False)  # s3 key or local path
    duration_seconds = Column(Float, default=0.0)
    status = Column(String, default="uploaded")  # uploaded | transcribed | indexed | error
    created_at = Column(DateTime, default=now)

    course = relationship("Course", back_populates="materials")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=uid)
    course_id = Column(String, ForeignKey("courses.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    video_time = Column(Float, nullable=True)
    sources_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=now)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id = Column(String, primary_key=True, default=uid)
    course_id = Column(String, ForeignKey("courses.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    score = Column(Integer, default=0)
    total = Column(Integer, default=0)
    questions_json = Column(Text, default="[]")
    answers_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=now)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(String, primary_key=True, default=uid)
    course_id = Column(String, ForeignKey("courses.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String, default="active")  # active | completed
    turn = Column(Integer, default=0)
    state_json = Column(Text, default="{}")
    scorecard_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=now)


class InterviewTurn(Base):
    __tablename__ = "interview_turns"

    id = Column(String, primary_key=True, default=uid)
    session_id = Column(String, ForeignKey("interview_sessions.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # interviewer | candidate
    content = Column(Text, nullable=False)
    evaluation_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=now)
