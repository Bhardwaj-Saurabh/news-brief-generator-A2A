"""Tests for the A2A contracts, region resolver, and MCP client (Task 6).

Covers: every model constructs with realistic data; frozen models are immutable; the generic
AgentMessage[T] round-trips JSON without losing the payload type; resolve_region maps and falls
back correctly; call_tool returns raw unwrapped data.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agents import mcp_client
from agents.contracts import (
    AgentMessage,
    BriefRequest,
    ContextBundle,
    Headline,
    MediaItem,
    PublishedBrief,
    Quote,
    QuoteError,
    ScoutReport,
    Section,
    SignalBundle,
    Source,
    WeatherSnapshot,
)
from agents.regions import resolve_region

DT = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)


def _request() -> BriefRequest:
    return BriefRequest(topic="ai", region="UK", lookback_hours=12, audience="executives")


def _context() -> ContextBundle:
    return ContextBundle(
        headlines=[
            Headline(
                title="AI breakthrough",
                source="BBC News",
                url="https://bbc.co.uk/news/1",
                published_at=DT,
                summary="A summary.",
            )
        ],
        weather=WeatherSnapshot(
            city="London",
            country="GB",
            temp_c=15.0,
            feels_like_c=14.2,
            conditions="overcast clouds",
            wind_kph=12.0,
            observed_at=DT,
        ),
        region="UK",
    )


def _signals() -> SignalBundle:
    return SignalBundle(
        quotes=[
            Quote(
                symbol="AAPL",
                name="Apple Inc",
                price=Decimal("189.95"),
                change=Decimal("1.25"),
                change_pct=Decimal("0.66"),
                as_of=DT,
            ),
            QuoteError(symbol="INVALID", error="unknown symbol"),
        ],
        media_items=[
            MediaItem(
                title="Trending clip",
                channel="SomeChannel",
                url="https://www.youtube.com/watch?v=abc",
                published_at=DT,
                views=12345,
                summary="short",
            )
        ],
    )


def test_full_scout_report_constructs_with_realistic_data():
    report = ScoutReport(context=_context(), signals=_signals(), request=_request())
    assert report.context.headlines[0].source == "BBC News"
    assert report.context.weather.temp_c == 15.0
    # The discriminated union preserves both a success and an error entry.
    assert report.signals.quotes[0].status == "ok"
    assert report.signals.quotes[1].status == "error"
    assert report.request.topic == "ai"


def test_published_brief_and_source_domain():
    brief = PublishedBrief(
        title="Daily Brief",
        markdown="# Daily Brief\n...",
        sections=[Section(heading="World", body_markdown="Things happened.")],
        sources=[Source.from_url("BBC", "https://www.bbc.co.uk/news/1")],
        request=_request(),
    )
    assert brief.sections[0].heading == "World"
    assert brief.sources[0].domain == "bbc.co.uk"  # 'www.' stripped, host extracted


def test_source_from_url_strips_www():
    assert Source.from_url("X", "https://www.example.com/a/b").domain == "example.com"
    assert Source.from_url("Y", "https://news.ycombinator.com/item").domain == "news.ycombinator.com"


def test_frozen_models_are_immutable():
    req = _request()
    with pytest.raises(ValidationError):
        req.region = "US"  # frozen=True -> mutation rejected


def test_agent_message_roundtrips_payload_type():
    report = ScoutReport(context=_context(), signals=_signals(), request=_request())
    msg = AgentMessage[ScoutReport](
        from_agent="scout", to_agent="publisher", payload=report, trace_id="trace-123"
    )
    restored = AgentMessage[ScoutReport].model_validate_json(msg.model_dump_json())

    assert isinstance(restored.payload, ScoutReport)  # type survives the round-trip
    assert restored.payload.context.headlines[0].source == "BBC News"
    assert restored.payload.signals.quotes[1].status == "error"  # union variant preserved
    assert restored.payload.signals.quotes[0].price == Decimal("189.95")  # Decimal survives
    assert restored.id == msg.id and restored.trace_id == "trace-123"


def test_resolve_region_uk_triple():
    ids = resolve_region("UK")
    assert (ids.country_code, ids.weather_city, ids.media_region) == ("gb", "London", "GB")


def test_resolve_region_aliases_and_fallback():
    assert resolve_region("United Kingdom").country_code == "gb"  # alias
    assert resolve_region("usa").media_region == "US"  # case-insensitive alias
    assert resolve_region("Narnia").country_code == "gb"  # unknown -> default UK


def test_call_tool_returns_raw_unwrapped_data(monkeypatch):
    import servers.finance_server as fin

    async def fake(path, params):
        return {"c": 189.95, "d": 1.0, "dp": 0.5, "t": 1_750_000_000} if path == "/quote" else {"name": "Apple Inc"}

    monkeypatch.setattr(fin, "_request_finnhub", fake)

    async def scenario():
        # call_tool accepts an in-memory FastMCP server as well as a URL.
        return await mcp_client.call_tool(fin.mcp, "get_market_summary", {"symbols": ["AAPL"]})

    data = asyncio.run(scenario())
    assert isinstance(data, list)  # unwrapped from {"result": [...]}
    assert data[0]["symbol"] == "AAPL" and data[0]["status"] == "ok"
