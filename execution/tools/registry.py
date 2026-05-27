import inspect
from typing import Callable
from shared.models import ToolDefinition
from shared.errors import ToolNotFoundError


class ToolWrapper:
    def __init__(self, fn: Callable, name: str = None, description: str = None):
        self.fn = fn
        self.name = name or fn.__name__
        self.description = description or (fn.__doc__ or "").strip()
        self.input_schema = self._build_schema()

    def _build_schema(self) -> dict:
        sig = inspect.signature(self.fn)
        properties = {}
        required = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            default = None if param.default is inspect.Parameter.empty else param.default
            annotation = param.annotation if param.annotation is not inspect.Parameter.empty else str
            json_type = self._pytype_to_jsontype(annotation)
            prop = {"type": json_type}
            if default is not inspect.Parameter.empty:
                prop["default"] = default
            else:
                required.append(param_name)
            properties[param_name] = prop
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _pytype_to_jsontype(self, pytype) -> str:
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            dict: "object",
            list: "array",
            type(None): "null",
        }
        origin = getattr(pytype, "__origin__", None)
        if origin is dict:
            return "object"
        if origin is list:
            return "array"
        return type_map.get(pytype, "string")

    async def execute(self, **kwargs) -> dict:
        if inspect.iscoroutinefunction(self.fn):
            result = await self.fn(**kwargs)
        else:
            result = self.fn(**kwargs)
        return {"result": result}

    def to_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )


class ToolRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, fn: Callable = None, *, name: str = None, description: str = None):
        if fn is None:
            return lambda f: self.register(f, name=name, description=description)
        wrapper = ToolWrapper(fn, name=name, description=description)
        self._tools[wrapper.name] = wrapper
        return fn

    def get(self, name: str) -> ToolWrapper:
        tool = self._tools.get(name)
        if not tool:
            raise ToolNotFoundError(name)
        return tool

    def list_tools(self) -> list[ToolDefinition]:
        return [t.to_definition() for t in self._tools.values()]

    def has_tool(self, name: str) -> bool:
        return name in self._tools


registry = ToolRegistry()


def tool(name: str = None, description: str = None):
    return registry.register(name=name, description=description)