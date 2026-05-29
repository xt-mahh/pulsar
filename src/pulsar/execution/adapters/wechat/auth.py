"""WeChatTokenManager — manages WeChat access_tokens with auto-refresh and encrypted file cache."""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx


class WeChatAuthError(Exception):
    """Raised when WeChat authentication fails."""


class WeChatRateLimitError(Exception):
    """Raised when WeChat API rate limit is exceeded."""


class WeChatTokenManager:
    """WeChat Access Token manager.

    Responsibilities:
        - Obtain access_token via AppID + AppSecret
        - Auto-refresh before expiry
        - Encrypted/plain file persistence
        - Stable token endpoint support
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        base_url: str = "https://api.weixin.qq.com",
        auto_refresh: bool = True,
        refresh_ahead: int = 300,          # Refresh 5 minutes before expiry
        storage: str = "memory",            # memory | file | encrypted_file
        encrypt_key: Optional[str] = None,
        storage_path: Optional[str] = None,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._base_url = base_url.rstrip("/")
        self._auto_refresh = auto_refresh
        self._refresh_ahead = refresh_ahead
        self._storage = storage
        self._storage_path = storage_path or "./data/wechat/token_cache.json"
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None
        self._token: str | None = None
        self._expires_at: float = 0.0       # Unix timestamp
        self._logger = logging.getLogger(f"{__name__}.WeChatTokenManager")

    # ── Initialization ───────────────────────────────────────────────

    async def initialize(self) -> bool:
        """Initialize the token manager: load cached token or fetch new one."""
        loaded = await self._load_token()
        if loaded and self._expires_at > time.time() + 60:
            self._logger.info(
                "Restored token from cache, expires at %s",
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._expires_at)),
            )
        else:
            await self.get_token(force=True)

        if self._auto_refresh:
            self._start_auto_refresh()

        return self._token is not None

    # ── Token acquisition ────────────────────────────────────────────

    async def get_token(self, force: bool = False) -> str:
        """Get a valid access_token.

        Args:
            force: If True, force a fresh fetch even if cached token is valid.

        Returns:
            Access token string.
        """
        async with self._lock:
            if not force and self._token and self._expires_at > time.time():
                return self._token

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._base_url}/cgi-bin/token",
                    params={
                        "grant_type": "client_credential",
                        "appid": self._app_id,
                        "secret": self._app_secret,
                    },
                )
                data = response.json()

            if "access_token" not in data:
                err = data.get("errmsg", "Unknown error")
                errcode = data.get("errcode", -1)
                if errcode in (40001, 40002, 40125):
                    raise WeChatAuthError(f"Auth failed: {err} (errcode={errcode})")
                if errcode == 45009:
                    raise WeChatRateLimitError(f"Daily token limit exceeded: {err}")
                raise WeChatAuthError(f"Token fetch failed: {err} (errcode={errcode})")

            self._token = data["access_token"]
            self._expires_at = time.time() + data.get("expires_in", 7200)
            await self._save_token()
            return self._token

    async def get_stable_token(self, force: bool = False) -> str:
        """Get a stable access_token via the reliable POST endpoint.

        The stable endpoint returns the same token for repeated requests,
        making it suitable for high-concurrency scenarios.
        """
        async with self._lock:
            if not force and self._token and self._expires_at > time.time():
                return self._token

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._base_url}/cgi-bin/stable_token",
                    json={
                        "grant_type": "client_credential",
                        "appid": self._app_id,
                        "secret": self._app_secret,
                        "force_refresh": force,
                    },
                )
                data = response.json()

            if "access_token" not in data:
                raise WeChatAuthError(
                    f"Stable token fetch failed: {data.get('errmsg', 'unknown')}"
                )

            self._token = data["access_token"]
            self._expires_at = time.time() + data.get("expires_in", 7200)
            await self._save_token()
            return self._token

    async def get_valid_token(self) -> str:
        """Return the current cached token if valid, or fetch a new one."""
        return await self.get_token(force=False)

    # ── Auto-refresh ─────────────────────────────────────────────────

    def _start_auto_refresh(self) -> None:
        """Start the background token refresh loop."""
        async def refresh_loop():
            while True:
                sleep_time = max(
                    1,
                    (self._expires_at - self._refresh_ahead) - time.time(),
                )
                await asyncio.sleep(sleep_time)

                try:
                    self._logger.info("Auto-refreshing token...")
                    await self.get_token(force=True)
                    self._logger.info("Token refreshed successfully")
                except Exception as e:
                    self._logger.error("Token auto-refresh failed: %s", e)
                    await asyncio.sleep(30)  # Retry after 30s

        self._refresh_task = asyncio.create_task(refresh_loop())

    # ── Persistence ──────────────────────────────────────────────────

    async def _save_token(self) -> None:
        """Persist the current token to storage."""
        if self._storage == "memory" or self._token is None:
            return

        token_data = {
            "token": self._token,
            "expires_at": self._expires_at,
            "updated_at": time.time(),
        }
        path = self._storage_path
        os.makedirs(os.path.dirname(path), exist_ok=True)

        data_str = json.dumps(token_data)

        # Encrypt if using encrypted_file storage
        if self._storage == "encrypted_file":
            try:
                from cryptography.fernet import Fernet
                key = self._derive_fernet_key()
                cipher = Fernet(key)
                data_str = cipher.encrypt(data_str.encode()).decode()
            except ImportError:
                self._logger.warning("cryptography not installed; falling back to plain file")

        async with asyncio.get_event_loop().run_in_executor(
            None, lambda: Path(path).write_text(data_str)
        ):
            pass

    async def _load_token(self) -> bool:
        """Load a cached token from persistent storage."""
        if self._storage == "memory":
            return False

        path = self._storage_path
        try:
            loop = asyncio.get_event_loop()

            def _read():
                return Path(path).read_text()

            data_str = await loop.run_in_executor(None, _read)

            # Decrypt if encrypted
            if self._storage == "encrypted_file":
                try:
                    from cryptography.fernet import Fernet
                    key = self._derive_fernet_key()
                    cipher = Fernet(key)
                    data_str = cipher.decrypt(data_str.encode()).decode()
                except ImportError:
                    self._logger.warning("cryptography not installed; reading as plain")

            token_data = json.loads(data_str)
            self._token = token_data["token"]
            self._expires_at = token_data["expires_at"]
            return True
        except (FileNotFoundError, json.JSONDecodeError, KeyError, Exception):
            return False

    # ── Key derivation ───────────────────────────────────────────────

    def _derive_fernet_key(self, encrypt_key: str | None = None) -> bytes:
        """Derive a 32-byte Fernet-compatible key from the encrypt_key."""
        import base64
        import hashlib

        key = encrypt_key or self._app_secret
        raw = hashlib.sha256(key.encode()).digest()
        return base64.urlsafe_b64encode(raw)

    # ── Shutdown ─────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Cancel the refresh task and persist the current token."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        await self._save_token()
