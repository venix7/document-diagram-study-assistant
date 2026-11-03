import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from .config import database_url


def uid() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "study_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_hash: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(180))
    filename: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    text_page_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    chunks: Mapped[list["Chunk"]] = relationship(cascade="all, delete-orphan")
    interactions: Mapped[list["Interaction"]] = relationship(
        cascade="all, delete-orphan"
    )
    study_sets: Mapped[list["StudySet"]] = relationship(cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "study_document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_documents.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(384))


class Interaction(Base):
    __tablename__ = "study_interactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_documents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question: Mapped[str] = mapped_column(String(500))
    answer: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StudySet(Base):
    __tablename__ = "study_study_sets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_documents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    items: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


engine = None
SessionLocal = None


def initialize_database() -> None:
    global engine, SessionLocal
    engine = create_engine(database_url(), pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    if SessionLocal is None:
        raise RuntimeError("Database not initialized")
    with SessionLocal() as session:
        yield session


@contextmanager
def db_session():
    if SessionLocal is None:
        raise RuntimeError("Database not initialized")
    with SessionLocal() as session:
        yield session
