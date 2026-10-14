"""Collects tool functions from the tool modules; server.py registers them as tapsi_* tools."""

from collections.abc import Callable
from typing import Any

TOOLS: list[tuple[Callable[..., Any], str]] = []


def tool(title: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark an async function as an MCP tool with a human-readable title."""
    # Capability modules define plain function names (e.g. `find_location`);
    # server.py adds the public `tapsi_` prefix at registration time.

    def register(fn: Callable[..., Any]) -> Callable[..., Any]:
        TOOLS.append((fn, title))
        return fn

    return register
