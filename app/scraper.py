from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

from app.config import Settings
from app.extract import PageExtract, parse_html

USER_AGENT = "x402-markdown-scraper/0.1"
PAYMENT_RESPONSE_HEADER = "PAYMENT-RESPONSE"
REDIRECT_STATUS = {301, 302, 303, 307, 308}
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.internal",
    "kubernetes.default",
    "kubernetes.default.svc",
}


class ScrapeError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _is_private_host(hostname: str) -> bool:
    host = hostname.strip("[]").lower()
    try:
        if _ip_is_blocked(ipaddress.ip_address(host)):
            return True
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ScrapeError(f"Could not resolve host: {hostname}", status_code=400) from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _ip_is_blocked(ip):
            return True
    return False


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ScrapeError("Only http and https URLs are allowed")
    if not parsed.hostname:
        raise ScrapeError("URL is missing a hostname")
    host = parsed.hostname.lower()
    if host in BLOCKED_HOSTNAMES or host.endswith(".localhost"):
        raise ScrapeError("Localhost or cloud-metadata targets are not allowed")
    if _is_private_host(parsed.hostname):
        raise ScrapeError("Private or reserved IP targets are not allowed")
    return url


def redirect_target(current_url: str, location: str | None) -> str:
    if not location or not location.strip():
        raise ScrapeError("Redirect missing Location header", status_code=502)
    next_url = urljoin(current_url, location.strip())
    return validate_url(next_url)


def _plain_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def _timeout(settings: Settings, timeout_seconds: float | None) -> httpx.Timeout:
    seconds = settings.request_timeout_seconds if timeout_seconds is None else timeout_seconds
    if seconds <= 0:
        raise ScrapeError("Timed out fetching URL", status_code=504)
    return httpx.Timeout(seconds)


def _size_cap(settings: Settings, max_bytes: int | None) -> int:
    requested = max_bytes if max_bytes is not None else settings.max_html_bytes
    return max(1, min(requested, settings.max_download_bytes))


async def _read_limited(response: httpx.Response, cap: int) -> bytes:
    declared = response.headers.get("content-length")
    if declared:
        try:
            if int(declared) > cap:
                raise ScrapeError("Response exceeded size limit", status_code=413)
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        if not chunk:
            continue
        total += len(chunk)
        if total > cap:
            raise ScrapeError("Response exceeded size limit", status_code=413)
        chunks.append(chunk)
    return b"".join(chunks)


def _classify_status(status_code: int) -> None:
    if status_code == 402:
        raise ScrapeError(
            "Source returned 402 Payment Required. Set EVM_PRIVATE_KEY so the scraper "
            "can attach PAYMENT-SIGNATURE and retry.",
            status_code=402,
        )
    if status_code >= 400:
        raise ScrapeError(f"Source returned HTTP {status_code}", status_code=502)


async def _fetch_plain(
    url: str,
    settings: Settings,
    *,
    max_bytes: int,
    timeout_seconds: float | None,
) -> tuple[bytes, str, int, str]:
    current = validate_url(url)
    timeout = _timeout(settings, timeout_seconds)
    hops = max(1, settings.max_redirects)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers=_plain_headers(),
    ) as http:
        for _ in range(hops + 1):
            try:
                async with http.stream("GET", current) as response:
                    if response.status_code in REDIRECT_STATUS:
                        current = redirect_target(current, response.headers.get("Location"))
                        continue
                    _classify_status(response.status_code)
                    body = await _read_limited(response, max_bytes)
                    final_url = str(response.url) if response.url else current
                    validate_url(final_url)
                    content_type = response.headers.get("content-type", "")
                    return body, final_url, response.status_code, content_type
            except ScrapeError:
                raise
            except httpx.TimeoutException as exc:
                raise ScrapeError("Timed out fetching URL", status_code=504) from exc
            except httpx.RequestError as exc:
                raise ScrapeError(
                    f"Could not fetch URL: {exc.__class__.__name__}",
                    status_code=502,
                ) from exc
    raise ScrapeError("Too many redirects from source URL", status_code=502)


async def _fetch_paid(
    url: str,
    settings: Settings,
    *,
    max_bytes: int,
    timeout_seconds: float | None,
) -> tuple[bytes, str, int, str, bool]:
    from app.compat import install_optional_stubs

    install_optional_stubs()
    from eth_account import Account
    from x402 import x402Client
    from x402.http.clients import x402HttpxClient
    from x402.mechanisms.evm import EthAccountSigner
    from x402.mechanisms.evm.exact.register import register_exact_evm_client

    current = validate_url(url)
    timeout = _timeout(settings, timeout_seconds)
    hops = max(1, settings.max_redirects)
    client = x402Client()
    account = Account.from_key(settings.evm_private_key)
    register_exact_evm_client(client, EthAccountSigner(account))
    async with x402HttpxClient(
        client,
        timeout=timeout,
        follow_redirects=False,
        headers=_plain_headers(),
    ) as http:
        for _ in range(hops + 1):
            try:
                response = await http.get(current)
            except httpx.TimeoutException as exc:
                raise ScrapeError("Timed out fetching URL", status_code=504) from exc
            except httpx.RequestError as exc:
                raise ScrapeError(
                    f"Could not fetch URL: {exc.__class__.__name__}",
                    status_code=502,
                ) from exc
            if response.status_code in REDIRECT_STATUS:
                current = redirect_target(current, response.headers.get("Location"))
                continue
            _classify_status(response.status_code)
            if len(response.content) > max_bytes:
                raise ScrapeError("Response exceeded size limit", status_code=413)
            final_url = str(response.url) if response.url else current
            validate_url(final_url)
            paid = PAYMENT_RESPONSE_HEADER.lower() in {k.lower() for k in response.headers}
            return (
                response.content[:max_bytes],
                final_url,
                response.status_code,
                response.headers.get("content-type", ""),
                paid,
            )
    raise ScrapeError("Too many redirects from source URL", status_code=502)


async def fetch_bytes(
    url: str,
    settings: Settings,
    *,
    max_bytes: int | None = None,
    timeout_seconds: float | None = None,
    pay_for_source: bool = False,
) -> tuple[bytes, str, int]:
    cap = _size_cap(settings, max_bytes)
    if pay_for_source and settings.evm_private_key:
        body, final_url, status, _ctype, _paid = await _fetch_paid(
            url, settings, max_bytes=cap, timeout_seconds=timeout_seconds
        )
        return body, final_url, status
    body, final_url, status, _ctype = await _fetch_plain(
        url, settings, max_bytes=cap, timeout_seconds=timeout_seconds
    )
    return body, final_url, status


async def fetch_page(
    url: str,
    settings: Settings,
    pay_for_source: bool = True,
    timeout_seconds: float | None = None,
) -> PageExtract:
    cap = _size_cap(settings, settings.max_html_bytes)
    if pay_for_source and settings.evm_private_key:
        raw, final_url, status, content_type, paid_source = await _fetch_paid(
            url, settings, max_bytes=cap, timeout_seconds=timeout_seconds
        )
    else:
        raw, final_url, status, content_type = await _fetch_plain(
            url, settings, max_bytes=cap, timeout_seconds=timeout_seconds
        )
        paid_source = False

    text = raw.decode("utf-8", errors="replace")
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
    page.source_status = status
    page.paid_source = paid_source
    return page
