"""http_request tool — send HTTP requests using httpx.AsyncClient with connection pooling."""

import time
import json as json_module
from typing import Any

import httpx

from pulsar.execution.tools.registry import tool, get_registry

# Shared client pool with connection pooling
_client_pool: httpx.AsyncClient | None = None


def _get_client(timeout: int = 30, **kwargs) -> httpx.AsyncClient:
    """Get or create a shared httpx.AsyncClient with connection pooling."""
    global _client_pool
    if _client_pool is None:
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
            keepalive_expiry=30.0,
        )
        _client_pool = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=limits,
            follow_redirects=True,
            **kwargs,
        )
    return _client_pool


@tool(
    name="http_request",
    description="Send an HTTP request to a URL. Supports GET/POST/PUT/DELETE/PATCH/HEAD. "
                "Custom headers, body, timeout, and query params. Auto-follows redirects.",
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Target URL (must include protocol, e.g. https://api.example.com/v1)",
                "examples": ["https://api.weixin.qq.com/cgi-bin/token"],
            },
            "method": {
                "type": "string",
                "description": "HTTP method",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
                "default": "GET",
            },
            "headers": {
                "type": "object",
                "description": "Custom request headers (key-value pairs)",
                "default": {},
                "examples": [{"Content-Type": "application/json"}],
            },
            "body": {
                "type": ["object", "string", "null"],
                "description": "Request body. Dicts are auto-serialized to JSON.",
                "default": None,
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds",
                "default": 30,
                "minimum": 1,
                "maximum": 300,
            },
            "params": {
                "type": "object",
                "description": "URL query parameters (key-value pairs)",
                "default": {},
            },
        },
        "required": ["url"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "status_code": {"type": "integer", "description": "HTTP status code"},
            "headers": {"type": "object", "description": "Response headers"},
            "body": {"type": ["object", "string", "null"], "description": "Response body (JSON auto-parsed)"},
            "elapsed_ms": {"type": "integer", "description": "Request duration in milliseconds"},
        },
    },
)
async def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: Any = None,
    timeout: int = 30,
    params: dict | None = None,
) -> dict:
    """Send an HTTP request.

    Returns:
        {"status_code": 200, "headers": {...}, "body": {...}, "elapsed_ms": 234}

    Raises:
        httpx.HTTPError: On network/HTTP errors.
        ToolExecutionError: On unexpected failures.
    """
    headers = headers or {}
    params = params or {}

    # Auto-set Content-Type for JSON bodies
    if body is not None and "Content-Type" not in headers:
        if isinstance(body, dict):
            headers["Content-Type"] = "application/json"
            body = json_module.dumps(body)

    start = time.monotonic()
    client = _get_client(timeout=timeout)

    response = await client.request(
        method=method.upper(),
        url=url,
        headers=headers,
        content=body,
        params=params,
    )

    elapsed = int((time.monotonic() - start) * 1000)

    # Try to parse JSON response body
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type or "text/json" in content_type:
        try:
            result_body = response.json()
        except Exception:
            result_body = response.text
    else:
        result_body = response.text

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": result_body,
        "elapsed_ms": elapsed,
    }


async def shutdown_client() -> None:
    """Gracefully close the shared HTTP client pool."""
    global _client_pool
    if _client_pool is not None:
        await _client_pool.aclose()
        _client_pool = None


# Auto-register on import
__all__ = ["http_request", "shutdown_client"]
