from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str


class CourseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = ""


class CourseOut(BaseModel):
    id: str
    title: str
    description: str
    status: str
    error: str
    materials: list[dict] = []

    model_config = {"from_attributes": True}


class AskIn(BaseModel):
    course_id: str
    question: str = Field(min_length=2, max_length=2000)
    video_time: Optional[float] = None


class SourceOut(BaseModel):
    type: Literal["video", "pdf", "slides"]
    label: str
    start_time: Optional[float] = None
    page: Optional[int] = None
    slide: Optional[int] = None
    quote: str = ""


class AskOut(BaseModel):
    answer: str
    sources: list[SourceOut] = []
    in_material: bool = True
    covered_later: bool = False
    retrieved_count: int = 0


class QuizGenerateIn(BaseModel):
    course_id: str
    video_time: Optional[float] = None
    n_questions: int = Field(default=5, ge=1, le=10)


class QuizQuestion(BaseModel):
    id: str
    question: str
    options: list[str]
    correct_index: int
    explanation: str = ""
    source: SourceOut


class QuizGenerateOut(BaseModel):
    questions: list[QuizQuestion]


class QuizSubmitIn(BaseModel):
    course_id: str
    answers: dict[str, int]


class QuizResultOut(BaseModel):
    score: int
    total: int
    detail: list[dict]


class InterviewStartIn(BaseModel):
    course_id: str


class InterviewAnswerIn(BaseModel):
    session_id: str
    answer: str = Field(min_length=1, max_length=4000)


class InterviewTurnOut(BaseModel):
    role: str
    content: str
    evaluation: dict[str, Any] = {}


class InterviewStateOut(BaseModel):
    session_id: str
    turn: int
    status: str
    current_question: str = ""
    topics_covered: list[str] = []
    scorecard: dict[str, Any] = {}
