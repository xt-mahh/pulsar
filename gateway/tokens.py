"""Token 计数与预算管理"""

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("pulsar.gateway.tokens")


class TokenUsage:
    """单次调用的 Token 使用记录"""

    def __init__(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
    ):
        self.provider = provider
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens
        self.cost = cost
        self.timestamp = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
            "timestamp": self.timestamp.isoformat(),
        }


class TokenCounter:
    """Token 计数器与成本追踪

    记录所有 LLM 调用的 Token 使用情况和成本，
    支持按时间段查询和预算检查。
    """

    def __init__(self, daily_budget: float = 0.0):
        """初始化 Token 计数器

        Args:
            daily_budget: 每日预算上限（美元），0 表示不限制
        """
        self._daily_budget = daily_budget
        self._records: list[TokenUsage] = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0

    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
    ) -> TokenUsage:
        """记录一次 Token 使用

        Args:
            provider: 提供商名称
            model: 模型名称
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
            cost: 本次调用成本

        Returns:
            创建的 Token 使用记录
        """
        usage = TokenUsage(provider, model, input_tokens, output_tokens, cost)
        self._records.append(usage)
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_cost += cost
        return usage

    def get_daily_usage(self) -> dict[str, Any]:
        """获取今日使用统计"""
        today = datetime.now().date()
        today_records = [
            r for r in self._records if r.timestamp.date() == today
        ]

        total_input = sum(r.input_tokens for r in today_records)
        total_output = sum(r.output_tokens for r in today_records)
        total_cost = sum(r.cost for r in today_records)
        call_count = len(today_records)

        # 按提供商分组
        by_provider: dict[str, dict[str, Any]] = {}
        for r in today_records:
            if r.provider not in by_provider:
                by_provider[r.provider] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost": 0.0,
                }
            by_provider[r.provider]["calls"] += 1
            by_provider[r.provider]["input_tokens"] += r.input_tokens
            by_provider[r.provider]["output_tokens"] += r.output_tokens
            by_provider[r.provider]["cost"] += r.cost

        return {
            "date": today.isoformat(),
            "call_count": call_count,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost": round(total_cost, 6),
            "daily_budget": self._daily_budget,
            "budget_remaining": round(self._daily_budget - total_cost, 6)
            if self._daily_budget > 0
            else -1,
            "by_provider": by_provider,
        }

    def get_total_usage(self) -> dict[str, Any]:
        """获取累计使用统计"""
        return {
            "total_calls": len(self._records),
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
            "total_cost": round(self._total_cost, 6),
        }

    def check_budget(self) -> tuple[bool, float]:
        """检查是否超出预算

        Returns:
            (是否在预算内, 今日已用成本)
        """
        if self._daily_budget <= 0:
            return True, 0.0

        today_cost = sum(
            r.cost
            for r in self._records
            if r.timestamp.date() == datetime.now().date()
        )
        return today_cost <= self._daily_budget, today_cost

    def get_recent_calls(
        self, limit: int = 10
    ) -> list[dict[str, Any]]:
        """获取最近的调用记录"""
        return [
            r.to_dict() for r in self._records[-limit:]
        ]

    def set_daily_budget(self, budget: float) -> None:
        """设置每日预算

        Args:
            budget: 每日预算上限（美元），0 表示不限制
        """
        self._daily_budget = budget
        logger.info(f"每日预算已设置为 ${budget:.2f}")