import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def check_mcp() -> dict:
    url = os.getenv("MCP_URL", "http://localhost:8001/mcp")
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            if "system_status" not in names:
                raise RuntimeError("Missing system_status tool")
            result = await session.call_tool("system_status", {})
            if result.isError:
                raise RuntimeError("MCP database check failed")
            return {"status": "ok", "tools": names}
