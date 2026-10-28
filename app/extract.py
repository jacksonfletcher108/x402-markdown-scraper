from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown

_WORDS = re.compile(r"\b[\w'-]+\b", re.UNICODE)
_WORDS_PER_MINUTE = 230


@dataclass
class PageExtract:
    url: str
    title: str | None
    description: str | None
    markdown: str
    text: str
    headings: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    opengraph: dict[str, str] = field(default_factory=dict)
    json_ld: list[Any] = field(default_factory=list)
    author: str | None = None
    published: str | None = None
    word_count: int = 0
    reading_time_minutes: int = 1
    source_status: int = 200
    paid_source: bool = False


def _meta_content(soup: BeautifulSoup, **attrs: str) -> str | None:
    tag = soup.find("meta", attrs=attrs)
    if not tag:
        return None
    content = tag.get("content")
    if not content:
        return None
    value = str(content).strip()
    return value or None


def extract_opengraph(soup: BeautifulSoup) -> dict[str, str]:
    collected: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name")
        content = tag.get("content")
        if not key or not content:
            continue
        name = str(key).strip()
        if name.startswith(("og:", "twitter:", "article:")):
            collected[name] = str(content).strip()
    return collected


def extract_json_ld(soup: BeautifulSoup) -> list[Any]:
    items: list[Any] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            items.extend(parsed[:10])
        elif isinstance(parsed, dict) and isinstance(parsed.get("@graph"), list):
            items.extend(parsed["@graph"][:10])
            slim = {key: value for key, value in parsed.items() if key != "@graph"}
            if slim:
                items.append(slim)
        else:
            items.append(parsed)
        if len(items) >= 15:
            break
    return items[:15]


def _as_name(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "headline", "value"):
            found = value.get(key)
            if isinstance(found, str) and found.strip():
                return found.strip()
    if isinstance(value, list):
        for item in value:
            found = _as_name(item)
            if found:
                return found
    return None


def _ld_first(nodes: list[Any], *keys: str) -> str | None:
    stack: list[Any] = list(nodes)
    seen = 0
    while stack and seen < 80:
        seen += 1
        node = stack.pop(0)
        if isinstance(node, list):
            stack[0:0] = node[:20]
            continue
        if not isinstance(node, dict):
            continue
        for key in keys:
            if key in node:
                found = _as_name(node[key])
                if found:
                    return found
        for child in node.values():
            if isinstance(child, (dict, list)):
                stack.append(child)
    return None


def infer_author(soup: BeautifulSoup, json_ld: list[Any], opengraph: dict[str, str]) -> str | None:
    found = _ld_first(json_ld, "author", "creator")
    if found:
        return found
    return (
        _meta_content(soup, name="author")
        or _meta_content(soup, property="article:author")
        or _meta_content(soup, name="byl")
        or opengraph.get("article:author")
        or opengraph.get("og:article:author")
    )


def infer_published(soup: BeautifulSoup, json_ld: list[Any], opengraph: dict[str, str]) -> str | None:
    found = _ld_first(json_ld, "datePublished", "dateCreated", "dateModified")
    if found:
        return found
    return (
        _meta_content(soup, property="article:published_time")
        or _meta_content(soup, name="pubdate")
        or _meta_content(soup, name="publish-date")
        or _meta_content(soup, name="date")
        or _meta_content(soup, itemprop="datePublished")
        or opengraph.get("article:published_time")
        or opengraph.get("og:updated_time")
    )


def word_stats(text: str) -> tuple[int, int]:
    count = len(_WORDS.findall(text or ""))
    minutes = 1 if count == 0 else max(1, math.ceil(count / _WORDS_PER_MINUTE))
    return count, minutes


def parse_html(html: str, url: str) -> PageExtract:
    soup = BeautifulSoup(html, "lxml")
    opengraph = extract_opengraph(soup)
    json_ld = extract_json_ld(soup)
    author = infer_author(soup, json_ld, opengraph)
    published = infer_published(soup, json_ld, opengraph)

    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    title = (
        (soup.title.get_text(strip=True) if soup.title else None)
        or opengraph.get("og:title")
        or opengraph.get("twitter:title")
    )
    description = (
        _meta_content(soup, name="description")
        or opengraph.get("og:description")
        or opengraph.get("twitter:description")
    )

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
    words, minutes = word_stats(text)

    return PageExtract(
        url=url,
        title=title,
        description=description or None,
        markdown=markdown,
        text=text,
        headings=headings,
        links=links,
        opengraph=opengraph,
        json_ld=json_ld,
        author=author,
        published=published,
        word_count=words,
        reading_time_minutes=minutes,
    )
