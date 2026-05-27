from abc import ABC, abstractmethod
from shared.models import ToolDefinition


class BasePlatformAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def platform(self) -> str: ...

    @abstractmethod
    async def initialize(self) -> bool:
        ...

    @abstractmethod
    async def get_tools(self) -> list[ToolDefinition]:
        ...

    @abstractmethod
    async def handle_tool_call(self, name: str, args: dict) -> dict:
        ...