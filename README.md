# x402 Web Markdown Scraper

**Pay-per-request web scraping API and MCP web scraper for AI agents.** Turn any URL or PDF into clean Markdown for LLM context windows, and pay per call with **Base USDC micro-payments** over [x402](https://www.x402.org/) (HTTP 402). No account, no API key, no subscription.

- Live service: https://x402-markdown-scraper.onrender.com
- MCP server (Streamable HTTP): `https://x402-markdown-scraper.onrender.com/mcp`
- Python client: `pip install x402-scraper`
- Try it in your browser with MetaMask, Coinbase Wallet, Rabby or WalletConnect: https://x402-markdown-scraper.onrender.com/#playground
- For agents and crawlers: [`/llms.txt`](https://x402-markdown-scraper.onrender.com/llms.txt) · [`/llms-full.txt`](https://x402-markdown-scraper.onrender.com/llms-full.txt) · [`/openapi.json`](https://x402-markdown-scraper.onrender.com/openapi.json) · [`/.well-known/mcp`](https://x402-markdown-scraper.onrender.com/.well-known/mcp)

## Pricing

| SKU | Price (USDC on Base) | HTTP | MCP tool |
|---|---|---|---|
| Page → clean Markdown | $0.01 | `GET/POST /v1/scrape` | `scrape_md` |
| 3-bullet summary + Markdown | $0.02 | `GET/POST /v1/summary` | `page_summary` |
| Metadata (Open Graph, JSON-LD, author, date, word count) | $0.01 | `GET/POST /v1/extract-metadata` | `page_metadata` |
| PDF URL → structured Markdown | $0.05 | `GET/POST /v1/parse-pdf` | `doc_pdf` |
| Same-host crawl, depth 1–3 | $0.15 | `GET/POST /v1/deep-crawl` | `site_crawl` |

Also: `/v1/title` $0.001, `/v1/text` $0.005, `/v1/outline` $0.005, `/v1/links` $0.005.

Payment is the x402 v2 `exact` scheme: an EIP-3009 `TransferWithAuthorization` of USDC on Base (`eip155:8453`, contract `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`). Your agent only signs, so it needs no ETH for gas. If a request fails (bad URL, source error, timeout), the payment is not settled.

## How the x402 scraper works

1. Call a paid path with no payment, for example `GET /v1/scrape?url=https://example.com`.
2. The server answers **402 Payment Required** with a `PAYMENT-REQUIRED` header: base64 JSON with the price, asset, network and `payTo`.
3. Sign the transfer and retry the same request with `PAYMENT-SIGNATURE`.
4. You get the JSON result plus a `PAYMENT-RESPONSE` header carrying the Base transaction hash.

The x402 SDKs and `x402-scraper` do steps 2–3 for you. Raw header payloads and sample responses for every SKU are in [`/llms-full.txt`](https://x402-markdown-scraper.onrender.com/llms-full.txt).

## Quick start

Use a **dedicated wallet** holding a few dollars of USDC on Base, and export its key as `EVM_PRIVATE_KEY`.

### Python (`x402-scraper`)

```python
import asyncio
from x402_scraper import ScraperClient  # pip install x402-scraper

async def main():
    async with ScraperClient() as client:  # reads EVM_PRIVATE_KEY
        page = await client.scrape("https://example.com")
        print(page["markdown"])
        pdf = await client.parse_pdf("https://arxiv.org/pdf/1706.03762")
        crawl = await client.deep_crawl("https://example.com", max_depth=2)

asyncio.run(main())
```

### Python (`httpx` + x402 SDK)

```python
import asyncio, os
from eth_account import Account
from x402 import x402Client
from x402.http.clients import x402HttpxClient  # an httpx.AsyncClient
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client

async def main():
    payer = x402Client()
    register_exact_evm_client(payer, EthAccountSigner(Account.from_key(os.environ["EVM_PRIVATE_KEY"])))
    async with x402HttpxClient(payer) as http:
        r = await http.get("https://x402-markdown-scraper.onrender.com/v1/scrape", params={"url": "https://example.com"})
        print(r.json()["markdown"])

asyncio.run(main())
```

### LangChain tool

```python
from langchain_core.tools import StructuredTool
from x402_scraper import ScraperClient
client = ScraperClient()  # signs USDC on Base with EVM_PRIVATE_KEY
scrape = StructuredTool.from_function(coroutine=client.scrape, name="scrape_url", description="Fetch any URL as clean Markdown ($0.01 USDC on Base).")
```

### LangChain Markdown loader

```python
from langchain_core.documents import Document
from x402_scraper import ScraperClient

async def load_markdown(urls: list[str]) -> list[Document]:
    async with ScraperClient() as client:
        pages = [await client.scrape(url) for url in urls]
    return [Document(page_content=p["markdown"], metadata={"source": p["url"], "title": p.get("title")}) for p in pages]
```

### LlamaIndex tool

```python
from llama_index.core.tools import FunctionTool
from x402_scraper import ScraperClient
client = ScraperClient()  # signs USDC on Base with EVM_PRIVATE_KEY
parse_pdf = FunctionTool.from_defaults(async_fn=client.parse_pdf, name="parse_pdf", description="Convert a PDF URL to structured Markdown ($0.05 USDC on Base).")
```

### MCP web scraper

Point any MCP client at the Streamable HTTP endpoint:

```json
{
  "mcpServers": {
    "x402-markdown-scraper": { "type": "http", "url": "https://x402-markdown-scraper.onrender.com/mcp" }
  }
}
```

`initialize` and `tools/list` are free. `tools/call` is paid with x402's MCP transport: an unpaid call returns `isError: true` with the `PaymentRequired` object in `structuredContent`. Retry with the signed payload in `params._meta["x402/payment"]`, and the receipt comes back in `result._meta["x402/payment-response"]`. Clients without x402 support, such as Claude Desktop and Cursor today, can list the tools but get the payment request instead of a result.

## Limits

Public http(s) only: localhost, cloud-metadata and private IPs are blocked. No JavaScript rendering, logins or CAPTCHA solving. HTML up to 2 MB, PDFs up to 8 MB, 5 redirects, crawl timeout 15 s, crawl depth 1–3 on the same host.

## Self-hosting

```powershell
git clone https://github.com/jacksonfletcher108/x402-markdown-scraper
cd x402-markdown-scraper
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # set PAYMENT_WALLET_ADDRESS to your Base wallet
python -m uvicorn app.main:app --host 0.0.0.0 --port 4021
```

Run the tests with `python test_suite.py`.

Until `PAYMENT_WALLET_ADDRESS` is a real Base address, the shop only accepts Base Sepolia test USDC. A wallet showing "insufficient funds" usually means it's checking mainnet USDC while the shop is still on Sepolia.

### Deploy on Render

1. In Render: **New → Blueprint** (uses `render.yaml`) or **New Web Service** from this repo.
2. Set `PAYMENT_WALLET_ADDRESS` to your Base wallet. Optional: `SOLANA_WALLET_ADDRESS`, `CDP_API_KEY_ID`/`CDP_API_KEY_SECRET`, `WALLETCONNECT_PROJECT_ID`.
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`. Health check: `/health`.
