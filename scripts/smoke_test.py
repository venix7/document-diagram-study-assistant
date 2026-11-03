"""Exercise a running deployment with a generated two-page study PDF."""

import argparse
import io
import time

import pymupdf
import requests


def sample_pdf() -> bytes:
    pdf = pymupdf.open()
    first = pdf.new_page()
    first.insert_textbox(
        pymupdf.Rect(50, 70, 540, 260),
        "Binary search works on a sorted sequence. It compares the target "
        "with the middle element. If the target is smaller, it discards the "
        "upper half; if it is larger, it discards the lower half. Repeating "
        "this process makes the search interval shrink logarithmically.",
        fontsize=13,
    )
    first.draw_rect(pymupdf.Rect(55, 300, 280, 420))
    first.insert_text((75, 350), "START -> MIDDLE -> HALVE")
    second = pdf.new_page()
    second.insert_textbox(
        pymupdf.Rect(50, 70, 540, 260),
        "Breadth-first search visits nodes of a graph layer by layer. "
        "A queue tracks the frontier. It explores all neighbors of the "
        "current node before moving to nodes farther away. A visited set "
        "prevents repeated processing of the same node.",
        fontsize=13,
    )
    raw = pdf.tobytes()
    pdf.close()
    return raw


def request_json(client, method: str, url: str, **kwargs):
    response = client.request(method, url, timeout=90, **kwargs)
    if not response.ok:
        raise RuntimeError(
            f"{method} {url} returned {response.status_code}: {response.text[:400]}"
        )
    return response.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "base_url", help="http://127.0.0.1:8000 or the Railway public URL"
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    with requests.Session() as client:
        health = request_json(client, "GET", base + "/api/health")
        if not health["embedding_ready"] or not health["groq_configured"]:
            raise RuntimeError(f"Embedding or Groq is not configured: {health}")
        doc = request_json(
            client,
            "POST",
            base + "/api/documents",
            files={
                "file": ("smoke-study.pdf", io.BytesIO(sample_pdf()), "application/pdf")
            },
        )
        document_id = doc["id"]
        with requests.Session() as other_browser:
            foreign = other_browser.get(
                base + "/api/documents/" + document_id, timeout=15
            )
            assert foreign.status_code == 404, "A separate browser accessed the PDF"
        deadline = time.monotonic() + 180
        while doc["status"] not in {"ready", "failed"} and time.monotonic() < deadline:
            time.sleep(2)
            doc = request_json(client, "GET", base + "/api/documents/" + document_id)
        if doc["status"] != "ready" or doc["text_page_count"] != 2:
            raise AssertionError(f"Indexing did not complete: {doc}")
        answer = request_json(
            client,
            "POST",
            base + "/api/documents/" + document_id + "/questions",
            json={"question": "How does binary search reduce its search interval?"},
        )
        assert answer["citations"] and 1 in [c["page"] for c in answer["citations"]], (
            answer
        )
        preview = client.get(
            base + "/api/documents/" + document_id + "/pages/1/preview", timeout=45
        )
        assert preview.ok and preview.headers["content-type"].startswith("image/jpeg")
        diagram = request_json(
            client,
            "POST",
            base + "/api/documents/" + document_id + "/diagram-questions",
            json={
                "question": "What labels can you see in this region?",
                "page": 1,
                "x0": 0.07,
                "y0": 0.33,
                "x1": 0.52,
                "y1": 0.52,
            },
        )
        assert diagram["answer"] and diagram["citations"][0]["page"] == 1
        study = request_json(
            client,
            "POST",
            base + "/api/documents/" + document_id + "/study-sets",
            json={"kind": "flashcards", "count": 2},
        )
        assert len(study["items"]) == 2 and all(
            item["citations"] for item in study["items"]
        )
        turns = request_json(
            client, "GET", base + "/api/documents/" + document_id + "/interactions"
        )
        assert len(turns) == 2
        print(
            {
                "status": "passed",
                "pages": doc["page_count"],
                "indexed_pages": doc["text_page_count"],
                "text_citations": len(answer["citations"]),
                "diagram_citations": len(diagram["citations"]),
                "flashcards": len(study["items"]),
            }
        )


if __name__ == "__main__":
    main()
