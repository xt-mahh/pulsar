"""平台适配器基类 — 所有平台 MCP Adapter 必须实现的接口"""

from abc import ABC, abstractmethod
from typing import Any

from shared.models import ToolDefinition


class BasePlatformAdapter(ABC):
    """平台适配器基类

    所有内容平台（微信、微博、小红书等）的 MCP Adapter 必须继承此类。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """适配器名称（如 wechat, weibo）"""
        ...

    @property
    @abstractmethod
    def platform(self) -> str:
        """平台名称（如 微信公众号, 微博）"""
        ...

    @abstractmethod
    async def initialize(self) -> bool:
        """初始化适配器

        验证凭据有效性，建立必要连接。

        Returns:
            初始化是否成功
        """
        ...

    @abstractmethod
    async def get_tools(self) -> list[ToolDefinition]:
        """返回此适配器提供的所有 MCP 工具定义

        Returns:
            ToolDefinition 列表
        """
        ...

    @abstractmethod
    async def handle_tool_call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """处理 MCP 工具调用

        Args:
            name: 工具名称
            args: 工具参数

        Returns:
            工具执行结果
        """
        ...

    async def shutdown(self) -> None:
        """关闭适配器，释放资源

        子类可覆盖此方法实现清理逻辑。
        """
        pass