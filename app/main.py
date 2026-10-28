from app.compat import install_optional_stubs

install_optional_stubs()

import html
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.paywall import create_paywall, evm_paywall
from x402.http.types import PaywallConfig

from app.cache import cache
from app.catalog import PRODUCTS, public_catalog
from app.config import get_settings
from app.crawl import deep_crawl
from app.discovery import ai_plugin_manifest, llms_txt, mcp_manifest, x402_openapi_extension
from app.mcp_server import McpServer
from app.playground import PLAYGROUND_CSS, playground_html
from app.models import (
    CrawlRequest,
    CrawlResponse,
    LinksResponse,
    MetadataResponse,
    OutlineResponse,
    PdfParseResponse,
    ScrapeRequest,
    ScrapeResponse,
    SummaryResponse,
    TextResponse,
    TitleResponse,
)
from app.payments import paid_routes, paywall_is_testnet, resource_server, settlement_ready
from app.pdf import pdf_bytes_to_markdown
from app.scraper import ScrapeError, fetch_bytes, fetch_page
from app.summarize import executive_summary
from app.x402_log import X402TraceMiddleware, attach_payment_logs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("x402.shop")

settings = get_settings()
cache.ttl_seconds = settings.cache_ttl_seconds
log.info(
    "x402 shop starting pay_to=%s networks=%s facilitator=%s",
    settings.pay_to(),
    settings.networks(),
    settings.facilitator_kind(),
)

_OPENAPI_TAGS = [
    {"name": "Discovery", "description": "Unpaid machine-readable catalog, health, and agent manifests."},
    {"name": "Paid SKUs", "description": "x402 v2 Exact USDC on Base (eip155:8453). Unpaid calls return HTTP 402."},
]

app = FastAPI(
    title="x402 Markdown Scraper",
    description=(
        "Penny SKUs for AI agents: URL to Markdown, summary, metadata, PDF parse, and deep crawl. "
        "Pay Exact USDC on Base (`eip155:8453`) over HTTP 402 (x402 v2). "
        "Unpaid probes return `PAYMENT-REQUIRED`; retry with `PAYMENT-SIGNATURE`. "
        "Featured prices: `/v1/scrape` $0.01, `/v1/summary` $0.02, `/v1/extract-metadata` $0.01, "
        "`/v1/parse-pdf` $0.05, `/v1/deep-crawl` $0.15."
    ),
    version="0.5.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=_OPENAPI_TAGS,
    swagger_ui_parameters={"displayRequestDuration": True, "tryItOutEnabled": True},
)

server = attach_payment_logs(resource_server(settings))
routes = paid_routes(settings)
testnet = paywall_is_testnet(settings)
paywall = (
    create_paywall()
    .with_network(evm_paywall)
    .with_config(app_name="x402 Agent Store", testnet=testnet)
    .build()
)


class CoinbaseWalletCompatMiddleware(BaseHTTPMiddleware):
    """HEAD must be 200 so Coinbase Wallet can probe the page. Do not set COOP."""

    async def dispatch(self, request: Request, call_next):
        if request.method == "HEAD":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Expose-Headers": (
                        "PAYMENT-REQUIRED, PAYMENT-RESPONSE, PAYMENT-SIGNATURE"
                    ),
                    "Cache-Control": "no-store",
                },
            )
        return await call_next(request)


app.add_middleware(
    PaymentMiddlewareASGI,
    routes=routes,
    server=server,
    paywall_provider=paywall,
    paywall_config=PaywallConfig(app_name="x402 Agent Store", testnet=testnet),
)
app.add_middleware(X402TraceMiddleware)
_X402_HEADERS = [
    "PAYMENT-REQUIRED",
    "PAYMENT-RESPONSE",
    "PAYMENT-SIGNATURE",
    "X-PAYMENT",
    "X-PAYMENT-RESPONSE",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*", *_X402_HEADERS, "Content-Type", "Accept"],
    expose_headers=_X402_HEADERS,
)
app.add_middleware(CoinbaseWalletCompatMiddleware)


_FEATURED_SKUS = ("scrape.md", "page.summary", "page.metadata", "doc.pdf", "site.crawl")
_PUBLIC_HOST = "https://x402-markdown-scraper.onrender.com"


def _sku_params(product) -> str:
    keys = list((product.query_schema or {}).get("properties") or {"url": {}})
    required = set((product.query_schema or {}).get("required") or ["url"])
    parts = []
    for key in keys:
        mark = "required" if key in required else "optional"
        parts.append(f"<code>{html.escape(key)}</code> <span class=\"muted\">{mark}</span>")
    return " · ".join(parts) or "<code>url</code> <span class=\"muted\">required</span>"


def _storefront_html() -> str:
    ready = settlement_ready(settings)
    pay_to = html.escape(settings.pay_to())
    badge = "EVM / Base USDC Active" if ready else "Base Sepolia — set PAYMENT_WALLET_ADDRESS"
    badge_class = "ok" if ready else "warn"
    warning = ""
    if not ready:
        warning = (
            "<div class=\"banner\">This shop is on Base Sepolia until "
            "<code>PAYMENT_WALLET_ADDRESS</code> is a real Base wallet. "
            "Mainnet USDC will not settle here yet.</div>"
        )
    cards = []
    for product in PRODUCTS:
        if product.sku not in _FEATURED_SKUS:
            continue
        cards.append(
            "<article class=\"card\">"
            f"<div class=\"price\">{html.escape(product.price)} USDC</div>"
            f"<h3>{html.escape(product.name)}</h3>"
            f"<p class=\"path\"><code>GET</code> <code>POST</code> {html.escape(product.path)}</p>"
            f"<p>{html.escape(product.description)}</p>"
            f"<p class=\"params\">Params: {_sku_params(product)}</p>"
            f"<a class=\"try\" href=\"{html.escape(product.path)}?url=https://example.com\">Open unpaid 402</a>"
            "</article>"
        )
    python_src = html.escape(
        "import os\n"
        "import httpx\n"
        "from eth_account import Account\n"
        "from x402 import x402Client\n"
        "from x402.http.clients import x402HttpxClient\n"
        "from x402.mechanisms.evm import EthAccountSigner\n"
        "from x402.mechanisms.evm.exact.register import register_exact_evm_client\n"
        "\n"
        f'URL = "{_PUBLIC_HOST}/v1/scrape"\n'
        'PARAMS = {"url": "https://example.com"}\n'
        "\n"
        "# 1) Unpaid probe — HTTP 402 + PAYMENT-REQUIRED (x402 v2, eip155:8453)\n"
        "probe = httpx.get(URL, params=PARAMS)\n"
        'print(probe.status_code, probe.headers.get("PAYMENT-REQUIRED", "")[:64])\n'
        "\n"
        "# 2) Settle Exact USDC on Base with the x402 client SDK\n"
        'account = Account.from_key(os.environ["EVM_PRIVATE_KEY"])\n'
        "client = x402Client()\n"
        "register_exact_evm_client(client, EthAccountSigner(account))\n"
        "with x402HttpxClient(client) as http:\n"
        "    paid = http.get(URL, params=PARAMS)\n"
        '    print(paid.status_code, paid.json().get("sku"))\n'
    )
    js_src = html.escape(
        f'const url = "{_PUBLIC_HOST}/v1/scrape?url=https://example.com";\n'
        "const unpaid = await fetch(url);\n"
        'const challenge = unpaid.headers.get("PAYMENT-REQUIRED");\n'
        "console.log(unpaid.status, challenge);\n"
        "// 402: decode PAYMENT-REQUIRED, sign Exact USDC on Base (eip155:8453)\n"
        "// with an x402 EVM client, then retry:\n"
        "const paid = await fetch(url, {\n"
        '  headers: { "PAYMENT-SIGNATURE": signature },\n'
        "});\n"
        "console.log(paid.status, await paid.json());\n"
    )
    curl_src = html.escape(
        f'curl -i "{_PUBLIC_HOST}/v1/scrape?url=https://example.com"\n'
        "# HTTP/2 402 Payment Required\n"
        "# PAYMENT-REQUIRED: eyJ...   (x402 v2 Exact USDC, eip155:8453)\n"
        "# Retry the same URL with header PAYMENT-SIGNATURE from the x402 SDK.\n"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>x402 Agent Store</title>
  <style>
    :root {{ --bg:#f8fafc; --ink:#0f172a; --muted:#475569; --line:#e2e8f0; --accent:#0f766e; --card:#fff; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font:16px/1.5 ui-sans-serif,system-ui,sans-serif; color:var(--ink); background:var(--bg); }}
    header, main {{ max-width:1080px; margin:0 auto; padding:1.25rem 1rem; }}
    header {{ display:flex; flex-wrap:wrap; gap:1rem; justify-content:space-between; align-items:flex-start; }}
    h1 {{ margin:0 0 .25rem; font-size:1.65rem; }}
    .muted {{ color:var(--muted); }}
    .wallet {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:.75rem 1rem; max-width:28rem; }}
    .wallet code {{ font-size:.82rem; word-break:break-all; }}
    .badge {{ display:inline-block; margin-top:.4rem; padding:.15rem .55rem; border-radius:999px; font-size:.78rem; font-weight:600; }}
    .badge.ok {{ background:#d1fae5; color:#065f46; }}
    .badge.warn {{ background:#fef3c7; color:#92400e; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:.5rem; margin:0 0 1.25rem; }}
    .nav a {{ background:var(--ink); color:#fff; text-decoration:none; padding:.45rem .8rem; border-radius:8px; font-size:.9rem; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:.9rem; }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:1rem; display:flex; flex-direction:column; gap:.4rem; }}
    .price {{ font-weight:700; color:var(--accent); }}
    .card h3 {{ margin:0; font-size:1.05rem; }}
    .path code {{ background:#f1f5f9; padding:.1rem .35rem; border-radius:4px; font-size:.8rem; }}
    .try {{ margin-top:auto; color:var(--accent); font-weight:600; }}
    .banner {{ background:#fef3c7; border-radius:8px; padding:.75rem 1rem; margin-bottom:1rem; }}
    .tabs {{ display:flex; gap:.35rem; margin:1rem 0 .5rem; }}
    .tabs button {{ border:1px solid var(--line); background:#fff; border-radius:8px; padding:.35rem .7rem; cursor:pointer; }}
    .tabs button.active {{ background:var(--ink); color:#fff; }}
    pre {{ background:#0f172a; color:#e2e8f0; padding:1rem; border-radius:12px; overflow:auto; font-size:.82rem; display:none; }}
    pre.active {{ display:block; }}
    .copy {{ margin-left:.5rem; }}
{PLAYGROUND_CSS}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>x402 Agent Store</h1>
      <p class="muted">Human portal and agent gateway. Exact USDC on Base via HTTP 402.</p>
    </div>
    <div class="wallet">
      <div class="muted">Base payout address</div>
      <code id="pay-to">{pay_to}</code>
      <div class="badge {badge_class}">{html.escape(badge)}</div>
    </div>
  </header>
  <main>
    {warning}
    <nav class="nav" aria-label="Discovery">
      <a href="#playground">Playground</a>
      <a href="/docs">Swagger /docs</a>
      <a href="/llms.txt">llms.txt</a>
      <a href="/openapi.json">openapi.json</a>
      <a href="/.well-known/mcp">/.well-known/mcp</a>
    </nav>
    <h2>Featured SKUs</h2>
    <div class="grid">{"".join(cards)}</div>
    {playground_html(PRODUCTS)}
    <h2>Pay a 402 from a client</h2>
    <p class="muted">Probe unpaid, read <code>PAYMENT-REQUIRED</code>, settle Exact USDC on <code>eip155:8453</code>, retry with <code>PAYMENT-SIGNATURE</code>.</p>
    <div class="tabs">
      <button type="button" class="active" data-tab="python">Python (httpx)</button>
      <button type="button" data-tab="js">JavaScript (fetch)</button>
      <button type="button" data-tab="curl">cURL</button>
      <button type="button" class="copy" id="copy-btn">Copy</button>
    </div>
    <pre class="active" id="python">{python_src}</pre>
    <pre id="js">{js_src}</pre>
    <pre id="curl">{curl_src}</pre>
  </main>
  <script>
    const tabs = document.querySelectorAll(".tabs button[data-tab]");
    const panes = {{ python: document.getElementById("python"), js: document.getElementById("js"), curl: document.getElementById("curl") }};
    let current = "python";
    tabs.forEach((btn) => btn.addEventListener("click", () => {{
      current = btn.getAttribute("data-tab");
      tabs.forEach((b) => b.classList.toggle("active", b === btn));
      Object.entries(panes).forEach(([id, el]) => el.classList.toggle("active", id === current));
    }}));
    document.getElementById("copy-btn").addEventListener("click", async () => {{
      await navigator.clipboard.writeText(panes[current].innerText);
    }});
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, tags=["Discovery"], summary="Human developer portal")
async def index() -> str:
    return _storefront_html()


@app.get("/health", tags=["Discovery"], summary="Liveness probe")
async def health() -> dict[str, str]:
    """Unpaid keep-alive probe. Do not put work here."""
    return {"status": "ok"}


@app.get("/llms.txt", response_class=PlainTextResponse, include_in_schema=True, tags=["Discovery"], summary="llms.txt agent digest")
async def llms() -> str:
    """Unpaid. Lists SKUs and Exact USDC prices for language-model crawlers."""
    return llms_txt(settings)


@app.get("/.well-known/mcp", tags=["Discovery"], summary="MCP tool card")
@app.get("/.well-known/mcp.json", tags=["Discovery"], include_in_schema=False)
async def well_known_mcp() -> dict:
    """Unpaid machine-readable tool list for MCP / x402 agents."""
    return mcp_manifest(settings)


@app.get("/.well-known/ai-plugin.json")
async def well_known_ai_plugin() -> dict:
    return ai_plugin_manifest(settings)


@app.get("/v1/catalog", tags=["Discovery"], summary="Machine-readable SKU catalog")
async def catalog() -> dict:
    return public_catalog(
        settings.pay_to(),
        settings.networks(),
        settlement_ready(settings),
        pay_to_solana=settings.solana_pay_to() or None,
    )


async def _page(url: str, pay_for_source: bool = True):
    key = f"page:{url}"
    hit = cache.get(key)
    if hit is not None:
        hit._from_cache = True
        return hit
    try:
        page = await fetch_page(url, settings, pay_for_source=pay_for_source)
    except ScrapeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("unexpected fetch failure")
        raise HTTPException(status_code=502, detail="Failed to fetch or parse the page") from exc
    page._from_cache = False
    cache.set(key, page)
    return page


def _cached(page) -> bool:
    return bool(getattr(page, "_from_cache", False))


@app.get(
    "/v1/scrape",
    response_model=ScrapeResponse,
    tags=["Paid SKUs"],
    summary="Scrape URL to Markdown ($0.01 USDC)",
    description="Fetches a public page and returns stripped Markdown. Unpaid calls return HTTP 402 with x402 v2 Exact USDC on Base (`eip155:8453`).",
)
@app.get("/scrape", response_model=ScrapeResponse, include_in_schema=False)
async def scrape_get(
    url: str = Query(..., description="Public http(s) URL to fetch.", examples=["https://example.com"]),
    pay_for_source: bool = Query(True),
) -> ScrapeResponse:
    page = await _page(url, pay_for_source)
    return ScrapeResponse(
        url=page.url,
        title=page.title,
        markdown=page.markdown,
        source_status=page.source_status,
        paid_source=page.paid_source,
        cached=_cached(page),
    )


@app.post(
    "/v1/scrape",
    response_model=ScrapeResponse,
    tags=["Paid SKUs"],
    summary="Scrape URL to Markdown ($0.01 USDC)",
)
@app.post("/scrape", response_model=ScrapeResponse, include_in_schema=False)
async def scrape_post(body: ScrapeRequest) -> ScrapeResponse:
    page = await _page(str(body.url), body.pay_for_source)
    return ScrapeResponse(
        url=page.url,
        title=page.title,
        markdown=page.markdown,
        source_status=page.source_status,
        paid_source=page.paid_source,
        cached=_cached(page),
    )


@app.get(
    "/v1/summary",
    response_model=SummaryResponse,
    tags=["Paid SKUs"],
    summary="Executive summary ($0.02 USDC)",
    description="Returns three bullets plus Markdown. x402 v2 Exact USDC on Base.",
)
async def summary_get(
    url: str = Query(..., description="Public http(s) URL to fetch.", examples=["https://example.com"]),
) -> SummaryResponse:
    page = await _page(url)
    return SummaryResponse(
        url=page.url,
        title=page.title,
        summary=executive_summary(page.text, page.title, page.headings),
        markdown=page.markdown,
        source_status=page.source_status,
        cached=_cached(page),
    )


@app.post("/v1/summary", response_model=SummaryResponse, tags=["Paid SKUs"], summary="Executive summary ($0.02 USDC)")
async def summary_post(body: ScrapeRequest) -> SummaryResponse:
    page = await _page(str(body.url), body.pay_for_source)
    return SummaryResponse(
        url=page.url,
        title=page.title,
        summary=executive_summary(page.text, page.title, page.headings),
        markdown=page.markdown,
        source_status=page.source_status,
        cached=_cached(page),
    )


@app.get(
    "/v1/extract-metadata",
    response_model=MetadataResponse,
    tags=["Paid SKUs"],
    summary="Extract page metadata ($0.01 USDC)",
)
async def metadata_get(
    url: str = Query(..., description="Public http(s) URL to fetch.", examples=["https://example.com"]),
) -> MetadataResponse:
    page = await _page(url)
    return MetadataResponse(
        url=page.url,
        title=page.title,
        description=page.description,
        author=page.author,
        published=page.published,
        opengraph=page.opengraph,
        json_ld=page.json_ld,
        word_count=page.word_count,
        reading_time_minutes=page.reading_time_minutes,
        source_status=page.source_status,
        cached=_cached(page),
    )


@app.post("/v1/extract-metadata", response_model=MetadataResponse, tags=["Paid SKUs"], summary="Extract page metadata ($0.01 USDC)")
async def metadata_post(body: ScrapeRequest) -> MetadataResponse:
    page = await _page(str(body.url), body.pay_for_source)
    return MetadataResponse(
        url=page.url,
        title=page.title,
        description=page.description,
        author=page.author,
        published=page.published,
        opengraph=page.opengraph,
        json_ld=page.json_ld,
        word_count=page.word_count,
        reading_time_minutes=page.reading_time_minutes,
        source_status=page.source_status,
        cached=_cached(page),
    )


async def _parse_pdf(url: str) -> PdfParseResponse:
    key = f"pdf:{url}"
    hit = cache.get(key)
    if hit is not None:
        hit.cached = True
        return hit
    try:
        data, final_url, status = await fetch_bytes(url, settings, max_bytes=settings.max_pdf_bytes)
        markdown, page_count = pdf_bytes_to_markdown(data, final_url)
    except ScrapeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("unexpected pdf parse failure")
        raise HTTPException(status_code=502, detail="Failed to fetch or parse the PDF") from exc
    payload = PdfParseResponse(
        url=final_url,
        page_count=page_count,
        markdown=markdown,
        cached=False,
        source_status=status,
    )
    cache.set(key, payload)
    return payload


@app.get(
    "/v1/parse-pdf",
    response_model=PdfParseResponse,
    tags=["Paid SKUs"],
    summary="Parse PDF to Markdown ($0.05 USDC)",
)
async def parse_pdf_get(
    url: str = Query(..., description="Public http(s) PDF URL.", examples=["https://example.com/paper.pdf"]),
) -> PdfParseResponse:
    return await _parse_pdf(url)


@app.post("/v1/parse-pdf", response_model=PdfParseResponse, tags=["Paid SKUs"], summary="Parse PDF to Markdown ($0.05 USDC)")
async def parse_pdf_post(body: ScrapeRequest) -> PdfParseResponse:
    return await _parse_pdf(str(body.url))


async def _crawl(url: str, max_depth: int) -> CrawlResponse:
    depth = max(1, min(max_depth, 3))
    key = f"crawl:{url}:{depth}"
    hit = cache.get(key)
    if hit is not None:
        hit.cached = True
        return hit
    try:
        raw = await deep_crawl(url, depth, settings)
    except ScrapeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("unexpected crawl failure")
        raise HTTPException(status_code=502, detail="Failed to crawl the site") from exc
    payload = CrawlResponse(cached=False, **raw)
    cache.set(key, payload)
    return payload


@app.get(
    "/v1/deep-crawl",
    response_model=CrawlResponse,
    tags=["Paid SKUs"],
    summary="Deep site crawl ($0.15 USDC)",
    description="Same-host BFS, max_depth 1-3. x402 v2 Exact USDC on Base.",
)
async def crawl_get(
    url: str = Query(..., description="Public http(s) starting URL.", examples=["https://example.com"]),
    max_depth: int = Query(2, ge=1, le=3, description="Internal link depth, 1-3."),
) -> CrawlResponse:
    return await _crawl(url, max_depth)


@app.post("/v1/deep-crawl", response_model=CrawlResponse, tags=["Paid SKUs"], summary="Deep site crawl ($0.15 USDC)")
async def crawl_post(body: CrawlRequest) -> CrawlResponse:
    return await _crawl(str(body.url), body.max_depth)


@app.get("/v1/title", response_model=TitleResponse)
async def title_get(url: str = Query(..., description="Public http(s) URL to fetch.")) -> TitleResponse:
    page = await _page(url)
    return TitleResponse(
        url=page.url,
        title=page.title,
        description=page.description,
        source_status=page.source_status,
    )


@app.get("/v1/text", response_model=TextResponse)
async def text_get(url: str = Query(..., description="Public http(s) URL to fetch.")) -> TextResponse:
    page = await _page(url)
    return TextResponse(url=page.url, text=page.text, source_status=page.source_status)


@app.get("/v1/outline", response_model=OutlineResponse)
async def outline_get(url: str = Query(..., description="Public http(s) URL to fetch.")) -> OutlineResponse:
    page = await _page(url)
    return OutlineResponse(url=page.url, headings=page.headings, source_status=page.source_status)


@app.get("/v1/links", response_model=LinksResponse)
async def links_get(url: str = Query(..., description="Public http(s) URL to fetch.")) -> LinksResponse:
    page = await _page(url)
    return LinksResponse(url=page.url, links=page.links, source_status=page.source_status)


mcp = McpServer(server, settings, _PUBLIC_HOST)
_MCP_HANDLERS = {
    "scrape.md": lambda args: scrape_get(url=args["url"], pay_for_source=True),
    "page.summary": lambda args: summary_get(url=args["url"]),
    "page.metadata": lambda args: metadata_get(url=args["url"]),
    "doc.pdf": lambda args: parse_pdf_get(url=args["url"]),
    "site.crawl": lambda args: _crawl(args["url"], _depth(args.get("max_depth", 2))),
}
for _product in PRODUCTS:
    if _product.sku in _MCP_HANDLERS:
        mcp.tool(_product, _MCP_HANDLERS[_product.sku])


def _depth(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="max_depth must be an integer 1-3") from None


@app.post("/mcp", tags=["Discovery"], summary="MCP Streamable HTTP endpoint (tool calls paid via x402)")
async def mcp_post(request: Request) -> Response:
    """JSON-RPC over Streamable HTTP. tools/call is paid with x402 in params._meta["x402/payment"]."""
    return await mcp.handle(request)


@app.api_route("/mcp", methods=["GET", "DELETE"], include_in_schema=False)
async def mcp_no_stream() -> Response:
    # Stateless server: no SSE stream and no sessions to delete.
    return Response(status_code=405, headers={"Allow": "POST"})


_PAID_OPENAPI_PATHS = {
    "/v1/scrape": "$0.01",
    "/scrape": "$0.01",
    "/v1/summary": "$0.02",
    "/v1/extract-metadata": "$0.01",
    "/v1/parse-pdf": "$0.05",
    "/v1/deep-crawl": "$0.15",
    "/v1/title": "$0.001",
    "/v1/text": "$0.005",
    "/v1/outline": "$0.005",
    "/v1/links": "$0.005",
}


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema["info"]["x-x402"] = x402_openapi_extension(settings)
    payment_required = {
        "description": "Payment required. Read PAYMENT-REQUIRED and retry with PAYMENT-SIGNATURE.",
        "headers": {
            "PAYMENT-REQUIRED": {
                "schema": {"type": "string"},
                "description": "Base64 x402 PaymentRequired (v2).",
            }
        },
    }
    for path, price in _PAID_OPENAPI_PATHS.items():
        item = schema.get("paths", {}).get(path)
        if not item:
            continue
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            operation.setdefault("responses", {})["402"] = payment_required
            operation["x-x402"] = {
                "price": price,
                "asset": "USDC",
                "network": "eip155:8453",
                "scheme": "exact",
            }
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
