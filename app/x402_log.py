from __future__ import annotations

import logging
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from x402.server import x402ResourceServer

log = logging.getLogger("x402.shop")

PAID_PREFIXES = (
    "/v1/scrape",
    "/scrape",
    "/v1/summary",
    "/v1/extract-metadata",
    "/v1/title",
    "/v1/text",
    "/v1/outline",
    "/v1/links",
)


def is_paid_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in PAID_PREFIXES)


class X402TraceMiddleware(BaseHTTPMiddleware):
    """Log paid-route hits and 402 PAYMENT-REQUIRED responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        paid = is_paid_path(path)
        if paid:
            has_sig = bool(
                request.headers.get("payment-signature") or request.headers.get("x-payment")
            )
            log.info(
                "x402 request %s %s payment_signature=%s",
                request.method,
                path,
                has_sig,
            )
        response = await call_next(request)
        if paid and response.status_code == 402:
            log.info(
                "x402 402 PAYMENT-REQUIRED sent for %s %s",
                request.method,
                path,
            )
        return response


def attach_payment_logs(server: x402ResourceServer) -> x402ResourceServer:
    def _before(ctx) -> None:
        requirements = getattr(ctx, "requirements", None) or getattr(ctx, "payment_requirements", None)
        network = getattr(requirements, "network", None) if requirements is not None else None
        log.info("x402 verifying payment network=%s", network)

    def _after(ctx) -> None:
        result = getattr(ctx, "result", None) or getattr(ctx, "verify", None)
        valid = getattr(result, "is_valid", True)
        log.info("x402 payment verified is_valid=%s", valid)

    def _failed(ctx) -> None:
        error = getattr(ctx, "error", None)
        log.warning("x402 payment verify failed: %s", error)

    def _settled(ctx) -> None:
        result = getattr(ctx, "result", None)
        tx = getattr(result, "transaction", None) if result is not None else None
        log.info("x402 payment settled transaction=%s", tx)

    server.on_before_verify(_before)
    server.on_after_verify(_after)
    server.on_verify_failure(_failed)
    server.on_after_settle(_settled)
    return server
