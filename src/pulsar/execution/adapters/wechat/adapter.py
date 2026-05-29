"""WeChatAdapter — WeChat Official Account platform adapter.

Provides 24+ tools for draft management, publishing, material management,
statistics, menus, users, comments, tags, QR codes, and messaging.
"""

import logging
from typing import Any

from pulsar.execution.adapters.base import (
    AdapterAuthError,
    AdapterInitError,
    BasePlatformAdapter,
    ToolDefinition,
)
from pulsar.execution.adapters.wechat.auth import WeChatTokenManager
from pulsar.execution.adapters.wechat.tools import (
    ALL_WECHAT_TOOLS,
    WeChatAPIError,
    register_all_wechat_tools,
    set_adapter,
)
from pulsar.execution.tools.base import ToolExecutionError
from pulsar.execution.tools.registry import get_registry

logger = logging.getLogger(__name__)


class WeChatAdapter(BasePlatformAdapter):
    """WeChat Official Account platform adapter.

    Capabilities:
        - Token auto-refresh (memory / file / encrypted file)
        - Draft management (create, read, update, delete, list)
        - Publish management (submit, status, delete, schedule)
        - Permanent material (image, audio, video, thumbnail)
        - Temporary material upload
        - Statistics (article, user, interface)
        - Menu management (create, get, delete, conditional)
        - User management (info, followers)
        - Comment management (list)
        - Tag management (list)
        - Auto-reply rules (get)
        - Template messages (send)
        - QR code creation
    """

    name = "wechat_official"
    platform = "wechat"

    def __init__(self):
        self._token_manager: WeChatTokenManager | None = None
        self._base_url: str = "https://api.weixin.qq.com"
        self._tools: list = list(ALL_WECHAT_TOOLS)
        self._initialized = False
        self._config: dict = {}

    async def initialize(self, config: dict) -> bool:
        """Initialize the WeChat adapter.

        Config structure (from pulsar.yaml adapters.wechat):
            credentials:
                app_id: str
                app_secret: str
            token:
                auto_refresh: bool (default: true)
                refresh_ahead_seconds: int (default: 300)
                storage: str (memory|file|encrypted_file)
                encrypt_key: str (optional)
                storage_path: str (optional)
            network:
                proxy: str (optional)
                connect_timeout: int
                read_timeout: int
        """
        self._config = config
        creds = config.get("credentials", {})
        app_id = creds.get("app_id", "")
        app_secret = creds.get("app_secret", "")

        if not app_id or not app_secret:
            raise AdapterInitError("WeChat adapter requires app_id and app_secret")

        self._base_url = config.get("base_url", "https://api.weixin.qq.com")

        token_config = config.get("token", {})
        self._token_manager = WeChatTokenManager(
            app_id=app_id,
            app_secret=app_secret,
            base_url=self._base_url,
            auto_refresh=token_config.get("auto_refresh", True),
            refresh_ahead=token_config.get("refresh_ahead_seconds", 300),
            storage=token_config.get("storage", "memory"),
            encrypt_key=token_config.get("encrypt_key"),
            storage_path=token_config.get("storage_path"),
        )

        # Set the global adapter reference for tools
        set_adapter(self)

        # Initialize token
        initialized = await self._token_manager.initialize()
        if not initialized:
            raise AdapterInitError("WeChat token initialization failed")

        # Register all WeChat tools in the global ToolRegistry
        try:
            register_all_wechat_tools()
        except Exception as e:
            logger.warning("Tool registration error (may already be registered): %s", e)

        self._initialized = True
        logger.info(
            "WeChatAdapter initialized (app_id=%s, storage=%s)",
            app_id[:6] + "...",
            token_config.get("storage", "memory"),
        )
        return True

    async def get_tools(self) -> list[ToolDefinition]:
        """Return all tool definitions provided by this adapter."""
        return [tool.to_definition() for tool in self._tools]

    async def handle_tool_call(self, tool_name: str, arguments: dict) -> Any:
        """Route a tool call to the appropriate WeChat tool implementation.

        Args:
            tool_name: Tool name (e.g. "wechat.create_draft").
            arguments: Tool arguments (already validated).

        Returns:
            Tool execution result.

        Raises:
            ToolExecutionError: On execution failure.
            AdapterAuthError: On auth failure (triggers re-login).
        """
        if not self._initialized:
            raise RuntimeError("WeChatAdapter not initialized. Call initialize() first.")

        # Look up tool
        tool_instance = None
        for t in self._tools:
            if t.name == tool_name:
                tool_instance = t
                break

        if tool_instance is None:
            raise ToolExecutionError(
                message=f"Unknown WeChat tool: '{tool_name}'",
                tool_name=tool_name,
            )

        try:
            result = await tool_instance.execute(**arguments)
            return result
        except WeChatAPIError as e:
            # If token expired, try refreshing once
            if e.errcode in (40001, 40014, 42001):
                logger.info("Token expired (errcode=%d), refreshing and retrying...", e.errcode)
                try:
                    await self._token_manager.get_token(force=True)
                    result = await tool_instance.execute(**arguments)
                    return result
                except Exception as retry_error:
                    raise AdapterAuthError(
                        f"WeChat auth failed after token refresh: {retry_error}"
                    ) from retry_error
            raise ToolExecutionError(
                message=f"WeChat API error (errcode={e.errcode}): {e.errmsg}",
                tool_name=tool_name,
                original=e,
            ) from e
        except Exception as e:
            raise ToolExecutionError(
                message=str(e),
                tool_name=tool_name,
                original=e,
            ) from e

    async def shutdown(self) -> None:
        """Clean up: close token manager, persist cache."""
        if self._token_manager:
            await self._token_manager.shutdown()
        self._initialized = False
        logger.info("WeChatAdapter shut down")
