from __future__ import annotations

from dataclasses import dataclass, field

from x402.extensions.bazaar import OutputConfig, declare_discovery_extension

SCRAPE_DESCRIPTION = (
    "Converts any web article URL into clean, stripped Markdown for AI context windows."
)

URL_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "format": "uri",
            "description": "Public http(s) URL of the article or page to convert.",
        }
    },
    "required": ["url"],
    "additionalProperties": False,
}

SCRAPE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "sku": {"type": "string", "const": "scrape.md"},
        "url": {"type": "string", "format": "uri"},
        "title": {"type": ["string", "null"]},
        "markdown": {
            "type": "string",
            "description": "Main article content as stripped Markdown.",
        },
        "source_status": {"type": "integer"},
        "paid_source": {"type": "boolean"},
    },
    "required": ["sku", "url", "markdown", "source_status", "paid_source"],
}


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    description: str
    price: str
    method: str
    path: str
    tags: tuple[str, ...]
    query_example: dict[str, str]
    query_schema: dict
    output_example: dict
    output_schema: dict = field(default_factory=dict)
    category: str = "Data"


PRODUCTS: tuple[Product, ...] = (
    Product(
        sku="scrape.md",
        name="Markdown scrape",
        description=SCRAPE_DESCRIPTION,
        price="$0.01",
        method="GET",
        path="/v1/scrape",
        tags=("Data", "markdown", "scrape", "web", "agents"),
        query_example={"url": "https://example.com"},
        query_schema=URL_INPUT_SCHEMA,
        output_example={
            "sku": "scrape.md",
            "url": "https://example.com",
            "title": "Example Domain",
            "markdown": "# Example Domain\n\nThis domain is for use in documentation examples.",
            "source_status": 200,
            "paid_source": False,
        },
        output_schema=SCRAPE_OUTPUT_SCHEMA,
        category="Data",
    ),
    Product(
        sku="page.title",
        name="Title + description",
        description="Return the page title and meta description only.",
        price="$0.001",
        method="GET",
        path="/v1/title",
        tags=("Data", "metadata", "scrape", "web", "agents"),
        query_example={"url": "https://example.com"},
        query_schema=URL_INPUT_SCHEMA,
        output_example={
            "sku": "page.title",
            "url": "https://example.com",
            "title": "Example Domain",
            "description": None,
            "source_status": 200,
        },
        output_schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "url": {"type": "string", "format": "uri"},
                "title": {"type": ["string", "null"]},
                "description": {"type": ["string", "null"]},
                "source_status": {"type": "integer"},
            },
            "required": ["url", "source_status"],
        },
        category="Data",
    ),
    Product(
        sku="page.text",
        name="Plain text",
        description="Return visible page text without HTML.",
        price="$0.005",
        method="GET",
        path="/v1/text",
        tags=("Data", "text", "scrape", "web", "agents"),
        query_example={"url": "https://example.com"},
        query_schema=URL_INPUT_SCHEMA,
        output_example={
            "sku": "page.text",
            "url": "https://example.com",
            "text": "Example Domain",
            "source_status": 200,
        },
        output_schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "url": {"type": "string", "format": "uri"},
                "text": {"type": "string"},
                "source_status": {"type": "integer"},
            },
            "required": ["url", "text", "source_status"],
        },
        category="Data",
    ),
    Product(
        sku="page.outline",
        name="Heading outline",
        description="Return h1-h3 headings as a document outline.",
        price="$0.005",
        method="GET",
        path="/v1/outline",
        tags=("Data", "outline", "scrape", "web", "agents"),
        query_example={"url": "https://example.com"},
        query_schema=URL_INPUT_SCHEMA,
        output_example={
            "sku": "page.outline",
            "url": "https://example.com",
            "headings": ["Example Domain"],
            "source_status": 200,
        },
        output_schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "url": {"type": "string", "format": "uri"},
                "headings": {"type": "array", "items": {"type": "string"}},
                "source_status": {"type": "integer"},
            },
            "required": ["url", "headings", "source_status"],
        },
        category="Data",
    ),
    Product(
        sku="page.links",
        name="Outbound links",
        description="Return up to 50 absolute http(s) links from the page.",
        price="$0.005",
        method="GET",
        path="/v1/links",
        tags=("Data", "links", "scrape", "web", "agents"),
        query_example={"url": "https://example.com"},
        query_schema=URL_INPUT_SCHEMA,
        output_example={
            "sku": "page.links",
            "url": "https://example.com",
            "links": ["https://iana.org/domains/example"],
            "source_status": 200,
        },
        output_schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "url": {"type": "string", "format": "uri"},
                "links": {"type": "array", "items": {"type": "string", "format": "uri"}},
                "source_status": {"type": "integer"},
            },
            "required": ["url", "links", "source_status"],
        },
        category="Data",
    ),
)


def bazaar_extension(product: Product, *, body_type: str | None = None) -> dict:
    return declare_discovery_extension(
        input=product.query_example,
        input_schema=product.query_schema,
        body_type=body_type,  # type: ignore[arg-type]
        output=OutputConfig(example=product.output_example, schema=product.output_schema or None),
    )


def public_catalog(pay_to: str, networks: list[str], settlement_ready: bool) -> dict:
    return {
        "vendor": "x402 Markdown Scraper",
        "protocol": "x402",
        "x402Version": 2,
        "category": "Data",
        "settlement_ready": settlement_ready,
        "pay_to": pay_to,
        "networks": networks,
        "asset": "USDC",
        "discovery": {
            "free": [
                "GET /health",
                "GET /llms.txt",
                "GET /openapi.json",
                "GET /v1/catalog",
                "GET /.well-known/mcp",
                "GET /.well-known/ai-plugin.json",
            ],
            "note": "Call a paid path without PAYMENT-SIGNATURE to receive PAYMENT-REQUIRED.",
        },
        "products": [
            {
                "sku": product.sku,
                "name": product.name,
                "description": product.description,
                "category": product.category,
                "price": product.price,
                "method": product.method,
                "path": product.path,
                "tags": list(product.tags),
            }
            for product in PRODUCTS
        ],
    }
