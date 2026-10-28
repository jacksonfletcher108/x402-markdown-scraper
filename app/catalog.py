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
    query_example: dict[str, object]
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
        sku="page.summary",
        name="Executive summary",
        description="Scrape a URL and return a 3-bullet executive summary plus clean Markdown.",
        price="$0.02",
        method="GET",
        path="/v1/summary",
        tags=("Data", "summary", "markdown", "scrape", "agents"),
        query_example={"url": "https://example.com"},
        query_schema=URL_INPUT_SCHEMA,
        output_example={
            "sku": "page.summary",
            "url": "https://example.com",
            "title": "Example Domain",
            "summary": [
                "This domain is for use in documentation examples.",
                "It illustrates a typical article structure for agents.",
                "The page contains little additional narrative detail.",
            ],
            "markdown": "# Example Domain\n\nThis domain is for use in documentation examples.",
            "source_status": 200,
        },
        output_schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string", "const": "page.summary"},
                "url": {"type": "string", "format": "uri"},
                "title": {"type": ["string", "null"]},
                "summary": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {"type": "string"},
                    "description": "Three executive-summary bullets extracted from the article.",
                },
                "markdown": {"type": "string"},
                "source_status": {"type": "integer"},
            },
            "required": ["sku", "url", "summary", "markdown", "source_status"],
        },
        category="Data",
    ),
    Product(
        sku="page.metadata",
        name="Page metadata",
        description="Extract Open Graph, Schema.org JSON-LD, author, publish date, word count, and reading time.",
        price="$0.01",
        method="GET",
        path="/v1/extract-metadata",
        tags=("Data", "metadata", "opengraph", "schema", "agents"),
        query_example={"url": "https://example.com"},
        query_schema=URL_INPUT_SCHEMA,
        output_example={
            "sku": "page.metadata",
            "url": "https://example.com",
            "title": "Example Domain",
            "description": None,
            "author": None,
            "published": None,
            "opengraph": {"og:title": "Example Domain"},
            "json_ld": [],
            "word_count": 28,
            "reading_time_minutes": 1,
            "source_status": 200,
        },
        output_schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string", "const": "page.metadata"},
                "url": {"type": "string", "format": "uri"},
                "title": {"type": ["string", "null"]},
                "description": {"type": ["string", "null"]},
                "author": {"type": ["string", "null"]},
                "published": {"type": ["string", "null"]},
                "opengraph": {"type": "object", "additionalProperties": {"type": "string"}},
                "json_ld": {"type": "array"},
                "word_count": {"type": "integer"},
                "reading_time_minutes": {"type": "integer"},
                "source_status": {"type": "integer"},
            },
            "required": [
                "sku",
                "url",
                "opengraph",
                "json_ld",
                "word_count",
                "reading_time_minutes",
                "source_status",
            ],
        },
        category="Data",
    ),
    Product(
        sku="doc.pdf",
        name="PDF to markdown",
        description="Fetch a PDF URL and return stripped, structured Markdown of the document text.",
        price="$0.05",
        method="GET",
        path="/v1/parse-pdf",
        tags=("Data", "pdf", "markdown", "scrape", "agents"),
        query_example={"url": "https://example.com/paper.pdf"},
        query_schema=URL_INPUT_SCHEMA,
        output_example={
            "sku": "doc.pdf",
            "url": "https://example.com/paper.pdf",
            "page_count": 2,
            "markdown": "# PDF extract\n\n## Page 1\n\nHello",
            "cached": False,
            "source_status": 200,
        },
        output_schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string", "const": "doc.pdf"},
                "url": {"type": "string", "format": "uri"},
                "page_count": {"type": "integer"},
                "markdown": {"type": "string"},
                "cached": {"type": "boolean"},
                "source_status": {"type": "integer"},
            },
            "required": ["sku", "url", "markdown", "source_status"],
        },
        category="Data",
    ),
    Product(
        sku="site.crawl",
        name="Deep site crawl",
        description="Crawl a starting URL up to 3 internal levels and return a structured multi-page document map.",
        price="$0.15",
        method="GET",
        path="/v1/deep-crawl",
        tags=("Data", "crawl", "sitemap", "scrape", "agents"),
        query_example={"url": "https://example.com", "max_depth": 2},
        query_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "format": "uri",
                    "description": "Public http(s) starting URL.",
                },
                "max_depth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 3,
                    "description": "Internal link depth, 1-3.",
                },
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        output_example={
            "sku": "site.crawl",
            "root": "https://example.com/",
            "max_depth": 2,
            "page_count": 1,
            "pages": [{"url": "https://example.com/", "title": "Example", "depth": 0}],
            "cached": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string", "const": "site.crawl"},
                "root": {"type": "string"},
                "max_depth": {"type": "integer"},
                "page_count": {"type": "integer"},
                "pages": {"type": "array"},
                "cached": {"type": "boolean"},
            },
            "required": ["sku", "root", "pages"],
        },
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


def public_catalog(
    pay_to: str,
    networks: list[str],
    settlement_ready: bool,
    pay_to_solana: str | None = None,
) -> dict:
    return {
        "vendor": "x402 Markdown Scraper",
        "protocol": "x402",
        "x402Version": 2,
        "category": "Data",
        "settlement_ready": settlement_ready,
        "pay_to": pay_to,
        "pay_to_solana": pay_to_solana or None,
        "networks": networks,
        "asset": "USDC",
        "discovery": {
            "free": [
                "GET /health",
                "GET /llms.txt",
                "GET /openapi.json",
                "GET /v1/catalog",
                "GET /.well-known/mcp",
                "POST /mcp (initialize, tools/list; tools/call is paid)",
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
