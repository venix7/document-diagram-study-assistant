import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import db
from .ai import AIService
from .config import EMBEDDING_MODEL, MAX_FILE_BYTES, PDF_DIR, ROOT
from .db import Chunk, Document, Interaction, StudySet
from .ingest import ingest_document
from .pdf import inspect_pdf, render_page
from .schemas import (
    AnswerView,
    DiagramRequest,
    DocumentView,
    InteractionView,
    QuestionRequest,
    StudyRequest,
    StudySetView,
)

COOKIE_NAME = "study_session"
DIST = ROOT / "frontend" / "dist"
DbSession = Annotated[Session, Depends(db.get_db)]
PDFFile = Annotated[UploadFile, File()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.initialize_database()
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    app.state.embedder = SentenceTransformer(EMBEDDING_MODEL)
    app.state.ai = AIService()
    if os.getenv("APP_ENV") == "production" and app.state.ai.client is None:
        raise RuntimeError("Set GROQ_API_KEY for the production service")
    try:
        yield
    finally:
        if db.engine is not None:
            db.engine.dispose()


app = FastAPI(title="Margin Study Assistant", version="1.0.0", lifespan=lifespan)


def session_hash(token: str | None) -> str | None:
    if not token or not 16 <= len(token) <= 128:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def owned_document(session: Session, request: Request, document_id: str) -> Document:
    owner = session_hash(request.cookies.get(COOKIE_NAME))
    if owner is None:
        raise HTTPException(404, "Document not found")
    doc = session.scalar(
        select(Document).where(Document.id == document_id, Document.owner_hash == owner)
    )
    if (
        doc is None
        or doc.status not in {"ready", "failed"}
        or not document_path(doc).is_file()
    ):
        raise HTTPException(404, "Document not found")
    return doc


def document_path(doc: Document) -> Path:
    return PDF_DIR / f"{doc.id}.pdf"


def ready(doc: Document) -> None:
    if doc.status != "ready":
        raise HTTPException(409, "Wait for PDF processing to finish")


def ai_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RuntimeError) and "GROQ_API_KEY" in str(exc):
        return HTTPException(503, str(exc))
    return HTTPException(502, "Model request failed. Try again; no answer was saved.")


@app.get("/api/health")
def health(request: Request):
    return {
        "status": "ok",
        "embedding_ready": bool(getattr(request.app.state, "embedder", None)),
        "groq_configured": bool(getattr(request.app.state.ai, "client", None)),
    }


@app.get("/api/documents", response_model=list[DocumentView])
def documents(request: Request, session: DbSession):
    owner = session_hash(request.cookies.get(COOKIE_NAME))
    if owner is None:
        return []
    found = session.scalars(
        select(Document)
        .where(Document.owner_hash == owner)
        .order_by(Document.created_at.desc())
        .limit(50)
    ).all()
    return [
        doc
        for doc in found
        if doc.status in {"ready", "failed"} and document_path(doc).is_file()
    ]


@app.post("/api/documents", response_model=DocumentView, status_code=201)
async def upload_document(
    request: Request, response: Response, file: PDFFile, session: DbSession
):
    raw = await file.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES or not raw:
        raise HTTPException(413, "Upload a PDF smaller than 15 MB")
    try:
        page_count = inspect_pdf(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    token = request.cookies.get(COOKIE_NAME)
    if session_hash(token) is None:
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            secure=os.getenv("APP_ENV") == "production",
            samesite="lax",
            max_age=60 * 60 * 24 * 90,
        )
    name = (file.filename or "document.pdf").replace("\\", "/").split("/")[-1][:180]
    doc = Document(
        owner_hash=session_hash(token),
        title=Path(name).stem[:180] or "Untitled document",
        filename=name,
        status="pending",
        page_count=page_count,
    )
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    session.add(doc)
    session.flush()
    path = document_path(doc)
    try:
        path.write_bytes(raw)
        session.commit()
    except Exception:
        session.rollback()
        path.unlink(missing_ok=True)
        raise
    await run_in_threadpool(ingest_document, doc.id, request.app.state.embedder)
    session.refresh(doc)
    return doc


@app.get("/api/documents/{document_id}", response_model=DocumentView)
def get_document(document_id: str, request: Request, session: DbSession):
    return owned_document(session, request, document_id)


@app.get("/api/documents/{document_id}/file")
def get_file(document_id: str, request: Request, session: DbSession):
    doc = owned_document(session, request, document_id)
    path = document_path(doc)
    if not path.is_file():
        raise HTTPException(404, "PDF unavailable")
    return FileResponse(path, media_type="application/pdf", filename=doc.filename)


@app.get("/api/documents/{document_id}/pages/{page}/preview")
def preview(document_id: str, page: int, request: Request, session: DbSession):
    doc = owned_document(session, request, document_id)
    try:
        image = render_page(document_path(doc), page)
    except (ValueError, OSError) as exc:
        raise HTTPException(404, "Page unavailable") from exc
    return Response(content=image, media_type="image/jpeg")


@app.post("/api/documents/{document_id}/questions", response_model=AnswerView)
def ask(document_id: str, body: QuestionRequest, request: Request, session: DbSession):
    doc = owned_document(session, request, document_id)
    ready(doc)
    if not doc.text_page_count:
        raise HTTPException(
            422, "No selectable text found; use the diagram tool for this page"
        )
    question = body.question.strip()
    if len(question) < 3:
        raise HTTPException(422, "Enter a longer question")
    vector = request.app.state.embedder.encode(
        question, normalize_embeddings=True
    ).tolist()
    passages = session.scalars(
        select(Chunk)
        .where(Chunk.document_id == doc.id)
        .order_by(Chunk.embedding.cosine_distance(vector))
        .limit(5)
    ).all()
    if not passages:
        raise HTTPException(422, "No searchable text found")
    try:
        result = request.app.state.ai.answer(question, passages)
    except Exception as exc:
        raise ai_error(exc) from exc
    session.add(
        Interaction(
            document_id=doc.id,
            kind="text",
            question=question,
            answer=result["answer"],
            citations=result["citations"],
        )
    )
    session.commit()
    return result


@app.post("/api/documents/{document_id}/diagram-questions", response_model=AnswerView)
def ask_diagram(
    document_id: str, body: DiagramRequest, request: Request, session: DbSession
):
    doc = owned_document(session, request, document_id)
    ready(doc)
    question = body.question.strip()
    if len(question) < 3:
        raise HTTPException(422, "Enter a longer question")
    try:
        image = render_page(
            document_path(doc),
            body.page,
            (body.x0, body.y0, body.x1, body.y1),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    nearby = session.scalars(
        select(Chunk)
        .where(Chunk.document_id == doc.id, Chunk.page_number == body.page)
        .order_by(Chunk.ordinal)
        .limit(3)
    ).all()
    try:
        answer = request.app.state.ai.diagram(
            question, image, body.page, "\n".join(p.content for p in nearby)
        )
    except Exception as exc:
        raise ai_error(exc) from exc
    result = {
        "answer": answer,
        "citations": [
            {
                "reference": 1,
                "page": body.page,
                "excerpt": "The selected region on this PDF page.",
            }
        ],
    }
    session.add(
        Interaction(
            document_id=doc.id,
            kind="diagram",
            page_number=body.page,
            question=question,
            answer=answer,
            citations=result["citations"],
        )
    )
    session.commit()
    return result


@app.get(
    "/api/documents/{document_id}/interactions", response_model=list[InteractionView]
)
def interactions(document_id: str, request: Request, session: DbSession):
    doc = owned_document(session, request, document_id)
    return session.scalars(
        select(Interaction)
        .where(Interaction.document_id == doc.id)
        .order_by(Interaction.created_at.desc(), Interaction.id.desc())
        .limit(50)
    ).all()


@app.post(
    "/api/documents/{document_id}/study-sets",
    response_model=StudySetView,
    status_code=201,
)
def make_study_set(
    document_id: str, body: StudyRequest, request: Request, session: DbSession
):
    doc = owned_document(session, request, document_id)
    ready(doc)
    all_chunks = session.scalars(
        select(Chunk)
        .where(Chunk.document_id == doc.id)
        .order_by(Chunk.page_number, Chunk.ordinal)
    ).all()
    if not all_chunks:
        raise HTTPException(422, "No selectable text found for a study set")
    indices = (
        [
            round(i * (len(all_chunks) - 1) / (min(8, len(all_chunks)) - 1))
            for i in range(min(8, len(all_chunks)))
        ]
        if len(all_chunks) > 1
        else [0]
    )
    passages = [all_chunks[i] for i in indices]
    try:
        items = request.app.state.ai.study_set(body.kind, body.count, passages)
    except Exception as exc:
        raise ai_error(exc) from exc
    study_set = StudySet(document_id=doc.id, kind=body.kind, items=items)
    session.add(study_set)
    session.commit()
    session.refresh(study_set)
    return study_set


@app.get("/api/documents/{document_id}/study-sets", response_model=list[StudySetView])
def study_sets(document_id: str, request: Request, session: DbSession):
    doc = owned_document(session, request, document_id)
    return session.scalars(
        select(StudySet)
        .where(StudySet.document_id == doc.id)
        .order_by(StudySet.created_at.desc())
        .limit(20)
    ).all()


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: str, request: Request, session: DbSession):
    doc = owned_document(session, request, document_id)
    if doc.status in {"pending", "processing"}:
        raise HTTPException(409, "Wait for processing before deleting this PDF")
    path = document_path(doc)
    session.delete(doc)
    session.commit()
    path.unlink(missing_ok=True)


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path == "api" or path.startswith("api/"):
        raise HTTPException(404)
    requested = (DIST / path).resolve()
    if requested.is_relative_to(DIST.resolve()) and requested.is_file():
        return FileResponse(requested)
    index = DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(404, "Build the frontend first")
