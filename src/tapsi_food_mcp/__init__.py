"""Unofficial read-only MCP server for Tapsi Food (anonymous, no login)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tapsi-food-mcp")
except PackageNotFoundError:  # editable install not refreshed yet (Task 7 runs uv sync)
    __version__ = "0.1.0"
