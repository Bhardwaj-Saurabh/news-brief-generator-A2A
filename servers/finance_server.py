"""Finance MCP server — wraps Finnhub (quote + company profile).

Independent of the world-data server: its own process, its own port ($FINANCE_PORT, default 8802).
Stateless and "dumb": it normalises Finnhub responses into validated models and returns them.
Money is handled as Decimal, never float. Errors are data — batch calls return per-symbol error
entries instead of failing the whole request.

Run:  uv run python -m servers.finance_server
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("finance_server")

# Finnhub takes its key as the `token` query param (no header auth) — silence httpx URL logging.
logging.getLogger("httpx").setLevel(logging.WARNING)

FINNHUB_BASE = "https://finnhub.io/api/v1"
REQUEST_TIMEOUT = httpx.Timeout(10.0)

mcp = FastMCP(
    name="finance",
    instructions="Live equity quotes: single quote and multi-symbol market summary.",
)


class Quote(BaseModel):
    """A normalised stock quote. `status='ok'` discriminates it from QuoteError in mixed lists.
    Prices are Decimal (exact) — never float — because money must not accumulate binary rounding."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)
    price: Decimal
    change: Decimal
    change_pct: Decimal
    as_of: datetime


class QuoteError(BaseModel):
    """A per-symbol failure entry. Lets batch tools report partial success without raising."""

    model_config = ConfigDict(frozen=True)

    status: Literal["error"] = "error"
    symbol: str = Field(min_length=1)
    error: str


async def _request_finnhub(path: str, params: dict[str, object]) -> dict:
    """GET a Finnhub endpoint and return parsed JSON, or raise ToolError (transport-level)."""
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        raise ToolError("FINNHUB_API_KEY is not configured")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(f"{FINNHUB_BASE}{path}", params={**params, "token": key})
    except httpx.HTTPError as exc:
        raise ToolError(f"finance upstream unreachable: {exc}") from exc

    if resp.status_code != 200:
        # Finnhub uses 401 (bad key) / 429 (rate limit) with a text body.
        raise ToolError(f"finance upstream error [HTTP {resp.status_code}]: {resp.text[:200]}")

    try:
        return resp.json()
    except ValueError as exc:
        raise ToolError(f"finance upstream returned non-JSON (HTTP {resp.status_code})") from exc


def _dec(value: object) -> Decimal:
    """Coerce a Finnhub number to Decimal via str (avoids float binary artefacts). None -> 0."""
    return Decimal(str(value)) if value is not None else Decimal("0")


async def _fetch_one(symbol: str) -> Quote | QuoteError:
    """Resolve one symbol to a Quote, or a QuoteError. Never raises.

    Finnhub does NOT 404 unknown tickers — /quote returns all-zeros and /stock/profile2 returns
    an empty object. We treat an empty profile (no company name) as 'unknown symbol'.
    """
    sym = symbol.strip().upper()
    if not sym:
        return QuoteError(symbol=symbol, error="empty symbol")

    try:
        quote, profile = await asyncio.gather(
            _request_finnhub("/quote", {"symbol": sym}),
            _request_finnhub("/stock/profile2", {"symbol": sym}),
        )
    except ToolError as exc:
        # Transport-level failure becomes a per-symbol entry so a batch can still report the rest.
        return QuoteError(symbol=sym, error=str(exc))

    name = (profile or {}).get("name")
    if not name:
        return QuoteError(symbol=sym, error="unknown symbol")

    try:
        return Quote.model_validate(
            {
                "symbol": sym,
                "name": name,
                "price": _dec(quote.get("c")),
                "change": _dec(quote.get("d")),
                "change_pct": _dec(quote.get("dp")),
                "as_of": datetime.fromtimestamp(quote.get("t") or 0, tz=timezone.utc),
            }
        )
    except (TypeError, ValidationError) as exc:
        return QuoteError(symbol=sym, error=f"malformed quote data: {exc}")


@mcp.tool
async def get_quote(symbol: str) -> Quote:
    """Current quote for a single ticker (e.g. 'AAPL'). An unknown ticker is a clear error."""
    result = await _fetch_one(symbol)
    if isinstance(result, QuoteError):
        raise ToolError(f"{result.symbol}: {result.error}")
    log.info("get_quote %s -> %s @ %s", result.symbol, result.name, result.price)
    return result


@mcp.tool
async def get_market_summary(symbols: list[str]) -> list[Quote | QuoteError]:
    """Quotes for several tickers at once. Fans out concurrently; each symbol resolves to a Quote
    or a QuoteError entry, so one bad ticker never fails the whole call (partial success)."""
    if not symbols:
        return []
    results = await asyncio.gather(*(_fetch_one(s) for s in symbols))
    ok = sum(1 for r in results if isinstance(r, Quote))
    log.info("get_market_summary requested=%d ok=%d errors=%d", len(symbols), ok, len(results) - ok)
    return list(results)


if __name__ == "__main__":
    host = "127.0.0.1"
    port = int(os.environ.get("FINANCE_PORT", "8802"))
    tool_names = ", ".join(t.name for t in asyncio.run(mcp.list_tools()))
    log.info("starting MCP server '%s' on http://%s:%d | tools: %s", mcp.name, host, port, tool_names)
    mcp.run(transport="http", host=host, port=port)
