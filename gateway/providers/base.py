"""LLM 提供商基类 — 所有模型提供商必须实现此接口"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """LLM 调用响应"""

    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    """Token 使用情况，如 {"input": 100, "output": 50}"""

    cost: float = 0.0
    """本次调用的估算成本"""

    raw: dict[str, Any] = field(default_factory=dict)
    """原始 API 响应"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
            "cost": self.cost,
            "raw": self.raw,
        }


@dataclass
class ProviderConfig:
    """提供商配置"""

    type: str  # openai, anthropic, local
    base_url: str
    api_key: str
    model: str
    max_tokens: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)
    """提供商特定的额外配置"""


class BaseProvider(ABC):
    """LLM 提供商基类"""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """提供商名称"""
        ...

    @property
    def model(self) -> str:
        """当前使用的模型名称"""
        return self.config.model

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送聊天请求

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            **kwargs: 额外参数

        Returns:
            LLM 调用响应
        """
        ...

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """估算文本的 token 数

        Args:
            text: 输入文本

        Returns:
            估算的 token 数量
        """
        ...

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """计算调用成本

        Args:
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数

        Returns:
            估算成本（美元）
        """
        return (
            input_tokens * self.config.cost_per_1k_input / 1000
            + output_tokens * self.config.cost_per_1k_output / 1000
        )