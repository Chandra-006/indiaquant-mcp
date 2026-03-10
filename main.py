import asyncio
import json
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from modules.tools import handle_tool, TOOLS

app = Server("indiaquant-mcp")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    tools = []
    for tool in TOOLS:
        tools.append(
            types.Tool(
                name=tool["name"],
                description=tool["description"],
                inputSchema=tool["inputSchema"]
            )
        )
    return tools


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = handle_tool(name, arguments)
        return [types.TextContent(type="text", text=result)]
    except Exception as e:
        error = json.dumps({"error": str(e)})
        return [types.TextContent(type="text", text=error)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
