"""OpenAI 兼容 API 提供商 — 支持 DeepSeek / Claude / 本地模型的 OpenAI 格式 API"""

import logging
from typing import Any

import httpx

from gateway.providers.base import BaseProvider, LLMResponse, ProviderConfig

logger = logging.getLogger("pulsar.gateway.providers.openai")


class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 API 提供商

    适用于：
    - OpenAI GPT 系列
    - DeepSeek API
    - 任何兼容 OpenAI /v1/chat/completions 格式的 API
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._http: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return f"openai:{self.config.model}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._http

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送聊天请求到 OpenAI 兼容 API"""
        client = await self._get_client()

        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        body.update(kwargs)

        response = await client.post("/v1/chat/completions", json=body)
        response.raise_for_status()
        data: dict[str, Any] = response.json()

        choice = data["choices"][0]
        content = choice["message"]["content"] or ""

        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=content,
            model=data.get("model", self.config.model),
            provider=self.name,
            usage={"input": input_tokens, "output": output_tokens},
            cost=self.calculate_cost(input_tokens, output_tokens),
            raw=data,
        )

    async def count_tokens(self, text: str) -> int:
        """估算 token 数

        使用简单估算：英文约 1 token/4 字符，中文约 1 token/2 字符
        """
        # 粗略估算：中英文混合
        char_count = len(text)
        # 假设中英文各半
        return char_count // 3 + 1

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._http:
            await self._http.aclose()
            self._http = None