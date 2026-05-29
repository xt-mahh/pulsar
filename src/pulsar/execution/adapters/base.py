"""BasePlatformAdapter — abstract base class for all platform adapters.

Each adapter encapsulates one social media platform (WeChat, Weibo, Xiaohongshu, etc.)
and provides a uniform tool-call interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    """Tool definition consumed by upper layers (Task Layer / PIP)."""
    name: str                                     # Tool name (e.g. "wechat.create_draft")
    description: str                              # Tool description
    input_schema: dict                            # Input JSON Schema
    output_schema: dict = field(default_factory=dict)  # Output JSON Schema
    category: str = ""                            # Category (e.g. "wechat", "auth")


class AdapterError(Exception):
    """Base exception for adapter errors."""


class AdapterInitError(AdapterError):
    """Raised when adapter initialization fails."""


class AdapterAuthError(AdapterError):
    """Raised when authentication fails."""


class AdapterRateLimitError(AdapterError):
    """Raised when API rate limit is exceeded."""


class BasePlatformAdapter(ABC):
    """Abstract base for all platform adapters.

    Subclasses must implement:
        - initialize(config) -> bool
        - get_tools() -> list[ToolDefinition]
        - handle_tool_call(tool_name, arguments) -> Any
    """

    # === Metadata (subclasses override) ===
    name: str = ""          # Adapter name (e.g. "wechat_official")
    platform: str = ""      # Platform id (e.g. "wechat")

    @abstractmethod
    async def initialize(self, config: dict) -> bool:
        """Initialize the adapter.

        Includes: load config, establish connections, validate credentials.

        Args:
            config: Adapter config section from pulsar.yaml.

        Returns:
            True if initialization succeeded.

        Raises:
            AdapterInitError: On initialization failure.
        """
        ...

    @abstractmethod
    async def get_tools(self) -> list[ToolDefinition]:
        """Return all tool definitions provided by this adapter.

        Each ToolDefinition corresponds to a tool callable via handle_tool_call().

        Returns:
            List of ToolDefinition objects.
        """
        ...

    @abstractmethod
    async def handle_tool_call(self, tool_name: str, arguments: dict) -> Any:
        """Route a tool call to the appropriate implementation.

        Args:
            tool_name: Tool name (from get_tools() return values).
            arguments: Already-validated tool arguments.

        Returns:
            Tool execution result.

        Raises:
            ToolExecutionError: On execution failure.
            AdapterAuthError: On auth failure (triggers re-login).
        """
        ...

    async def shutdown(self) -> None:
        """Clean up resources (connections, token cache, etc.)."""
        pass  # Subclasses may override
