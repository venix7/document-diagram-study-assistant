import io
import tempfile
import unittest
from pathlib import Path

import pymupdf
from PIL import Image

from backend.app.pdf import extract_chunks, inspect_pdf, render_page


class PDFTests(unittest.TestCase):
    def test_page_numbers_and_selected_region(self):
        pdf = pymupdf.open()
        first = pdf.new_page()
        first.insert_text(
            (50, 80), "Binary search checks the middle of a sorted sequence."
        )
        second = pdf.new_page()
        second.draw_rect(pymupdf.Rect(40, 50, 250, 160))
        second.insert_text((60, 100), "START -> COMPARE -> HALVE")
        raw = pdf.tobytes()
        pdf.close()
        self.assertEqual(inspect_pdf(raw), 2)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notes.pdf"
            path.write_bytes(raw)
            chunks, text_pages = extract_chunks(path)
            self.assertEqual(text_pages, 2)
            self.assertEqual({item[0] for item in chunks}, {1, 2})
            preview = render_page(path, 2)
            selection = render_page(path, 2, (0.05, 0.05, 0.5, 0.4))
            self.assertEqual(Image.open(io.BytesIO(preview)).format, "JPEG")
            self.assertNotEqual(selection, preview)
            with self.assertRaises(ValueError):
                render_page(path, 3)
            with self.assertRaises(ValueError):
                render_page(path, 1, (0.5, 0.5, 0.51, 0.51))

    def test_invalid_pdf_rejected(self):
        with self.assertRaises(ValueError):
            inspect_pdf(b"not a pdf")


if __name__ == "__main__":
    unittest.main()
