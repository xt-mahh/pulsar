import json
import sys
import asyncio
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import TextContent
from interaction.mcp_server.tools import EXTERNAL_TOOLS, handle_tool_call


server = Server("pulsar")


@server.list_tools()
async def list_tools():
    return EXTERNAL_TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    result = await handle_tool_call(name, arguments)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def run_server(transport: str = "stdio"):
    if transport == "stdio":
        async with server.run(
            sys.stdin,
            sys.stdout,
            InitializationOptions(
                server_name="pulsar",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        ):
            await asyncio.Future()
    else:
        raise ValueError(f"Unsupported transport: {transport}")


def main():
    asyncio.run(run_server("stdio"))