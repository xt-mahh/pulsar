"""多模型路由 — 按配置选择默认/备用提供商，支持 Fallback 链"""

import logging
from typing import Any

from gateway.providers.base import BaseProvider, LLMResponse, ProviderConfig
from gateway.providers.local import LocalProvider
from gateway.providers.openai import OpenAIProvider

logger = logging.getLogger("pulsar.gateway.router")


class ModelRouter:
    """多模型路由

    根据配置选择默认提供商，在失败时自动切换到备用提供商。
    支持链式 Fallback：default → fallback → local。
    """

    def __init__(self, config: dict[str, Any]):
        """初始化路由

        Args:
            config: gateway 配置段，格式：
                {
                    "default_provider": "deepseek",
                    "fallback_provider": "local",
                    "timeout": 30,
                    "max_retries": 3,
                    "retry_delay": 2,
                    "providers": {
                        "deepseek": {...},
                        "local": {...},
                    }
                }
        """
        self._config = config
        self._providers: dict[str, BaseProvider] = {}
        self._default_name = config.get("default_provider", "")
        self._fallback_name = config.get("fallback_provider", "")
        self._timeout = config.get("timeout", 30)
        self._max_retries = config.get("max_retries", 3)
        self._retry_delay = config.get("retry_delay", 2)

    async def initialize(self) -> None:
        """初始化所有配置的提供商"""
        providers_config = self._config.get("providers", {})
        for name, cfg in providers_config.items():
            provider = self._create_provider(name, cfg)
            if provider:
                self._providers[name] = provider
                logger.info(f"已注册提供商: {name} ({provider.model})")

        if self._default_name not in self._providers:
            logger.warning(
                f"默认提供商 '{self._default_name}' 未配置，"
                f"可用: {list(self._providers.keys())}"
            )

    def _create_provider(
        self, name: str, cfg: dict[str, Any]
    ) -> BaseProvider | None:
        """根据配置创建提供商实例"""
        try:
            provider_config = ProviderConfig(
                type=cfg.get("type", "openai"),
                base_url=cfg.get("base_url", ""),
                api_key=cfg.get("api_key", ""),
                model=cfg.get("model", ""),
                max_tokens=cfg.get("max_tokens", 4096),
                cost_per_1k_input=cfg.get("cost_per_1k_input", 0.0),
                cost_per_1k_output=cfg.get("cost_per_1k_output", 0.0),
                extra=cfg.get("extra", {}),
            )

            provider_type = provider_config.type
            if provider_type == "openai":
                return OpenAIProvider(provider_config)
            elif provider_type == "local":
                return LocalProvider(provider_config)
            else:
                logger.warning(f"未知的提供商类型: {provider_type}")
                return None
        except Exception as e:
            logger.error(f"创建提供商 '{name}' 失败: {e}")
            return None

    def get_provider(self, name: str | None = None) -> BaseProvider | None:
        """获取指定名称的提供商

        Args:
            name: 提供商名称，None 则返回默认提供商

        Returns:
            提供商实例，不存在则返回 None
        """
        provider_name = name if name is not None else self._default_name
        if provider_name not in self._providers:
            return None
        return self._providers[provider_name]

    def list_providers(self) -> list[dict[str, str]]:
        """列出所有已注册的提供商"""
        return [
            {
                "name": name,
                "model": p.model,
                "type": p.config.type,
                "is_default": name == self._default_name,
                "is_fallback": name == self._fallback_name,
            }
            for name, p in self._providers.items()
        ]

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送聊天请求，带自动 Fallback

        尝试顺序：默认提供商 → Fallback 提供商 → 本地模型

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            **kwargs: 额外参数

        Returns:
            LLM 调用响应

        Raises:
            RuntimeError: 所有提供商都失败时
        """
        # 构建尝试链
        attempt_order: list[str] = []
        if self._default_name and self._default_name in self._providers:
            attempt_order.append(self._default_name)
        if (
            self._fallback_name
            and self._fallback_name != self._default_name
            and self._fallback_name in self._providers
        ):
            attempt_order.append(self._fallback_name)

        # 如果还有未在链中的提供商，追加作为最后兜底
        for name in self._providers:
            if name not in attempt_order:
                attempt_order.append(name)

        last_error: Exception | None = None
        for provider_name in attempt_order:
            provider = self._providers[provider_name]
            try:
                logger.info(
                    f"尝试提供商: {provider_name} ({provider.model})"
                )
                return await provider.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
            except Exception as e:
                logger.warning(
                    f"提供商 '{provider_name}' 调用失败: {e}"
                )
                last_error = e
                continue

        error_msg = (
            f"所有提供商均调用失败，已尝试: {attempt_order}"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg) from last_error

    async def close(self) -> None:
        """关闭所有提供商，释放资源"""
        for name, provider in self._providers.items():
            if hasattr(provider, "close"):
                try:
                    await provider.close()  # type: ignore[union-attr]
                except Exception as e:
                    logger.warning(f"关闭提供商 '{name}' 时出错: {e}")
        self._providers.clear()