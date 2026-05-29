"""BaseTool — abstract base class for all tools in Pulsar.

Every tool must inherit from BaseTool and implement the async execute() method.
Provides metadata validation, JSON Schema argument validation, and ToolDefinition conversion.
"""

from abc import ABC, abstractmethod
from typing import Any


class ToolExecutionError(Exception):
    """Raised when a tool execution fails at runtime."""

    def __init__(self, message: str, tool_name: str = "", original: Exception | None = None):
        self.tool_name = tool_name
        self.original = original
        super().__init__(f"[{tool_name}] {message}" if tool_name else message)


class ToolDefinition:
    """Lightweight tool definition for LLM consumption and introspection."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict,
        output_schema: dict | None = None,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema or {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


class BaseTool(ABC):
    """Abstract base class for all tools.

    Subclasses must set class attributes (name, description, input_schema)
    and implement the async execute() method.

    Example:
        class MyTool(BaseTool):
            name = "my_tool"
            description = "Does something useful"
            input_schema = {
                "type": "object",
                "properties": {"x": {"type": "integer"}},
                "required": ["x"],
            }

            async def execute(self, **kwargs) -> Any:
                return {"result": kwargs["x"] * 2}
    """

    # === Metadata (subclasses MUST define) ===
    name: str = ""
    description: str = ""
    input_schema: dict = {}
    output_schema: dict = {}

    # === Lifecycle ===
    def __init__(self):
        """Initialize the tool instance. Validates metadata completeness."""
        self._validate_metadata()

    def _validate_metadata(self) -> None:
        """Validate that required metadata attributes are set."""
        if not self.name:
            raise ValueError(f"{type(self).__name__} must define 'name'")
        if not self.description:
            raise ValueError(f"{type(self).__name__} must define 'description'")
        if not self.input_schema:
            raise ValueError(f"{type(self).__name__} must define 'input_schema'")

    # === Core method ===
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool logic.

        Args:
            **kwargs: Arguments validated against input_schema.

        Returns:
            Result conforming to output_schema.

        Raises:
            ToolExecutionError: On execution failure.
        """
        ...

    # === Helper methods ===
    def to_definition(self) -> ToolDefinition:
        """Convert to a lightweight ToolDefinition for LLM consumption."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
        )

    def validate_args(self, **kwargs) -> dict:
        """Validate keyword arguments against input_schema using jsonschema.

        Returns:
            The validated kwargs dict (defaults are filled by the schema validator).

        Raises:
            ValidationError: If args don't conform to input_schema.
        """
        try:
            from jsonschema import validate as js_validate
            from jsonschema import ValidationError as JSError
            js_validate(kwargs, self.input_schema)
        except ImportError:
            # Fallback: basic type checking without jsonschema dependency
            self._basic_validate(kwargs)
        except JSError as e:
            raise ValueError(f"Argument validation failed for '{self.name}': {e}") from e
        return kwargs

    def _basic_validate(self, kwargs: dict) -> None:
        """Basic argument validation when jsonschema is not available."""
        props = self.input_schema.get("properties", {})
        required = self.input_schema.get("required", [])

        for req_key in required:
            if req_key not in kwargs:
                raise ValueError(
                    f"Missing required argument '{req_key}' for tool '{self.name}'"
                )

        for key, value in kwargs.items():
            if key in props:
                expected_type = props[key].get("type", "string")
                py_type = {
                    "string": str,
                    "integer": int,
                    "number": (int, float),
                    "boolean": bool,
                    "object": dict,
                    "array": (list, tuple),
                }.get(expected_type)

                if py_type and value is not None and not isinstance(value, py_type):
                    raise ValueError(
                        f"Argument '{key}' for tool '{self.name}' expected {expected_type}, "
                        f"got {type(value).__name__}"
                    )
