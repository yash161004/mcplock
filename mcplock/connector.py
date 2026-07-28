"""Talks to MCP servers and pulls the raw ``tools/list`` response.

v0.1 supports two transports:
  * stdio  — a local server launched as a subprocess (``npx ...``, ``python ...``)
  * http   — one remote transport (streamable HTTP)

Everything downstream consumes the raw dicts returned here; no normalization
happens in this module.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass(frozen=True)
class ServerTarget:
    """How to reach one MCP server, plus the id its snapshots are stored under."""

    server_id: str
    transport: str  # "stdio" | "http"
    command: str | None = None
    args: tuple[str, ...] = ()
    url: str | None = None

    @classmethod
    def from_command(cls, command_line: str) -> "ServerTarget":
        """Parse a stdio command line, e.g. ``npx -y @scope/server /tmp``."""
        parts = shlex.split(command_line, posix=False)
        if not parts:
            raise ValueError("empty server command")
        return cls(
            server_id=derive_server_id(command_line),
            transport="stdio",
            command=parts[0],
            args=tuple(parts[1:]),
        )

    @classmethod
    def from_url(cls, url: str) -> "ServerTarget":
        return cls(server_id=derive_server_id(url), transport="http", url=url)


def derive_server_id(connection: str) -> str:
    """Filesystem-safe id derived from the connection command or URL.

    Stable across runs so snapshots line up, and readable so
    ``~/.mcplock/snapshots/`` can be inspected by hand.
    """
    safe = []
    for ch in connection.strip().lower():
        safe.append(ch if ch.isalnum() or ch in "-._" else "-")
    collapsed = "-".join(filter(None, "".join(safe).split("-")))
    return collapsed[:120] or "unnamed-server"


async def fetch_tools(target: ServerTarget) -> list[dict[str, Any]]:
    """Connect to ``target`` and return the raw tool definitions.

    Each element is the JSON-RPC ``tools/list`` entry as a plain dict:
    ``{"name", "description", "inputSchema", ...}``.
    """
    if target.transport == "stdio":
        return await _fetch_tools_stdio(target)
    if target.transport == "http":
        return await _fetch_tools_http(target)
    raise ValueError(f"unsupported transport: {target.transport}")


async def _fetch_tools_stdio(target: ServerTarget) -> list[dict[str, Any]]:
    params = StdioServerParameters(command=target.command, args=list(target.args))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            return await _list_all_tools(session)


async def _fetch_tools_http(target: ServerTarget) -> list[dict[str, Any]]:
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(target.url) as (read, write):
        async with ClientSession(read, write) as session:
            return await _list_all_tools(session)


async def _list_all_tools(session: ClientSession) -> list[dict[str, Any]]:
    """Initialize the session and walk every page of ``tools/list``.

    A server that paginates would otherwise look like it had "removed" the
    tools on later pages, so pagination is not optional here.
    """
    from mcp import types

    await session.initialize()

    tools: list[dict[str, Any]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()

    while True:
        params = types.PaginatedRequestParams(cursor=cursor) if cursor else None
        result = await session.list_tools(params=params)
        tools.extend(_tool_to_dict(tool) for tool in result.tools)

        cursor = result.next_cursor
        if not cursor or cursor in seen_cursors:
            break
        seen_cursors.add(cursor)

    return tools


def _tool_to_dict(tool: Any) -> dict[str, Any]:
    """Convert an SDK ``Tool`` model back to the wire-shaped dict.

    ``by_alias`` keeps ``inputSchema`` in camelCase, and unset fields are
    dropped so absent keys stay absent rather than becoming ``null`` — the
    hash must reflect what the server actually sent.
    """
    return tool.model_dump(by_alias=True, exclude_none=True, mode="json")
