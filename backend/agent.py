"""Google ADK agent wired to the local FastMCP server over stdio."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from mcp import StdioServerParameters

BACKEND_DIR = Path(__file__).resolve().parent
MCP_SERVER_PATH = BACKEND_DIR / "mcp_server.py"

# Load environment variables, trying both the backend folder and parent/root folder
load_dotenv(dotenv_path=BACKEND_DIR / ".env")
load_dotenv(dotenv_path=BACKEND_DIR.parent / ".env")

SYSTEM_INSTRUCTION = (
    "You are a GitHub profile analyst and dev card generator. "
    "When a user gives you a GitHub username, you ALWAYS follow this exact "
    "sequence: first call scrape_github, then analyze_profile with the "
    "result, then generate_card_html with all three inputs, then save_card. "
    "Never skip steps. Be enthusiastic about developers' work. If the profile "
    "is private or doesn't exist, say so clearly."
)

# MCP toolset speaks to backend/mcp_server.py over stdio.
mcp_toolset = McpToolset(
    connection_params=StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_SERVER_PATH)],
        env={**os.environ},
    ),
)

github_card_agent = Agent(
    name="github_card_agent",
    model="gemini-2.5-flash",
    description=(
        "Generates a beautiful developer card for any public GitHub profile "
        "by scraping, analyzing, rendering, and saving it."
    ),
    instruction=SYSTEM_INSTRUCTION,
    tools=[mcp_toolset],
)

# Convenience alias
root_agent = github_card_agent

__all__ = ["github_card_agent", "root_agent"]
