"""Smoke tests for the Media MCP server (get_trending, search_media).

Quota-free: the network seam `_request_youtube` is monkeypatched. Covers both tools, deterministic
description truncation (fixed input), and quota-exceeded surfacing as a typed error.
"""

from __future__ import annotations

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import servers.media_server as md

TRENDING = {
    "items": [
        {
            "id": "vid1",
            "snippet": {
                "title": "Big News Today",
                "channelTitle": "BBC",
                "publishedAt": "2026-06-17T08:00:00Z",
                "description": "A short description.",
            },
            "statistics": {"viewCount": "12345"},
        },
        {  # malformed: no title -> skipped
            "id": "vid2",
            "snippet": {"channelTitle": "X", "publishedAt": "2026-06-17T09:00:00Z"},
            "statistics": {"viewCount": "10"},
        },
    ]
}

SEARCH = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {
                "title": "Tutorial",
                "channelTitle": "DevChannel",
                "publishedAt": "2026-06-17T07:00:00Z",
                "description": "Learn things.",
            },
        }
    ]
}
SEARCH_STATS = {"items": [{"id": "abc123", "statistics": {"viewCount": "777"}}]}


def _run(coro):
    return asyncio.run(coro)


def test_lists_both_tools():
    async def scenario():
        async with Client(md.mcp) as client:
            return [t.name for t in await client.list_tools()]

    assert {"get_trending", "search_media"} <= set(_run(scenario()))


def test_truncation_is_deterministic():
    # Pure-function test with a fixed input (no network).
    long_text = "x" * 250
    out = md._truncate(long_text, limit=200)
    assert len(out) == 201  # 200 chars + the ellipsis
    assert out == "x" * 200 + "…"
    # Short text is returned unchanged and stripped.
    assert md._truncate("  hello  ") == "hello"
    assert md._truncate(None) == ""


def test_trending_returns_validated_items_with_views(monkeypatch):
    async def fake(path, params):
        return TRENDING

    monkeypatch.setattr(md, "_request_youtube", fake)

    async def scenario():
        async with Client(md.mcp) as client:
            return (await client.call_tool("get_trending", {"region": "GB", "limit": 5})).data

    items = _run(scenario())
    assert len(items) == 1  # malformed vid2 skipped (partial success)
    assert items[0].title == "Big News Today" and items[0].channel == "BBC"
    assert items[0].views == 12345
    assert str(items[0].url) == "https://www.youtube.com/watch?v=vid1"


def test_search_backfills_views_with_batched_call(monkeypatch):
    calls: list[str] = []

    async def fake(path, params):
        calls.append(path)
        return SEARCH if path == "/search" else SEARCH_STATS

    monkeypatch.setattr(md, "_request_youtube", fake)

    async def scenario():
        async with Client(md.mcp) as client:
            return (await client.call_tool("search_media", {"query": "python", "limit": 5})).data

    items = _run(scenario())
    assert calls == ["/search", "/videos"]  # search then ONE batched stats call
    assert len(items) == 1 and items[0].views == 777


def test_quota_exceeded_surfaces_as_typed_error(monkeypatch):
    async def fake(path, params):
        raise ToolError("media upstream error [quotaExceeded]: daily quota exceeded")

    monkeypatch.setattr(md, "_request_youtube", fake)

    async def scenario():
        async with Client(md.mcp) as client:
            await client.call_tool("get_trending", {})

    with pytest.raises(ToolError) as excinfo:
        _run(scenario())
    assert "quotaExceeded" in str(excinfo.value)
