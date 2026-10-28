"""Production audit against the live Render x402 v2 storefront.

Usage:
    python verify_production_live.py
    python verify_production_live.py --base https://x402-markdown-scraper.onrender.com
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

FEATURED = (
    ("/v1/scrape", "$0.01", "10000"),
    ("/v1/summary", "$0.02", "20000"),
    ("/v1/extract-metadata", "$0.01", "10000"),
    ("/v1/parse-pdf", "$0.05", "50000"),
    ("/v1/deep-crawl", "$0.15", "150000"),
)


@dataclass
class Row:
    endpoint: str
    status: str
    price: str
    paywall: str


@dataclass
class Suite:
    passed: int = 0
    failed: int = 0
    rows: list[Row] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        if ok:
            self.passed += 1
            print(f"  PASS  {label}" + (f"  ({detail})" if detail else ""))
        else:
            self.failed += 1
            note = f"{label}: {detail}" if detail else label
            self.details.append(note)
            print(f"  FAIL  {note}")
        return ok


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


def verify_health(suite: Suite, client: httpx.Client) -> None:
    print("\n## GET /health")
    response = client.get("/health")
    suite.check(response.status_code == 200, "status is 200", str(response.status_code))
    try:
        body = response.json()
    except json.JSONDecodeError:
        suite.check(False, "JSON body", response.text[:120])
        suite.rows.append(Row("GET /health", str(response.status_code), "free", "n/a"))
        return
    suite.check(body.get("status") == "ok", 'JSON status is "ok"', json.dumps(body))
    suite.rows.append(
        Row("GET /health", str(response.status_code), "free", "n/a (public)")
    )


def verify_root(suite: Suite, client: httpx.Client) -> None:
    print("\n## GET /")
    response = client.get("/")
    suite.check(response.status_code == 200, "status is 200", str(response.status_code))
    suite.check(response.status_code != 402, "root is not paywalled")
    ctype = response.headers.get("content-type", "")
    suite.check("text/html" in ctype, "content-type is HTML", ctype)
    for path in ("/v1/scrape", "/v1/summary", "/v1/extract-metadata", "/v1/parse-pdf", "/v1/deep-crawl"):
        suite.check(path in response.text, f"root lists {path}")
    suite.rows.append(Row("GET /", str(response.status_code), "portal", "n/a (public HTML)"))


def verify_catalog(suite: Suite, client: httpx.Client) -> None:
    print("\n## GET /v1/catalog")
    response = client.get("/v1/catalog")
    suite.check(response.status_code == 200, "status is 200", str(response.status_code))
    try:
        body = response.json()
    except json.JSONDecodeError:
        suite.check(False, "JSON body", response.text[:160])
        suite.rows.append(Row("GET /v1/catalog", str(response.status_code), "free", "n/a"))
        return
    prices = {item.get("path"): item.get("price") for item in (body.get("products") or [])}
    for path, price, _amount in FEATURED:
        suite.check(prices.get(path) == price, f"{path} priced {price}", str(prices.get(path)))
    suite.rows.append(Row("GET /v1/catalog", str(response.status_code), "5 featured SKUs", "n/a (public)"))


def verify_discovery(suite: Suite, client: httpx.Client) -> None:
    print("\n## GET /llms.txt")
    llms = client.get("/llms.txt")
    suite.check(llms.status_code == 200, "status is 200", str(llms.status_code))
    for path, _price, _amount in FEATURED:
        suite.check(path in llms.text, f"llms.txt lists {path}")
    suite.rows.append(Row("GET /llms.txt", str(llms.status_code), "discovery", "n/a (public)"))

    print("\n## GET /openapi.json")
    spec = client.get("/openapi.json")
    suite.check(spec.status_code == 200, "status is 200", str(spec.status_code))
    try:
        body = spec.json()
    except json.JSONDecodeError:
        suite.check(False, "JSON body")
        suite.rows.append(Row("GET /openapi.json", str(spec.status_code), "discovery", "n/a"))
        return
    paths = body.get("paths") or {}
    for path, price, _amount in FEATURED:
        suite.check(path in paths, f"openapi documents {path}")
        get_op = (paths.get(path) or {}).get("get") or {}
        x402 = get_op.get("x-x402") or {}
        suite.check(x402.get("price") == price, f"openapi {path} GET x-x402.price {price}", str(x402.get("price")))
    info = body.get("info") or {}
    info_x402 = info.get("x-x402") or {}
    suite.check(info.get("version") == "0.5.0", "openapi info.version is 0.5.0 (v2)", str(info.get("version")))
    suite.check(info_x402.get("asset") == "USDC", "info.x-x402.asset is USDC", str(info_x402.get("asset")))
    suite.rows.append(
        Row("GET /openapi.json", str(spec.status_code), f"v{info.get('version')}", "n/a (public)")
    )

    print("\n## GET /.well-known/mcp")
    mcp = client.get("/.well-known/mcp")
    suite.check(mcp.status_code == 200, "status is 200", str(mcp.status_code))
    try:
        tools = {item.get("path"): item.get("price") for item in (mcp.json().get("tools") or [])}
    except json.JSONDecodeError:
        suite.check(False, "JSON body", mcp.text[:160])
        suite.rows.append(Row("GET /.well-known/mcp", str(mcp.status_code), "discovery", "n/a"))
        return
    for path, price, _amount in FEATURED:
        suite.check(tools.get(path) == price, f"mcp tool {path} {price}", str(tools.get(path)))
    suite.rows.append(Row("GET /.well-known/mcp", str(mcp.status_code), "discovery", "n/a (public)"))


def verify_unpaid(
    suite: Suite,
    client: httpx.Client,
    method: str,
    path: str,
    price: str,
    expected_amount: str,
) -> None:
    print(f"\n## {method} {path} (unpaid)")
    if method == "GET":
        response = client.get(path, params={"url": SAMPLE_URL})
    else:
        payload: dict[str, Any] = {"url": SAMPLE_URL}
        if path == "/v1/deep-crawl":
            payload["max_depth"] = 2
        response = client.post(path, json=payload)

    label = f"{method} {path}"
    ok_status = suite.check(response.status_code == 402, "status is 402", str(response.status_code))
    header = payment_header(response)
    suite.check(bool(header), "PAYMENT-REQUIRED header present")
    if not header:
        suite.rows.append(
            Row(label, str(response.status_code), price, "FAIL missing PAYMENT-REQUIRED")
        )
        return

    try:
        challenge = decode_payment_required(header)
    except (ValueError, json.JSONDecodeError) as exc:
        suite.check(False, "PAYMENT-REQUIRED is base64 JSON", str(exc))
        suite.rows.append(Row(label, str(response.status_code), price, "FAIL invalid challenge"))
        return

    option = base_accept(challenge)
    amount = str(option.get("amount", ""))
    pay_to = option.get("payTo") or option.get("pay_to")
    asset = option.get("asset")
    resource = challenge.get("resource") or {}

    suite.check(challenge.get("x402Version") == 2, "x402Version is 2", str(challenge.get("x402Version")))
    suite.check(option.get("scheme") == "exact", "scheme is exact", str(option.get("scheme")))
    suite.check(option.get("network") == BASE_MAINNET, "network is eip155:8453", str(option.get("network")))
    suite.check(amount == expected_amount, f"amount is {expected_amount}", amount)
    suite.check(
        isinstance(pay_to, str) and pay_to.startswith("0x") and len(pay_to) == 42,
        "payTo is 42-char 0x",
        str(pay_to),
    )
    suite.check(
        isinstance(asset, str) and asset.lower() == BASE_USDC.lower(),
        "asset is Base USDC",
        str(asset),
    )
    suite.check(path in str(resource.get("url") or ""), "resource.url includes path", str(resource.get("url")))

    paywall = (
        f"402 x402 v2 exact {price} on {option.get('network')}"
        if ok_status and amount == expected_amount
        else f"FAIL status={response.status_code} amount={amount}"
    )
    suite.rows.append(Row(label, str(response.status_code), price, paywall))


def print_report(suite: Suite, base: str) -> None:
    print("\n# Production audit report")
    print(f"\nTarget: `{base}`\n")
    print("| Endpoint | HTTP | Price | x402 paywall |")
    print("|---|---|---|---|")
    for row in suite.rows:
        print(f"| `{row.endpoint}` | {row.status} | {row.price} | {row.paywall} |")
    print()
    if suite.failed:
        print(f"**Result:** {suite.failed} failed, {suite.passed} passed. Storefront is **not** fully operational.")
        for item in suite.details:
            print(f"- {item}")
    else:
        print(f"**Result:** all {suite.passed} checks passed. Live storefront is **100% operational** for unpaid discovery and x402 402 handshakes.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Live production audit for the x402 v2 shop.")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"Live production audit  {base}")
    print("Free-tier hosts may take ~30s on the first request after idle.")

    suite = Suite()
    try:
        with httpx.Client(base_url=base, timeout=args.timeout, follow_redirects=True) as client:
            verify_health(suite, client)
            verify_root(suite, client)
            verify_catalog(suite, client)
            verify_discovery(suite, client)
            for path, price, amount in FEATURED:
                verify_unpaid(suite, client, "GET", path, price, amount)
                verify_unpaid(suite, client, "POST", path, price, amount)
    except httpx.RequestError as exc:
        print(f"\nNetwork error: {exc}")
        return 2

    print_report(suite, base)
    return 1 if suite.failed else 0


if __name__ == "__main__":
    sys.exit(main())
