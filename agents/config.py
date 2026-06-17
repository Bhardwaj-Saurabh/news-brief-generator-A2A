"""Where the MCP servers live. One place to resolve server URLs from the environment.

Each server binds 127.0.0.1:<port> over HTTP; the MCP endpoint path is `/mcp`. Ports come from
the same env vars the servers read (WORLD_DATA_PORT etc.), so the agent and the server agree by
construction. An explicit *_URL env var overrides (useful if servers move off localhost).
Functions, not constants, so the env is read after load_dotenv() has run.
"""

from __future__ import annotations

import os


def _server_url(url_var: str, port_var: str, default_port: int) -> str:
    explicit = os.environ.get(url_var)
    if explicit:
        return explicit
    port = os.environ.get(port_var, str(default_port))
    return f"http://127.0.0.1:{port}/mcp"


def world_data_url() -> str:
    return _server_url("WORLD_DATA_URL", "WORLD_DATA_PORT", 8801)


def finance_url() -> str:
    return _server_url("FINANCE_URL", "FINANCE_PORT", 8802)


def media_url() -> str:
    return _server_url("MEDIA_URL", "MEDIA_PORT", 8803)
