from __future__ import annotations

from app.catalog import PRODUCTS
from app.config import Settings

PUBLIC_HOST = "https://x402-markdown-scraper.onrender.com"


def llms_txt(settings: Settings) -> str:
    lines = [
        "# x402 Markdown Scraper",
        "",
        "> Penny-priced page extraction APIs for AI agents.",
        "> Pay USDC on Base (eip155:8453) over HTTP 402 (x402 v2).",
        "",
        f"Base: {PUBLIC_HOST}",
        f"Pay to: {settings.pay_to()}",
        f"Asset: USDC on Base. Networks: {', '.join(settings.networks())}",
        "",
        "## Free (no payment)",
        "",
        f"- [Health]({PUBLIC_HOST}/health): GET /health — keep-alive liveness",
        f"- [Catalog]({PUBLIC_HOST}/v1/catalog): GET /v1/catalog — machine-readable SKUs",
        f"- [OpenAPI]({PUBLIC_HOST}/openapi.json): GET /openapi.json — request/response schemas",
        f"- [llms.txt]({PUBLIC_HOST}/llms.txt): this file",
        "",
        "## Paid (x402)",
        "",
        "Call a paid path without PAYMENT-SIGNATURE to receive HTTP 402 and PAYMENT-REQUIRED.",
        "Retry the same URL with PAYMENT-SIGNATURE to settle Exact EVM USDC.",
        "",
    ]
    for product in PRODUCTS:
        example_q = "&".join(f"{k}={v}" for k, v in product.query_example.items())
        lines.append(
            f"- [{product.name}]({PUBLIC_HOST}{product.path}?{example_q}): "
            f"{product.method} {product.path}?url= — {product.price} USDC. {product.description}"
        )
    lines.extend(
        [
            "",
            "## Primary SKU",
            "",
            f"GET {PUBLIC_HOST}/v1/scrape?url={{url}} costs $0.01 USDC on Base.",
            "Query: url (uri, required). Optional: pay_for_source (boolean, default true).",
            "",
            "## Optional SKUs",
            "",
            "GET /v1/title $0.001, GET /v1/text $0.005, GET /v1/outline $0.005, GET /v1/links $0.005.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def x402_openapi_extension(settings: Settings) -> dict:
    return {
        "protocol": "x402",
        "x402Version": 2,
        "asset": "USDC",
        "payTo": settings.pay_to(),
        "networks": list(settings.networks()),
        "primaryPrice": "$0.01",
        "primaryPath": "GET /v1/scrape",
        "note": "Unpaid calls to paid paths return HTTP 402 with a PAYMENT-REQUIRED header.",
    }
