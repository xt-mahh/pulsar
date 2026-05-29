"""工具注册中心 — 所有 Native Tool 的注册、发现与调用"""

import logging
from typing import Any

from execution.tools.base import BaseTool
from shared.models import ToolDefinition

logger = logging.getLogger("pulsar.tools.registry")


class ToolRegistry:
    """工具注册中心

    所有工具通过 register() 注册，按名称发现和调用。
    支持能力标签过滤和批量注册。
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool | type[BaseTool]) -> None:
        """注册一个工具

        Args:
            tool: 工具实例或工具类（会自动实例化）
        """
        if isinstance(tool, type):
            tool = tool()

        if tool.name in self._tools:
            logger.warning(f"工具 '{tool.name}' 已存在，将被覆盖")

        self._tools[tool.name] = tool
        logger.debug(f"工具已注册: {tool.name}")

    def register_many(self, tools: list[BaseTool | type[BaseTool]]) -> None:
        """批量注册工具"""
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> BaseTool | None:
        """按名称获取工具

        Args:
            name: 工具名称

        Returns:
            工具实例，未找到返回 None
        """
        return self._tools.get(name)

    def list(self) -> list[ToolDefinition]:
        """列出所有已注册的工具定义

        Returns:
            MCP ToolDefinition 列表
        """
        return [tool.to_definition() for tool in self._tools.values()]

    async def execute(self, name: str, **kwargs: Any) -> Any:
        """执行指定工具

        Args:
            name: 工具名称
            **kwargs: 工具参数

        Returns:
            工具执行结果

        Raises:
            KeyError: 工具未找到
        """
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"工具 '{name}' 未注册")

        logger.info(f"执行工具: {name}, 参数: {kwargs}")
        result = await tool.execute(**kwargs)
        logger.debug(f"工具 '{name}' 执行完成")
        return result

    def unregister(self, name: str) -> None:
        """注销一个工具

        Args:
            name: 工具名称
        """
        if name in self._tools:
            del self._tools[name]
            logger.debug(f"工具已注销: {name}")

    def clear(self) -> None:
        """清空所有工具"""
        self._tools.clear()
        logger.debug("所有工具已清空")

    @property
    def count(self) -> int:
        """已注册工具数量"""
        return len(self._tools)