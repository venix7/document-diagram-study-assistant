import io
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import db, main
from backend.app.db import Base, Document


@compiles(VECTOR, "sqlite")
def compile_vector_for_test(element, compiler, **kwargs):
    return "BLOB"


class Jobs:
    def submit(self, *args):
        return None


class FakeAI:
    client = object()

    def diagram(self, question, image, page, nearby):
        return "The selected region contains a labelled process."


class APIFlowTests(unittest.TestCase):
    def test_upload_private_page_diagram_and_delete(self):
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        sessions = sessionmaker(engine, expire_on_commit=False)

        def override_db():
            with sessions() as session:
                yield session

        @asynccontextmanager
        async def fake_lifespan(app):
            app.state.embedder = object()
            app.state.ai = FakeAI()
            app.state.jobs = Jobs()
            yield

        previous_lifespan = main.app.router.lifespan_context
        previous_dir = main.PDF_DIR
        main.app.router.lifespan_context = fake_lifespan
        main.app.dependency_overrides[db.get_db] = override_db
        try:
            with tempfile.TemporaryDirectory() as folder:
                main.PDF_DIR = Path(folder)
                pdf = pymupdf.open()
                page = pdf.new_page()
                page.insert_text((50, 90), "Node A points to Node B.")
                picture = pdf.tobytes()
                pdf.close()
                with TestClient(main.app) as browser:
                    posted = browser.post(
                        "/api/documents",
                        files={
                            "file": (
                                "diagram.pdf",
                                io.BytesIO(picture),
                                "application/pdf",
                            )
                        },
                    )
                    self.assertEqual(posted.status_code, 201, posted.text)
                    doc_id = posted.json()["id"]
                    self.assertEqual(
                        browser.get("/api/documents").json()[0]["id"], doc_id
                    )
                    with TestClient(main.app) as stranger:
                        self.assertEqual(
                            stranger.get("/api/documents/" + doc_id).status_code, 404
                        )
                        self.assertEqual(
                            stranger.get(
                                "/api/documents/" + doc_id + "/pages/1/preview"
                            ).status_code,
                            404,
                        )
                    with sessions() as session:
                        doc = session.get(Document, doc_id)
                        doc.status = "ready"
                        session.commit()
                    self.assertEqual(
                        browser.get(
                            "/api/documents/" + doc_id + "/pages/1/preview"
                        ).status_code,
                        200,
                    )
                    self.assertEqual(
                        browser.post(
                            "/api/documents/" + doc_id + "/questions",
                            json={"question": "What is the algorithm?"},
                        ).status_code,
                        422,
                    )
                    diagram = browser.post(
                        "/api/documents/" + doc_id + "/diagram-questions",
                        json={
                            "question": "What is visible?",
                            "page": 1,
                            "x0": 0.02,
                            "y0": 0.02,
                            "x1": 0.8,
                            "y1": 0.4,
                        },
                    )
                    self.assertEqual(diagram.status_code, 200, diagram.text)
                    self.assertEqual(diagram.json()["citations"][0]["page"], 1)
                    self.assertEqual(
                        len(
                            browser.get(
                                "/api/documents/" + doc_id + "/interactions"
                            ).json()
                        ),
                        1,
                    )
                    self.assertEqual(
                        browser.delete("/api/documents/" + doc_id).status_code, 204
                    )
                    self.assertEqual(browser.get("/api/documents").json(), [])
        finally:
            main.app.router.lifespan_context = previous_lifespan
            main.app.dependency_overrides.clear()
            main.PDF_DIR = previous_dir
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
