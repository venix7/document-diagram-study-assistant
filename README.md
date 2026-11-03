# Margin — Document and Diagram Study Assistant

Upload a CS lecture PDF, ask questions about its text, select a diagram region for visual explanation, and make cited quiz questions or flashcards. The React frontend and FastAPI API are served from one origin in production.

## What is included

- **Text RAG:** PyMuPDF extracts selectable text by page, LangChain splits it, a PyTorch Sentence Transformers MiniLM model creates 384-dimensional embeddings, and Neon PostgreSQL/pgvector retrieves passages within the selected PDF.
- **Grounded answers:** Groq GPT-OSS 20B returns structured answers and excerpt numbers. The API maps those numbers to real pages and excerpts, rejecting nonexistent references.
- **Diagram questions:** select a rectangle on the displayed PDF page; PyMuPDF renders only that region and Groq's configurable vision model explains it. The page is shown as the source.
- **Practice:** generate three cited quiz questions or flashcards from the PDF; save questions, answers, and study sets in Neon.
- **Files:** PDFs reside in `data/pdfs` locally and on a Railway volume at `/app/data`. An HttpOnly session cookie restricts files and history to the current browser.

No labelled training dataset or custom classifier is needed. The pretrained embedding model runs with PyTorch and is downloaded during the Docker build. The live smoke-test PDF is generated in code. This first version indexes selectable text; image-only scans still have page previews and manually selected diagram questions, but no whole-page OCR.

## Run locally (Windows PowerShell)

From the project root, use your installed Python and Node.js. Check `python --version` first; Node.js 22 is used by the Docker build.

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r tests\requirements.txt
npm ci --prefix frontend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `DATABASE_URL` and `GROQ_API_KEY` in `.env`. Use a fresh Neon PostgreSQL database where the `vector` extension can be created. Do not commit `.env`.

Database tables use the `study_` prefix. This prevents collisions with the crop advisor's `document_chunks` table if the same Neon database was used earlier. Upload the sample PDF again after updating from an older build; failed uploads in older unprefixed tables are not migrated.

Start two terminals from the project root (activate the virtual environment in the API terminal):

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
npm run dev --prefix frontend
```

Open `http://127.0.0.1:5173` and upload `samples\algorithms-demo.pdf` to try the text and selected-diagram flows. Vite proxies `/api` to port 8000. If the API uses port 8001, set `$env:VITE_API_PROXY="http://127.0.0.1:8001"` **before** starting Vite. For one-origin local serving, run `npm run build --prefix frontend`, then open `http://127.0.0.1:8000`.

## Verify

```powershell
python -m unittest discover -s tests -v
python -m ruff check backend scripts tests
npm run lint --prefix frontend
npm run build --prefix frontend
python scripts\smoke_test.py http://127.0.0.1:8000
```

The seven local tests do not need Neon, Groq, or the embedding model download. The live smoke test **does** need a running API, Neon, and Groq. It generates a two-page PDF and checks ingestion, isolation between browser sessions, text citations, selected-region vision, study items, and saved history. Passing the smoke test does not establish accuracy on arbitrary PDFs or diagrams; evaluate those separately on your own notes.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Embedding and Groq readiness |
| POST | `/api/documents` | Upload a PDF as multipart `file`; return processing status |
| GET | `/api/documents` | Current browser's documents |
| GET | `/api/documents/{id}` | Poll processing status |
| GET | `/api/documents/{id}/file` | Private PDF download |
| GET | `/api/documents/{id}/pages/{page}/preview` | Private page JPEG |
| POST | `/api/documents/{id}/questions` | JSON `{"question":"..."}`; cited answer |
| POST | `/api/documents/{id}/diagram-questions` | JSON `{"question":"...","page":1,"x0":0.1,"y0":0.1,"x1":0.8,"y1":0.8}` with normalized rectangle |
| GET | `/api/documents/{id}/interactions` | Saved text and diagram answers |
| POST | `/api/documents/{id}/study-sets` | JSON `{"kind":"quiz","count":3}` or `flashcards` |
| GET | `/api/documents/{id}/study-sets` | Saved study sets |
| DELETE | `/api/documents/{id}` | Delete PDF and its records after processing |

`/docs` exposes the OpenAPI interface. Uploaded files are capped at 15 MB and 100 unlocked PDF pages. Processing status is `pending`, `processing`, `ready`, or `failed`. Pending work resumes after a service restart. All document endpoints check the browser cookie.

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the exact Docker/Railway/Neon steps and [PHASES.md](PHASES.md) for the six-commit build map. Keep the Railway service at one replica with one Uvicorn worker, because PDF jobs are processed in the API process and resumed at startup. The app starts only after PostgreSQL and the local embedding model are ready. Set Railway's health check to `/api/health`.

This is a browser-session study workspace, not an account-based document vault. Clearing the session cookie loses access to previous PDFs; avoid confidential material until account authentication and retention policy are added. Text excerpts and selected diagram crops are sent to Groq when the corresponding feature is used. The supported vision model can change; `GROQ_VISION_MODEL` is configurable.

## Technology sources

- [PyMuPDF page text and rendering](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)
- [pgvector Python SQLAlchemy support](https://github.com/pgvector/pgvector-python#sqlalchemy)
- [Groq vision and local-image format](https://console.groq.com/docs/vision)
- [Groq structured outputs](https://console.groq.com/docs/structured-outputs)
