from __future__ import annotations

import json
from decimal import Decimal

from app.catalog import PRODUCTS, SCRAPE_DESCRIPTION
from app.config import MAINNET, SEPOLIA, Settings

FEATURED_SKUS = ("scrape.md", "page.summary", "page.metadata", "doc.pdf", "site.crawl")
# Circle USDC contracts and their EIP-712 domain (name, version) per network.
USDC = {
    MAINNET: ("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "USD Coin", "2", 8453, "Base"),
    SEPOLIA: ("0x036CbD53842c5426634e7929541eC2318f3dCF7e", "USDC", "2", 84532, "Base Sepolia"),
}


def llms_txt(settings: Settings) -> str:
    host = settings.public_url.rstrip("/")
    lines = [
        "# x402 Web Markdown Scraper",
        "",
        "> Pay-per-request web scraping API and MCP server for AI agents: any URL or PDF to clean Markdown.",
        "> Pay USDC on Base (eip155:8453) over HTTP 402 (x402 v2). No account or API key. Category: Data.",
        f"> Full reference with schemas and payment payloads: {host}/llms-full.txt",
        "",
        f"Base: {host}",
        f"Pay to: {settings.pay_to()}",
        f"Asset: USDC on Base. Networks: {', '.join(settings.networks())}",
        "",
        "## Free (no payment)",
        "",
        f"- [Health]({host}/health): GET /health — keep-alive liveness",
        f"- [Catalog]({host}/v1/catalog): GET /v1/catalog — machine-readable SKUs",
        f"- [OpenAPI]({host}/openapi.json): GET /openapi.json — request/response schemas",
        f"- [MCP server]({host}/mcp): POST /mcp — Streamable HTTP MCP; tools/call paid via x402 in _meta",
        f"- [MCP]({host}/.well-known/mcp): GET /.well-known/mcp — agent tool card",
        f"- [Plugin]({host}/.well-known/ai-plugin.json): GET /.well-known/ai-plugin.json",
        f"- [llms.txt]({host}/llms.txt): this file",
        f"- [llms-full.txt]({host}/llms-full.txt): full reference — schemas, x402 headers, sample payloads, USDC contract",
        f"- [Playground]({host}/#playground): try every SKU from a browser wallet",
        "- Python client: `pip install x402-scraper`",
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
            f"- [{product.name}]({host}{product.path}?{example_q}): "
            f"{product.method} {product.path}?url= — {product.price} USDC. {product.description}"
        )
    lines.extend(
        [
            "",
            "## Primary SKU",
            "",
            f"GET/POST {host}/v1/scrape costs $0.01 USDC. Query or JSON body: {{\"url\": \"...\"}}.",
            f"GET/POST {host}/v1/summary costs $0.02 USDC. Returns 3-bullet summary + markdown.",
            f"GET/POST {host}/v1/extract-metadata costs $0.01 USDC. Returns Open Graph, JSON-LD, author, date, word count.",
            f"GET/POST {host}/v1/parse-pdf costs $0.05 USDC. PDF URL to structured Markdown.",
            f"GET/POST {host}/v1/deep-crawl costs $0.15 USDC. Internal crawl, max_depth 1-3.",
            "",
            "## Optional SKUs",
            "",
            "GET /v1/title $0.001, GET /v1/text $0.005, GET /v1/outline $0.005, GET /v1/links $0.005.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _atomic(price: str) -> str:
    """USDC has 6 decimals: "$0.05" -> "50000"."""
    return str(int(Decimal(price.lstrip("$")) * 10**6))


def _json(value: object) -> str:
    return json.dumps(value, indent=2)


def llms_full_txt(settings: Settings) -> str:
    """Long-form reference for AI crawlers: every SKU, schema, payload and header."""
    host = settings.public_url.rstrip("/")
    networks = [network for network in settings.networks() if network in USDC]
    pay_to = settings.pay_to()
    featured = [product for product in PRODUCTS if product.sku in FEATURED_SKUS]
    scrape = featured[0]
    asset, token_name, token_version, chain_id, chain_name = USDC[networks[0] if networks else MAINNET]

    def accepts(price: str) -> list[dict]:
        return [
            {
                "scheme": "exact",
                "network": network,
                "asset": USDC[network][0],
                "amount": _atomic(price),
                "payTo": pay_to,
                "maxTimeoutSeconds": 300,
                "extra": {"name": USDC[network][1], "version": USDC[network][2]},
            }
            for network in networks
        ]

    lines = [
        "# x402 Web Markdown Scraper — full reference",
        "",
        "> Pay-per-request web scraping API and MCP server for AI agents. Converts any public URL or PDF into clean",
        "> Markdown for LLM context windows. Payment is USDC on Base (eip155:8453) over HTTP 402 using the x402 v2",
        "> `exact` scheme (EIP-3009 TransferWithAuthorization). No account, no API key, no subscription.",
        "",
        "## Quick facts",
        "",
        f"- Base URL: {host}",
        f"- MCP server (Streamable HTTP, stateless): {host}/mcp",
        f"- OpenAPI 3 spec: {host}/openapi.json · Swagger UI: {host}/docs",
        f"- Short manifest: {host}/llms.txt · MCP tool card: {host}/.well-known/mcp",
        f"- Machine catalog: {host}/v1/catalog",
        f"- Browser playground: {host}/#playground",
        "- Python client: `pip install x402-scraper` (PyPI package `x402-scraper`, import `x402_scraper`)",
        "- Source: https://github.com/jacksonfletcher108/x402-markdown-scraper",
        "- Protocol: x402 v2, scheme `exact`, headers PAYMENT-REQUIRED / PAYMENT-SIGNATURE / PAYMENT-RESPONSE",
        f"- Networks accepted: {', '.join(networks)}",
        f"- Asset: USDC (6 decimals) on {chain_name}, contract {asset}",
        f"- Pay to: {pay_to}",
        "- Gas: payers sign only; the facilitator submits the transfer, so no ETH is needed.",
        "",
        "## Price list",
        "",
        "| SKU | Name | Price (USDC) | Atomic amount | HTTP | MCP tool |",
        "|---|---|---|---|---|---|",
    ]
    for product in featured:
        lines.append(
            f"| `{product.sku}` | {product.name} | {product.price} | {_atomic(product.price)} | "
            f"GET/POST {product.path} | `{product.sku.replace('.', '_')}` |"
        )
    lines.extend(
        [
            "",
            "Optional low-cost SKUs: GET /v1/title $0.001, GET /v1/text $0.005, GET /v1/outline $0.005, GET /v1/links $0.005.",
            "",
            "## SKUs",
            "",
        ]
    )
    for product in featured:
        query = "&".join(f"{key}={value}" for key, value in product.query_example.items())
        lines.extend(
            [
                f"### {product.name} — {product.price} USDC (`{product.sku}`)",
                "",
                product.description,
                "",
                f"- GET {host}{product.path}?{query}",
                f"- POST {host}{product.path} with JSON body {json.dumps(product.query_example)}",
                f"- MCP: `tools/call` name `{product.sku.replace('.', '_')}`, arguments {json.dumps(product.query_example)}",
                "",
                "Input schema:",
                "",
                "```json",
                _json(product.query_schema),
                "```",
                "",
                "Example 200 response after payment:",
                "",
                "```json",
                _json(product.output_example),
                "```",
                "",
            ]
        )

    payment_required = {
        "x402Version": 2,
        "error": "Payment required",
        "resource": {
            "url": f"{host}{scrape.path}?url=https%3A%2F%2Fexample.com",
            "description": scrape.description,
            "mimeType": "application/json",
        },
        "accepts": accepts(scrape.price),
    }
    payment_payload = {
        "x402Version": 2,
        "accepted": accepts(scrape.price)[0] if networks else {},
        "resource": payment_required["resource"],
        "payload": {
            "authorization": {
                "from": "0xPayerAddress",
                "to": pay_to,
                "value": _atomic(scrape.price),
                "validAfter": "0",
                "validBefore": "1767225600",
                "nonce": "0x<32 random bytes, hex>",
            },
            "signature": "0x<65-byte EIP-712 signature>",
        },
    }
    typed_data = {
        "domain": {"name": token_name, "version": token_version, "chainId": chain_id, "verifyingContract": asset},
        "primaryType": "TransferWithAuthorization",
        "types": {
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ]
        },
    }
    payment_response = {
        "success": True,
        "transaction": "0x<Base transaction hash>",
        "network": networks[0] if networks else MAINNET,
        "payer": "0xPayerAddress",
    }
    lines.extend(
        [
            "## x402 payment flow (HTTP)",
            "",
            "1. Call any paid path without payment.",
            "2. The server answers `402 Payment Required`, body `{\"error\":\"Payment required\"}`, and header",
            "   `PAYMENT-REQUIRED: <base64(JSON PaymentRequired)>`.",
            "3. Pick the `accepts` entry for your network, sign an EIP-3009 TransferWithAuthorization for exactly",
            "   `amount` to `payTo` with EIP-712 (domain below).",
            "4. Retry the identical request with header `PAYMENT-SIGNATURE: <base64(JSON PaymentPayload)>`.",
            "5. On success: HTTP 200, the SKU JSON, and header `PAYMENT-RESPONSE: <base64(JSON settlement)>`.",
            "   If the handler fails (4xx/5xx), the payment is not settled.",
            "",
            "Raw unpaid exchange:",
            "",
            "```http",
            f"GET {scrape.path}?url=https://example.com HTTP/1.1",
            f"Host: {host.split('://', 1)[-1]}",
            "Accept: application/json",
            "",
            "HTTP/1.1 402 Payment Required",
            "Content-Type: application/json",
            "PAYMENT-REQUIRED: eyJ4NDAyVmVyc2lvbiI6Miwi...",
            "",
            '{"error":"Payment required"}',
            "```",
            "",
            "Decoded PAYMENT-REQUIRED (the live header also carries a `bazaar` discovery extension):",
            "",
            "```json",
            _json(payment_required),
            "```",
            "",
            "EIP-712 typed data to sign:",
            "",
            "```json",
            _json(typed_data),
            "```",
            "",
            "Decoded PAYMENT-SIGNATURE (send base64 of this JSON; echo `resource` and `extensions` from the challenge):",
            "",
            "```json",
            _json(payment_payload),
            "```",
            "",
            "Decoded PAYMENT-RESPONSE:",
            "",
            "```json",
            _json(payment_response),
            "```",
            "",
            "## MCP server",
            "",
            f"Endpoint: `POST {host}/mcp` (JSON-RPC 2.0, Streamable HTTP, JSON responses, no sessions;",
            "GET/DELETE return 405). Protocol versions 2025-06-18, 2025-03-26, 2024-11-05.",
            "",
            "- Free: `initialize`, `ping`, `tools/list`.",
            "- Paid: `tools/call`. Unpaid calls return a result with `isError: true` and the PaymentRequired object",
            "  (same shape as above, resource `mcp://tool/<name>`) in `structuredContent`.",
            '- Pay by retrying with the PaymentPayload object (not base64) in `params._meta["x402/payment"]`.',
            '- The settlement receipt is returned in `result._meta["x402/payment-response"]`.',
            "- Clients without x402 support (e.g. Claude Desktop, Cursor) can list tools but receive the",
            "  PaymentRequired result instead of data.",
            "",
            "```json",
            _json(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "scrape_md",
                        "arguments": {"url": "https://example.com"},
                        "_meta": {"x402/payment": {"x402Version": 2, "accepted": "...", "payload": "..."}},
                    },
                }
            ),
            "```",
            "",
            "## Client code",
            "",
            "Python with the x402 SDK and httpx (signs and retries automatically):",
            "",
            "```python",
            "import asyncio, os",
            "from eth_account import Account",
            "from x402 import x402Client",
            "from x402.http.clients import x402HttpxClient  # an httpx.AsyncClient",
            "from x402.mechanisms.evm import EthAccountSigner",
            "from x402.mechanisms.evm.exact.register import register_exact_evm_client",
            "",
            "async def main():",
            "    payer = x402Client()",
            '    register_exact_evm_client(payer, EthAccountSigner(Account.from_key(os.environ["EVM_PRIVATE_KEY"])))',
            "    async with x402HttpxClient(payer) as http:",
            f'        r = await http.get("{host}/v1/scrape", params={{"url": "https://example.com"}})',
            '        print(r.json()["markdown"])',
            "",
            "asyncio.run(main())",
            "```",
            "",
            "Python with `x402-scraper`:",
            "",
            "```python",
            "import asyncio",
            "from x402_scraper import ScraperClient  # reads EVM_PRIVATE_KEY",
            'md = asyncio.run(ScraperClient().scrape("https://example.com"))["markdown"]',
            "```",
            "",
            "LangChain tool:",
            "",
            "```python",
            "from langchain_core.tools import StructuredTool",
            "from x402_scraper import ScraperClient",
            "client = ScraperClient()",
            'scrape = StructuredTool.from_function(coroutine=client.scrape, name="scrape_url", description="Fetch any URL as clean Markdown ($0.01 USDC on Base).")',
            "```",
            "",
            "LlamaIndex tool:",
            "",
            "```python",
            "from llama_index.core.tools import FunctionTool",
            "from x402_scraper import ScraperClient",
            "client = ScraperClient()",
            'parse_pdf = FunctionTool.from_defaults(async_fn=client.parse_pdf, name="parse_pdf", description="Convert a PDF URL to structured Markdown ($0.05 USDC on Base).")',
            "```",
            "",
            "## Errors and limits",
            "",
            "- 400: not http(s), missing host, unresolvable host, localhost/metadata/private IP targets (blocked).",
            "- 402: payment required or rejected (see PAYMENT-REQUIRED `error`).",
            "- 413: source response over the size limit.",
            "- 422: invalid input, URL is not a PDF, encrypted or unreadable PDF, bad `max_depth`.",
            "- 502: source returned an error, too many redirects, or content could not be parsed.",
            "- 504: source or crawl timed out.",
            f"- Limits: HTML {settings.max_html_bytes // 1_000_000} MB, PDF {settings.max_pdf_bytes // 1_000_000} MB, "
            f"{settings.max_redirects} redirects, crawl timeout {settings.crawl_timeout_seconds:g}s, crawl depth 1-3 on the same host.",
            f"- Responses are cached for {settings.cache_ttl_seconds / 60:g} minutes (`cached: true`); repeat calls still pay.",
            "- No login walls, no JavaScript rendering, no CAPTCHA solving.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def mcp_manifest(settings: Settings) -> dict:
    host = settings.public_url.rstrip("/")
    featured = [
        product
        for product in PRODUCTS
        if product.sku in {"scrape.md", "page.summary", "page.metadata", "doc.pdf", "site.crawl"}
    ]
    scrape = featured[0]
    return {
        "name": "x402-markdown-scraper",
        "description": SCRAPE_DESCRIPTION,
        "version": "0.5.0",
        "protocol": "x402",
        "x402Version": 2,
        "category": "Data",
        "homepage": host,
        "mcpEndpoint": f"{host}/mcp",
        "transport": "streamable-http",
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
                "name": product.sku.replace(".", "_"),
                "description": product.description,
                "method": "GET",
                "path": product.path,
                "url": f"{host}{product.path}",
                "price": product.price,
                "inputSchema": product.query_schema,
                "outputSchema": product.output_schema,
                "outputMimeType": "application/json",
            }
            for product in featured
        ],
    }


def ai_plugin_manifest(settings: Settings) -> dict:
    host = settings.public_url.rstrip("/")
    scrape = next(product for product in PRODUCTS if product.sku == "scrape.md")
    return {
        "schema_version": "v1",
        "name_for_human": "x402 Markdown Scraper",
        "name_for_model": "x402_markdown_scraper",
        "description_for_human": SCRAPE_DESCRIPTION,
        "description_for_model": (
            f"{SCRAPE_DESCRIPTION} Also /v1/summary $0.02, /v1/extract-metadata $0.01, "
            "/v1/parse-pdf $0.05, /v1/deep-crawl $0.15. Pay USDC on Base and optional Solana via x402."
        ),
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": f"{host}/openapi.json",
            "is_user_authenticated": False,
        },
        "legal_info_url": host,
        "x402": {
            "price": scrape.price,
            "asset": "USDC",
            "network": "eip155:8453",
            "payTo": settings.pay_to(),
            "tools": [
                {"path": "GET /v1/scrape", "price": "$0.01"},
                {"path": "GET /v1/summary", "price": "$0.02"},
                {"path": "GET /v1/extract-metadata", "price": "$0.01"},
                {"path": "GET /v1/parse-pdf", "price": "$0.05"},
                {"path": "GET /v1/deep-crawl", "price": "$0.15"},
            ],
            "input": {"url": "string, required, public article URL"},
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
        "payToSolana": settings.solana_pay_to() or None,
        "featured": [
            {"path": "GET /v1/scrape", "price": "$0.01"},
            {"path": "GET /v1/summary", "price": "$0.02"},
            {"path": "GET /v1/extract-metadata", "price": "$0.01"},
            {"path": "GET /v1/parse-pdf", "price": "$0.05"},
            {"path": "GET /v1/deep-crawl", "price": "$0.15"},
        ],
        "note": "Unpaid calls to paid paths return HTTP 402 with a PAYMENT-REQUIRED header.",
    }
