"""Smoke tests for the Finance MCP server (get_quote, get_market_summary).

Quota-free: the network seam `_request_finnhub` is monkeypatched. Tests drive the tools through a
real in-memory MCP Client, exercising the partial-success contract end to end.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import servers.finance_server as fin

QUOTES = {
    "AAPL": {"c": 189.95, "d": 1.25, "dp": 0.66, "t": 1_750_000_000},
    "MSFT": {"c": 430.10, "d": -2.0, "dp": -0.46, "t": 1_750_000_000},
    "INVALID": {"c": 0, "d": None, "dp": None, "t": 0},  # Finnhub's "unknown ticker" shape
}
PROFILES = {
    "AAPL": {"name": "Apple Inc"},
    "MSFT": {"name": "Microsoft Corp"},
    "INVALID": {},  # empty profile == unknown symbol
}


def _install_fake(monkeypatch):
    async def fake_req(path, params):
        sym = params["symbol"]
        return QUOTES[sym] if path == "/quote" else PROFILES[sym]

    monkeypatch.setattr(fin, "_request_finnhub", fake_req)


def _run(coro):
    return asyncio.run(coro)


def test_lists_both_tools():
    async def scenario():
        async with Client(fin.mcp) as client:
            return [t.name for t in await client.list_tools()]

    assert {"get_quote", "get_market_summary"} <= set(_run(scenario()))


def test_market_summary_partial_success(monkeypatch):
    _install_fake(monkeypatch)

    async def scenario():
        async with Client(fin.mcp) as client:
            res = await client.call_tool(
                "get_market_summary", {"symbols": ["AAPL", "MSFT", "INVALID"]}
            )
            return res.data

    data = _run(scenario())
    assert len(data) == 3
    by_symbol = {r.symbol: r for r in data}
    assert by_symbol["AAPL"].status == "ok" and Decimal(by_symbol["AAPL"].price) == Decimal("189.95")
    assert by_symbol["MSFT"].status == "ok" and Decimal(by_symbol["MSFT"].change) == Decimal("-2.0")
    # The invalid one is a structured error entry, NOT a raised exception.
    assert by_symbol["INVALID"].status == "error"
    assert by_symbol["INVALID"].error == "unknown symbol"


def test_get_quote_valid(monkeypatch):
    _install_fake(monkeypatch)

    async def scenario():
        async with Client(fin.mcp) as client:
            return (await client.call_tool("get_quote", {"symbol": "AAPL"})).data

    quote = _run(scenario())
    assert quote.symbol == "AAPL" and quote.name == "Apple Inc"
    assert Decimal(quote.price) == Decimal("189.95")


def test_get_quote_unknown_raises_clean_error(monkeypatch):
    _install_fake(monkeypatch)

    async def scenario():
        async with Client(fin.mcp) as client:
            await client.call_tool("get_quote", {"symbol": "INVALID"})

    with pytest.raises(ToolError) as excinfo:
        _run(scenario())
    assert "unknown symbol" in str(excinfo.value)


def test_market_summary_transport_error_becomes_entry(monkeypatch):
    async def boom(path, params):
        raise ToolError("finance upstream error [HTTP 429]: rate limit")

    monkeypatch.setattr(fin, "_request_finnhub", boom)

    async def scenario():
        async with Client(fin.mcp) as client:
            return (await client.call_tool("get_market_summary", {"symbols": ["AAPL"]})).data

    data = _run(scenario())
    # Never raises out of the batch tool — the failure is a per-symbol entry.
    assert len(data) == 1 and data[0].status == "error"
    assert "rate limit" in data[0].error


def test_empty_symbols_returns_empty_list():
    async def scenario():
        async with Client(fin.mcp) as client:
            return (await client.call_tool("get_market_summary", {"symbols": []})).data

    assert _run(scenario()) == []
