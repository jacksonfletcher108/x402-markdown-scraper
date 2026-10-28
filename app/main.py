from app.compat import install_optional_stubs

install_optional_stubs()

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

from app.catalog import PRODUCTS, public_catalog
from app.config import get_settings
from app.discovery import ai_plugin_manifest, llms_txt, mcp_manifest, x402_openapi_extension
from app.models import (
    LinksResponse,
    MetadataResponse,
    OutlineResponse,
    ScrapeRequest,
    ScrapeResponse,
    SummaryResponse,
    TextResponse,
    TitleResponse,
)
from app.payments import paid_routes, paywall_is_testnet, resource_server, settlement_ready
from app.scraper import ScrapeError, fetch_page
from app.summarize import executive_summary
from app.x402_log import X402TraceMiddleware, attach_payment_logs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("x402.shop")

settings = get_settings()
log.info(
    "x402 shop starting pay_to=%s networks=%s facilitator=%s",
    settings.pay_to(),
    settings.networks(),
    settings.facilitator_kind(),
)

app = FastAPI(
    title="x402 Markdown Scraper",
    description=(
        "Converts any web article URL into clean, stripped Markdown for AI context windows. "
        "GET /v1/scrape $0.01, GET /v1/summary $0.02, GET /v1/extract-metadata $0.01 USDC on Base via x402."
    ),
    version="0.4.0",
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


def _storefront_html() -> str:
    ready = settlement_ready(settings)
    warning = ""
    if not ready:
        warning = """
        <p style="padding:1rem;background:#fef3c7;border-radius:8px">
          <strong>Why Coinbase Wallet says insufficient funds:</strong>
          your USDC is on <em>Base mainnet</em>. This shop is still on
          <em>Base Sepolia</em> because <code>X402_PAY_TO</code> is a placeholder.
          Put your Base wallet in <code>PAYMENT_WALLET_ADDRESS</code> and restart to accept real $0.01 USDC.
        </p>
        """
    items = "\n".join(
        f"<li><a href=\"{product.path}?url=https://example.com\"><strong>{product.price}</strong> {product.name}</a> — {product.description}</li>"
        for product in PRODUCTS
    )
    networks = ", ".join(settings.networks())
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>x402 Agent Store</title>
</head>
<body style="font-family:system-ui;max-width:44rem;margin:3rem auto;padding:0 1rem;line-height:1.5">
  <h1>x402 Agent Store</h1>
  <p>Penny SKUs for AI agents. Pay USDC over HTTP 402. Free catalog: <a href="/v1/catalog"><code>GET /v1/catalog</code></a>.</p>
  {warning}
  <p>Networks: <code>{networks}</code>. Pay to <code>{settings.pay_to()}</code>.</p>
  <p>Use <strong>Chrome or Edge</strong> for Coinbase Smart Wallet (not an embedded browser).</p>
  <h2>Products</h2>
  <ul>{items}</ul>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _storefront_html()


@app.get("/health")
async def health() -> dict[str, str]:
    """Unpaid keep-alive probe. Do not put work here."""
    return {"status": "ok"}


@app.get("/llms.txt", response_class=PlainTextResponse, include_in_schema=True)
async def llms() -> str:
    return llms_txt(settings)


@app.get("/.well-known/mcp")
@app.get("/.well-known/mcp.json")
async def well_known_mcp() -> dict:
    return mcp_manifest(settings)


@app.get("/.well-known/ai-plugin.json")
async def well_known_ai_plugin() -> dict:
    return ai_plugin_manifest(settings)


@app.get("/v1/catalog")
async def catalog() -> dict:
    return public_catalog(settings.pay_to(), settings.networks(), settlement_ready(settings))


async def _page(url: str, pay_for_source: bool = True):
    try:
        return await fetch_page(url, settings, pay_for_source=pay_for_source)
    except ScrapeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("unexpected fetch failure")
        raise HTTPException(status_code=502, detail="Failed to fetch or parse the page") from exc


@app.get("/v1/scrape", response_model=ScrapeResponse)
@app.get("/scrape", response_model=ScrapeResponse)
async def scrape_get(
    url: str = Query(..., description="Public http(s) URL to fetch."),
    pay_for_source: bool = Query(True),
) -> ScrapeResponse:
    page = await _page(url, pay_for_source)
    return ScrapeResponse(
        url=page.url,
        title=page.title,
        markdown=page.markdown,
        source_status=page.source_status,
        paid_source=page.paid_source,
    )


@app.post("/v1/scrape", response_model=ScrapeResponse)
@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_post(body: ScrapeRequest) -> ScrapeResponse:
    page = await _page(str(body.url), body.pay_for_source)
    return ScrapeResponse(
        url=page.url,
        title=page.title,
        markdown=page.markdown,
        source_status=page.source_status,
        paid_source=page.paid_source,
    )


@app.get("/v1/summary", response_model=SummaryResponse)
async def summary_get(url: str = Query(..., description="Public http(s) URL to fetch.")) -> SummaryResponse:
    page = await _page(url)
    return SummaryResponse(
        url=page.url,
        title=page.title,
        summary=executive_summary(page.text, page.title, page.headings),
        markdown=page.markdown,
        source_status=page.source_status,
    )


@app.post("/v1/summary", response_model=SummaryResponse)
async def summary_post(body: ScrapeRequest) -> SummaryResponse:
    page = await _page(str(body.url), body.pay_for_source)
    return SummaryResponse(
        url=page.url,
        title=page.title,
        summary=executive_summary(page.text, page.title, page.headings),
        markdown=page.markdown,
        source_status=page.source_status,
    )


@app.get("/v1/extract-metadata", response_model=MetadataResponse)
async def metadata_get(
    url: str = Query(..., description="Public http(s) URL to fetch."),
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
    )


@app.post("/v1/extract-metadata", response_model=MetadataResponse)
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
    )


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


_PAID_OPENAPI_PATHS = {
    "/v1/scrape": "$0.01",
    "/scrape": "$0.01",
    "/v1/summary": "$0.02",
    "/v1/extract-metadata": "$0.01",
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
