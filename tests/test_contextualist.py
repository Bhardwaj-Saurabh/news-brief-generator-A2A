"""Tests for the Contextualist agent (Task 7).

The `call_tool` seam is monkeypatched, so no MCP servers or keys are needed. Covers a populated
bundle, graceful degradation of each section, topic->search routing, and budget bounding.
"""

from __future__ import annotations

import asyncio
import time

from fastmcp.exceptions import ToolError

import agents.contextualist as ctx
from agents.contracts import BriefRequest

HEADLINES_RAW = [
    {
        "title": "AI breakthrough",
        "source": "BBC News",
        "url": "https://bbc.co.uk/news/1",
        "published_at": "2026-06-17T10:00:00Z",
        "summary": "A summary.",
    }
]
WEATHER_RAW = {
    "city": "London",
    "country": "GB",
    "temp_c": 15.0,
    "feels_like_c": 14.2,
    "conditions": "overcast clouds",
    "wind_kph": 12.0,
    "observed_at": "2026-06-17T10:00:00Z",
}


def _run(coro):
    return asyncio.run(coro)


def _patch_calls(monkeypatch, *, headlines=HEADLINES_RAW, weather=WEATHER_RAW, capture=None):
    async def fake_call_tool(server_url, tool, args=None):
        if capture is not None:
            capture[tool] = args
        if tool == "get_top_headlines":
            if isinstance(headlines, Exception):
                raise headlines
            return headlines
        if tool == "get_current_weather":
            if isinstance(weather, Exception):
                raise weather
            return weather
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(ctx, "call_tool", fake_call_tool)


def test_gather_context_populated(monkeypatch):
    _patch_calls(monkeypatch)
    bundle = _run(ctx.gather_context(BriefRequest(region="UK")))
    assert bundle.region == "UK"
    assert len(bundle.headlines) == 1 and bundle.headlines[0].source == "BBC News"
    assert bundle.weather is not None and bundle.weather.city == "London"


def test_weather_failure_degrades_gracefully(monkeypatch):
    _patch_calls(monkeypatch, weather=ToolError("weather upstream error [404]: city not found"))
    bundle = _run(ctx.gather_context(BriefRequest(region="UK")))
    assert len(bundle.headlines) == 1  # news still present
    assert bundle.weather is None  # weather degraded, no crash


def test_news_failure_degrades_gracefully(monkeypatch):
    _patch_calls(monkeypatch, headlines=ToolError("news upstream error [429]: rate limit"))
    bundle = _run(ctx.gather_context(BriefRequest(region="UK")))
    assert bundle.headlines == []  # news degraded
    assert bundle.weather is not None  # weather still present


def test_topic_routes_to_search_with_window(monkeypatch):
    capture: dict = {}
    _patch_calls(monkeypatch, capture=capture)
    _run(ctx.gather_context(BriefRequest(region="UK", topic="openai", lookback_hours=12)))
    news_args = capture["get_top_headlines"]
    assert news_args["query"] == "openai"
    assert news_args["since_hours"] == 12
    assert "country" not in news_args  # search path, not top-headlines


def test_no_topic_uses_top_headlines_for_region(monkeypatch):
    capture: dict = {}
    _patch_calls(monkeypatch, capture=capture)
    _run(ctx.gather_context(BriefRequest(region="US")))  # resolves to country_code 'us'
    news_args = capture["get_top_headlines"]
    assert news_args["country"] == "us"
    assert "query" not in news_args


def test_expired_deadline_degrades_without_hanging(monkeypatch):
    async def slow_call(server_url, tool, args=None):
        await asyncio.sleep(5)  # would blow any sane budget
        return HEADLINES_RAW if tool == "get_top_headlines" else WEATHER_RAW

    monkeypatch.setattr(ctx, "call_tool", slow_call)

    async def scenario():
        start = time.monotonic()
        # Deadline ~50ms out: both fetches must time out and degrade fast.
        bundle = await ctx.gather_context(BriefRequest(region="UK"), deadline=time.monotonic() + 0.05)
        return bundle, time.monotonic() - start

    bundle, elapsed = _run(scenario())
    assert bundle.headlines == [] and bundle.weather is None  # both degraded
    assert elapsed < 2.0  # bounded by the deadline, not the 5s sleep
