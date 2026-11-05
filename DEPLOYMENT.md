# Deploy Margin on Google Cloud Run (PowerShell)

PDF files are temporary. Neon retains metadata and answers, but the app only lists PDFs that still exist in the current Cloud Run instance. Re-upload after an instance is replaced. Use one instance and one Uvicorn worker so PDF page requests access the same temporary filesystem.

## 1. Check the updated project locally

From the project directory with your Python environment active:

```powershell
python -m unittest discover -s tests -v
npm ci --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

The upload endpoint now indexes the PDF before returning. It does not rely on background CPU after a request ends.

## 2. Push to GitHub

If the project already has an `origin` remote:

```powershell
git add backend/app/main.py tests/test_api.py scripts/smoke_test.py DEPLOYMENT.md README.md PHASES.md
git diff --cached --check
git status --short
git commit -m "feat: support temporary PDFs on Cloud Run"
git push
```

For a new repository, create it on GitHub first and run `git init`, `git add .`, `git commit -m "feat: build Margin study assistant"`, `git branch -M main`, `git remote add origin https://github.com/YOUR_USERNAME/document-diagram-study-assistant.git`, and `git push -u origin main`. Ensure `.env`, `.venv`, `data`, and `frontend/node_modules` are not staged.

## 3. Set up Google Cloud

1. Create/select a Google Cloud project and attach a billing account. Enable Cloud Run, Cloud Build, and Artifact Registry when prompted.
2. Open **Cloud Run → Create service → Continuously deploy from a repository**. Connect GitHub, select the repository and main branch, and use the root `Dockerfile`.
3. Name the service `margin-study`, choose a region, and allow unauthenticated access so the website is public.
4. Set **1 vCPU**, **2 GiB memory**, **request-based billing**, **minimum instances 0**, **maximum instances 1**, **concurrency 1**, and **request timeout 300 seconds**. The Dockerfile reads Cloud Run's `PORT` automatically.
5. Add these environment variables:

   ```text
   DATABASE_URL=your Neon PostgreSQL connection string
   GROQ_API_KEY=your Groq API key
   GROQ_TEXT_MODEL=openai/gpt-oss-20b
   GROQ_VISION_MODEL=qwen/qwen3.8-27b
   APP_ENV=production
   DATA_DIR=/tmp/margin-data
   ```

   Store the connection string and Groq key as secrets if Secret Manager integration is available. Keep them out of Git. Use a fresh Neon database or one already using the current `study_*` tables.

6. Click **Create/Deploy** and copy the `https://...run.app` service URL.

## 4. Check the public service

Replace the URL with your actual Cloud Run URL:

```powershell
Invoke-RestMethod https://YOUR-SERVICE-URL.run.app/api/health
python scripts\smoke_test.py https://YOUR-SERVICE-URL.run.app
```

Health should show `status: ok`, `embedding_ready: True`, and `groq_configured: True`. Open the URL, upload `samples\algorithms-demo.pdf`, ask a question, try a page/diagram, and generate a study set. If indexing exceeds 300 seconds, the request times out; reduce PDF size or raise both the Cloud Run timeout and the smoke test request timeout.

Cloud Run has a monthly free allowance rather than a guaranteed zero bill. Builds, image storage, network traffic and usage above free allowances can cost money; check Google Cloud Billing after deployment.
