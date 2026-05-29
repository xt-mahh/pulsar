"""OpenAI-compatible LLM provider — also handles DeepSeek, Groq, and other OpenAI-compatible APIs."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from pulsar.gateway.providers.base import BaseProvider, ChatResponse, ChatChunk, ToolCall

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """Provider for any OpenAI-compatible API (OpenAI, DeepSeek, Groq, Together, etc.).

    Config keys (from ``config.yaml``):
    - ``base_url``: API base URL (e.g. ``https://api.openai.com/v1``)
    - ``api_key``: API key
    - ``model``: Model name (e.g. ``gpt-4o``, ``deepseek-chat``)
    - ``max_tokens``: Max output tokens
    - ``temperature``: Sampling temperature (0.0–2.0)
    - ``top_p``: Top-p sampling
    - ``timeout``: Request timeout in seconds
    - ``retry``: Dict with ``max_retries``, ``base_delay_ms``, ``max_delay_ms``
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._model = config.get("model", "gpt-4o")
        self._api_key = config.get("api_key", "")
        self._max_tokens = config.get("max_tokens", 4096)
        self._temperature = config.get("temperature", 0.7)
        self._top_p = config.get("top_p", 0.95)

        retry_cfg = config.get("retry", {})
        self._max_retries = retry_cfg.get("max_retries", 3)
        self._base_delay_ms = retry_cfg.get("base_delay_ms", 1000)
        self._max_delay_ms = retry_cfg.get("max_delay_ms", 30000)

    # ── chat ──────────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send a non-streaming chat completion request."""
        if stream:
            # Collect streaming chunks into a single response
            chunks: list[ChatChunk] = []
            async for chunk in self.chat_stream(messages, tools, tool_choice, **kwargs):
                chunks.append(chunk)
            return self._merge_chunks(chunks)

        body = self._build_body(messages, tools, tool_choice, **kwargs)
        body["stream"] = False

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                client = await self._get_client()
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
                resp = await client.post(
                    "/chat/completions",
                    json=body,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                return self._parse_response(data)
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    delay = self._backoff_delay(attempt)
                    logger.warning(
                        "OpenAI API error (attempt %d/%d): %s — retrying in %.2fs",
                        attempt + 1, self._max_retries, exc, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("OpenAI API failed after %d attempts", self._max_retries + 1)

        raise RuntimeError(f"OpenAI API request failed: {last_error}")

    # ── streaming ─────────────────────────────────────────────────────────

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatChunk]:
        """Stream a chat completion response."""
        body = self._build_body(messages, tools, tool_choice, **kwargs)
        body["stream"] = True
        body["stream_options"] = {"include_usage": False}

        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        async with client.stream(
            "POST",
            "/chat/completions",
            json=body,
            headers=headers,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if line == "data: [DONE]":
                    break
                if not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                chunk = self._parse_stream_chunk(data)
                if chunk is not None:
                    yield chunk

    # ── embeddings ────────────────────────────────────────────────────────

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via the OpenAI-compatible embeddings endpoint."""
        body = {
            "model": self._model,
            "input": texts,
        }
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        resp = await client.post("/embeddings", json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]

    # ── token counting ────────────────────────────────────────────────────

    async def count_tokens(self, text: str) -> int:
        """Estimate token count (heuristic: ~4 chars per token)."""
        return len(text) // 4 + 1  # rough approximation

    # ── internal helpers ──────────────────────────────────────────────────

    def _build_body(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build the JSON request body for the /chat/completions endpoint."""
        body: dict[str, Any] = {
            "model": kwargs.get("model", self._model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "temperature": kwargs.get("temperature", self._temperature),
            "top_p": kwargs.get("top_p", self._top_p),
        }

        if tools:
            body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice
        elif tool_choice:
            body["tool_choice"] = tool_choice

        # Response format for structured output
        response_model = kwargs.get("response_model")
        if response_model:
            body["response_format"] = {"type": "json_object"}

        return body

    def _parse_response(self, data: dict[str, Any]) -> ChatResponse:
        """Parse a non-streaming API response into a ChatResponse."""
        choices = data.get("choices", [])
        if not choices:
            return ChatResponse()

        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "") or ""
        finish_reason = choice.get("finish_reason", "")

        tool_calls: list[ToolCall] = []
        for tc_data in message.get("tool_calls") or []:
            tc = ToolCall(
                id=tc_data.get("id", ""),
                name=tc_data["function"]["name"],
                args=json.loads(tc_data["function"].get("arguments", "{}")),
            )
            tool_calls.append(tc)

        usage = data.get("usage", {})
        model = data.get("model", self._model)

        return ChatResponse(
            content=content,
            tool_calls=tool_calls,
            model=model,
            usage=usage,
            finish_reason=finish_reason,
        )

    def _parse_stream_chunk(self, data: dict[str, Any]) -> ChatChunk | None:
        """Parse a single SSE stream chunk into a ChatChunk."""
        choices = data.get("choices", [])
        if not choices:
            return None

        delta = choices[0].get("delta", {})
        content = delta.get("content", "") or ""
        finish_reason = choices[0].get("finish_reason", "")

        tool_calls: list[ToolCall] = []
        for tc_data in delta.get("tool_calls") or []:
            fn = tc_data.get("function", {})
            # Streaming tool calls may arrive in multiple chunks
            tc = ToolCall(
                id=tc_data.get("id", ""),
                name=fn.get("name", ""),
                args=json.loads(fn.get("arguments", "{}")) if fn.get("arguments") else {},
            )
            tool_calls.append(tc)

        if not content and not tool_calls and not finish_reason:
            return None

        return ChatChunk(content=content, tool_calls=tool_calls, finish_reason=finish_reason)

    def _merge_chunks(self, chunks: list[ChatChunk]) -> ChatResponse:
        """Merge streaming chunks into a single ChatResponse."""
        content = "".join(c.content for c in chunks if c.content)
        finish_reason = chunks[-1].finish_reason if chunks else ""
        return ChatResponse(content=content, finish_reason=finish_reason)

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter."""
        import random
        delay = min(self._base_delay_ms * (2**attempt), self._max_delay_ms) / 1000.0
        jitter = random.uniform(0, delay * 0.1)
        return delay + jitter


# Fix forward reference
import asyncio
import httpx
