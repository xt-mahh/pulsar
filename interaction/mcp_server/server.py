"""Pulsar 对外 MCP Server — 基于 MCP 协议暴露系统能力"""

import asyncio
import json
import sys
from typing import Any

from interaction.mcp_server.tools import get_tool_definitions, find_tool


class PulsarMCPServer:
    """Pulsar MCP Server — 对外暴露系统能力

    通过 stdio 传输层与外部 MCP Client（如 Claude Code）通信。
    支持 tools/list 和 tools/call 方法。
    """

    def __init__(self, runtime: Any = None) -> None:
        self.runtime = runtime
        self._running = False

    async def handle_request(self, request: dict) -> dict:
        """处理单个 MCP 请求"""
        method = request.get("method", "")
        req_id = request.get("id", "")
        params = request.get("params", {})

        if method == "tools/list":
            return self._handle_list_tools(req_id)
        elif method == "tools/call":
            return await self._handle_call_tool(req_id, params)
        elif method == "resources/list":
            return self._handle_list_resources(req_id)
        elif method == "ping":
            return self._handle_ping(req_id)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }

    def _handle_list_tools(self, req_id: str) -> dict:
        """处理 tools/list 请求"""
        tools = get_tool_definitions()
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools},
        }

    async def _handle_call_tool(self, req_id: str, params: dict) -> dict:
        """处理 tools/call 请求"""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool_def = find_tool(name)
        if not tool_def:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32602,
                    "message": f"Tool not found: {name}",
                },
            }

        try:
            result = await self._execute_tool(name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result,
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32000,
                    "message": f"Tool execution failed: {str(e)}",
                },
            }

    def _handle_list_resources(self, req_id: str) -> dict:
        """处理 resources/list 请求"""
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"resources": []},
        }

    def _handle_ping(self, req_id: str) -> dict:
        """处理 ping 请求"""
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"status": "ok"},
        }

    async def _execute_tool(self, name: str, arguments: dict) -> dict:
        """执行 MCP 工具调用"""
        if not self.runtime:
            return {"error": "Runtime not initialized"}

        # 路由到对应的内部工具
        tool_routes = {
            "platform_publish": ("adapter.wechat", "wechat_publish_submit"),
            "platform_draft_create": ("adapter.wechat", "wechat_draft_add"),
            "platform_draft_list": ("adapter.wechat", "wechat_draft_list"),
            "platform_stats": ("adapter.wechat", "wechat_stats"),
            "platform_upload_media": ("adapter.wechat", "wechat_media_upload"),
            "system_status": ("system", "system_status"),
            "task_schedule": ("scheduler", "create_schedule"),
            "task_list": ("scheduler", "list_jobs"),
        }

        route = tool_routes.get(name)
        if not route:
            return {"error": f"No route for tool: {name}"}

        agent_name, tool_name = route
        return await self.runtime.call_tool(agent_name, tool_name, arguments)

    async def run_stdio(self) -> None:
        """通过 stdio 运行 MCP Server

        从 stdin 读取 JSON-RPC 请求，处理后将结果写入 stdout。
        """
        self._running = True

        while self._running:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                request = json.loads(line)
                response = await self.handle_request(request)

                response_line = json.dumps(response)
                sys.stdout.write(response_line + "\n")
                sys.stdout.flush()

            except json.JSONDecodeError as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": f"Parse error: {str(e)}",
                    },
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()

            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32000,
                        "message": f"Internal error: {str(e)}",
                    },
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()

    def stop(self) -> None:
        """停止 MCP Server"""
        self._running = False