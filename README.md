# x402 Agent Store

Penny-priced extraction APIs for AI agents. Buyers pay **USDC** over [x402](https://www.x402.org/) (`402` + `PAYMENT-REQUIRED` / `PAYMENT-SIGNATURE`).

## Use it

| SKU | Price (USDC on Base) | Path / MCP tool |
|---|---|---|
| Page → clean Markdown | $0.01 | `/v1/scrape` · `scrape_md` |
| 3-bullet summary + Markdown | $0.02 | `/v1/summary` · `page_summary` |
| Metadata (Open Graph, JSON-LD, author, date) | $0.01 | `/v1/extract-metadata` · `page_metadata` |
| PDF URL → structured Markdown | $0.05 | `/v1/parse-pdf` · `doc_pdf` |
| Same-host crawl, depth 1–3 | $0.15 | `/v1/deep-crawl` · `site_crawl` |

No account or API key: your agent pays from its own Base wallet (USDC only, no ETH for gas).

- **Browser:** try every SKU with a wallet at https://x402-markdown-scraper.onrender.com/#playground
- **Python:** `pip install x402-scraper`, set `EVM_PRIVATE_KEY` to a dedicated wallet holding a few dollars of USDC.

```python
# LangChain
from langchain_core.tools import StructuredTool
from x402_scraper import ScraperClient
client = ScraperClient()  # signs USDC on Base with EVM_PRIVATE_KEY
scrape = StructuredTool.from_function(coroutine=client.scrape, name="scrape_url", description="Fetch any URL as clean Markdown ($0.01 USDC on Base).")
```

```python
# LlamaIndex
from llama_index.core.tools import FunctionTool
from x402_scraper import ScraperClient
client = ScraperClient()  # signs USDC on Base with EVM_PRIVATE_KEY
parse_pdf = FunctionTool.from_defaults(async_fn=client.parse_pdf, name="parse_pdf", description="Convert a PDF URL to structured Markdown ($0.05 USDC on Base).")
```

- **MCP:** Streamable HTTP at `https://x402-markdown-scraper.onrender.com/mcp`. Any client can `initialize` and `tools/list`; paid `tools/call` needs an x402-aware MCP client (payment in `params._meta["x402/payment"]`). Clients without x402 support, such as Claude Desktop and Cursor today, receive the `PaymentRequired` object instead of a result.
- **Agents:** [`/llms.txt`](https://x402-markdown-scraper.onrender.com/llms.txt) · [`/openapi.json`](https://x402-markdown-scraper.onrender.com/openapi.json) · [`/.well-known/mcp`](https://x402-markdown-scraper.onrender.com/.well-known/mcp)

## Why Coinbase Wallet said insufficient funds

Coinbase Wallet USDC is **Base mainnet**. This shop stayed on **Base Sepolia** while `X402_PAY_TO` was a placeholder, so the wallet checked the wrong token and reported no balance.

Set a real Base address in `.env`, restart, and the shop advertises **eip155:8453** (mainnet USDC) plus Sepolia.

## Setup

```powershell
cd $HOME\x402-markdown-scraper
.\.venv\Scripts\Activate.ps1
copy .env.example .env
```

Edit `.env` → `X402_PAY_TO`. Then:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 4021
```

Open in **Chrome or Edge** (not Cursor’s browser): http://127.0.0.1:4021

## Free vs paid

| Path | Price | Notes |
| --- | --- | --- |
| `GET /health` | free | Liveness + settlement flag |
| `GET /v1/catalog` | free | Machine catalog for agents |
| `GET /v1/scrape?url=` | $0.01 | Markdown |
| `GET /v1/title?url=` | $0.001 | Title + description |
| `GET /v1/text?url=` | $0.005 | Visible text |
| `GET /v1/outline?url=` | $0.005 | h1–h3 |
| `GET /v1/links?url=` | $0.005 | Outbound links |

Agents: `GET /v1/catalog`, then call a paid path, read `PAYMENT-REQUIRED`, retry with `PAYMENT-SIGNATURE`.

## Deploy on Render

1. Push this repo to GitHub.
2. In Render: **New → Blueprint** (uses `render.yaml`) or **New Web Service** from the repo.
3. Set `X402_PAY_TO` to your Base wallet (`0xf84EF3669eA39b87D4a850B4510f7aCBAC19be5f`).
4. After deploy, open `https://<service>.onrender.com/health`, then pay `https://<service>.onrender.com/v1/title?url=https://example.com` from a second network (phone).

The start command is `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`. Health check path: `/health`. Python **3.12** (`runtime.txt`).

