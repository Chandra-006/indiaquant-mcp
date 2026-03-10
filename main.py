"""
main.py
=======
Entry point for the IndiaQuant MCP Server.

Run this file to start the server:
    python main.py

How it works:
    Claude Desktop --> MCP Protocol --> main.py --> modules/tools.py --> modules/
"""

import asyncio  # Allows async/await for non-blocking server operations
import json     # Used to convert Python dicts to JSON strings for error responses
import sys      # System-level operations (imported but not used — can be removed)

# MCP SDK: Core server class
from mcp.server import Server

# MCP SDK: stdio transport — Claude communicates via stdin/stdout pipes
from mcp.server.stdio import stdio_server

# MCP SDK: Data types used in responses (Tool, TextContent)
from mcp import types

# Our custom tool handler and tool definitions list
from modules.tools import handle_tool, TOOLS


# ─────────────────────────────────────────────
# CREATE SERVER INSTANCE
# ─────────────────────────────────────────────
# "indiaquant-mcp" is the server name shown in Claude Desktop
app = Server("indiaquant-mcp")


# ─────────────────────────────────────────────
# TOOL REGISTRATION
# ─────────────────────────────────────────────
@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """
    Register all 10 tools with Claude.

    Claude calls this once on startup to discover
    what tools are available — like reading a menu.

    Reads the TOOLS list from modules/tools.py and
    converts each entry into an MCP Tool object.
    """
    tools = []
    for tool in TOOLS:
        tools.append(
            types.Tool(
                name=tool["name"],               # Unique tool identifier
                description=tool["description"], # What the tool does (Claude reads this)
                inputSchema=tool["inputSchema"]  # What inputs the tool expects
            )
        )
    return tools


# ─────────────────────────────────────────────
# TOOL EXECUTION
# ─────────────────────────────────────────────
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """
    Execute a tool when Claude requests it.

    Flow:
        Claude calls tool → this function runs →
        handle_tool() routes to correct module →
        result returned to Claude as JSON text

    Args:
        name:      Tool name e.g. "get_live_price"
        arguments: Tool inputs e.g. {"symbol": "RELIANCE"}

    Returns:
        List containing one TextContent with JSON result
    """
    try:
        # Route the tool call to the correct module function
        result = handle_tool(name, arguments)

        # Wrap result in MCP TextContent format and return
        return [types.TextContent(type="text", text=result)]

    except Exception as e:
        # If anything crashes, return a clean JSON error
        # This prevents the entire server from crashing
        error = json.dumps({"error": str(e)})
        return [types.TextContent(type="text", text=error)]


# ─────────────────────────────────────────────
# SERVER STARTUP
# ─────────────────────────────────────────────
async def main():
    """
    Start the MCP server using stdio transport.

    stdio_server() opens stdin/stdout pipes so
    Claude Desktop can communicate with this server.

    The server runs forever until stopped with Ctrl+C.
    A blinking cursor = server is running correctly.
    """
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,    # Incoming messages from Claude
            write_stream,   # Outgoing responses to Claude
            app.create_initialization_options()  # Default MCP settings
        )


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # asyncio.run() starts the event loop and runs main()
    # Only runs when executed directly, not when imported
    asyncio.run(main())