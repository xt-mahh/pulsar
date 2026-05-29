"""ToolRegistry — singleton registry for all tools in Pulsar.

Provides register(), get(), list(), and execute() methods plus the @tool decorator.
"""

from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable

from pulsar.execution.tools.base import BaseTool, ToolExecutionError


class ToolRegistry:
    """Tool registry — singleton pattern.

    Maintains a global mapping of tool name → BaseTool instance,
    plus an alias map for alternative names.
    """

    _instance: "ToolRegistry | None" = None

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: dict[str, BaseTool] = {}
            cls._instance._aliases: dict[str, str] = {}
        return cls._instance

    def __init__(self):
        # Prevent re-initialization in singleton
        if not hasattr(self, "_tools"):
            self._tools: dict[str, BaseTool] = {}
            self._aliases: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance.

        Args:
            tool: A BaseTool subclass instance. Uses tool.name as key.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Expected BaseTool instance, got {type(tool).__name__}")

        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        self._tools[tool.name] = tool

    def register_alias(self, alias: str, tool_name: str) -> None:
        """Register an alias for an existing tool.

        Args:
            alias: Alternative name to register.
            tool_name: The canonical tool name.

        Raises:
            KeyError: If tool_name is not registered.
        """
        if tool_name not in self._tools:
            raise KeyError(f"Cannot alias '{alias}': tool '{tool_name}' not found")
        self._aliases[alias] = tool_name

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name or alias.

        Args:
            name: Tool name or alias.

        Returns:
            The BaseTool instance, or None if not found.
        """
        tool = self._tools.get(name)
        if tool is None:
            aliased = self._aliases.get(name)
            if aliased:
                tool = self._tools.get(aliased)
        return tool

    def get_definition(self, name: str) -> Any:
        """Get a tool's definition by name or alias.

        Args:
            name: Tool name or alias.

        Returns:
            ToolDefinition or None.
        """
        from pulsar.execution.tools.base import ToolDefinition

        tool = self.get(name)
        return tool.to_definition() if tool else None

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list(self, include_hidden: bool = False) -> list:
        """List all registered tool definitions.

        Args:
            include_hidden: Whether to include tools whose name starts with '_'.

        Returns:
            List of ToolDefinition objects.
        """
        from pulsar.execution.tools.base import ToolDefinition

        tools: list = []
        for name, tool in self._tools.items():
            if not include_hidden and name.startswith("_"):
                continue
            tools.append(tool.to_definition())
        return tools

    def list_names(self, include_hidden: bool = False) -> list[str]:
        """List all registered tool names."""
        return [td.name for td in self.list(include_hidden=include_hidden)]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(self, name: str, **kwargs) -> Any:
        """Execute a tool by name.

        Args:
            name: Tool name or alias.
            **kwargs: Arguments to pass to the tool (should conform to its input_schema).

        Returns:
            Tool execution result.

        Raises:
            KeyError: If the tool is not registered.
            ValueError: If argument validation fails.
            ToolExecutionError: If execution fails at runtime.
        """
        tool = self.get(name)
        if tool is None:
            raise KeyError(
                f"Tool '{name}' not found. "
                f"Available tools: {list(self._tools.keys())}"
            )

        try:
            validated = tool.validate_args(**kwargs)
            return await tool.execute(**validated)
        except ValueError as e:
            raise ValueError(f"Argument validation for '{name}': {e}") from e
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(
                message=str(e),
                tool_name=name,
                original=e,
            ) from e

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all registered tools and aliases (useful for testing)."""
        self._tools.clear()
        self._aliases.clear()

    def __contains__(self, name: str) -> bool:
        return self.get(name) is not None

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"<ToolRegistry: {len(self._tools)} tools, {len(self._aliases)} aliases>"


# ======================================================================
# @tool decorator
# ======================================================================

_registry = ToolRegistry()


def tool(
    name: str | None = None,
    description: str = "",
    input_schema: dict | None = None,
    output_schema: dict | None = None,
    auto_register: bool = True,
) -> Callable:
    """Decorator that wraps an async function as a BaseTool and optionally registers it.

    Usage:
        @tool(name="http_request", description="Send an HTTP request")
        async def my_http_request(url: str, method: str = "GET") -> dict:
            ...

    Args:
        name: Tool name (defaults to function name).
        description: Tool description (defaults to function docstring).
        input_schema: JSON Schema for input validation (inferred from signature if omitted).
        output_schema: JSON Schema for output.
        auto_register: Whether to auto-register in the global ToolRegistry.

    Returns:
        A decorator that returns the wrapped function (which also has a ._tool attribute).
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        schema = input_schema or _infer_schema_from_signature(func)
        tool_desc = description or func.__doc__ or ""
        out_schema = output_schema or {}

        class DecoratedTool(BaseTool):
            name = tool_name
            description = tool_desc
            input_schema = schema
            output_schema = out_schema

            async def execute(self, **kwargs) -> Any:
                return await func(**kwargs)

        instance = DecoratedTool()

        if auto_register:
            _registry.register(instance)

        @wraps(func)
        async def wrapper(**kwargs) -> Any:
            return await instance.execute(**kwargs)

        wrapper._tool = instance  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ======================================================================
# Schema inference helpers
# ======================================================================


def _infer_schema_from_signature(func: Callable) -> dict:
    """Infer a JSON Schema from a function's signature."""
    sig = inspect.signature(func)
    properties: dict[str, dict] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        prop = _type_to_schema(param.annotation)
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        else:
            if param.default is not None:
                prop["default"] = param.default
        properties[param_name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _type_to_schema(annotation: type) -> dict:
    """Map Python types to JSON Schema types."""
    mapping: dict = {
        str:     {"type": "string"},
        int:     {"type": "integer"},
        float:   {"type": "number"},
        bool:    {"type": "boolean"},
        dict:    {"type": "object"},
        list:    {"type": "array"},
        bytes:   {"type": "string", "contentEncoding": "base64"},
        type(None): {"type": "null"},
    }
    # Handle Optional types (Union[..., None])
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        args = getattr(annotation, "__args__", ())
        if origin is dict:
            return {"type": "object"}
        if origin is list:
            return {"type": "array"}
        if origin is tuple:
            return {"type": "array"}
        # Union/Optional — pick the first non-None type
        for arg in args:
            if arg is not type(None):
                return _type_to_schema(arg)
        return {"type": "null"}

    return mapping.get(annotation, {"type": "string"})


# Singleton convenience
def get_registry() -> ToolRegistry:
    """Return the global ToolRegistry singleton."""
    return _registry
