"""PIPBus — Pulsar Internal Protocol message bus over JSON-RPC 2.0.

Supports:
- In-process transport (asyncio.Queue) for same-process communication.
- stdio transport (JSON-line-delimited over stdin/stdout) for subprocess communication.
- All PIP methods: tools/call, tools/list, event/publish, event/subscribe, system/ping, system/status.
"""

from __future__ import annotations

import json
import logging
import asyncio
import uuid
from typing import Any, AsyncIterator, Callable, Awaitable

logger = logging.getLogger(__name__)

# ── Error codes (JSON-RPC 2.0 + PIP extensions) ──────────────────────────

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
TIMEOUT_ERROR = -32101
AUTH_FAILED = -32102
TOOL_EXEC_ERROR = -32104
RATE_LIMITED = -32107

ERROR_MESSAGES: dict[int, str] = {
    PARSE_ERROR: "Parse error",
    INVALID_REQUEST: "Invalid Request",
    METHOD_NOT_FOUND: "Method not found",
    TIMEOUT_ERROR: "Request timeout",
    AUTH_FAILED: "Auth failed",
    TOOL_EXEC_ERROR: "Tool execution error",
    RATE_LIMITED: "Rate limited",
}

# ── Data types ────────────────────────────────────────────────────────────


class PIPError(Exception):
    """JSON-RPC error with structured fields."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")


class PIPRequest:
    """Represents a JSON-RPC 2.0 request."""

    def __init__(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        self.jsonrpc = "2.0"
        self.method = method
        self.params = params or {}
        self.id = request_id or f"req-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict[str, Any]:
        return {"jsonrpc": self.jsonrpc, "id": self.id, "method": self.method, "params": self.params}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PIPRequest:
        return cls(
            method=data["method"],
            params=data.get("params", {}),
            request_id=data.get("id"),
        )


class PIPResponse:
    """Represents a JSON-RPC 2.0 response (success or error)."""

    def __init__(self, request_id: str | None, result: Any = None, error: dict | None = None) -> None:
        self.jsonrpc = "2.0"
        self.id = request_id
        self.result = result
        self.error = error

    @property
    def is_success(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def success(cls, request_id: str | None, result: Any = None) -> PIPResponse:
        return cls(request_id, result=result)

    @classmethod
    def error(cls, request_id: str | None, code: int, message: str, data: Any = None) -> PIPResponse:
        return cls(request_id, error={"code": code, "message": message, "data": data})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PIPResponse:
        return cls(
            request_id=data.get("id"),
            result=data.get("result"),
            error=data.get("error"),
        )

    @classmethod
    def parse(cls, line: str) -> PIPResponse:
        return cls.from_dict(json.loads(line))

    @classmethod
    def parse_request(cls, line: str) -> PIPRequest:
        return PIPRequest.from_dict(json.loads(line))


# ── Handler type ──────────────────────────────────────────────────────────

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


# ── Transport abstractions ────────────────────────────────────────────────


class InProcessTransport:
    """Same-process transport using asyncio.Queue pairs."""

    def __init__(self) -> None:
        self._request_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._response_queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def send(self, data: bytes) -> None:
        await self._request_queue.put(data)

    async def recv(self) -> bytes:
        return await self._request_queue.get()

    async def send_response(self, data: bytes) -> None:
        await self._response_queue.put(data)

    async def recv_response(self) -> bytes:
        return await self._response_queue.get()


class StdioTransport:
    """Subprocess transport over stdin/stdout with JSON-line delimiting."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer

    async def send(self, data: bytes) -> None:
        self._writer.write(data + b"\n")
        await self._writer.drain()

    async def recv(self) -> bytes:
        line = await self._reader.readline()
        if not line:
            raise ConnectionError("stdin closed")
        return line.rstrip(b"\n\r")

    async def close(self) -> None:
        if not self._writer.is_closing():
            self._writer.close()
            await self._writer.wait_closed()


# ── PIPBus ────────────────────────────────────────────────────────────────


class PIPBus:
    """Pulsar Internal Protocol message bus.

    Routes JSON-RPC 2.0 messages between components.  Supports in-process
    and stdio transports.  Provides a request/response pattern plus
    pub/sub for events.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self._pending: dict[str, asyncio.Future[PIPResponse]] = {}
        self._subscribers: dict[str, list[Callable[[str, Any], Awaitable[None]]]] = {}
        self._transport: InProcessTransport | StdioTransport | None = None
        self._running = False
        self._event_loop_task: asyncio.Task | None = None

        # Register default handlers
        self.register("system/ping", self._handle_ping)
        self.register("system/status", self._handle_status)

    # ── registration ──────────────────────────────────────────────────────

    def register(self, method: str, handler: Handler) -> None:
        """Register a handler for a PIP method."""
        self._handlers[method] = handler

    def unregister(self, method: str) -> None:
        self._handlers.pop(method, None)

    # ── transport binding ─────────────────────────────────────────────────

    def bind_in_process(self) -> InProcessTransport:
        """Bind an in-process transport and return it for use by the peer."""
        t = InProcessTransport()
        self._transport = t
        return t

    def bind_stdio(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> StdioTransport:
        t = StdioTransport(reader, writer)
        self._transport = t
        return t

    # ── request / response ────────────────────────────────────────────────

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        """Send a JSON-RPC request and wait for the response."""
        req = PIPRequest(method, params)
        future: asyncio.Future[PIPResponse] = asyncio.get_event_loop().create_future()
        self._pending[req.id] = future

        try:
            if self._transport is None:
                # In-process with direct handler dispatch
                resp = await self._dispatch_local(req)
                future.set_result(resp)
            else:
                await self._transport.send(req.to_json().encode("utf-8"))

            pip_resp = await asyncio.wait_for(future, timeout=timeout)
            if pip_resp.error:
                raise PIPError(pip_resp.error["code"], pip_resp.error["message"], pip_resp.error.get("data"))
            return pip_resp.result
        except asyncio.TimeoutError:
            raise PIPError(TIMEOUT_ERROR, f"Request timed out after {timeout}s")
        finally:
            self._pending.pop(req.id, None)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        """Convenience: call a tool via tools/call."""
        return await self.call("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout)

    async def list_tools(self, timeout: float = 10.0) -> list[dict[str, Any]]:
        """Convenience: list tools via tools/list."""
        result = await self.call("tools/list", timeout=timeout)
        return result.get("tools", []) if isinstance(result, dict) else []

    async def ping(self, timeout: float = 5.0) -> bool:
        """Convenience: health check via system/ping."""
        result = await self.call("system/ping", timeout=timeout)
        return isinstance(result, dict) and result.get("pong") is True

    # ── events (pub/sub) ──────────────────────────────────────────────────

    async def publish(self, event: str, data: Any = None) -> dict[str, Any]:
        """Publish an event — subscribers are notified asynchronously."""
        subscribers = self._subscribers.get(event, [])
        notified = 0
        for cb in subscribers:
            try:
                await cb(event, data)
                notified += 1
            except Exception:
                logger.exception("Event subscriber error for %s", event)
        return {"success": True, "subscribers_notified": notified}

    async def subscribe(self, events: list[str], callback: Callable[[str, Any], Awaitable[None]]) -> dict[str, Any]:
        """Subscribe to one or more event types."""
        sub_id = f"sub-{uuid.uuid4().hex[:8]}"
        for event in events:
            self._subscribers.setdefault(event, []).append(callback)
        return {"success": True, "subscription_id": sub_id}

    # ── server loop ───────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the message-processing loop (reads from transport or dispatches)."""
        if self._event_loop_task is not None:
            return
        self._running = True
        self._event_loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._event_loop_task:
            self._event_loop_task.cancel()
            try:
                await self._event_loop_task
            except asyncio.CancelledError:
                pass
            self._event_loop_task = None
        # Cancel all pending futures
        for future in self._pending.values():
            if not future.done():
                future.set_exception(PIPError(-32000, "Bus shutting down"))
        self._pending.clear()

    async def _loop(self) -> None:
        """Main message processing loop."""
        while self._running:
            try:
                if self._transport is None:
                    await asyncio.sleep(0.1)
                    continue

                data = await self._transport.recv()
                line = data.decode("utf-8")

                # Determine if it's a request or response
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError as exc:
                    # Send parse error back if we can identify the request
                    resp = PIPResponse.error(None, PARSE_ERROR, str(exc))
                    await self._send_response(resp)
                    continue

                # Response (has result or error, not method)
                if "method" not in parsed:
                    resp = PIPResponse.from_dict(parsed)
                    future = self._pending.pop(resp.id, None)
                    if future and not future.done():
                        future.set_result(resp)
                    continue

                # Request
                try:
                    req = PIPRequest.from_dict(parsed)
                except (KeyError, TypeError) as exc:
                    resp = PIPResponse.error(parsed.get("id"), INVALID_REQUEST, str(exc))
                    await self._send_response(resp)
                    continue

                asyncio.create_task(self._handle_request(req))
            except (ConnectionError, EOFError):
                logger.info("PIPBus transport closed")
                break
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("PIPBus loop error")

    async def _handle_request(self, req: PIPRequest) -> None:
        """Dispatch a single request and send the response."""
        try:
            handler = self._handlers.get(req.method)
            if handler is None:
                resp = PIPResponse.error(req.id, METHOD_NOT_FOUND, f"Method '{req.method}' not found")
            else:
                result = await handler(req.params)
                resp = PIPResponse.success(req.id, result)
        except PIPError as exc:
            resp = PIPResponse.error(req.id, exc.code, exc.message, exc.data)
        except Exception as exc:
            logger.exception("Handler error for %s", req.method)
            resp = PIPResponse.error(req.id, TOOL_EXEC_ERROR, str(exc))

        await self._send_response(resp)

    async def _send_response(self, resp: PIPResponse) -> None:
        if self._transport:
            await self._transport.send_response(resp.to_json().encode("utf-8"))
        else:
            # In-process without transport: resolve pending future
            future = self._pending.pop(resp.id, None)
            if future and not future.done():
                future.set_result(resp)

    async def _dispatch_local(self, req: PIPRequest) -> PIPResponse:
        """Direct dispatch for in-process mode (no serialization)."""
        try:
            handler = self._handlers.get(req.method)
            if handler is None:
                return PIPResponse.error(req.id, METHOD_NOT_FOUND, f"Method '{req.method}' not found")
            result = await handler(req.params)
            return PIPResponse.success(req.id, result)
        except PIPError as exc:
            return PIPResponse.error(req.id, exc.code, exc.message, exc.data)
        except Exception as exc:
            logger.exception("Local handler error for %s", req.method)
            return PIPResponse.error(req.id, TOOL_EXEC_ERROR, str(exc))

    # ── built-in handlers ─────────────────────────────────────────────────

    async def _handle_ping(self, params: dict[str, Any]) -> dict[str, Any]:
        from datetime import datetime, timezone
        return {"pong": True, "timestamp": datetime.now(timezone.utc).isoformat()}

    async def _handle_status(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "running", "active_tasks": len(self._pending)}
