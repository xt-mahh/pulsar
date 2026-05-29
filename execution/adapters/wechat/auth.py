"""微信 access_token 管理 — 带缓存与自动刷新"""

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("pulsar.adapter.wechat.auth")


class WeChatTokenManager:
    """微信 access_token 管理器

    负责 access_token 的获取、缓存和自动刷新。
    支持普通 token 和稳定版 token 两种获取方式。
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        api_base: str = "https://api.weixin.qq.com",
        cache_ttl: int = 7200,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.api_base = api_base.rstrip("/")
        self.cache_ttl = cache_ttl

        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._http = httpx.AsyncClient(timeout=15)

    async def get_token(self) -> str:
        """获取可用 access_token（优先使用缓存）

        Returns:
            有效的 access_token 字符串
        """
        if self._token and time.time() < self._token_expires_at:
            return self._token

        return await self._refresh(stable=False)

    async def get_stable_token(self) -> str:
        """获取稳定版 access_token（推荐用于定时任务）

        通过 POST /cgi-bin/stable_token 接口获取，
        该接口保证在有效期内 token 不会变化。

        Returns:
            有效的稳定版 access_token 字符串
        """
        return await self._refresh(stable=True)

    async def _refresh(self, stable: bool = False) -> str:
        """从微信服务器获取新的 access_token

        Args:
            stable: 是否获取稳定版 token

        Returns:
            新的 access_token 字符串
        """
        if stable:
            url = f"{self.api_base}/cgi-bin/stable_token"
            payload = {
                "grant_type": "client_credential",
                "appid": self.app_id,
                "secret": self.app_secret,
                "force_refresh": False,
            }
            response = await self._http.post(url, json=payload)
        else:
            url = f"{self.api_base}/cgi-bin/token"
            params = {
                "grant_type": "client_credential",
                "appid": self.app_id,
                "secret": self.app_secret,
            }
            response = await self._http.get(url, params=params)

        data: dict[str, Any] = response.json()

        if "access_token" not in data:
            error_msg = data.get("errmsg", "未知错误")
            error_code = data.get("errcode", -1)
            raise RuntimeError(f"获取 access_token 失败 [{error_code}]: {error_msg}")

        self._token = data["access_token"]
        expires_in = data.get("expires_in", 7200)

        # 提前 5 分钟刷新，避免边界情况
        self._token_expires_at = time.time() + expires_in - 300

        logger.info(
            f"access_token 已刷新 (稳定版={stable}), "
            f"有效期 {expires_in}s, "
            f"过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._token_expires_at))}"
        )

        return self._token

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        await self._http.aclose()