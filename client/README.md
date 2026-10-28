# x402-scraper

Lightweight **httpx** client for [x402 Markdown Scraper](https://x402-markdown-scraper.onrender.com). It wraps all five featured SKUs and settles **x402 v2 Exact USDC** on Base (`eip155:8453`). On HTTP 402 the x402 SDK builds the EIP-3009 transfer authorization, sets `PAYMENT-SIGNATURE`, and retries.

## Install

```bash
pip install x402-scraper
```

Python 3.12 or 3.13 is recommended for EVM signing wheels.

## Usage

```python
import asyncio
import os

from x402_scraper import ScraperClient

os.environ["EVM_PRIVATE_KEY"] = "0x..."  # Base wallet that holds USDC


async def main() -> None:
    async with ScraperClient() as client:
        page = await client.scrape("https://example.com")       # $0.01
        brief = await client.summary("https://example.com")     # $0.02
        meta = await client.extract_metadata("https://example.com")  # $0.01
        pdf = await client.parse_pdf("https://example.com/paper.pdf")  # $0.05
        site = await client.deep_crawl("https://example.com", max_depth=2)  # $0.15
        print(page["sku"], brief["summary"], meta["word_count"], pdf["page_count"], site["page_count"])


asyncio.run(main())
```

Without `EVM_PRIVATE_KEY`, unpaid calls raise `ScraperError` with `status_code=402` so you can inspect `PAYMENT-REQUIRED` yourself.

## SKUs

| Method | Path | Price |
|---|---|---|
| GET/POST | `/v1/scrape` | $0.01 USDC |
| GET/POST | `/v1/summary` | $0.02 USDC |
| GET/POST | `/v1/extract-metadata` | $0.01 USDC |
| GET/POST | `/v1/parse-pdf` | $0.05 USDC |
| GET/POST | `/v1/deep-crawl` | $0.15 USDC |

Network: `eip155:8453`. Asset: Base USDC. Scheme: `exact`.

Shop docs: https://x402-markdown-scraper.onrender.com/docs
