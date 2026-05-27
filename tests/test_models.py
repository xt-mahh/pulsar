import pytest
from shared.models import (
    AgentConfig, MCPRequest, MCPResponse,
    ToolDefinition, Task, AuditLog, PulsarConfig,
)


class TestModels:
    def test_agent_config_defaults(self):
        ac = AgentConfig(name="test", layer=1, type="runtime")
        assert ac.name == "test"
        assert ac.enabled is True
        assert ac.config == {}

    def test_agent_config_disabled(self):
        ac = AgentConfig(name="test", layer=1, type="runtime", enabled=False)
        assert ac.enabled is False

    def test_mcp_request_defaults(self):
        req = MCPRequest(method="tools/call")
        assert req.jsonrpc == "2.0"
        assert req.params == {}

    def test_mcp_response_success(self):
        resp = MCPResponse(id="test", result={"status": "ok"})
        assert resp.error is None
        assert resp.result["status"] == "ok"

    def test_mcp_response_error(self):
        resp = MCPResponse(id="test", error={"code": -32000, "message": "err"})
        assert resp.result is None

    def test_tool_definition(self):
        td = ToolDefinition(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )
        assert td.name == "test_tool"

    def test_task_default_status(self):
        task = Task(type="publish")
        assert task.status == "pending"
        assert task.retry_count == 0

    def test_audit_log(self):
        log = AuditLog(
            event_type="tool_call", agent="test",
            action="test_action", params={"key": "value"},
        )
        assert log.success is True
        assert log.user == "system"

    def test_pulsar_config(self):
        cfg = PulsarConfig(system={"name": "Pulsar"})
        assert cfg.system["name"] == "Pulsar"


class TestErrors:
    from shared.errors import (
        PulsarError, ToolNotFoundError, AdapterError,
        ConfigError, AuthError, AgentNotReadyError, TaskError,
    )

    def test_base_error(self):
        e = self.PulsarError("test")
        assert str(e) == "test"

    def test_tool_not_found(self):
        e = self.ToolNotFoundError("test_tool")
        assert "test_tool" in str(e)

    def test_adapter_error(self):
        e = self.AdapterError("wechat", "API failed")
        assert "[wechat]" in str(e)

    def test_config_error(self):
        e = self.ConfigError("bad config")
        assert "bad config" in str(e)

    def test_auth_error(self):
        e = self.AuthError()
        assert "Authentication" in str(e)

    def test_agent_not_ready(self):
        e = self.AgentNotReadyError("agent1")
        assert "agent1" in str(e)