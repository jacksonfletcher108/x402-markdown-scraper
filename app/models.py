from pydantic import BaseModel, Field, HttpUrl


class ScrapeRequest(BaseModel):
    url: HttpUrl = Field(description="Public http(s) URL to fetch.")
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
    cached: bool = False


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


class SummaryResponse(BaseModel):
    sku: str = "page.summary"
    url: str
    title: str | None
    summary: list[str] = Field(min_length=3, max_length=3)
    markdown: str
    source_status: int
    cached: bool = False


class PdfParseResponse(BaseModel):
    sku: str = "doc.pdf"
    url: str
    page_count: int
    markdown: str
    cached: bool = False
    source_status: int


class CrawlRequest(BaseModel):
    url: HttpUrl = Field(description="Public http(s) starting URL.")
    max_depth: int = Field(default=2, ge=1, le=3)
    pay_for_source: bool = True


class CrawlPage(BaseModel):
    url: str
    title: str | None = None
    depth: int
    headings: list[str] = Field(default_factory=list)
    markdown: str = ""
    links: list[str] = Field(default_factory=list)


class CrawlResponse(BaseModel):
    sku: str = "site.crawl"
    root: str
    max_depth: int
    page_count: int
    pages: list[CrawlPage]
    errors: list[dict] = Field(default_factory=list)
    cached: bool = False


class MetadataResponse(BaseModel):
    sku: str = "page.metadata"
    url: str
    title: str | None
    description: str | None
    author: str | None
    published: str | None
    opengraph: dict[str, str]
    json_ld: list[object]
    word_count: int
    reading_time_minutes: int
    source_status: int
    cached: bool = False
