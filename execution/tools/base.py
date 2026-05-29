"""工具基类与装饰器 — 所有 Native Tool 的抽象基类"""

import asyncio
import functools
import inspect
from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine

from shared.models import ToolDefinition


class BaseTool(ABC):
    """工具抽象基类

    所有 Native Tool 必须继承此类并实现 execute 方法。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（全局唯一）"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema 格式的输入参数定义"""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """执行工具逻辑"""
        ...

    def to_definition(self) -> ToolDefinition:
        """转换为 MCP ToolDefinition"""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            agent="native_tools",
        )


def tool(
    name: str | None = None,
    description: str | None = None,
    input_schema: dict[str, Any] | None = None,
) -> Callable:
    """工具装饰器 — 将异步函数快速注册为工具

    用法:
        @tool(name="http_request", description="发送 HTTP 请求")
        async def http_request(url: str, method: str = "GET") -> dict:
            ...

    如果函数有类型注解，会自动生成 input_schema。
    """

    def decorator(func: Callable[..., Coroutine]) -> type[BaseTool]:
        # 从函数签名自动生成 input_schema
        sig = inspect.signature(func)
        auto_schema: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        for param_name, param in sig.parameters.items():
            param_type = "string"  # 默认
            if param.annotation != inspect.Parameter.empty:
                type_map = {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                    dict: "object",
                    list: "array",
                }
                param_type = type_map.get(param.annotation, "string")

            auto_schema["properties"][param_name] = {
                "type": param_type,
                "description": f"参数 {param_name}",
            }

            if param.default == inspect.Parameter.empty:
                auto_schema["required"].append(param_name)

        final_name = name or func.__name__
        final_desc = description or func.__doc__ or ""
        final_schema = input_schema or auto_schema

        # 动态创建 Tool 子类
        class _DynamicTool(BaseTool):
            @property
            def name(self) -> str:
                return final_name

            @property
            def description(self) -> str:
                return final_desc

            @property
            def input_schema(self) -> dict[str, Any]:
                return final_schema

            async def execute(self, **kwargs: Any) -> Any:
                return await func(**kwargs)

        _DynamicTool.__name__ = f"Tool_{final_name}"
        _DynamicTool.__qualname__ = _DynamicTool.__name__
        _DynamicTool.__module__ = func.__module__

        return _DynamicTool

    return decorator