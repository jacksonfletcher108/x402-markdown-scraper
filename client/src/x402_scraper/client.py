"""httpx client with automatic x402 v2 Exact USDC settlement on Base."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://x402-markdown-scraper.onrender.com"
BASE_NETWORK = "eip155:8453"


class ScraperError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _check_private_key(key: str) -> None:
    """Fail early with a readable message; never echo the key itself."""
    body = key[2:] if key.lower().startswith("0x") else key
    is_hex = all(char in "0123456789abcdefABCDEF" for char in body)
    if is_hex and len(body) == 64:
        return
    if is_hex and len(body) == 40:
        raise ValueError(
            "EVM_PRIVATE_KEY looks like a wallet address (40 hex characters), not a private key. "
            "Export the account's private key (64 hex characters) from your wallet instead."
        )
    raise ValueError(
        f"EVM_PRIVATE_KEY must be 64 hex characters (optionally 0x-prefixed); got {len(body)} characters"
        + ("" if is_hex else " including non-hex characters")
        + ". Check you copied the private key, not a recovery phrase or address."
    )


class ScraperClient:
    """Call all five featured SKUs. On HTTP 402, the x402 SDK signs an Exact
    (EIP-3009) USDC payment on Base and retries with PAYMENT-SIGNATURE.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        private_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.private_key = (private_key or os.environ.get("EVM_PRIVATE_KEY") or "").strip() or None
        if self.private_key:
            _check_private_key(self.private_key)
        self.timeout = timeout
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ScraperClient:
        self._http = self._build_http()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _build_http(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(self.timeout)
        if not self.private_key:
            return httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout,
                headers={"Accept": "application/json"},
            )
        from eth_account import Account
        from x402 import x402Client
        from x402.http.clients import x402HttpxClient
        from x402.mechanisms.evm import EthAccountSigner
        from x402.mechanisms.evm.exact.register import register_exact_evm_client

        payer = x402Client()
        register_exact_evm_client(payer, EthAccountSigner(Account.from_key(self.private_key)))
        return x402HttpxClient(
            payer,
            base_url=self.base_url,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = self._build_http()
        return self._http

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        http = await self._client()
        response = await http.get(path, params=params)
        if response.status_code == 402:
            raise ScraperError(
                "HTTP 402 Payment Required. Set EVM_PRIVATE_KEY so ScraperClient "
                "can sign Exact USDC on Base (eip155:8453) and attach PAYMENT-SIGNATURE.",
                status_code=402,
            )
        if response.status_code >= 400:
            detail = response.text[:240]
            raise ScraperError(f"{path} failed HTTP {response.status_code}: {detail}", response.status_code)
        return response.json()

    async def scrape(self, url: str) -> dict[str, Any]:
        """GET /v1/scrape — $0.01 USDC. Page to stripped Markdown."""
        return await self._get("/v1/scrape", {"url": url})

    async def summary(self, url: str) -> dict[str, Any]:
        """GET /v1/summary — $0.02 USDC. Three-bullet summary plus Markdown."""
        return await self._get("/v1/summary", {"url": url})

    async def extract_metadata(self, url: str) -> dict[str, Any]:
        """GET /v1/extract-metadata — $0.01 USDC. Open Graph, JSON-LD, author, date."""
        return await self._get("/v1/extract-metadata", {"url": url})

    async def parse_pdf(self, url: str) -> dict[str, Any]:
        """GET /v1/parse-pdf — $0.05 USDC. PDF URL to structured Markdown."""
        return await self._get("/v1/parse-pdf", {"url": url})

    async def deep_crawl(self, url: str, max_depth: int = 2) -> dict[str, Any]:
        """GET /v1/deep-crawl — $0.15 USDC. Same-host crawl, depth 1-3."""
        depth = max(1, min(int(max_depth), 3))
        return await self._get("/v1/deep-crawl", {"url": url, "max_depth": depth})

    async def aclose(self) -> None:
        await self.__aexit__()
