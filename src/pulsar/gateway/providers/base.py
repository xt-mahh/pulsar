"""BaseProvider — abstract base class for LLM providers with connection pool management."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)


# ── Response types ────────────────────────────────────────────────────────


class ToolCall:
    """Represents a function/tool call requested by the LLM."""

    def __init__(self, id: str, name: str, args: dict[str, Any]) -> None:
        self.id = id
        self.name = name
        self.args = args

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "args": self.args}


class ChatResponse:
    """Unified response from any LLM provider."""

    def __init__(
        self,
        content: str = "",
        tool_calls: list[ToolCall] | None = None,
        model: str = "",
        usage: dict[str, int] | None = None,
        finish_reason: str = "",
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.model = model
        self.usage = usage or {}
        self.finish_reason = finish_reason


class ChatChunk:
    """A single streaming chunk from any LLM provider."""

    def __init__(
        self,
        content: str = "",
        tool_calls: list[ToolCall] | None = None,
        finish_reason: str = "",
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason


# ── Base Provider ─────────────────────────────────────────────────────────


class BaseProvider(ABC):
    """Abstract base class for LLM providers.

    Each provider holds its own ``httpx.AsyncClient`` connection pool to avoid
    per-request TCP handshake overhead.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init the HTTPX client (connection pool reuse)."""
        if self._client is None:
            limits = httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0,
            )
            self._client = httpx.AsyncClient(
                base_url=self.config.get("base_url", ""),
                timeout=httpx.Timeout(self.config.get("timeout", 30.0)),
                limits=limits,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the connection pool. Called when the provider is destroyed."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── abstract methods ──────────────────────────────────────────────────

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send a chat completion request (non-streaming)."""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatChunk]:
        """Send a chat completion request (streaming)."""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        ...

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a text string."""
        ...
