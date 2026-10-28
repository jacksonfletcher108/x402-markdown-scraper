"""Stateless MCP Streamable HTTP endpoint with x402 payments per tool call.

Payment rides in params._meta["x402/payment"]; unpaid calls get an isError
result whose structuredContent is the x402 PaymentRequired (x402 MCP transport).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from x402.mcp.server_async import PaymentWrapperConfig, create_payment_wrapper
from x402.mcp.types import MCPToolResult, ResourceInfo
from x402.schemas.config import ResourceConfig
from x402.server import x402ResourceServer

from app.catalog import Product
from app.config import Settings
from app.payments import payment_options

log = logging.getLogger("x402.mcp")

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "x402-markdown-scraper", "title": "x402 Web Markdown Scraper", "version": "0.5.0"}
INSTRUCTIONS = (
    "Each tool call costs USDC on Base via x402. Call without payment to receive the "
    "PaymentRequired object in structuredContent, then retry with the signed payload "
    'in params._meta["x402/payment"]. The receipt is returned in result._meta["x402/payment-response"].'
)

ToolHandler = Callable[[dict[str, Any]], Awaitable[BaseModel]]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def tool_name(product: Product) -> str:
    return product.sku.replace(".", "_")


class McpServer:
    def __init__(self, server: x402ResourceServer, settings: Settings, public_host: str) -> None:
        self._server = server
        self._settings = settings
        self._public_host = public_host
        self._tools: dict[str, tuple[Product, ToolHandler]] = {}
        self._paid: dict[str, Callable[..., Awaitable[MCPToolResult]]] = {}
        self._init_lock = asyncio.Lock()

    def tool(self, product: Product, handler: ToolHandler) -> None:
        self._tools[tool_name(product)] = (product, handler)

    def tool_list(self) -> list[dict]:
        return [
            {
                "name": name,
                "title": product.name,
                "description": f"{product.description} Costs {product.price} USDC on Base via x402.",
                "inputSchema": product.query_schema,
                "annotations": {"readOnlyHint": True, "openWorldHint": True},
            }
            for name, (product, _) in self._tools.items()
        ]

    async def _paid_handler(self, name: str) -> Callable[..., Awaitable[MCPToolResult]]:
        """Build the x402 wrapper lazily: requirements need the facilitator's /supported."""
        async with self._init_lock:
            if name in self._paid:
                return self._paid[name]
            if not self._paid:
                await asyncio.to_thread(self._server.initialize)
            product, handler = self._tools[name]
            accepts = []
            for option in payment_options(self._settings, product.price):
                accepts.extend(
                    self._server.build_payment_requirements(
                        ResourceConfig(
                            scheme=option.scheme,
                            pay_to=option.pay_to,
                            price=option.price,
                            network=option.network,
                        )
                    )
                )
            wrapper = create_payment_wrapper(
                self._server,
                PaymentWrapperConfig(
                    accepts=accepts,
                    resource=ResourceInfo(
                        url=f"mcp://tool/{name}",
                        description=product.description,
                        mime_type="application/json",
                        service_name=product.name[:32],
                        tags=list(product.tags)[:5],
                    ),
                ),
            )

            async def run(args: dict[str, Any], _context: Any) -> MCPToolResult:
                try:
                    payload = await handler(args)
                except HTTPException as exc:
                    # isError makes the wrapper cancel settlement, so failed fetches are not charged.
                    return MCPToolResult(content=[{"type": "text", "text": str(exc.detail)}], is_error=True)
                data = payload.model_dump(mode="json")
                return MCPToolResult(
                    content=[{"type": "text", "text": json.dumps(data)}],
                    structured_content=data,
                )

            self._paid[name] = wrapper(run)
            return self._paid[name]

    async def _call_tool(self, params: dict) -> dict:
        name = params.get("name")
        if name not in self._tools:
            raise _RpcError(INVALID_PARAMS, f"Unknown tool: {name}")
        args = params.get("arguments") or {}
        if not isinstance(args, dict) or not isinstance(args.get("url"), str):
            raise _RpcError(INVALID_PARAMS, "arguments.url (string) is required")
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        paid = await self._paid_handler(name)
        result = await paid(args, {"_meta": meta, "toolName": name})
        body: dict[str, Any] = {"content": result.content, "isError": result.is_error}
        if result.structured_content is not None:
            body["structuredContent"] = result.structured_content
        if result.meta:
            body["_meta"] = result.meta
        return body

    async def _dispatch(self, message: Any) -> dict | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            return _error(None, INVALID_REQUEST, "Invalid JSON-RPC request")
        msg_id = message.get("id")
        if msg_id is None:
            return None  # notification
        method = message["method"]
        params = message.get("params") or {}
        try:
            if method == "initialize":
                requested = params.get("protocolVersion")
                version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
                result: dict = {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {**SERVER_INFO, "websiteUrl": self._public_host},
                    "instructions": INSTRUCTIONS,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tool_list()}
            elif method == "tools/call":
                result = await self._call_tool(params)
            else:
                raise _RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")
        except _RpcError as exc:
            return _error(msg_id, exc.code, exc.message)
        except Exception:
            log.exception("mcp %s failed", method)
            return _error(msg_id, -32603, "Internal error")
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    async def handle(self, request: Request) -> Response:
        try:
            message = json.loads(await request.body())
        except (ValueError, UnicodeDecodeError):
            return JSONResponse(_error(None, PARSE_ERROR, "Parse error"), status_code=400)
        if isinstance(message, list):
            replies = [reply for reply in [await self._dispatch(item) for item in message] if reply]
            return JSONResponse(replies) if replies else Response(status_code=202)
        reply = await self._dispatch(message)
        return JSONResponse(reply) if reply else Response(status_code=202)


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
