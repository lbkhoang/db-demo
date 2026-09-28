"""LangChain agent loop that can read the Markdown file only through MCP tools."""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_ollama import ChatOllama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler(ROOT / "agent.log", encoding="utf-8")])
log = logging.getLogger("agent-demo")


class EmptyArgs(BaseModel):
    """Schema for the list_chunks tool."""


class ChunkArgs(BaseModel):
    index: int = Field(description="The chunk ID returned by list_chunks")


class TerminalArgs(BaseModel):
    command: str = Field(description="A read-only command such as cat data/software_policy.md")


async def run(prompt: str):
    server = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server.py")])
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            remote = {tool.name: tool for tool in (await session.list_tools()).tools}

            async def invoke(name: str, arguments: dict):
                log.info("MCP tool call: %s(%s)", name, arguments)
                result = await session.call_tool(name, arguments)
                return "\n".join(item.text for item in result.content if getattr(item, "text", None))

            # Wrap the two MCP tools as LangChain tools so the model can choose them.
            tools = [
                StructuredTool.from_function(
                    coroutine=lambda: invoke("list_chunks", {}),
                    name="list_chunks", description=remote["list_chunks"].description or "List Markdown chunks.",
                    args_schema=EmptyArgs),
                StructuredTool.from_function(
                    coroutine=lambda index: invoke("read_chunk", {"index": index}),
                    name="read_chunk", description=remote["read_chunk"].description or "Read one Markdown chunk.",
                    args_schema=ChunkArgs),
                StructuredTool.from_function(
                    coroutine=lambda command: invoke("run_terminal", {"command": command}),
                    name="run_terminal", description=remote["run_terminal"].description or "Read the policy through a restricted terminal command.",
                    args_schema=TerminalArgs),
            ]
            model = ChatOllama(model=os.getenv("CHAT_MODEL", "qwen3:4b"),
                               base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"), temperature=0)
            model = model.bind_tools(tools)
            messages = [SystemMessage(content=(
                "You answer from the Markdown policy only. You cannot read files directly. "
                "You may use list_chunks/read_chunk for structured retrieval, or run_terminal only when a terminal read is useful. "
                "If the first result is not enough, call another tool. Cite the evidence source in your answer.")), HumanMessage(content=prompt)]
            max_calls = int(os.getenv("MAX_TOOL_CALLS", "4"))
            calls = 0
            while calls < max_calls:
                response = await model.ainvoke(messages)
                messages.append(response)
                if not response.tool_calls:
                    print("\nAnswer:\n" + response.content)
                    print(f"Agent tool calls: {calls}")
                    return
                for call in response.tool_calls:
                    calls += 1
                    if calls > max_calls:
                        break
                    # Show the observable action selected by the model.
                    # This is an action trace, not the model's private chain-of-thought.
                    print(
                        f"\n[step {calls}] model selected "
                        f"{call['name']}({call.get('args', {})})",
                        flush=True,
                    )
                    output = await tools_by_name(tools, call["name"], call.get("args", {}))
                    log.info("MCP result: %d characters", len(output))
                    print(
                        f"[step {calls}] tool returned {len(output)} characters; "
                        "sending result back to model",
                        flush=True,
                    )
                    messages.append(ToolMessage(content=output, tool_call_id=call["id"]))
            messages.append(SystemMessage(content="Tool-call limit reached. Answer only from collected evidence."))
            final = await model.ainvoke(messages)
            print("\nAnswer:\n" + final.content)
            print(f"Agent tool calls: {calls} (limit reached)")


async def tools_by_name(tools, name, args):
    for tool in tools:
        if tool.name == name:
            return await tool.ainvoke(args)
    raise ValueError(f"Unknown tool requested: {name}")


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Classify uTorrent and list all blacklist software."
    try:
        asyncio.run(run(question))
    except Exception as error:
        log.exception("Agent demo failed")
        raise SystemExit(f"ERROR: {error}")
