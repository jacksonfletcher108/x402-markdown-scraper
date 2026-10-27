from __future__ import annotations

from dataclasses import dataclass

from x402.extensions.bazaar import OutputConfig, declare_discovery_extension


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


PRODUCTS: tuple[Product, ...] = (
    Product(
        sku="scrape.md",
        name="Markdown scrape",
        description="Fetch a public URL and return clean markdown for agents.",
        price="$0.01",
        method="GET",
        path="/v1/scrape",
        tags=("scrape", "markdown", "web"),
        query_example={"url": "https://example.com"},
        query_schema={
            "properties": {"url": {"type": "string", "format": "uri"}},
            "required": ["url"],
        },
        output_example={"url": "https://example.com", "title": "Example", "markdown": "# Example"},
    ),
    Product(
        sku="page.title",
        name="Title + description",
        description="Return the page title and meta description only.",
        price="$0.001",
        method="GET",
        path="/v1/title",
        tags=("scrape", "metadata"),
        query_example={"url": "https://example.com"},
        query_schema={
            "properties": {"url": {"type": "string", "format": "uri"}},
            "required": ["url"],
        },
        output_example={"url": "https://example.com", "title": "Example", "description": "Example domain"},
    ),
    Product(
        sku="page.text",
        name="Plain text",
        description="Return visible page text without HTML.",
        price="$0.005",
        method="GET",
        path="/v1/text",
        tags=("scrape", "text"),
        query_example={"url": "https://example.com"},
        query_schema={
            "properties": {"url": {"type": "string", "format": "uri"}},
            "required": ["url"],
        },
        output_example={"url": "https://example.com", "text": "Example Domain"},
    ),
    Product(
        sku="page.outline",
        name="Heading outline",
        description="Return h1–h3 headings as a document outline.",
        price="$0.005",
        method="GET",
        path="/v1/outline",
        tags=("scrape", "outline"),
        query_example={"url": "https://example.com"},
        query_schema={
            "properties": {"url": {"type": "string", "format": "uri"}},
            "required": ["url"],
        },
        output_example={"url": "https://example.com", "headings": ["Example Domain"]},
    ),
    Product(
        sku="page.links",
        name="Outbound links",
        description="Return up to 50 absolute http(s) links from the page.",
        price="$0.005",
        method="GET",
        path="/v1/links",
        tags=("scrape", "links"),
        query_example={"url": "https://example.com"},
        query_schema={
            "properties": {"url": {"type": "string", "format": "uri"}},
            "required": ["url"],
        },
        output_example={"url": "https://example.com", "links": ["https://iana.org/domains/example"]},
    ),
)


def bazaar_extension(product: Product) -> dict:
    return declare_discovery_extension(
        input=product.query_example,
        input_schema=product.query_schema,
        output=OutputConfig(example=product.output_example),
    )


def public_catalog(pay_to: str, networks: list[str], settlement_ready: bool) -> dict:
    return {
        "vendor": "x402 Markdown Scraper",
        "protocol": "x402",
        "x402Version": 2,
        "settlement_ready": settlement_ready,
        "pay_to": pay_to,
        "networks": networks,
        "asset": "USDC",
        "discovery": {
            "free": ["GET /health", "GET /v1/catalog"],
            "note": "Call a paid path without PAYMENT-SIGNATURE to receive PAYMENT-REQUIRED.",
        },
        "products": [
            {
                "sku": product.sku,
                "name": product.name,
                "description": product.description,
                "price": product.price,
                "method": product.method,
                "path": product.path,
                "tags": list(product.tags),
            }
            for product in PRODUCTS
        ],
    }
