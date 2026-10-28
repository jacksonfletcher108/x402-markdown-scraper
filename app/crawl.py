from __future__ import annotations

from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse

from app.config import Settings
from app.extract import PageExtract
from app.scraper import ScrapeError, fetch_page, validate_url

_SKIP_EXT = (
    ".pdf",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".mp4",
    ".mp3",
    ".css",
    ".js",
)
_MAX_PAGES = 8


def _normalize(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", parsed.query, ""))


def _same_site(root: str, candidate: str) -> bool:
    a = urlparse(root)
    b = urlparse(candidate)
    return a.scheme in {"http", "https"} and a.hostname == b.hostname and b.scheme in {"http", "https"}


def _internal_links(page: PageExtract, root: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for href in page.links:
        absolute = _normalize(urljoin(page.url, href))
        if absolute in seen:
            continue
        seen.add(absolute)
        if not _same_site(root, absolute):
            continue
        path = urlparse(absolute).path.lower()
        if any(path.endswith(ext) for ext in _SKIP_EXT):
            continue
        found.append(absolute)
    return found


async def deep_crawl(url: str, max_depth: int, settings: Settings) -> dict:
    root = _normalize(validate_url(url))
    depth = max(1, min(int(max_depth), 3))
    queue: deque[tuple[str, int]] = deque([(root, 0)])
    visited: set[str] = {root}
    pages: list[dict] = []
    errors: list[dict] = []

    while queue and len(pages) < _MAX_PAGES:
        current, level = queue.popleft()
        try:
            page = await fetch_page(current, settings, pay_for_source=False)
        except ScrapeError as exc:
            errors.append({"url": current, "error": str(exc)})
            continue
        pages.append(
            {
                "url": page.url,
                "title": page.title,
                "depth": level,
                "headings": page.headings[:20],
                "markdown": page.markdown[:4000],
                "links": _internal_links(page, root)[:20],
            }
        )
        if level >= depth:
            continue
        for child in _internal_links(page, root):
            if child in visited:
                continue
            visited.add(child)
            queue.append((child, level + 1))
            if len(visited) >= _MAX_PAGES * 3:
                break

    return {
        "root": root,
        "max_depth": depth,
        "page_count": len(pages),
        "pages": pages,
        "errors": errors,
    }
