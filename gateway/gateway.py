"""LLM 统一调用接口 — 整合 Router + TokenCounter，提供统一的 LLM 访问入口"""

import asyncio
import logging
from typing import Any

from gateway.router import ModelRouter
from gateway.tokens import TokenCounter

logger = logging.getLogger("pulsar.gateway.gateway")


class LLMGateway:
    """LLM 统一调用接口

    整合多模型路由、Token 计数、成本追踪、超时控制和重试逻辑。
    系统中所有需要 LLM 能力的组件通过此接口访问。
    """

    def __init__(self, config: dict[str, Any]):
        """初始化 LLM Gateway

        Args:
            config: gateway 配置段
        """
        self._config = config
        self._router = ModelRouter(config)
        self._counter = TokenCounter(
            daily_budget=config.get("daily_budget", 0.0)
        )
        self._timeout = config.get("timeout", 30)
        self._max_retries = config.get("max_retries", 3)
        self._retry_delay = config.get("retry_delay", 2)
        self._initialized = False

    async def initialize(self) -> None:
        """初始化 Gateway（加载提供商配置）"""
        if self._initialized:
            return
        await self._router.initialize()
        self._initialized = True
        providers = self._router.list_providers()
        logger.info(
            f"LLM Gateway 初始化完成，"
            f"已加载 {len(providers)} 个提供商"
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        provider: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """统一的 LLM 聊天接口

        Args:
            messages: 消息列表，格式：[{"role": "user", "content": "..."}]
            temperature: 温度参数 (0.0-2.0)
            max_tokens: 最大输出 token 数
            provider: 指定使用的提供商，None 则使用默认
            **kwargs: 传递给提供商的额外参数

        Returns:
            包含响应内容和元数据的字典：
            {
                "content": "模型回复内容",
                "model": "使用的模型名称",
                "provider": "使用的提供商",
                "usage": {"input": int, "output": int},
                "cost": float,
                "raw": dict,  # 原始 API 响应
            }

        Raises:
            RuntimeError: 所有提供商都失败时
        """
        if not self._initialized:
            await self.initialize()

        # 预算检查
        within_budget, today_cost = self._counter.check_budget()
        if not within_budget:
            logger.warning(
                f"今日预算已超限 (${today_cost:.4f})，"
                f"拒绝本次调用"
            )
            return {
                "content": "[预算超限，调用被拒绝]",
                "model": "budget_control",
                "provider": "system",
                "usage": {"input": 0, "output": 0},
                "cost": 0.0,
                "raw": {"error": "budget_exceeded"},
            }

        # 如果指定了提供商，直接使用
        if provider:
            target = self._router.get_provider(provider)
            if target is None:
                raise ValueError(
                    f"提供商 '{provider}' 未配置，"
                    f"可用: {[p['name'] for p in self._router.list_providers()]}"
                )
            try:
                response = await target.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
            except Exception as e:
                logger.error(
                    f"指定提供商 '{provider}' 调用失败: {e}"
                )
                raise

            self._counter.record(
                provider=response.provider,
                model=response.model,
                input_tokens=response.usage.get("input", 0),
                output_tokens=response.usage.get("output", 0),
                cost=response.cost,
            )
            return response.to_dict()

        # 使用 Router 的自动 Fallback
        response = await self._router.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        self._counter.record(
            provider=response.provider,
            model=response.model,
            input_tokens=response.usage.get("input", 0),
            output_tokens=response.usage.get("output", 0),
            cost=response.cost,
        )
        return response.to_dict()

    async def chat_with_retry(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """带重试的 LLM 调用

        在失败时自动重试，使用指数退避策略。

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            **kwargs: 额外参数

        Returns:
            包含响应内容和元数据的字典
        """
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return await self.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
            except Exception as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._retry_delay * (2**attempt)
                    logger.warning(
                        f"LLM 调用失败 (第 {attempt + 1} 次)，"
                        f"{delay}s 后重试: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"LLM 调用已重试 {self._max_retries} 次，"
                        f"全部失败: {e}"
                    )

        return {
            "content": f"[LLM 调用失败: {last_error}]",
            "model": "error",
            "provider": "system",
            "usage": {"input": 0, "output": 0},
            "cost": 0.0,
            "raw": {"error": str(last_error)},
        }

    def get_usage_stats(self) -> dict[str, Any]:
        """获取使用统计"""
        return {
            "daily": self._counter.get_daily_usage(),
            "total": self._counter.get_total_usage(),
        }

    def get_recent_calls(
        self, limit: int = 10
    ) -> list[dict[str, Any]]:
        """获取最近的调用记录"""
        return self._counter.get_recent_calls(limit=limit)

    def list_providers(self) -> list[dict[str, str]]:
        """列出所有已注册的提供商"""
        return self._router.list_providers()

    async def close(self) -> None:
        """关闭 Gateway，释放资源"""
        await self._router.close()
        self._initialized = False
        logger.info("LLM Gateway 已关闭")