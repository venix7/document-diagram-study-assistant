# Six-commit build map

| Commit | Concrete contents |
| --- | --- |
| 1 — scaffold | React/Vite, FastAPI, `.env.example`, configuration, project layout |
| 2 — PDFs | validated upload, private storage, page text extraction and preview |
| 3 — retrieval | PyTorch MiniLM embeddings, page chunks, Neon/pgvector and document-scoped vector search |
| 4 — sourced answers | Groq structured response, server-validated page citations, history |
| 5 — diagram + practice | selected page-region vision, quiz/flashcards, study interface |
| 6 — release | tests, generated-PDF smoke test, Docker image, Railway volume and setup docs |

The supplied source tree is the final state without Git history. The table records the six development milestones; the deployment guide shows how to make an initial commit from the final tree. No dataset, custom model training, or saved model checkpoint is required; the embedding checkpoint is fetched during Docker build. This project is independent of the crop advisor and its model scores.
