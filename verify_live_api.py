"""QA sweep against the live Render x402 shop.

Usage:
    python verify_live_api.py
    python verify_live_api.py --base https://x402-markdown-scraper.onrender.com
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_BASE = "https://x402-markdown-scraper.onrender.com"
SAMPLE_URL = "https://example.com"
BASE_MAINNET = "eip155:8453"
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
FEATURED_PATHS = ("/v1/scrape", "/v1/summary", "/v1/extract-metadata")

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _enable_windows_color() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def paint(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"


def decode_payment_required(header: str) -> dict[str, Any]:
    padded = header + "=" * (-len(header) % 4)
    return json.loads(base64.b64decode(padded).decode("utf-8"))


def payment_header(response: httpx.Response) -> str | None:
    return response.headers.get("PAYMENT-REQUIRED") or response.headers.get("payment-required")


def base_accept(challenge: dict[str, Any]) -> dict[str, Any]:
    accepts = challenge.get("accepts") or []
    return next(
        (item for item in accepts if item.get("network") == BASE_MAINNET),
        accepts[0] if accepts else {},
    )


def usd_from_atomic(amount: str) -> str:
    return f"${int(amount) / 1_000_000:.2f}"


@dataclass
class Suite:
    passed: int = 0
    failed: int = 0
    details: list[str] = field(default_factory=list)

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        if ok:
            self.passed += 1
            suffix = f" {DIM}{detail}{RESET}" if detail else ""
            print(f"  {paint(GREEN, 'PASS')}  {label}{suffix}")
        else:
            self.failed += 1
            suffix = f" {paint(RED, detail)}" if detail else ""
            print(f"  {paint(RED, 'FAIL')}  {label}{suffix}")
            self.details.append(f"{label}: {detail}" if detail else label)


def get(client: httpx.Client, path: str, **kwargs: Any) -> httpx.Response:
    return client.get(path, **kwargs)


def verify_health(suite: Suite, client: httpx.Client) -> None:
    print(paint(BOLD, "1. GET /health"))
    response = get(client, "/health")
    suite.check(response.status_code == 200, "status is 200", str(response.status_code))
    try:
        body = response.json()
    except json.JSONDecodeError:
        suite.check(False, "JSON body", response.text[:120])
        return
    suite.check(body == {"status": "ok"}, "body is {\"status\": \"ok\"}", json.dumps(body))


def verify_catalog(suite: Suite, client: httpx.Client) -> None:
    print(paint(BOLD, "2. GET /v1/catalog"))
    response = get(client, "/v1/catalog")
    suite.check(response.status_code == 200, "status is 200", str(response.status_code))
    try:
        body = response.json()
    except json.JSONDecodeError:
        suite.check(False, "JSON body", response.text[:120])
        return
    products = body.get("products") or []
    paths = {item.get("path") for item in products}
    prices = {item.get("path"): item.get("price") for item in products}
    suite.check(bool(products), "catalog has products", f"count={len(products)}")
    for path in FEATURED_PATHS:
        suite.check(path in paths, f"lists {path}", prices.get(path, "missing"))
    suite.check(prices.get("/v1/scrape") == "$0.01", "/v1/scrape priced $0.01", str(prices.get("/v1/scrape")))
    suite.check(prices.get("/v1/summary") == "$0.02", "/v1/summary priced $0.02", str(prices.get("/v1/summary")))
    suite.check(
        prices.get("/v1/extract-metadata") == "$0.01",
        "/v1/extract-metadata priced $0.01",
        str(prices.get("/v1/extract-metadata")),
    )


def verify_llms(suite: Suite, client: httpx.Client) -> None:
    print(paint(BOLD, "3. GET /llms.txt"))
    response = get(client, "/llms.txt")
    suite.check(response.status_code == 200, "status is 200", str(response.status_code))
    text = response.text
    suite.check("text/plain" in response.headers.get("content-type", ""), "content-type is text/plain")
    suite.check("/v1/scrape" in text and "/v1/summary" in text, "mentions scrape and summary SKUs")
    suite.check("/v1/extract-metadata" in text, "mentions extract-metadata SKU")


def verify_openapi(suite: Suite, client: httpx.Client) -> None:
    print(paint(BOLD, "4. GET /openapi.json"))
    response = get(client, "/openapi.json")
    suite.check(response.status_code == 200, "status is 200", str(response.status_code))
    try:
        body = response.json()
    except json.JSONDecodeError:
        suite.check(False, "JSON body")
        return
    paths = body.get("paths") or {}
    suite.check("/v1/scrape" in paths, "documents /v1/scrape")
    suite.check("/v1/summary" in paths, "documents /v1/summary")
    suite.check("/v1/extract-metadata" in paths, "documents /v1/extract-metadata")
    x402 = (body.get("info") or {}).get("x-x402") or {}
    suite.check(x402.get("asset") == "USDC", "info.x-x402.asset is USDC", str(x402.get("asset")))


def verify_paywall(
    suite: Suite,
    client: httpx.Client,
    path: str,
    expected_amount: str,
    expected_usd: str,
    title: str,
) -> None:
    print(paint(BOLD, title))
    response = get(client, path, params={"url": SAMPLE_URL})
    suite.check(response.status_code == 402, "status is 402 Payment Required", str(response.status_code))
    header = payment_header(response)
    suite.check(bool(header), "PAYMENT-REQUIRED header is present")
    if not header:
        print(paint(DIM, f"    body: {response.text[:200]}"))
        return
    try:
        challenge = decode_payment_required(header)
    except (ValueError, json.JSONDecodeError) as exc:
        suite.check(False, "PAYMENT-REQUIRED is base64 JSON", str(exc))
        return

    option = base_accept(challenge)
    amount = str(option.get("amount", ""))
    pay_to = option.get("payTo") or option.get("pay_to")
    asset = option.get("asset")
    resource = challenge.get("resource") or {}

    print(
        paint(
            CYAN,
            f"    payTo={pay_to}  amount={amount} ({usd_from_atomic(amount) if amount.isdigit() else 'n/a'})  "
            f"network={option.get('network')}  scheme={option.get('scheme')}",
        )
    )

    suite.check(challenge.get("x402Version") == 2, "x402Version is 2", str(challenge.get("x402Version")))
    suite.check(option.get("scheme") == "exact", "scheme is exact", str(option.get("scheme")))
    suite.check(option.get("network") == BASE_MAINNET, "network is Base mainnet", str(option.get("network")))
    suite.check(
        amount == expected_amount,
        f"amount is {expected_amount} ({expected_usd} USDC)",
        f"{amount} {usd_from_atomic(amount) if amount.isdigit() else ''}".strip(),
    )
    suite.check(
        isinstance(pay_to, str) and pay_to.startswith("0x") and len(pay_to) == 42,
        "wallet payTo is a 42-char 0x address",
        str(pay_to),
    )
    suite.check(
        isinstance(asset, str) and asset.lower() == BASE_USDC.lower(),
        "asset is Base USDC",
        str(asset),
    )
    suite.check(path in (resource.get("url") or ""), "resource.url includes this path", str(resource.get("url")))
    suite.check(bool(resource.get("description")), "resource.description is set")
    bazaar = (challenge.get("extensions") or {}).get("bazaar")
    suite.check(bool(bazaar), "extensions.bazaar is present")


def main() -> int:
    _enable_windows_color()
    parser = argparse.ArgumentParser(description="Verify the live Render x402 API.")
    parser.add_argument("--base", default=DEFAULT_BASE, help="Deployment origin")
    parser.add_argument("--timeout", type=float, default=90.0, help="HTTP timeout (Render cold start)")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(paint(BOLD, f"Live QA  {base}"))
    print(paint(YELLOW, "Free-tier hosts may take ~30s on the first request after idle.\n"))

    suite = Suite()
    try:
        with httpx.Client(base_url=base, timeout=args.timeout, follow_redirects=True) as client:
            verify_health(suite, client)
            verify_catalog(suite, client)
            verify_llms(suite, client)
            verify_openapi(suite, client)
            verify_paywall(
                suite,
                client,
                "/v1/scrape",
                "10000",
                "$0.01",
                "5. GET /v1/scrape?url=https://example.com",
            )
            verify_paywall(
                suite,
                client,
                "/v1/summary",
                "20000",
                "$0.02",
                "6. GET /v1/summary?url=https://example.com",
            )
            verify_paywall(
                suite,
                client,
                "/v1/extract-metadata",
                "10000",
                "$0.01",
                "7. GET /v1/extract-metadata?url=https://example.com",
            )
    except httpx.RequestError as exc:
        print(paint(RED, f"\nNetwork error: {exc}"))
        return 2

    print()
    if suite.failed:
        print(paint(RED, f"{suite.failed} failed, {suite.passed} passed"))
        for item in suite.details:
            print(paint(RED, f"  - {item}"))
        return 1
    print(paint(GREEN, f"All {suite.passed} checks passed."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
