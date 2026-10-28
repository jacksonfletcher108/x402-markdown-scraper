from __future__ import annotations

import re
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.scraper import ScrapeError

_MAX_PAGES = 80
_NOISE = re.compile(r"[ \t]+\n")


def pdf_bytes_to_markdown(data: bytes, url: str) -> tuple[str, int]:
    if not data or not data.lstrip().startswith(b"%PDF"):
        raise ScrapeError("URL did not return a PDF", status_code=422)
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise ScrapeError("Could not read PDF", status_code=422) from exc
    if getattr(reader, "is_encrypted", False):
        raise ScrapeError("Encrypted PDFs are not supported", status_code=422)
    try:
        pages = reader.pages[:_MAX_PAGES]
        chunks: list[str] = [f"# PDF extract\n\nSource: {url}"]
        for index, page in enumerate(pages, start=1):
            raw = page.extract_text() or ""
            text = _NOISE.sub("\n", raw).strip()
            if text:
                chunks.append(f"## Page {index}\n\n{text}")
    except ScrapeError:
        raise
    except Exception as exc:
        raise ScrapeError("Could not parse PDF content", status_code=422) from exc
    markdown = "\n\n".join(chunks).strip()
    if len(chunks) == 1:
        markdown = f"{chunks[0]}\n\nNo extractable text was found in this PDF."
    return markdown, len(pages)
