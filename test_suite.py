"""Local mocked suite for unpaid discovery, paywall binding, and fulfillment handlers.

Run:
    python test_suite.py
"""

from __future__ import annotations

import base64
import json
import sys
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.catalog import PRODUCTS
from app.config import MAINNET, Settings
from app.extract import PageExtract, parse_html
from app.main import (
    app,
    metadata_get,
    scrape_get,
    summary_get,
)
from app.payments import paid_routes
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


class DiscoveryRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_catalog(self) -> None:
        response = self.client.get("/v1/catalog")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        paths = {item["path"]: item["price"] for item in body["products"]}
        self.assertEqual(paths["/v1/scrape"], "$0.01")
        self.assertEqual(paths["/v1/summary"], "$0.02")
        self.assertEqual(paths["/v1/extract-metadata"], "$0.01")

    def test_llms_txt(self) -> None:
        response = self.client.get("/llms.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/v1/scrape", response.text)
        self.assertIn("/v1/summary", response.text)
        self.assertIn("/v1/extract-metadata", response.text)

    def test_openapi(self) -> None:
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertIn("/v1/scrape", paths)
        self.assertIn("/v1/summary", paths)
        self.assertIn("/v1/extract-metadata", paths)
        self.assertEqual(response.json()["info"]["x-x402"]["asset"], "USDC")

    def test_well_known_mcp(self) -> None:
        response = self.client.get("/.well-known/mcp")
        self.assertEqual(response.status_code, 200)
        tools = {item["path"] for item in response.json()["tools"]}
        self.assertEqual(tools, {"/v1/scrape", "/v1/summary", "/v1/extract-metadata"})


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


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
