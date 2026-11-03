import logging

from sqlalchemy import delete

from . import db
from .config import PDF_DIR
from .db import Chunk, Document
from .pdf import extract_chunks

logger = logging.getLogger(__name__)


def ingest_document(document_id: str, embedder) -> None:
    try:
        with db.db_session() as session:
            doc = session.get(Document, document_id)
            if doc is None:
                return
            doc.status = "processing"
            doc.error = None
            session.commit()
        chunks, text_pages = extract_chunks(PDF_DIR / f"{document_id}.pdf")
        vectors = (
            embedder.encode(
                [content for _, _, content in chunks],
                normalize_embeddings=True,
                batch_size=24,
            ).tolist()
            if chunks
            else []
        )
        with db.db_session() as session:
            doc = session.get(Document, document_id)
            if doc is None:
                return
            session.execute(delete(Chunk).where(Chunk.document_id == document_id))
            session.add_all(
                Chunk(
                    document_id=document_id,
                    page_number=page,
                    ordinal=ordinal,
                    content=content,
                    embedding=vector,
                )
                for (page, ordinal, content), vector in zip(
                    chunks, vectors, strict=True
                )
            )
            doc.text_page_count = text_pages
            doc.status = "ready"
            session.commit()
    except Exception as exc:
        logger.exception("Failed to ingest document %s", document_id)
        with db.db_session() as session:
            doc = session.get(Document, document_id)
            if doc is not None:
                doc.status = "failed"
                doc.error = f"Could not process this PDF ({type(exc).__name__}). Retry the upload."
                session.commit()
