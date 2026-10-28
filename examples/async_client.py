"""Raw asyncio integration with ScraperClient.

    pip install -e ./client
    set EVM_PRIVATE_KEY=0x...
    python examples/async_client.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client" / "src"))

from x402_scraper import ScraperClient  # noqa: E402

URL = os.environ.get("DEMO_URL", "https://example.com")


async def main() -> None:
    async with ScraperClient() as client:
        page = await client.scrape(URL)
        print("scrape", page.get("sku"), (page.get("title") or "")[:80])
        brief = await client.summary(URL)
        print("summary", brief.get("summary"))
        meta = await client.extract_metadata(URL)
        print("metadata", meta.get("word_count"), "words")
        site = await client.deep_crawl(URL, max_depth=1)
        print("crawl", site.get("page_count"), "pages")


if __name__ == "__main__":
    asyncio.run(main())
