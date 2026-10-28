"""Live x402 paywall self-test against the public Render shop.

Usage:
    python test_client.py
    python test_client.py --base https://x402-markdown-scraper.onrender.com
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from typing import Any

import httpx

DEFAULT_BASE = "https://x402-markdown-scraper.onrender.com"
SCRAPE_URL = "https://example.com"
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
EXPECTED_AMOUNT = "10000"  # $0.01 USDC (6 decimals)
SELLER_FACILITATOR = "https://facilitator.payai.network"


def decode_payment_required(header: str) -> dict[str, Any]:
    padded = header + "=" * (-len(header) % 4)
    raw = base64.b64decode(padded)
    return json.loads(raw.decode("utf-8"))


def atomic_to_usd(amount: str) -> str:
    value = int(amount) / 1_000_000
    return f"${value:.2f}"


def check(ok: bool, label: str, failures: list[str]) -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}")
    if not ok:
        failures.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the live x402 scrape paywall.")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    target = f"{args.base.rstrip('/')}/v1/scrape"
    failures: list[str] = []

    print(f"GET {target}?url={SCRAPE_URL}")
    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        response = client.get(target, params={"url": SCRAPE_URL})

    print(f"status: {response.status_code}")
    check(response.status_code == 402, "HTTP 402 Payment Required", failures)

    header = response.headers.get("PAYMENT-REQUIRED") or response.headers.get("payment-required")
    check(bool(header), "PAYMENT-REQUIRED header present", failures)
    if not header:
        print(response.text[:500])
        return 1

    challenge = decode_payment_required(header)
    print("\nParsed PAYMENT-REQUIRED:")
    print(json.dumps(challenge, indent=2)[:4000])

    accepts = challenge.get("accepts") or []
    resource = challenge.get("resource") or {}
    extensions = challenge.get("extensions") or {}
    bazaar = extensions.get("bazaar") or {}

    base_option = next(
        (item for item in accepts if item.get("network") == "eip155:8453"),
        accepts[0] if accepts else {},
    )
    amount = str(base_option.get("amount", ""))
    pay_to = base_option.get("payTo") or base_option.get("pay_to")
    asset = base_option.get("asset")
    extra = base_option.get("extra") or {}

    print("\nChallenge parameters")
    print(f"  x402Version:     {challenge.get('x402Version')}")
    print(f"  price (atomic):  {amount} ({atomic_to_usd(amount) if amount.isdigit() else 'n/a'})")
    print(f"  wallet / payTo:  {pay_to}")
    print(f"  network:         {base_option.get('network')}")
    print(f"  scheme:          {base_option.get('scheme')}")
    print(f"  asset:           {asset}")
    print(f"  asset name:      {extra.get('name')}")
    print(f"  resource url:    {resource.get('url')}")
    print(f"  description:     {resource.get('description')}")
    print(f"  tags:            {resource.get('tags')}")
    print(f"  serviceName:     {resource.get('serviceName')}")
    print(
        "  facilitator URL: not included in 402 (seller-side). "
        f"This shop settles via {SELLER_FACILITATOR} unless CDP keys are set."
    )

    check(challenge.get("x402Version") == 2, "x402Version is 2", failures)
    check(bool(accepts), "accepts[] is non-empty", failures)
    check(base_option.get("scheme") == "exact", "scheme is exact", failures)
    check(base_option.get("network") == "eip155:8453", "network is Base mainnet eip155:8453", failures)
    check(amount == EXPECTED_AMOUNT, f"amount is {EXPECTED_AMOUNT} ($0.01 USDC)", failures)
    check(
        isinstance(pay_to, str) and pay_to.startswith("0x") and len(pay_to) == 42,
        "payTo is a 42-char 0x address",
        failures,
    )
    check(
        isinstance(asset, str) and asset.lower() == BASE_USDC.lower(),
        "asset is Base USDC",
        failures,
    )
    check("url" in (resource.get("url") or ""), "resource.url points at scrape", failures)
    check(bool(resource.get("description")), "resource.description is set", failures)
    check("Data" in (resource.get("tags") or []), "resource.tags includes Data", failures)
    check(bool(bazaar), "extensions.bazaar is present", failures)
    bazaar_info = bazaar.get("info") or {}
    bazaar_input = bazaar_info.get("input") or {}
    check(
        "url" in json.dumps(bazaar_input),
        "bazaar input declares url",
        failures,
    )
    check(
        bool((bazaar_info.get("output") or {}).get("example") or bazaar.get("schema")),
        "bazaar output example/schema present",
        failures,
    )

    if failures:
        print(f"\nPaywall is NOT fully compliant ({len(failures)} check(s) failed).")
        return 1
    print("\nPaywall is 100% compliant with the x402 v2 Exact USDC Base challenge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
