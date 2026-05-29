"""LLMGateway — unified multi-provider LLM interface with routing, fallback, and streaming."""

from __future__ import annotations

import logging
import re
from typing import Any, AsyncIterator

from .providers.base import BaseProvider, ChatResponse, ChatChunk
from pulsar.gateway.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)

# Model prefix → provider class mapping
MODEL_ROUTES: dict[str, type[BaseProvider]] = {
    "gpt-": OpenAIProvider,
    "deepseek-": OpenAIProvider,
    "o1-": OpenAIProvider,
    "o3-": OpenAIProvider,
}


class LLMGateway:
    """Unified LLM interface that routes requests to the correct provider.

    Features:
    - Automatic provider selection based on model name prefix
    - Multi-provider fallback chain
    - Streaming support
    - Structured output (response_model)
    - Tool/function calling
    - Per-provider connection pool management
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._providers: dict[str, BaseProvider] = {}
        self._provider_configs: dict[str, dict[str, Any]] = {}

        # Cache the provider configs from gateway config
        gw_cfg = self._config.get("gateway", self._config)
        self._default_provider_name = gw_cfg.get("default_provider", "deepseek")
        self._fallback_provider_name = gw_cfg.get("fallback_provider", "")
        self._timeout = gw_cfg.get("timeout", 30.0)
        self._max_retries = gw_cfg.get("max_retries", 3)

        provider_configs = gw_cfg.get("providers", {})
        if isinstance(provider_configs, dict):
            for name, pcfg in provider_configs.items():
                if isinstance(pcfg, dict):
                    self._provider_configs[name] = pcfg

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Create provider instances (lazy init with connection pools)."""
        for name, pcfg in self._provider_configs.items():
            try:
                provider = self._create_provider(name, pcfg)
                self._providers[name] = provider
                logger.debug("Provider '%s' initialized (%s)", name, type(provider).__name__)
            except Exception:
                logger.exception("Failed to initialize provider '%s'", name)

        if not self._providers:
            logger.warning("No LLM providers configured")

    async def close(self) -> None:
        """Close all provider connection pools."""
        for name, provider in self._providers.items():
            try:
                await provider.close()
                logger.debug("Provider '%s' closed", name)
            except Exception:
                logger.exception("Error closing provider '%s'", name)
        self._providers.clear()

    # ── chat API ──────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        stream: bool = False,
        response_model: type | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> ChatResponse:
        """Unified LLM chat completion.

        Args:
            messages: Chat messages in OpenAI format.
            tools: Tool definitions for function calling.
            tool_choice: ``"auto"``, ``"any"``, or ``"none"``.
            stream: If True, use chat_stream() instead.
            response_model: Pydantic model for structured output.
            temperature: Sampling temperature (overrides provider default).
            max_tokens: Max output tokens (overrides provider default).
            model: Model name (auto-routes to the right provider).
            provider: Explicit provider name to use.

        Returns:
            ChatResponse with content and/or tool_calls.
        """
        if stream:
            chunks: list[ChatChunk] = []
            async for chunk in self.chat_stream(
                messages, tools, tool_choice, response_model=response_model,
                temperature=temperature, max_tokens=max_tokens,
                model=model, provider=provider,
            ):
                chunks.append(chunk)
            return self._merge_chunks(chunks)

        prov, model_name = self._resolve_provider(model, provider)
        kwargs: dict[str, Any] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_model is not None:
            kwargs["response_model"] = response_model
        if model_name:
            kwargs["model"] = model_name

        try:
            return await prov.chat(
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                stream=False,
                **kwargs,
            )
        except Exception as exc:
            # Fallback
            return await self._fallback(exc, messages, tools, tool_choice, **kwargs)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_model: type | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Streaming version of chat()."""
        prov, model_name = self._resolve_provider(model, provider)
        kwargs: dict[str, Any] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_model is not None:
            kwargs["response_model"] = response_model
        if model_name:
            kwargs["model"] = model_name

        try:
            async for chunk in prov.chat_stream(
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                **kwargs,
            ):
                yield chunk
        except Exception as exc:
            # Fallback — non-streaming fallback, re-yield as chunks
            logger.warning("Stream failed, falling back: %s", exc)
            resp = await self._fallback(exc, messages, tools, tool_choice, **kwargs)
            yield ChatChunk(content=resp.content, finish_reason=resp.finish_reason)

    # ── embeddings ────────────────────────────────────────────────────────

    async def embed(
        self,
        texts: list[str],
        model: str | None = None,
        provider: str | None = None,
    ) -> list[list[float]]:
        """Generate embeddings via the routed provider."""
        prov, _ = self._resolve_provider(model, provider)
        return await prov.embed(texts)

    # ── token counting ────────────────────────────────────────────────────

    async def count_tokens(
        self,
        text: str,
        model: str | None = None,
        provider: str | None = None,
    ) -> int:
        """Count tokens via the routed provider."""
        prov, _ = self._resolve_provider(model, provider)
        return await prov.count_tokens(text)

    # ── provider management ───────────────────────────────────────────────

    def get_provider(self, name: str) -> BaseProvider | None:
        return self._providers.get(name)

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    # ── internals ─────────────────────────────────────────────────────────

    def _resolve_provider(
        self,
        model: str | None = None,
        provider: str | None = None,
    ) -> tuple[BaseProvider, str | None]:
        """Resolve the provider and effective model name.

        Priority:
        1. Explicit ``provider`` name
        2. Model prefix match (e.g. ``gpt-*`` → OpenAIProvider)
        3. Default provider
        4. First available provider
        """
        resolved_model = model

        # 1. Explicit provider
        if provider and provider in self._providers:
            return self._providers[provider], resolved_model

        # 2. Model-based routing
        if model:
            for prefix, prov_cls in MODEL_ROUTES.items():
                if model.startswith(prefix):
                    # Find a provider instance of this type
                    for pname, pinst in self._providers.items():
                        if isinstance(pinst, prov_cls):
                            return pinst, model
                    break

        # 3. Default provider
        if self._default_provider_name in self._providers:
            return self._providers[self._default_provider_name], resolved_model

        # 4. Fallback — first available
        if self._providers:
            name, inst = next(iter(self._providers.items()))
            logger.info("Falling back to provider '%s'", name)
            return inst, resolved_model

        raise RuntimeError("No LLM providers available")

    async def _fallback(
        self,
        original_error: Exception,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Try the fallback provider when the primary fails."""
        if not self._fallback_provider_name or self._fallback_provider_name not in self._providers:
            raise original_error

        logger.info("Attempting fallback to provider '%s'", self._fallback_provider_name)
        fallback_prov = self._providers[self._fallback_provider_name]
        try:
            return await fallback_prov.chat(
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                stream=False,
                **kwargs,
            )
        except Exception as fallback_error:
            raise RuntimeError(
                f"Primary provider failed ({original_error}) and fallback failed ({fallback_error})"
            ) from fallback_error

    def _merge_chunks(self, chunks: list[ChatChunk]) -> ChatResponse:
        content = "".join(c.content for c in chunks if c.content)
        finish_reason = chunks[-1].finish_reason if chunks else ""
        return ChatResponse(content=content, finish_reason=finish_reason)

    def _create_provider(self, name: str, pcfg: dict[str, Any]) -> BaseProvider:
        """Factory: create a provider from config."""
        provider_type = pcfg.get("type", "openai")

        if provider_type == "openai":
            return OpenAIProvider(pcfg)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
