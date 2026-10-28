from __future__ import annotations

import re
from collections import Counter

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]{3,}")
_STOP = frozenset(
    {
        "about",
        "after",
        "also",
        "been",
        "before",
        "being",
        "between",
        "could",
        "from",
        "have",
        "into",
        "more",
        "other",
        "said",
        "should",
        "that",
        "their",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "under",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "will",
        "with",
        "would",
        "your",
    }
)


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = [part.strip() for part in _SENTENCE_SPLIT.split(cleaned)]
    return [part for part in parts if 40 <= len(part) <= 400]


def executive_summary(text: str, title: str | None, headings: list[str]) -> list[str]:
    """Return three extractive bullets. Deterministic; no external LLM."""
    fallback = "Additional article detail was not available on this page."
    sentences = _sentences(text)
    if not sentences:
        paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 40]
        bullets = paragraphs[:3] or [
            "No extractable article text was found on this page.",
        ]
        while len(bullets) < 3:
            bullets.append(fallback)
        return bullets[:3]

    if len(sentences) <= 3:
        bullets = list(sentences)
        while len(bullets) < 3:
            bullets.append(fallback)
        return bullets[:3]

    tokens = [word.lower() for word in _WORD.findall(text) if word.lower() not in _STOP]
    keywords = {word for word, _count in Counter(tokens).most_common(30)}
    heading_words = {
        word.lower()
        for heading in ([title] if title else []) + headings
        for word in _WORD.findall(heading or "")
        if word.lower() not in _STOP
    }

    ranked: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences[:100]):
        words = [word.lower() for word in _WORD.findall(sentence)]
        score = float(sum(1 for word in words if word in keywords))
        score += 2.0 * sum(1 for word in words if word in heading_words)
        score += max(0.0, 10.0 - index) * 0.25
        if 70 <= len(sentence) <= 260:
            score += 1.5
        ranked.append((score, index, sentence))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    picked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for _score, index, sentence in ranked:
        key = sentence[:96].lower()
        if key in seen:
            continue
        seen.add(key)
        picked.append((index, sentence))
        if len(picked) == 3:
            break
    picked.sort(key=lambda item: item[0])
    return [sentence for _index, sentence in picked]
