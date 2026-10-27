from pydantic import BaseModel, Field, HttpUrl


class ScrapeRequest(BaseModel):
    url: HttpUrl
    pay_for_source: bool = Field(
        default=True,
        description="If the source returns HTTP 402, attach x402 payment headers and retry.",
    )


class ScrapeResponse(BaseModel):
    sku: str = "scrape.md"
    url: str
    title: str | None
    markdown: str
    source_status: int
    paid_source: bool


class TitleResponse(BaseModel):
    sku: str = "page.title"
    url: str
    title: str | None
    description: str | None
    source_status: int


class TextResponse(BaseModel):
    sku: str = "page.text"
    url: str
    text: str
    source_status: int


class OutlineResponse(BaseModel):
    sku: str = "page.outline"
    url: str
    headings: list[str]
    source_status: int


class LinksResponse(BaseModel):
    sku: str = "page.links"
    url: str
    links: list[str]
    source_status: int
