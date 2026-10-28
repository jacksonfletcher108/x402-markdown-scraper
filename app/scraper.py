from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.extract import PageExtract, parse_html

USER_AGENT = "x402-markdown-scraper/0.1"
PAYMENT_RESPONSE_HEADER = "PAYMENT-RESPONSE"


class ScrapeError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _is_private_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ScrapeError(f"Could not resolve host: {hostname}", status_code=400) from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return True
    return False


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ScrapeError("Only http and https URLs are allowed")
    if not parsed.hostname:
        raise ScrapeError("URL is missing a hostname")
    if parsed.hostname.lower() in {"localhost"}:
        raise ScrapeError("Localhost targets are not allowed")
    if _is_private_host(parsed.hostname):
        raise ScrapeError("Private or reserved IP targets are not allowed")
    return url


def _plain_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


async def _fetch_with_optional_payment(
    url: str,
    settings: Settings,
    pay_for_source: bool,
) -> tuple[httpx.Response, bool]:
    timeout = httpx.Timeout(settings.request_timeout_seconds)

    if pay_for_source and settings.evm_private_key:
        from app.compat import install_optional_stubs

        install_optional_stubs()
        from eth_account import Account
        from x402 import x402Client
        from x402.http.clients import x402HttpxClient
        from x402.mechanisms.evm import EthAccountSigner
        from x402.mechanisms.evm.exact.register import register_exact_evm_client

        client = x402Client()
        account = Account.from_key(settings.evm_private_key)
        register_exact_evm_client(client, EthAccountSigner(account))
        async with x402HttpxClient(
            client,
            timeout=timeout,
            follow_redirects=True,
            headers=_plain_headers(),
        ) as http:
            response = await http.get(url)
            paid = PAYMENT_RESPONSE_HEADER.lower() in {k.lower() for k in response.headers}
            return response, paid

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=_plain_headers(),
    ) as http:
        response = await http.get(url)
        return response, False


async def fetch_bytes(url: str, settings: Settings, *, max_bytes: int | None = None) -> tuple[bytes, str, int]:
    url = validate_url(url)
    try:
        response, _paid = await _fetch_with_optional_payment(url, settings, pay_for_source=False)
    except httpx.TimeoutException as exc:
        raise ScrapeError("Timed out fetching URL", status_code=504) from exc
    except httpx.RequestError as exc:
        raise ScrapeError(f"Could not fetch URL: {exc.__class__.__name__}", status_code=502) from exc
    if response.status_code >= 400:
        raise ScrapeError(f"Source returned HTTP {response.status_code}", status_code=502)
    validate_url(str(response.url))
    limit = max_bytes or settings.max_html_bytes
    return response.content[:limit], str(response.url), response.status_code


async def fetch_page(
    url: str,
    settings: Settings,
    pay_for_source: bool = True,
) -> PageExtract:
    url = validate_url(url)
    try:
        response, paid_source = await _fetch_with_optional_payment(url, settings, pay_for_source)
    except httpx.TimeoutException as exc:
        raise ScrapeError("Timed out fetching URL", status_code=504) from exc
    except httpx.TooManyRedirects as exc:
        raise ScrapeError("Too many redirects from source URL", status_code=502) from exc
    except httpx.RequestError as exc:
        raise ScrapeError(f"Could not fetch URL: {exc.__class__.__name__}", status_code=502) from exc

    if response.status_code == 402:
        raise ScrapeError(
            "Source returned 402 Payment Required. Set EVM_PRIVATE_KEY so the scraper "
            "can attach PAYMENT-SIGNATURE and retry.",
            status_code=402,
        )
    if response.status_code >= 400:
        raise ScrapeError(
            f"Source returned HTTP {response.status_code}",
            status_code=502,
        )

    final_url = str(response.url)
    validate_url(final_url)

    content_type = response.headers.get("content-type", "")
    raw = response.content[: settings.max_html_bytes]
    text = raw.decode(response.encoding or "utf-8", errors="replace")

    try:
        if "html" in content_type.lower() or text.lstrip().startswith("<"):
            page = parse_html(text, final_url)
        else:
            page = PageExtract(
                url=final_url,
                title=None,
                description=None,
                markdown=text.strip() or f"Fetched {final_url} but found no extractable text.",
                text=text.strip(),
            )
    except ScrapeError:
        raise
    except Exception as exc:
        raise ScrapeError("Failed to parse page content", status_code=502) from exc
    page.source_status = response.status_code
    page.paid_source = paid_source
    return page
