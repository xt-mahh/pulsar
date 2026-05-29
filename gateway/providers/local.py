"""本地模型提供商 — 连接本地运行的 LLM 服务（llama.cpp / Ollama 等）"""

import logging
from typing import Any

import httpx

from gateway.providers.base import BaseProvider, LLMResponse, ProviderConfig

logger = logging.getLogger("pulsar.gateway.providers.local")


class LocalProvider(BaseProvider):
    """本地模型提供商

    适用于：
    - llama.cpp 服务器（OpenAI 兼容模式）
    - Ollama API
    - vLLM 本地部署
    - 任何本地运行的 OpenAI 兼容 API
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._http: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return f"local:{self.config.model}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=60.0,  # 本地模型通常较慢
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
        """发送聊天请求到本地模型"""
        client = await self._get_client()

        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        body.update(kwargs)

        try:
            response = await client.post("/v1/chat/completions", json=body)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except httpx.ConnectError:
            logger.warning(
                f"本地模型 {self.config.model} 连接失败 "
                f"({self.config.base_url})，返回降级响应"
            )
            return LLMResponse(
                content="[本地模型不可用]",
                model=self.config.model,
                provider=self.name,
                usage={"input": 0, "output": 0},
                cost=0.0,
                raw={"error": "connection_failed"},
            )
        except httpx.TimeoutException:
            logger.warning(f"本地模型 {self.config.model} 请求超时")
            return LLMResponse(
                content="[本地模型请求超时]",
                model=self.config.model,
                provider=self.name,
                usage={"input": 0, "output": 0},
                cost=0.0,
                raw={"error": "timeout"},
            )

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
            cost=0.0,  # 本地模型免费
            raw=data,
        )

    async def count_tokens(self, text: str) -> int:
        """估算 token 数"""
        char_count = len(text)
        return char_count // 3 + 1

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._http:
            await self._http.aclose()
            self._http = None