from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    filename: str
    status: str
    error: str | None
    page_count: int
    text_page_count: int
    created_at: datetime


class QuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class DiagramRequest(QuestionRequest):
    page: int = Field(ge=1)
    x0: float = Field(ge=0, le=1)
    y0: float = Field(ge=0, le=1)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)


class StudyRequest(BaseModel):
    kind: Literal["quiz", "flashcards"]
    count: int = Field(default=3, ge=1, le=5)


class Citation(BaseModel):
    reference: int
    page: int
    excerpt: str


class AnswerView(BaseModel):
    answer: str
    citations: list[Citation]


class InteractionView(AnswerView):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    question: str
    page_number: int | None = None
    created_at: datetime


class StudySetView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    items: list[dict]
    created_at: datetime
