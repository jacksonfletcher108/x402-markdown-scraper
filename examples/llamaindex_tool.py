"""LlamaIndex FunctionTools backed by the x402 scraper shop.

    pip install -e "./client[examples]"
    set EVM_PRIVATE_KEY=0x...
    python examples/llamaindex_tool.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client" / "src"))

from x402_scraper import ScraperClient  # noqa: E402

try:
    from llama_index.core.tools import FunctionTool
except ImportError:  # pragma: no cover
    FunctionTool = None  # type: ignore[misc, assignment]


def build_tools(client: ScraperClient) -> list:
    async def scrape_url(url: str) -> str:
        """Fetch a public URL as stripped Markdown ($0.01 USDC)."""
        data = await client.scrape(url)
        return str(data.get("markdown") or "")

    async def summarize_url(url: str) -> str:
        """Return a 3-bullet summary ($0.02 USDC)."""
        data = await client.summary(url)
        return "\n".join(data.get("summary") or [])

    async def extract_metadata(url: str) -> dict:
        """Extract Open Graph and JSON-LD ($0.01 USDC)."""
        return await client.extract_metadata(url)

    async def parse_pdf(url: str) -> str:
        """Convert a PDF URL to Markdown ($0.05 USDC)."""
        data = await client.parse_pdf(url)
        return str(data.get("markdown") or "")

    async def deep_crawl(url: str, max_depth: int = 2) -> dict:
        """Crawl internal links into a document map ($0.15 USDC)."""
        return await client.deep_crawl(url, max_depth=max_depth)

    fns = [scrape_url, summarize_url, extract_metadata, parse_pdf, deep_crawl]
    if FunctionTool is None:
        return fns
    return [FunctionTool.from_defaults(async_fn=fn) for fn in fns]


async def main() -> None:
    async with ScraperClient() as client:
        tools = build_tools(client)
        print("loaded", len(tools), "LlamaIndex-compatible tools")
        first = tools[0]
        if hasattr(first, "acall"):
            result = await first.acall(url="https://example.com")
            print(str(result)[:400])
        else:
            print((await first("https://example.com"))[:400])


if __name__ == "__main__":
    asyncio.run(main())
