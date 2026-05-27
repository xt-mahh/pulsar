import asyncio
import json
import uuid
from datetime import datetime, timezone
from shared.models import MCPRequest, MCPResponse


class AgentConnection:
    def __init__(self, name: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.name = name
        self.reader = reader
        self.writer = writer
        self.tools: list[dict] = []
        self.last_heartbeat: datetime = datetime.now(timezone.utc)

    async def send_request(self, request: MCPRequest) -> MCPResponse:
        data = request.model_dump_json() + "\n"
        self.writer.write(data.encode())
        await self.writer.drain()
        response_line = await self.reader.readline()
        if not response_line:
            return MCPResponse(id=request.id, error={"code": -32000, "message": "No response"})
        try:
            resp_data = json.loads(response_line.decode())
            return MCPResponse(**resp_data)
        except (json.JSONDecodeError, Exception) as e:
            return MCPResponse(id=request.id, error={"code": -32700, "message": str(e)})

    async def send_event(self, method: str, params: dict):
        request = MCPRequest(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            method=method,
            params=params,
        )
        data = request.model_dump_json() + "\n"
        self.writer.write(data.encode())
        await self.writer.drain()

    def close(self):
        try:
            self.writer.close()
        except Exception:
            pass


class MCPBus:
    def __init__(self):
        self._agents: dict[str, AgentConnection] = {}
        self._subscriptions: dict[str, list[str]] = {}
        self._running = False

    def register_agent(self, name: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> AgentConnection:
        conn = AgentConnection(name, reader, writer)
        self._agents[name] = conn
        return conn

    def unregister_agent(self, name: str):
        if name in self._agents:
            self._agents[name].close()
            del self._agents[name]
        self._subscriptions.pop(name, None)

    def get_agent(self, name: str) -> AgentConnection | None:
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())

    async def call_tool(self, target_agent: str, tool_name: str, arguments: dict, source_agent: str = "system") -> dict:
        conn = self._agents.get(target_agent)
        if not conn:
            return {"error": f"Agent '{target_agent}' not found"}
        request = MCPRequest(
            method="tools/call",
            params={
                "name": tool_name,
                "arguments": arguments,
                "source_agent": source_agent,
                "target_agent": target_agent,
            },
        )
        response = await conn.send_request(request)
        if response.error:
            return {"error": response.error}
        return response.result or {}

    async def list_agent_tools(self, agent_name: str) -> list[dict]:
        conn = self._agents.get(agent_name)
        if not conn:
            return []
        request = MCPRequest(method="tools/list")
        response = await conn.send_request(request)
        if response.error:
            return []
        return (response.result or {}).get("tools", [])

    def subscribe(self, subscriber: str, event_type: str):
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
        if subscriber not in self._subscriptions[event_type]:
            self._subscriptions[event_type].append(subscriber)

    def unsubscribe(self, subscriber: str, event_type: str):
        if event_type in self._subscriptions:
            self._subscriptions[event_type] = [s for s in self._subscriptions[event_type] if s != subscriber]

    async def publish_event(self, event_type: str, data: dict, source: str = "system"):
        subscribers = self._subscriptions.get(event_type, [])
        for subscriber_name in subscribers:
            conn = self._agents.get(subscriber_name)
            if conn:
                await conn.send_event(event_type, {"source": source, "type": event_type, "data": data})

    async def listen(self):
        self._running = True
        while self._running:
            await asyncio.sleep(0.1)

    async def close(self):
        self._running = False
        for conn in self._agents.values():
            conn.close()
        self._agents.clear()
        self._subscriptions.clear()