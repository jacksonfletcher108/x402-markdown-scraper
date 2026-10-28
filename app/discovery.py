from __future__ import annotations

from app.catalog import PRODUCTS, SCRAPE_DESCRIPTION, SCRAPE_OUTPUT_SCHEMA, URL_INPUT_SCHEMA
from app.config import Settings

PUBLIC_HOST = "https://x402-markdown-scraper.onrender.com"


def llms_txt(settings: Settings) -> str:
    lines = [
        "# x402 Markdown Scraper",
        "",
        "> Converts any web article URL into clean, stripped Markdown for AI context windows.",
        "> Pay $0.01 USDC on Base (eip155:8453) over HTTP 402 (x402 v2). Category: Data.",
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
        f"- [MCP]({PUBLIC_HOST}/.well-known/mcp): GET /.well-known/mcp — agent tool card",
        f"- [Plugin]({PUBLIC_HOST}/.well-known/ai-plugin.json): GET /.well-known/ai-plugin.json",
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


def mcp_manifest(settings: Settings) -> dict:
    scrape = next(product for product in PRODUCTS if product.sku == "scrape.md")
    return {
        "name": "x402-markdown-scraper",
        "description": SCRAPE_DESCRIPTION,
        "version": "0.3.0",
        "protocol": "x402",
        "x402Version": 2,
        "category": "Data",
        "homepage": PUBLIC_HOST,
        "auth": {
            "type": "x402",
            "scheme": "exact",
            "price": scrape.price,
            "asset": "USDC",
            "network": "eip155:8453",
            "payTo": settings.pay_to(),
        },
        "tools": [
            {
                "name": "scrape_markdown",
                "description": SCRAPE_DESCRIPTION,
                "method": "GET",
                "path": "/v1/scrape",
                "url": f"{PUBLIC_HOST}/v1/scrape",
                "inputSchema": URL_INPUT_SCHEMA,
                "outputSchema": SCRAPE_OUTPUT_SCHEMA,
                "outputMimeType": "application/json",
            }
        ],
    }


def ai_plugin_manifest(settings: Settings) -> dict:
    scrape = next(product for product in PRODUCTS if product.sku == "scrape.md")
    return {
        "schema_version": "v1",
        "name_for_human": "x402 Markdown Scraper",
        "name_for_model": "x402_markdown_scraper",
        "description_for_human": SCRAPE_DESCRIPTION,
        "description_for_model": (
            f"{SCRAPE_DESCRIPTION} Call GET /v1/scrape?url= with a public article URL. "
            f"Unpaid requests return HTTP 402. Pay {scrape.price} USDC on Base (eip155:8453) "
            "via x402 PAYMENT-SIGNATURE, then retry. Response JSON includes markdown."
        ),
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": f"{PUBLIC_HOST}/openapi.json",
            "is_user_authenticated": False,
        },
        "legal_info_url": PUBLIC_HOST,
        "x402": {
            "price": scrape.price,
            "asset": "USDC",
            "network": "eip155:8453",
            "payTo": settings.pay_to(),
            "tool": "GET /v1/scrape",
            "input": {"url": "string, required, public article URL"},
            "output": "JSON { sku, url, title, markdown, source_status, paid_source }",
        },
    }


def x402_openapi_extension(settings: Settings) -> dict:
    return {
        "protocol": "x402",
        "x402Version": 2,
        "asset": "USDC",
        "payTo": settings.pay_to(),
        "networks": list(settings.networks()),
        "category": "Data",
        "primaryPrice": "$0.01",
        "primaryPath": "GET /v1/scrape",
        "note": "Unpaid calls to paid paths return HTTP 402 with a PAYMENT-REQUIRED header.",
    }
