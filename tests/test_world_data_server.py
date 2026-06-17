"""Smoke tests for the World Data MCP server's get_top_headlines tool.

Quota-free: the single network seam `_request_newsapi` is monkeypatched, so no real NewsAPI
calls (and no key) are needed. Tests drive the tool through a real in-memory MCP Client, so
they exercise tool discovery + invocation + output validation end to end.
"""

from __future__ import annotations

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import servers.world_data_server as wd

# Two valid articles + one malformed (title None, unpar'able date) to prove partial success.
OK_PAYLOAD = {
    "status": "ok",
    "totalResults": 3,
    "articles": [
        {
            "source": {"name": "BBC News"},
            "title": "AI model breaks benchmark",
            "description": "A short summary.",
            "url": "https://bbc.co.uk/news/1",
            "publishedAt": "2026-06-17T10:00:00Z",
        },
        {
            "source": {"name": "Reuters"},
            "title": "Markets edge higher",
            "description": None,  # summary is optional
            "url": "https://reuters.com/2",
            "publishedAt": "2026-06-17T09:00:00Z",
        },
        {  # malformed -> must be skipped, not crash the call
            "source": {"name": "Broken"},
            "title": None,
            "url": "https://example.com/3",
            "publishedAt": "not-a-date",
        },
    ],
}


def _run(coro):
    return asyncio.run(coro)


def test_lists_and_invokes_tool_with_partial_success(monkeypatch):
    async def fake_req(path, params):
        return OK_PAYLOAD

    monkeypatch.setattr(wd, "_request_newsapi", fake_req)

    async def scenario():
        async with Client(wd.mcp) as client:
            names = [t.name for t in await client.list_tools()]
            assert "get_top_headlines" in names
            result = await client.call_tool("get_top_headlines", {"country": "gb", "limit": 5})
            return result.data

    data = _run(scenario())
    # Malformed article dropped; the two valid ones survive and are validated.
    assert len(data) == 2
    assert data[0].title == "AI model breaks benchmark"
    assert data[0].source == "BBC News"
    assert str(data[0].url).startswith("https://")
    assert data[1].summary is None  # optional field preserved


def test_query_routes_to_everything_with_time_window(monkeypatch):
    captured: dict = {}

    async def fake_req(path, params):
        captured["path"] = path
        captured["params"] = params
        return {"status": "ok", "totalResults": 0, "articles": []}

    monkeypatch.setattr(wd, "_request_newsapi", fake_req)

    async def scenario():
        async with Client(wd.mcp) as client:
            await client.call_tool(
                "get_top_headlines", {"query": "openai", "since_hours": 24, "limit": 3}
            )

    _run(scenario())
    assert captured["path"] == "/everything"
    assert captured["params"]["q"] == "openai"
    assert "from" in captured["params"] and "to" in captured["params"]  # since_hours -> window


def test_upstream_error_surfaces_as_clean_tool_error(monkeypatch):
    async def fake_req(path, params):
        raise ToolError("news upstream error [401]: apiKeyInvalid")

    monkeypatch.setattr(wd, "_request_newsapi", fake_req)

    async def scenario():
        async with Client(wd.mcp) as client:
            await client.call_tool("get_top_headlines", {})

    with pytest.raises(ToolError) as excinfo:
        _run(scenario())
    assert "upstream error" in str(excinfo.value)


# --- Weather tool (Task 3) ---

# OWM "metric" response: temp already °C, wind in m/s.
OWM_METRIC = {
    "cod": 200,
    "name": "London",
    "sys": {"country": "GB"},
    "main": {"temp": 15.0, "feels_like": 14.2},
    "wind": {"speed": 3.6},  # m/s -> 12.96 kph
    "weather": [{"description": "overcast clouds"}],
    "dt": 1_750_000_000,
}

# OWM "imperial" response: temp in °F, wind in mph — must be normalised to metric.
OWM_IMPERIAL = {
    "cod": 200,
    "name": "New York",
    "sys": {"country": "US"},
    "main": {"temp": 59.0, "feels_like": 57.2},  # 59°F -> 15.0°C
    "wind": {"speed": 10.0},  # mph -> 16.1 kph
    "weather": [{"description": "clear sky"}],
    "dt": 1_750_000_000,
}


def test_both_tools_discoverable_in_one_server():
    async def scenario():
        async with Client(wd.mcp) as client:
            return [t.name for t in await client.list_tools()]

    names = _run(scenario())
    assert {"get_top_headlines", "get_current_weather"} <= set(names)


def test_weather_metric_snapshot(monkeypatch):
    async def fake_owm(params):
        return OWM_METRIC

    monkeypatch.setattr(wd, "_request_owm", fake_owm)

    async def scenario():
        async with Client(wd.mcp) as client:
            return (await client.call_tool("get_current_weather", {"city": "London"})).data

    snap = _run(scenario())
    assert snap.city == "London" and snap.country == "GB"
    assert snap.temp_c == 15.0
    assert snap.wind_kph == 13.0  # 3.6 m/s * 3.6, rounded 1dp
    assert snap.conditions == "overcast clouds"


def test_weather_imperial_is_normalised_to_metric(monkeypatch):
    async def fake_owm(params):
        return OWM_IMPERIAL

    monkeypatch.setattr(wd, "_request_owm", fake_owm)

    async def scenario():
        async with Client(wd.mcp) as client:
            return (
                await client.call_tool("get_current_weather", {"city": "New York", "units": "imperial"})
            ).data

    snap = _run(scenario())
    assert snap.temp_c == 15.0  # 59°F -> 15.0°C
    assert snap.wind_kph == 16.1  # 10 mph -> 16.09344 kph, 1dp


def test_invalid_units_rejected():
    async def scenario():
        async with Client(wd.mcp) as client:
            await client.call_tool("get_current_weather", {"city": "London", "units": "kelvin"})

    with pytest.raises(ToolError) as excinfo:
        _run(scenario())
    assert "units must be" in str(excinfo.value)


def test_invalid_city_surfaces_clean_error(monkeypatch):
    async def fake_owm(params):
        raise ToolError("weather upstream error [404]: city not found")

    monkeypatch.setattr(wd, "_request_owm", fake_owm)

    async def scenario():
        async with Client(wd.mcp) as client:
            await client.call_tool("get_current_weather", {"city": "Nowheresville"})

    with pytest.raises(ToolError) as excinfo:
        _run(scenario())
    assert "city not found" in str(excinfo.value)
