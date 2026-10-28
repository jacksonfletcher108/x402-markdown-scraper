"""Local mocked suite for unpaid discovery, paywall binding, and fulfillment handlers.

Run:
    python test_suite.py
"""

from __future__ import annotations

import base64
import json
import socket
import sys
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.catalog import PRODUCTS
from app.cache import TtlCache, cache
from app.config import MAINNET, SOLANA, Settings
from app.extract import PageExtract, parse_html
from app.crawl import deep_crawl
from app.main import (
    app,
    crawl_get,
    metadata_get,
    parse_pdf_get,
    scrape_get,
    summary_get,
)
from app.payments import paid_routes
from app.pdf import pdf_bytes_to_markdown
from app.scraper import ScrapeError, fetch_bytes, redirect_target, validate_url
from app.summarize import executive_summary

TEST_WALLET = "0xf84EF3669eA39b87D4a850B4510f7aCBAC19be5f"
SAMPLE_HTML = """<!doctype html><html><head>
<title>Widget Launch</title>
<meta property="og:title" content="Widget Launch">
<meta name="author" content="Ada Lovelace">
<meta property="article:published_time" content="2026-03-01T12:00:00Z">
<script type="application/ld+json">{"@type":"NewsArticle","headline":"Widget Launch","datePublished":"2026-03-01","author":{"name":"Ada Lovelace"}}</script>
</head><body>
<h1>Widget Launch</h1>
<p>The company released a new widget today after three years of quiet development work.</p>
<p>Analysts said demand could reshape the market because buyers want simpler research tools.</p>
<p>Leadership promised a public roadmap next quarter for autonomous agents.</p>
</body></html>"""


def _price(route) -> str:
    accepts = route.accepts if isinstance(route.accepts, list) else [route.accepts]
    return str(accepts[0].price)


def _network(route) -> str:
    accepts = route.accepts if isinstance(route.accepts, list) else [route.accepts]
    return str(accepts[0].network)


def _pay_to(route) -> str:
    accepts = route.accepts if isinstance(route.accepts, list) else [route.accepts]
    return str(accepts[0].pay_to)


def _sample_page() -> PageExtract:
    page = parse_html(SAMPLE_HTML, "https://example.com/article")
    page.source_status = 200
    page.paid_source = False
    return page


class PaywallBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            payment_wallet_address=TEST_WALLET,
            x402_pay_to="",
            x402_networks="eip155:8453,eip155:84532",
        )
        self.routes = paid_routes(self.settings)

    def test_featured_prices_and_base_network(self) -> None:
        expected = {
            "GET /v1/scrape": "$0.01",
            "POST /v1/scrape": "$0.01",
            "GET /v1/summary": "$0.02",
            "POST /v1/summary": "$0.02",
            "GET /v1/extract-metadata": "$0.01",
            "POST /v1/extract-metadata": "$0.01",
            "GET /v1/parse-pdf": "$0.05",
            "POST /v1/parse-pdf": "$0.05",
            "GET /v1/deep-crawl": "$0.15",
            "POST /v1/deep-crawl": "$0.15",
        }
        for key, price in expected.items():
            self.assertIn(key, self.routes, key)
            self.assertEqual(_price(self.routes[key]), price, key)
            self.assertEqual(_network(self.routes[key]), MAINNET, key)
            self.assertEqual(_pay_to(self.routes[key]), TEST_WALLET, key)

    def test_wallet_comes_from_env_fields_not_literals_in_routes(self) -> None:
        other = "0x1111111111111111111111111111111111111111"
        routes = paid_routes(Settings(payment_wallet_address=other, x402_pay_to=""))
        self.assertEqual(_pay_to(routes["GET /v1/scrape"]), other)
        fallback = paid_routes(Settings(payment_wallet_address="", x402_pay_to=TEST_WALLET))
        self.assertEqual(_pay_to(fallback["GET /v1/scrape"]), TEST_WALLET)

    def test_catalog_lists_featured_skus(self) -> None:
        paths = {product.path: product.price for product in PRODUCTS}
        self.assertEqual(paths["/v1/scrape"], "$0.01")
        self.assertEqual(paths["/v1/summary"], "$0.02")
        self.assertEqual(paths["/v1/extract-metadata"], "$0.01")
        self.assertEqual(paths["/v1/parse-pdf"], "$0.05")
        self.assertEqual(paths["/v1/deep-crawl"], "$0.15")

    def test_solana_option_when_wallet_set(self) -> None:
        sol = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        routes = paid_routes(
            Settings(
                payment_wallet_address=TEST_WALLET,
                x402_pay_to="",
                solana_wallet_address=sol,
            )
        )
        accepts = routes["GET /v1/scrape"].accepts
        networks = [str(item.network) for item in accepts]
        self.assertIn(SOLANA, networks)
        svm = next(item for item in accepts if str(item.network) == SOLANA)
        self.assertEqual(svm.pay_to, sol)


class DiscoveryRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_storefront_portal(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        text = response.text
        for path in (
            "/v1/scrape",
            "/v1/summary",
            "/v1/extract-metadata",
            "/v1/parse-pdf",
            "/v1/deep-crawl",
            "/docs",
            "/llms.txt",
            "/openapi.json",
            "/.well-known/mcp",
        ):
            self.assertIn(path, text)
        self.assertIn("$0.01", text)
        self.assertIn("$0.15", text)
        self.assertIn("Python (httpx)", text)
        self.assertIn("JavaScript (fetch)", text)
        self.assertIn("cURL", text)
        self.assertIn("PAYMENT-REQUIRED", text)
        self.assertIn("eip155:8453", text)
        self.assertIn(Settings().pay_to(), text)
        self.assertTrue("EVM / Base USDC Active" in text or "Base Sepolia" in text)

    def test_storefront_playground(self) -> None:
        text = self.client.get("/").text
        self.assertIn('id="playground"', text)
        for path, price in (
            ("/v1/scrape", "$0.01"),
            ("/v1/summary", "$0.02"),
            ("/v1/extract-metadata", "$0.01"),
            ("/v1/parse-pdf", "$0.05"),
            ("/v1/deep-crawl", "$0.15"),
        ):
            self.assertIn(f'<option value="{path}"', text)
            self.assertIn(f'data-price="{price}"', text)
        for marker in (
            "PAYMENT-REQUIRED",
            "PAYMENT-SIGNATURE",
            "eth_signTypedData_v4",
            "TransferWithAuthorization",
            'id="pg-nowallet"',
            "eip6963:requestProvider",
            "metamask.app.link/dapp/",
        ):
            self.assertIn(marker, text)

    def test_playground_walletconnect_only_with_project_id(self) -> None:
        from app.playground import playground_html

        self.assertNotIn('id="pg-wc"', playground_html(PRODUCTS))
        self.assertNotIn("pg-hint", playground_html(PRODUCTS))
        page = playground_html(PRODUCTS, "abc123")
        self.assertIn('id="pg-wc" data-project-id="abc123"', page)
        self.assertIn("not your phone camera", page)
        self.assertIn("@walletconnect/ethereum-provider@2.26.0", page)
        self.assertIn('id="pg-steps" hidden', page)
        self.assertIn('id="pg-wc"', self.client.get("/").text)

    def test_swagger_docs_unpaid(self) -> None:
        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("swagger", response.text.lower())
        spec = self.client.get("/openapi.json").json()
        scrape = spec["paths"]["/v1/scrape"]["get"]
        self.assertIn("$0.01", scrape.get("summary", ""))
        self.assertEqual(scrape["x-x402"]["network"], "eip155:8453")
        self.assertEqual(scrape["x-x402"]["scheme"], "exact")

    def test_catalog(self) -> None:
        response = self.client.get("/v1/catalog")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        paths = {item["path"]: item["price"] for item in body["products"]}
        self.assertEqual(paths["/v1/scrape"], "$0.01")
        self.assertEqual(paths["/v1/summary"], "$0.02")
        self.assertEqual(paths["/v1/extract-metadata"], "$0.01")
        self.assertEqual(paths["/v1/parse-pdf"], "$0.05")
        self.assertEqual(paths["/v1/deep-crawl"], "$0.15")

    def test_llms_txt(self) -> None:
        response = self.client.get("/llms.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/v1/scrape", response.text)
        self.assertIn("/v1/summary", response.text)
        self.assertIn("/v1/extract-metadata", response.text)
        self.assertIn("/v1/parse-pdf", response.text)
        self.assertIn("/v1/deep-crawl", response.text)

    def test_llms_full_and_crawler_files(self) -> None:
        full = self.client.get("/llms-full.txt")
        self.assertEqual(full.status_code, 200)
        for marker in (
            "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "PAYMENT-REQUIRED",
            "PAYMENT-SIGNATURE",
            "PAYMENT-RESPONSE",
            "TransferWithAuthorization",
            "| 150000 |",
            "x402/payment",
            "/mcp",
        ):
            self.assertIn(marker, full.text)
        for tool in ("scrape_md", "page_summary", "page_metadata", "doc_pdf", "site_crawl"):
            self.assertIn(tool, full.text)
        self.assertIn("/llms-full.txt", self.client.get("/llms.txt").text)
        robots = self.client.get("/robots.txt").text
        self.assertIn("User-agent: GPTBot", robots)
        self.assertIn("Sitemap: https://x402-markdown-scraper.onrender.com/sitemap.xml", robots)
        sitemap = self.client.get("/sitemap.xml")
        self.assertIn("application/xml", sitemap.headers["content-type"])
        self.assertIn("/llms-full.txt</loc>", sitemap.text)

    def test_openapi(self) -> None:
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertIn("/v1/scrape", paths)
        self.assertIn("/v1/summary", paths)
        self.assertIn("/v1/extract-metadata", paths)
        self.assertIn("/v1/parse-pdf", paths)
        self.assertIn("/v1/deep-crawl", paths)
        self.assertEqual(response.json()["info"]["x-x402"]["asset"], "USDC")

    def test_well_known_mcp(self) -> None:
        response = self.client.get("/.well-known/mcp")
        self.assertEqual(response.status_code, 200)
        tools = {item["path"] for item in response.json()["tools"]}
        self.assertEqual(
            tools,
            {
                "/v1/scrape",
                "/v1/summary",
                "/v1/extract-metadata",
                "/v1/parse-pdf",
                "/v1/deep-crawl",
            },
        )


class PaidFourOhTwoTests(unittest.TestCase):
    """Hits the live facilitator once to build 402s. Skip if offline."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def _challenge(self, path: str) -> dict:
        response = self.client.get(path, params={"url": "https://example.com"})
        self.assertEqual(response.status_code, 402, response.text[:200])
        header = response.headers.get("payment-required") or response.headers.get("PAYMENT-REQUIRED")
        self.assertTrue(header)
        padded = header + "=" * (-len(header) % 4)
        return json.loads(base64.b64decode(padded).decode("utf-8"))

    def _amount_on_base(self, challenge: dict) -> str:
        option = next(
            item for item in challenge["accepts"] if item.get("network") == "eip155:8453"
        )
        self.assertEqual(option["scheme"], "exact")
        self.assertTrue(str(option["payTo"]).startswith("0x"))
        return str(option["amount"])

    def test_scrape_402_one_cent(self) -> None:
        self.assertEqual(self._amount_on_base(self._challenge("/v1/scrape")), "10000")

    def test_summary_402_two_cents(self) -> None:
        self.assertEqual(self._amount_on_base(self._challenge("/v1/summary")), "20000")

    def test_metadata_402_one_cent(self) -> None:
        self.assertEqual(self._amount_on_base(self._challenge("/v1/extract-metadata")), "10000")

    def test_pdf_402_five_cents(self) -> None:
        self.assertEqual(self._amount_on_base(self._challenge("/v1/parse-pdf")), "50000")

    def test_crawl_402_fifteen_cents(self) -> None:
        self.assertEqual(self._amount_on_base(self._challenge("/v1/deep-crawl")), "150000")


class FulfillmentMockTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.page = _sample_page()

    async def test_scrape_handler(self) -> None:
        with patch("app.main.fetch_page", AsyncMock(return_value=self.page)):
            result = await scrape_get(url="https://example.com/article")
        self.assertEqual(result.sku, "scrape.md")
        self.assertTrue(result.markdown)
        self.assertEqual(result.source_status, 200)

    async def test_summary_handler(self) -> None:
        with patch("app.main.fetch_page", AsyncMock(return_value=self.page)):
            result = await summary_get(url="https://example.com/article")
        self.assertEqual(result.sku, "page.summary")
        self.assertEqual(len(result.summary), 3)
        self.assertTrue(result.markdown)

    async def test_metadata_handler(self) -> None:
        with patch("app.main.fetch_page", AsyncMock(return_value=self.page)):
            result = await metadata_get(url="https://example.com/article")
        self.assertEqual(result.sku, "page.metadata")
        self.assertEqual(result.author, "Ada Lovelace")
        self.assertEqual(result.opengraph["og:title"], "Widget Launch")
        self.assertGreater(result.word_count, 10)

    def test_extractive_summary_length(self) -> None:
        bullets = executive_summary(self.page.text, self.page.title, self.page.headings)
        self.assertEqual(len(bullets), 3)

    async def test_pdf_handler(self) -> None:
        from io import BytesIO

        from pypdf import PdfWriter

        buf = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(buf)
        with patch("app.main.fetch_bytes", AsyncMock(return_value=(buf.getvalue(), "https://ex.com/a.pdf", 200))):
            result = await parse_pdf_get(url="https://ex.com/a.pdf")
        self.assertEqual(result.sku, "doc.pdf")
        self.assertTrue(result.markdown)

    def test_ttl_cache(self) -> None:
        local = TtlCache(ttl_seconds=60)
        local.set("k", {"ok": True})
        self.assertEqual(local.get("k"), {"ok": True})

    async def test_scrape_cache_skips_second_fetch(self) -> None:
        cache._items.clear()
        mock = AsyncMock(return_value=self.page)
        with patch("app.main.fetch_page", mock):
            first = await scrape_get(url="https://cache-test.example/article")
            second = await scrape_get(url="https://cache-test.example/article")
        self.assertEqual(mock.await_count, 1)
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)


class McpEndpointTests(unittest.TestCase):
    """JSON-RPC over /mcp. Tool calls hit the live facilitator once for requirements."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            headers={"Accept": "application/json, text/event-stream"},
        )
        self.assertEqual(response.status_code, 200, response.text[:200])
        return response.json()

    def _call(self, name: str, meta: dict | None = None) -> dict:
        params = {"name": name, "arguments": {"url": "https://example.com/article"}}
        if meta:
            params["_meta"] = meta
        return self._rpc("tools/call", params)["result"]

    def test_initialize(self) -> None:
        result = self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "x402-markdown-scraper")

    def test_notification_accepted(self) -> None:
        response = self.client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(response.status_code, 202)

    def test_tools_list_matches_featured_skus(self) -> None:
        tools = {tool["name"]: tool for tool in self._rpc("tools/list")["result"]["tools"]}
        self.assertEqual(set(tools), {"scrape_md", "page_summary", "page_metadata", "doc_pdf", "site_crawl"})
        self.assertIn("$0.15", tools["site_crawl"]["description"])
        self.assertIn("max_depth", tools["site_crawl"]["inputSchema"]["properties"])

    def test_unknown_method_and_get(self) -> None:
        self.assertEqual(self._rpc("resources/list")["error"]["code"], -32601)
        self.assertEqual(self.client.get("/mcp").status_code, 405)

    def test_unpaid_call_returns_payment_required(self) -> None:
        result = self._call("page_summary")
        self.assertTrue(result["isError"])
        option = next(
            item for item in result["structuredContent"]["accepts"] if item["network"] == "eip155:8453"
        )
        self.assertEqual(option["amount"], "20000")
        self.assertEqual(result["structuredContent"]["resource"]["url"], "mcp://tool/page_summary")

    def _payment_meta(self, name: str) -> dict:
        accepted = next(
            item for item in self._call(name)["structuredContent"]["accepts"] if item["network"] == "eip155:8453"
        )
        return {"x402/payment": {"x402Version": 2, "accepted": accepted, "payload": {"signature": "0xtest"}}}

    def test_paid_call_settles_and_returns_markdown(self) -> None:
        from x402.schemas import SettleResponse, VerifyResponse

        from app.main import server

        cache._items.clear()
        meta = self._payment_meta("scrape_md")
        settle = AsyncMock(
            return_value=SettleResponse(success=True, transaction="0xabc", network="eip155:8453")
        )
        with (
            patch("app.main.fetch_page", AsyncMock(return_value=_sample_page())),
            patch.object(server, "verify_payment", AsyncMock(return_value=VerifyResponse(is_valid=True))),
            patch.object(server, "settle_payment", settle),
        ):
            result = self._call("scrape_md", meta)
        self.assertFalse(result["isError"], result)
        self.assertEqual(result["structuredContent"]["sku"], "scrape.md")
        self.assertIn("Widget Launch", result["structuredContent"]["markdown"])
        self.assertEqual(result["_meta"]["x402/payment-response"]["transaction"], "0xabc")
        settle.assert_awaited_once()

    def test_failed_fetch_is_not_settled(self) -> None:
        from x402.schemas import VerifyResponse

        from app.main import server

        cache._items.clear()
        meta = self._payment_meta("scrape_md")
        settle = AsyncMock()
        with (
            patch("app.main.fetch_page", AsyncMock(side_effect=ScrapeError("upstream 404", 404))),
            patch.object(server, "verify_payment", AsyncMock(return_value=VerifyResponse(is_valid=True))),
            patch.object(server, "settle_payment", settle),
        ):
            result = self._call("scrape_md", meta)
        self.assertTrue(result["isError"])
        self.assertIn("upstream 404", result["content"][0]["text"])
        settle.assert_not_awaited()


class ClientKeyValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent / "client" / "src"))
        from x402_scraper import ScraperClient

        cls.ScraperClient = ScraperClient

    def test_address_instead_of_key_is_explained(self) -> None:
        with self.assertRaisesRegex(ValueError, "looks like a wallet address"):
            self.ScraperClient(private_key=TEST_WALLET)

    def test_bad_key_message_never_echoes_input(self) -> None:
        secret = "word " * 12
        with self.assertRaises(ValueError) as ctx:
            self.ScraperClient(private_key=secret)
        self.assertNotIn("word", str(ctx.exception))
        self.assertIn("64 hex characters", str(ctx.exception))

    def test_valid_key_and_no_key_accepted(self) -> None:
        self.ScraperClient(private_key="0x" + "11" * 32)
        self.ScraperClient(private_key="")


def _public_dns(host, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0))]


class SecurityBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_blocks_loopback_and_metadata_literals(self) -> None:
        for target in (
            "http://127.0.0.1/secret",
            "http://169.254.169.254/latest/meta-data",
            "http://localhost/admin",
            "http://metadata.google.internal/",
        ):
            with self.assertRaises(ScrapeError) as ctx:
                validate_url(target)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_redirect_to_metadata_is_rejected_before_fetch(self) -> None:
        with self.assertRaises(ScrapeError) as ctx:
            redirect_target("https://example.com/go", "http://169.254.169.254/latest/meta-data")
        self.assertEqual(ctx.exception.status_code, 400)
        with self.assertRaises(ScrapeError):
            redirect_target("https://example.com/go", "http://127.0.0.1/secret")

    async def test_http_redirect_to_loopback_never_followed(self) -> None:
        fetched: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            fetched.append(str(request.url))
            if request.url.path == "/go":
                return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
            return httpx.Response(200, content=b"leaked")

        transport = httpx.MockTransport(handler)
        real = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real(*args, **kwargs)

        with (
            patch("socket.getaddrinfo", side_effect=_public_dns),
            patch("app.scraper.httpx.AsyncClient", side_effect=factory),
        ):
            with self.assertRaises(ScrapeError) as ctx:
                await fetch_bytes("https://public.test/go", Settings())
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(fetched, ["https://public.test/go"])

    async def test_oversized_body_aborts(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"x" * 200, headers={"content-length": "200"})

        transport = httpx.MockTransport(handler)
        real = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real(*args, **kwargs)

        with (
            patch("socket.getaddrinfo", side_effect=_public_dns),
            patch("app.scraper.httpx.AsyncClient", side_effect=factory),
        ):
            with self.assertRaises(ScrapeError) as ctx:
                await fetch_bytes("https://public.test/big", Settings(), max_bytes=50)
        self.assertEqual(ctx.exception.status_code, 413)

    def test_corrupt_pdf_is_422(self) -> None:
        with self.assertRaises(ScrapeError) as ctx:
            pdf_bytes_to_markdown(b"not a pdf", "https://ex.com/a.pdf")
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_pdf_handler_maps_unexpected_errors_to_502(self) -> None:
        with patch("app.main.fetch_bytes", AsyncMock(side_effect=RuntimeError("boom"))):
            with self.assertRaises(HTTPException) as ctx:
                await parse_pdf_get(url="https://ex.com/a.pdf")
        self.assertEqual(ctx.exception.status_code, 502)

    async def test_crawl_handler_maps_unexpected_errors_to_502(self) -> None:
        with patch("app.main.deep_crawl", AsyncMock(side_effect=RuntimeError("boom"))):
            with self.assertRaises(HTTPException) as ctx:
                await crawl_get(url="https://example.com", max_depth=1)
        self.assertEqual(ctx.exception.status_code, 502)

    async def test_crawl_timeout_returns_structured_error(self) -> None:
        with (
            patch("socket.getaddrinfo", side_effect=_public_dns),
            patch(
                "app.crawl.fetch_page",
                AsyncMock(side_effect=ScrapeError("Timed out fetching URL", status_code=504)),
            ),
        ):
            with self.assertRaises(ScrapeError) as ctx:
                await deep_crawl("https://public.test/", 2, Settings(crawl_timeout_seconds=15))
        self.assertEqual(ctx.exception.status_code, 504)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
