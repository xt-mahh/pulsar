"""HTTP 请求工具 — 通用 HTTP/HTTPS 调用"""

import logging
from typing import Any

import httpx

from execution.tools.base import tool

logger = logging.getLogger("pulsar.tools.http")


@tool(name="http_request", description="发送 HTTP/HTTPS 请求到指定 URL")
async def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """通用 HTTP 请求工具

    Args:
        url: 请求目标 URL
        method: HTTP 方法 (GET/POST/PUT/DELETE/PATCH)
        headers: 请求头字典
        body: 请求体字符串（JSON 格式）
        timeout: 超时秒数

    Returns:
        {
            "status_code": 200,
            "headers": {...},
            "body": "..."
        }
    """
    method = method.upper()
    valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
    if method not in valid_methods:
        raise ValueError(f"不支持的 HTTP 方法: {method}，支持: {', '.join(valid_methods)}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers or {},
            content=body,
        )

        result: dict[str, Any] = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
        }

        # 尝试解析 JSON 响应
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type or "text/json" in content_type:
            try:
                result["json"] = response.json()
            except Exception:
                pass

        logger.debug(f"HTTP {method} {url} → {response.status_code}")
        return result