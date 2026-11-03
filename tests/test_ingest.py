import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pymupdf
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import db, ingest
from backend.app.db import Base, Chunk, Document


@compiles(VECTOR, "sqlite")
def compile_vector_for_test(element, compiler, **kwargs):
    return "BLOB"


class FakeEmbedder:
    def encode(self, texts, **kwargs):
        return SimpleNamespace(tolist=lambda: [[0.01] * 384 for _ in texts])


class IngestionTests(unittest.TestCase):
    def test_pdf_pages_become_persisted_vector_chunks(self):
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE document_chunks (id VARCHAR PRIMARY KEY, class_id VARCHAR)"
                )
            )
        Base.metadata.create_all(engine)
        sessions = sessionmaker(engine, expire_on_commit=False)
        previous_sessions = db.SessionLocal
        previous_dir = ingest.PDF_DIR
        try:
            with tempfile.TemporaryDirectory() as folder:
                ingest.PDF_DIR = Path(folder)
                db.SessionLocal = sessions
                pdf = pymupdf.open()
                page = pdf.new_page()
                page.insert_text((40, 80), "A stack uses last in, first out ordering.")
                with sessions() as session:
                    doc = Document(
                        owner_hash="test-owner",
                        title="Data structures",
                        filename="notes.pdf",
                        status="pending",
                        page_count=1,
                    )
                    session.add(doc)
                    session.commit()
                    document_id = doc.id
                (ingest.PDF_DIR / f"{document_id}.pdf").write_bytes(pdf.tobytes())
                pdf.close()
                ingest.ingest_document(document_id, FakeEmbedder())
                with sessions() as session:
                    doc = session.get(Document, document_id)
                    chunks = session.scalars(
                        select(Chunk).where(Chunk.document_id == document_id)
                    ).all()
                    self.assertEqual(doc.status, "ready")
                    self.assertEqual(doc.text_page_count, 1)
                    self.assertEqual(len(chunks), 1)
                    self.assertEqual(len(chunks[0].embedding), 384)
                    self.assertEqual(chunks[0].page_number, 1)
        finally:
            db.SessionLocal = previous_sessions
            ingest.PDF_DIR = previous_dir
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
