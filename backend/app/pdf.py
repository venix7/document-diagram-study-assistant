import io
import re
from pathlib import Path

import pymupdf
from langchain_text_splitters import RecursiveCharacterTextSplitter
from PIL import Image

from .config import MAX_PAGES

SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=950,
    chunk_overlap=140,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def inspect_pdf(raw: bytes) -> int:
    try:
        with pymupdf.open(stream=raw, filetype="pdf") as pdf:
            if pdf.needs_pass or pdf.page_count < 1 or pdf.page_count > MAX_PAGES:
                raise ValueError(
                    f"PDF must be unlocked and contain 1–{MAX_PAGES} pages"
                )
            return pdf.page_count
    except (pymupdf.FileDataError, pymupdf.EmptyFileError, RuntimeError) as exc:
        raise ValueError("Upload a valid, unlocked PDF") from exc


def page_text(page: pymupdf.Page) -> str:
    blocks = [block for block in page.get_text("blocks", sort=True) if block[6] == 0]
    return "\n\n".join(
        re.sub(r"[ \t]+", " ", block[4]).strip() for block in blocks if block[4].strip()
    )


def extract_chunks(path: Path) -> tuple[list[tuple[int, int, str]], int]:
    chunks = []
    text_pages = 0
    with pymupdf.open(path) as pdf:
        for index, page in enumerate(pdf, start=1):
            text = page_text(page)
            if text:
                text_pages += 1
            for ordinal, content in enumerate(SPLITTER.split_text(text)):
                if content.strip():
                    chunks.append((index, ordinal, content.strip()))
    return chunks, text_pages


def render_page(
    path: Path, page_number: int, box: tuple[float, float, float, float] | None = None
) -> bytes:
    with pymupdf.open(path) as pdf:
        if not 1 <= page_number <= pdf.page_count:
            raise ValueError("Page out of range")
        page = pdf[page_number - 1]
        clip = page.rect
        if box is not None:
            x0, y0, x1, y1 = box
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError("Select a valid region on the page")
            if x1 - x0 < 0.03 or y1 - y0 < 0.03:
                raise ValueError("Selected region is too small")
            clip = pymupdf.Rect(
                page.rect.x0 + x0 * page.rect.width,
                page.rect.y0 + y0 * page.rect.height,
                page.rect.x0 + x1 * page.rect.width,
                page.rect.y0 + y1 * page.rect.height,
            )
        scale = min(6.0, 1400 / max(clip.width, clip.height))
        pix = page.get_pixmap(
            matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False
        )
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        result = io.BytesIO()
        image.save(result, format="JPEG", quality=85, optimize=True)
        return result.getvalue()
