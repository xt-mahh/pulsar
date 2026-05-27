import pytest
from execution.tools.registry import ToolRegistry, tool
from shared.errors import ToolNotFoundError


@pytest.fixture
def registry():
    reg = ToolRegistry()
    reg._tools.clear()
    return reg


class TestToolRegistry:
    def test_register_and_get(self, registry):
        @tool(name="test_fn", description="A test function")
        async def test_fn(param1: str, param2: int = 42):
            return {"result": f"{param1}-{param2}"}

        wrapper = registry.get("test_fn")
        assert wrapper.name == "test_fn"
        assert "param1" in wrapper.input_schema["properties"]
        assert "param2" in wrapper.input_schema["properties"]

    def test_get_not_found(self, registry):
        with pytest.raises(ToolNotFoundError):
            registry.get("nonexistent")

    def test_list_tools(self, registry):
        @tool(name="tool_a", description="Tool A")
        async def tool_a(): ...

        @tool(name="tool_b", description="Tool B")
        async def tool_b(): ...

        tools = registry.list_tools()
        assert len(tools) == 2

    def test_has_tool(self, registry):
        @tool(name="exists", description="Exists")
        async def exists(): ...

        assert registry.has_tool("exists")
        assert not registry.has_tool("nope")