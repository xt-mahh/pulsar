import time
import httpx
from shared.errors import AuthError


class WeChatTokenManager:
    def __init__(self, app_id: str, app_secret: str, api_base: str = "https://api.weixin.qq.com", cache_ttl: int = 7200):
        self.app_id = app_id
        self.app_secret = app_secret
        self.api_base = api_base
        self.cache_ttl = cache_ttl
        self._token: str | None = None
        self._expires_at: float = 0
        self._refresh_buffer: int = 300

    async def get_token(self) -> str:
        if self._token and time.time() < self._expires_at - self._refresh_buffer:
            return self._token
        return await self._refresh(stable=False)

    async def get_stable_token(self) -> str:
        return await self._refresh(stable=True)

    async def _refresh(self, stable: bool = False) -> str:
        if stable:
            url = f"{self.api_base}/cgi-bin/stable_token"
            payload = {
                "grant_type": "client_credential",
                "appid": self.app_id,
                "secret": self.app_secret,
                "force_refresh": False,
            }
        else:
            url = f"{self.api_base}/cgi-bin/token"
            payload = {
                "grant_type": "client_credential",
                "appid": self.app_id,
                "secret": self.app_secret,
            }

        async with httpx.AsyncClient() as client:
            if stable:
                response = await client.post(url, json=payload)
            else:
                response = await client.get(url, params=payload)
            data = response.json()

        if "access_token" not in data:
            raise AuthError(f"Failed to get access_token: {data.get('errmsg', 'unknown error')}")

        self._token = data["access_token"]
        expires_in = data.get("expires_in", self.cache_ttl)
        self._expires_at = time.time() + expires_in
        return self._token