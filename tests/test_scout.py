"""Tests for the Scout agent (Task 8).

Mocks the Contextualist (`gather_context`) and the finance/media `call_tool` seam, so no servers or
keys are needed. Covers report composition, LLM-free symbol selection, per-section degradation,
media routing, and budget bounding.
"""

from __future__ import annotations

import asyncio
import time

import agents.scout as scout_mod
from agents.contracts import ContextBundle, ScoutReport
from agents.scout import _select_symbols, scout
from agents.contracts import BriefRequest

MARKET_RAW = [
    {"status": "ok", "symbol": "AAPL", "name": "Apple Inc", "price": "189.95",
     "change": "1.0", "change_pct": "0.5", "as_of": "2026-06-17T15:00:00Z"},
    {"status": "error", "symbol": "INVALID", "error": "unknown symbol"},
]
MEDIA_RAW = [
    {"title": "Clip", "channel": "Chan", "url": "https://www.youtube.com/watch?v=x",
     "published_at": "2026-06-17T10:00:00Z", "views": 100, "summary": "s"},
]


def _run(coro):
    return asyncio.run(coro)


def _fake_context(region="UK"):
    return ContextBundle(headlines=[], weather=None, region=region)


def _patch(monkeypatch, *, context=None, market=MARKET_RAW, media=MEDIA_RAW, capture=None):
    async def fake_gather_context(request, deadline=None):
        return context if context is not None else _fake_context(request.region)

    async def fake_call_tool(server_url, tool, args=None):
        if capture is not None:
            capture[tool] = args
        if tool == "get_market_summary":
            if isinstance(market, Exception):
                raise market
            return market
        if tool in ("search_media", "get_trending"):
            if isinstance(media, Exception):
                raise media
            return media
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(scout_mod, "gather_context", fake_gather_context)
    monkeypatch.setattr(scout_mod, "call_tool", fake_call_tool)


# --- symbol selection (pure) ---

def test_symbol_selection_keyword_and_fallback():
    assert _select_symbols("The AI boom") == ["NVDA", "MSFT", "GOOGL"]
    assert _select_symbols("energy crisis") == ["XOM", "CVX", "COP"]
    assert _select_symbols("retail sales") == ["AMZN", "WMT", "COST"]
    # 'retail' must NOT match the 'ai' keyword (token-exact, not substring)
    assert _select_symbols("retail") != ["NVDA", "MSFT", "GOOGL"]
    # no match and no topic both fall back to the watchlist
    assert _select_symbols("blah blah") == ["SPY", "AAPL", "MSFT"]
    assert _select_symbols(None) == ["SPY", "AAPL", "MSFT"]


# --- composition + degradation ---

def test_scout_composes_full_report(monkeypatch):
    _patch(monkeypatch, context=ContextBundle(headlines=[], weather=None, region="UK"))
    report = _run(scout(BriefRequest(region="UK", topic="ai")))
    assert isinstance(report, ScoutReport)
    assert report.request.topic == "ai"
    assert [q.status for q in report.signals.quotes] == ["ok", "error"]  # partial success preserved
    assert len(report.signals.media_items) == 1


def test_finance_failure_degrades(monkeypatch):
    _patch(monkeypatch, market=RuntimeError("finance down"))
    report = _run(scout(BriefRequest(region="UK", topic="ai")))
    assert report.signals.quotes == []  # degraded
    assert len(report.signals.media_items) == 1  # media unaffected


def test_media_failure_degrades(monkeypatch):
    _patch(monkeypatch, media=RuntimeError("media down"))
    report = _run(scout(BriefRequest(region="UK", topic="ai")))
    assert len(report.signals.quotes) == 2
    assert report.signals.media_items == []  # degraded


def test_topic_routes_media_to_search(monkeypatch):
    capture: dict = {}
    _patch(monkeypatch, capture=capture)
    _run(scout(BriefRequest(region="UK", topic="python")))
    assert "search_media" in capture and capture["search_media"]["query"] == "python"
    assert "get_trending" not in capture


def test_no_topic_routes_media_to_trending(monkeypatch):
    capture: dict = {}
    _patch(monkeypatch, capture=capture)
    _run(scout(BriefRequest(region="US")))  # resolves media_region 'US'
    assert "get_trending" in capture and capture["get_trending"]["region"] == "US"
    assert "search_media" not in capture


def test_budget_bounds_total_walltime(monkeypatch):
    monkeypatch.setattr(scout_mod, "BUDGET", 0.1)

    async def slow_call(server_url, tool, args=None):
        await asyncio.sleep(5)
        return MARKET_RAW

    async def fast_context(request, deadline=None):
        return _fake_context(request.region)

    monkeypatch.setattr(scout_mod, "gather_context", fast_context)
    monkeypatch.setattr(scout_mod, "call_tool", slow_call)

    async def scenario():
        start = time.monotonic()
        report = await scout(BriefRequest(region="UK", topic="ai"))
        return report, time.monotonic() - start

    report, elapsed = _run(scenario())
    assert report.signals.quotes == [] and report.signals.media_items == []
    assert elapsed < 2.0  # bounded by the 0.1s budget, not the 5s sleep
