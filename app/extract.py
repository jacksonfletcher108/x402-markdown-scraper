from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown


@dataclass
class PageExtract:
    url: str
    title: str | None
    description: str | None
    markdown: str
    text: str
    headings: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    source_status: int = 200
    paid_source: bool = False


def parse_html(html: str, url: str) -> PageExtract:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else None
    desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    description = desc_tag.get("content", "").strip() if desc_tag else None

    headings = [
        node.get_text(" ", strip=True)
        for node in soup.find_all(["h1", "h2", "h3"])
        if node.get_text(strip=True)
    ][:40]

    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if href.startswith("http") and href not in seen:
            seen.add(href)
            links.append(href)
        if len(links) >= 50:
            break

    body = soup.body or soup
    markdown = html_to_markdown(
        str(body),
        heading_style="ATX",
        bullets="-",
        strip=["img"],
    ).strip() or f"Fetched {url} but found no extractable text."
    text = body.get_text("\n", strip=True)

    return PageExtract(
        url=url,
        title=title,
        description=description or None,
        markdown=markdown,
        text=text,
        headings=headings,
        links=links,
    )
