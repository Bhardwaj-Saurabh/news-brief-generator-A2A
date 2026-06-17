"""Thin MCP client — the one helper agents use to call any tool over HTTP.

Deliberately trace-free: the MCP protocol does not propagate our correlation id across the
boundary, so threading a trace param here would be dishonest. Correlation is handled out-of-band
by a contextvars trace id + a logging filter (see the trace strategy in the PRD/architecture).

`call_tool` returns the tool's raw JSON-able result (a dict, or a list of dicts) — never a typed
model. The calling agent immediately `model_validate`s it into the relevant contract, so the
untyped dict never leaks past the agent boundary.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import Client

log = logging.getLogger("mcp_client")


async def call_tool(server_url: str, tool: str, args: dict[str, Any] | None = None) -> Any:
    """Call one MCP tool and return its raw structured payload.

    `server_url` is an HTTP URL in production (e.g. 'http://127.0.0.1:8801/mcp'); a FastMCP server
    object also works for in-memory tests. FastMCP wraps non-object outputs (lists, scalars) under
    a single 'result' key — we unwrap that so callers get the plain list/dict.
    """
    async with Client(server_url) as client:
        result = await client.call_tool(tool, args or {})

    payload = result.structured_content
    if isinstance(payload, dict) and list(payload.keys()) == ["result"]:
        return payload["result"]
    return payload
