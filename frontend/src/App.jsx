import { useEffect, useRef, useState } from "react";

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
  });
  const data =
    response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Request failed (" + response.status + ")",
    );
  }
  return data;
}

function dateLabel(value) {
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function PageLinks({ citations, goToPage }) {
  if (!citations?.length)
    return (
      <span className="no-source">
        No supporting passage found in this document
      </span>
    );
  return (
    <div className="citations">
      {citations.map((cite) => (
        <button
          key={cite.reference + "-" + cite.page}
          type="button"
          onClick={() => goToPage(cite.page)}
          title={cite.excerpt}
        >
          Page {cite.page} <span>↗</span>
        </button>
      ))}
    </div>
  );
}

export default function App() {
  const [documents, setDocuments] = useState([]);
  const [active, setActive] = useState(null);
  const [health, setHealth] = useState(null);
  const [page, setPage] = useState(1);
  const [mode, setMode] = useState("ask");
  const [selection, setSelection] = useState(null);
  const [draft, setDraft] = useState("");
  const [file, setFile] = useState(null);
  const [interactions, setInteractions] = useState([]);
  const [sets, setSets] = useState([]);
  const [kind, setKind] = useState("quiz");
  const [revealed, setRevealed] = useState({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const imageRef = useRef(null);
  const dragRef = useRef(null);
  const activeRef = useRef(null);

  async function refreshDocuments() {
    const list = await api("/api/documents");
    setDocuments(list);
    if (activeRef.current) {
      const updated = list.find((item) => item.id === activeRef.current);
      if (updated) setActive(updated);
    }
  }

  useEffect(() => {
    Promise.all([api("/api/documents"), api("/api/health")])
      .then(([list, status]) => {
        setDocuments(list);
        setHealth(status);
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (
      !documents.some(
        (doc) => doc.status === "pending" || doc.status === "processing",
      )
    )
      return undefined;
    const timer = window.setInterval(() => {
      refreshDocuments().catch((err) => setError(err.message));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [documents]);

  const activeId = active?.id;
  useEffect(() => {
    if (!activeId) return undefined;
    let cancelled = false;
    Promise.all([
      api("/api/documents/" + activeId + "/interactions"),
      api("/api/documents/" + activeId + "/study-sets"),
    ])
      .then(([turns, studySets]) => {
        if (!cancelled) {
          setInteractions(turns);
          setSets(studySets);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  function openDocument(doc) {
    activeRef.current = doc.id;
    setActive(doc);
    setPage(1);
    setSelection(null);
    setDraft("");
    setInteractions([]);
    setSets([]);
    setError("");
  }

  function jumpToPage(nextPage) {
    setPage(nextPage);
    setSelection(null);
  }

  async function upload(event) {
    event.preventDefault();
    if (!file) return;
    setBusy("upload");
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const doc = await api("/api/documents", { method: "POST", body: form });
      await refreshDocuments();
      openDocument(doc);
      setFile(null);
      event.target.reset();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  function point(event) {
    const rect = imageRef.current.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
    };
  }

  function startDrag(event) {
    if (mode !== "diagram" || !imageRef.current) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const at = point(event);
    dragRef.current = at;
    setSelection({ x0: at.x, y0: at.y, x1: at.x, y1: at.y });
  }

  function moveDrag(event) {
    if (!dragRef.current) return;
    const at = point(event);
    setSelection({
      x0: Math.min(dragRef.current.x, at.x),
      y0: Math.min(dragRef.current.y, at.y),
      x1: Math.max(dragRef.current.x, at.x),
      y1: Math.max(dragRef.current.y, at.y),
    });
  }

  function endDrag(event) {
    if (!dragRef.current) return;
    const at = point(event);
    const box = {
      x0: Math.min(dragRef.current.x, at.x),
      y0: Math.min(dragRef.current.y, at.y),
      x1: Math.max(dragRef.current.x, at.x),
      y1: Math.max(dragRef.current.y, at.y),
    };
    setSelection(box.x1 - box.x0 < 0.03 || box.y1 - box.y0 < 0.03 ? null : box);
    dragRef.current = null;
  }

  async function ask(event) {
    event.preventDefault();
    const question = draft.trim();
    if (!active || question.length < 3) return;
    if (mode === "diagram" && !selection) {
      setError("Select a diagram region on the page first.");
      return;
    }
    setBusy("ask");
    setError("");
    try {
      const diagram = mode === "diagram";
      const path =
        "/api/documents/" +
        active.id +
        (diagram ? "/diagram-questions" : "/questions");
      const body = diagram ? { question, page, ...selection } : { question };
      await api(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setInteractions(
        await api("/api/documents/" + active.id + "/interactions"),
      );
      setDraft("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function generate() {
    if (!active) return;
    setBusy("study");
    setError("");
    try {
      await api("/api/documents/" + active.id + "/study-sets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, count: 3 }),
      });
      setSets(await api("/api/documents/" + active.id + "/study-sets"));
      setRevealed({});
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function remove() {
    if (!active || !window.confirm("Delete this PDF and its study history?"))
      return;
    setBusy("delete");
    setError("");
    try {
      await api("/api/documents/" + active.id, { method: "DELETE" });
      activeRef.current = null;
      setActive(null);
      setInteractions([]);
      setSets([]);
      await refreshDocuments();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  const isReady = active?.status === "ready";
  const canAsk = isReady && (mode === "diagram" || active.text_page_count > 0);
  const newestSet = sets[0];

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-symbol">
            m<span>.</span>
          </span>
          <div>
            <strong>Margin</strong>
            <small>Study workspace</small>
          </div>
        </div>
        <div className="sidebar-section-label">YOUR LIBRARY</div>
        <form className="upload-card" onSubmit={upload}>
          <label htmlFor="upload-file">
            <span className="upload-icon">↥</span>
            <strong>Add a PDF</strong>
            <small>
              {file ? file.name : "Lecture notes, chapters, slides"}
            </small>
          </label>
          <input
            id="upload-file"
            type="file"
            accept=".pdf,application/pdf"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
          {file && (
            <button className="upload-button" type="submit" disabled={!!busy}>
              {busy === "upload" ? "Uploading…" : "Upload & index →"}
            </button>
          )}
          <span className="upload-limit">
            Selectable-text PDFs · up to 15 MB / 100 pages
          </span>
        </form>
        <div className="doc-list">
          {documents.map((doc) => (
            <button
              type="button"
              className={
                "doc-item" + (active?.id === doc.id ? " selected" : "")
              }
              onClick={() => openDocument(doc)}
              key={doc.id}
            >
              <span className="doc-icon">▤</span>
              <span className="doc-label">
                <strong>{doc.title}</strong>
                <small>
                  {doc.status === "ready"
                    ? doc.page_count + " pages"
                    : doc.status}
                </small>
              </span>
            </button>
          ))}
          {!documents.length && (
            <p className="empty-library">Your documents will appear here.</p>
          )}
        </div>
        <div className="sidebar-bottom">
          <span className="status-dot" />{" "}
          {health?.groq_configured ? "AI ready" : "Add a Groq API key"}
          <small>Files stay in this browser’s workspace.</small>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <span>DOCUMENT & DIAGRAM ASSISTANT</span>
          <span className="topbar-right">
            Source-backed learning <span>✳</span>
          </span>
        </header>
        {error && (
          <div className="error" role="alert">
            <strong>Something needs attention</strong>
            <span>{error}</span>
            <button
              onClick={() => setError("")}
              aria-label="Dismiss error"
              type="button"
            >
              ×
            </button>
          </div>
        )}
        {!active ? (
          <section className="welcome">
            <span className="eyebrow">A BETTER WAY TO READ / 01</span>
            <h1>
              Make room for
              <br />
              <em>understanding.</em>
            </h1>
            <p>
              Bring your lecture notes and diagrams into one study space. Ask a
              question, inspect the page behind each answer, and build a quick
              revision set.
            </p>
            <div className="welcome-steps">
              <div>
                <span>01</span>
                <strong>Upload a PDF</strong>
                <small>Pages become searchable</small>
              </div>
              <div>
                <span>02</span>
                <strong>Ask or select a diagram</strong>
                <small>See the source page</small>
              </div>
              <div>
                <span>03</span>
                <strong>Practice</strong>
                <small>Review cited questions</small>
              </div>
            </div>
          </section>
        ) : (
          <>
            <section className="document-header">
              <div>
                <span className="eyebrow">
                  OPEN DOCUMENT / {dateLabel(active.created_at)}
                </span>
                <h1>{active.title}</h1>
                <p>
                  {active.page_count} pages <span>·</span>{" "}
                  {active.text_page_count} pages with searchable text{" "}
                  <span>·</span> {active.status}
                </p>
              </div>
              <div className="header-actions">
                <a href={"/api/documents/" + active.id + "/file"}>
                  Download PDF ↗
                </a>
                <button
                  type="button"
                  onClick={remove}
                  disabled={!!busy || !isReady}
                >
                  Delete
                </button>
              </div>
            </section>
            {!isReady ? (
              <div className="processing-card">
                <span className="processing-mark">◌</span>
                <h2>
                  {active.status === "failed"
                    ? "Processing stopped"
                    : "Preparing your study space"}
                </h2>
                <p>
                  {active.error ||
                    "Extracting pages and indexing their text. This view updates automatically."}
                </p>
              </div>
            ) : (
              <div className="work-grid">
                <section className="viewer panel">
                  <div className="panel-top">
                    <div>
                      <span className="eyebrow">DOCUMENT VIEWER</span>
                      <h2>Original page</h2>
                    </div>
                    <span className="page-count">
                      PAGE {page} / {active.page_count}
                    </span>
                  </div>
                  <div className="page-controls">
                    <button
                      type="button"
                      onClick={() => {
                        setPage(Math.max(1, page - 1));
                        setSelection(null);
                      }}
                      disabled={page === 1}
                    >
                      ← Previous
                    </button>
                    <input
                      aria-label="Page number"
                      type="number"
                      min="1"
                      max={active.page_count}
                      value={page}
                      onChange={(event) => {
                        const n = Number(event.target.value);
                        if (n >= 1 && n <= active.page_count) {
                          setPage(n);
                          setSelection(null);
                        }
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setPage(Math.min(active.page_count, page + 1));
                        setSelection(null);
                      }}
                      disabled={page === active.page_count}
                    >
                      Next →
                    </button>
                  </div>
                  <div className="page-area">
                    <div className="page-surface">
                      <img
                        ref={imageRef}
                        src={
                          "/api/documents/" +
                          active.id +
                          "/pages/" +
                          page +
                          "/preview"
                        }
                        alt={"Document page " + page}
                      />
                      <div
                        className={
                          "selection-layer" +
                          (mode === "diagram" ? " enabled" : "")
                        }
                        onPointerDown={startDrag}
                        onPointerMove={moveDrag}
                        onPointerUp={endDrag}
                        onPointerCancel={() => {
                          dragRef.current = null;
                        }}
                        aria-label="Drag to select a diagram region"
                      >
                        {selection && mode === "diagram" && (
                          <div
                            className="selection-box"
                            style={{
                              left: selection.x0 * 100 + "%",
                              top: selection.y0 * 100 + "%",
                              width: (selection.x1 - selection.x0) * 100 + "%",
                              height: (selection.y1 - selection.y0) * 100 + "%",
                            }}
                          />
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="viewer-foot">
                    {mode === "diagram"
                      ? "Drag across the diagram you want explained."
                      : "Citations open the exact page used for an answer."}
                  </div>
                </section>
                <section className="assistant panel">
                  <div className="panel-top">
                    <div>
                      <span className="eyebrow">YOUR STUDY PARTNER</span>
                      <h2>Explore this document</h2>
                    </div>
                    <span className="asterisk">✳</span>
                  </div>
                  <div className="tabs" role="tablist" aria-label="Study modes">
                    <button
                      type="button"
                      className={mode === "ask" ? "active" : ""}
                      onClick={() => setMode("ask")}
                    >
                      Ask text
                    </button>
                    <button
                      type="button"
                      className={mode === "diagram" ? "active" : ""}
                      onClick={() => setMode("diagram")}
                    >
                      Explain diagram
                    </button>
                    <button
                      type="button"
                      className={mode === "practice" ? "active" : ""}
                      onClick={() => setMode("practice")}
                    >
                      Practice
                    </button>
                  </div>
                  {mode === "practice" ? (
                    <div className="practice-pane">
                      <p className="mode-intro">
                        Create questions from the text in this PDF. Every answer
                        points back to a page.
                      </p>
                      <div className="practice-actions">
                        <select
                          value={kind}
                          onChange={(e) => setKind(e.target.value)}
                          aria-label="Study set type"
                        >
                          <option value="quiz">Quiz questions</option>
                          <option value="flashcards">Flashcards</option>
                        </select>
                        <button
                          className="primary"
                          type="button"
                          onClick={generate}
                          disabled={!!busy || !active.text_page_count}
                        >
                          {busy === "study" ? "Generating…" : "Create 3 →"}
                        </button>
                      </div>
                      {!active.text_page_count && (
                        <p className="muted">
                          No selectable text was found. Try a text-based PDF.
                        </p>
                      )}
                      {newestSet && (
                        <div className="study-items">
                          <span className="eyebrow">
                            {newestSet.kind.toUpperCase()} /{" "}
                            {newestSet.items.length} ITEMS
                          </span>
                          {newestSet.items.map((item, i) => (
                            <div
                              className="study-item"
                              key={newestSet.id + "-" + i}
                            >
                              <span className="study-number">0{i + 1}</span>
                              <strong>{item.question}</strong>
                              <button
                                type="button"
                                className="reveal"
                                onClick={() =>
                                  setRevealed({
                                    ...revealed,
                                    [i]: !revealed[i],
                                  })
                                }
                              >
                                {revealed[i]
                                  ? "Hide answer ↑"
                                  : "Reveal answer ↓"}
                              </button>
                              {revealed[i] && (
                                <>
                                  <p>{item.answer}</p>
                                  <PageLinks
                                    citations={item.citations}
                                    goToPage={jumpToPage}
                                  />
                                </>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      {!newestSet && (
                        <div className="blank-answer">
                          Your first study set will appear here.
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="ask-pane">
                      <p className="mode-intro">
                        {mode === "diagram"
                          ? "Select a region on the page, then ask about its labels, steps, or connections."
                          : "Ask about a concept in the PDF. Answers include the page and a supporting excerpt."}
                      </p>
                      <form onSubmit={ask}>
                        <label htmlFor="question">
                          {mode === "diagram"
                            ? "Question about your selection"
                            : "Your question"}
                        </label>
                        <textarea
                          id="question"
                          rows="3"
                          maxLength="500"
                          value={draft}
                          onChange={(e) => setDraft(e.target.value)}
                          placeholder={
                            mode === "diagram"
                              ? "What does this flowchart show?"
                              : "Explain the main idea of this section…"
                          }
                        />
                        <button
                          className="primary"
                          disabled={
                            !!busy ||
                            !canAsk ||
                            draft.trim().length < 3 ||
                            (mode === "diagram" && !selection)
                          }
                          type="submit"
                        >
                          {busy === "ask" ? "Thinking…" : "Ask document →"}
                        </button>
                      </form>
                      {!active.text_page_count && mode === "ask" && (
                        <p className="muted">
                          This PDF has no selectable text. You can still select
                          a page region in Diagram mode.
                        </p>
                      )}
                      <div className="answers">
                        <span className="eyebrow">RECENT ANSWERS</span>
                        {interactions.map((item) => (
                          <article className="answer" key={item.id}>
                            <div className="answer-kind">
                              {item.kind === "diagram"
                                ? "◈ DIAGRAM"
                                : "≡ DOCUMENT"}
                            </div>
                            <h3>{item.question}</h3>
                            <p>{item.answer}</p>
                            <PageLinks
                              citations={item.citations}
                              goToPage={jumpToPage}
                            />
                          </article>
                        ))}
                        {!interactions.length && (
                          <div className="blank-answer">
                            Your questions and sourced answers appear here.
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </section>
              </div>
            )}
          </>
        )}
        <footer>
          Margin · Learn from the page, then make it your own.{" "}
          <span>
            Experimental AI explanations should be checked against the original
            document.
          </span>
        </footer>
      </main>
    </div>
  );
}
