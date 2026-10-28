"""LangChain tools backed by the x402 scraper shop.

    pip install -e "./client[examples]"
    set EVM_PRIVATE_KEY=0x...
    python examples/langchain_tool.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client" / "src"))

from x402_scraper import ScraperClient  # noqa: E402

try:
    from langchain_core.tools import StructuredTool
except ImportError:  # pragma: no cover
    StructuredTool = None  # type: ignore[misc, assignment]


def build_tools(client: ScraperClient) -> list:
    async def scrape(url: str) -> str:
        data = await client.scrape(url)
        return str(data.get("markdown") or "")

    async def summarize(url: str) -> str:
        data = await client.summary(url)
        return "\n".join(data.get("summary") or [])

    async def metadata(url: str) -> dict:
        return await client.extract_metadata(url)

    async def parse_pdf(url: str) -> str:
        data = await client.parse_pdf(url)
        return str(data.get("markdown") or "")

    async def crawl(url: str, max_depth: int = 2) -> dict:
        return await client.deep_crawl(url, max_depth=max_depth)

    if StructuredTool is None:
        return [
            ("scrape_url", scrape),
            ("summarize_url", summarize),
            ("extract_metadata", metadata),
            ("parse_pdf", parse_pdf),
            ("deep_crawl", crawl),
        ]

    return [
        StructuredTool.from_function(coroutine=scrape, name="scrape_url", description="Fetch a URL as Markdown ($0.01 USDC)."),
        StructuredTool.from_function(coroutine=summarize, name="summarize_url", description="Three-bullet summary ($0.02 USDC)."),
        StructuredTool.from_function(coroutine=metadata, name="extract_metadata", description="Page metadata ($0.01 USDC)."),
        StructuredTool.from_function(coroutine=parse_pdf, name="parse_pdf", description="PDF to Markdown ($0.05 USDC)."),
        StructuredTool.from_function(coroutine=crawl, name="deep_crawl", description="Crawl a site map ($0.15 USDC)."),
    ]


async def main() -> None:
    async with ScraperClient() as client:
        tools = build_tools(client)
        print("loaded", len(tools), "LangChain-compatible tools")
        first = tools[0]
        if hasattr(first, "ainvoke"):
            text = await first.ainvoke({"url": "https://example.com"})
            print(str(text)[:400])
        else:
            text = await first[1]("https://example.com")
            print(str(text)[:400])


if __name__ == "__main__":
    asyncio.run(main())
