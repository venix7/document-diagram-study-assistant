# Deploy Margin on Railway (PowerShell)

1. Create a **new Neon PostgreSQL database** and copy its connection string. The API creates the `vector` extension and tables on startup. Keep the database separate from the crop project.

2. Set these Railway service variables:

   ```text
   DATABASE_URL=<your Neon connection string>
   GROQ_API_KEY=<your Groq API key>
   GROQ_TEXT_MODEL=openai/gpt-oss-20b
   GROQ_VISION_MODEL=qwen/qwen3.8-27b
   APP_ENV=production
   DATA_DIR=/app/data
   ```

   Groq lists `qwen/qwen3.8-27b` as a supported vision model as of this build. If availability changes, set `GROQ_VISION_MODEL` to an image-capable model supported by your Groq account. The key stays in Railway variables, never in Git.

3. Push the project to its own GitHub repository:

   ```powershell
   git init
   git add .
   git diff --cached --check
   git status --short
   git commit -m "feat: build document and diagram study assistant"
   git remote add origin https://github.com/YOUR_USERNAME/document-diagram-study-assistant.git
   git branch -M main
   git push -u origin main
   ```

   If the folder is already a Git repository, omit `git init`; if the remote is configured, omit `git remote add origin`. `.gitignore` excludes `.env`, `.venv`, uploads, `node_modules`, and build output.

4. In Railway, create a service from the GitHub repository. Keep **Root Directory** at the repository root so it detects `Dockerfile`. The Docker build installs CPU PyTorch, builds the React app, and caches the MiniLM embedding model. Its command reads Railway's `PORT` and serves `/` and `/api` from the same FastAPI process. Set **Healthcheck Path** to `/api/health`. A service with insufficient memory may fail while loading PyTorch; inspect Railway memory usage if startup fails.

5. Attach a Railway volume to the service at exactly:

   ```text
   /app/data
   ```

   PDF files are saved under `/app/data/pdfs`; this keeps them across redeployments. Neon stores metadata, vectors, questions, and study sets. Use one service replica to avoid multiple in-process job workers handling the same pending PDF.

6. Generate a public Railway domain. Check its `/api/health` response; `embedding_ready` and `groq_configured` must both be `true`. Open `/` to check the React page. Run the generated-PDF smoke test from your local project:

   ```powershell
   python scripts\smoke_test.py https://YOUR-RAILWAY-DOMAIN
   ```

7. Upload one of your own text-based lecture PDFs, ask a text question, click its page citation, select a diagram region, ask about its labels, and generate a study set. The smoke test proves plumbing and source mapping; report answer quality separately using manually checked questions from your documents.

For optional local Docker testing, start Docker Desktop and run:

```powershell
docker build -t margin-study .
docker run --rm -p 8000:8000 --env-file .env -e APP_ENV=development margin-study
```

`APP_ENV=development` makes the session cookie work over local HTTP. Production uses a Secure cookie over Railway HTTPS.
