"""Scout agent — the aggregator. Fans out to the Contextualist + Finance + Media, returns a ScoutReport.

Owns the single overall time budget: it sets one monotonic deadline and passes it down to the
Contextualist so nested budgets don't compound, and bounds its own Finance/Media calls by the same
remaining time. Every upstream is isolated — one failure degrades that section to empty (logged),
never crashes the report.

Symbol selection is deliberately LLM-free: a static keyword->ticker map over the topic, falling back
to a default watchlist (with a warning) when a provided topic matches nothing. Richer topic->symbol
resolution would need the LLM or a symbol-search API and is out of scope — it would break the
"Publisher is the only LLM call" invariant.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time

from pydantic import TypeAdapter, ValidationError

from agents.config import finance_url, media_url
from agents.contextualist import gather_context
from agents.contracts import (
    BriefRequest,
    MediaItem,
    QuoteResult,
    ScoutReport,
    SignalBundle,
)
from agents.mcp_client import call_tool
from agents.regions import resolve_region

log = logging.getLogger("scout")

BUDGET = float(os.environ.get("AGENT_BUDGET_SECONDS", "10"))
MEDIA_LIMIT = 5

# Validates a single finance result dict into Quote | QuoteError via the `status` discriminator.
_QUOTE_ADAPTER: TypeAdapter = TypeAdapter(QuoteResult)

# --- LLM-free symbol selection ---------------------------------------------------------------
_TECH = ["AAPL", "MSFT", "NVDA", "GOOGL"]
_AI = ["NVDA", "MSFT", "GOOGL"]
_ENERGY = ["XOM", "CVX", "COP"]
_CRYPTO = ["COIN", "MSTR"]
_EV = ["TSLA", "RIVN", "GM"]
_FINANCE = ["JPM", "GS", "BAC"]
_RETAIL = ["AMZN", "WMT", "COST"]
_HEALTH = ["JNJ", "PFE", "UNH"]
_SEMI = ["NVDA", "AMD", "TSM"]

# Whole-word keyword -> tickers (token-exact match, so 'retail' won't match 'ai').
_KEYWORD_TICKERS: dict[str, list[str]] = {
    "tech": _TECH, "technology": _TECH,
    "ai": _AI, "artificial": _AI,
    "energy": _ENERGY, "oil": _ENERGY, "gas": _ENERGY,
    "crypto": _CRYPTO, "bitcoin": _CRYPTO, "blockchain": _CRYPTO,
    "ev": _EV, "electric": _EV, "tesla": _EV, "auto": _EV, "car": _EV,
    "finance": _FINANCE, "bank": _FINANCE, "banking": _FINANCE,
    "retail": _RETAIL, "shopping": _RETAIL,
    "health": _HEALTH, "healthcare": _HEALTH, "pharma": _HEALTH,
    "semiconductor": _SEMI, "chip": _SEMI, "chips": _SEMI,
}
DEFAULT_WATCHLIST = ["SPY", "AAPL", "MSFT"]


def _select_symbols(topic: str | None) -> list[str]:
    """Map a topic to tickers via the keyword table; fall back to the watchlist (warn on a real miss)."""
    if not topic:
        log.debug("no topic; using default watchlist %s", DEFAULT_WATCHLIST)
        return DEFAULT_WATCHLIST

    tokens = set(re.findall(r"[a-z0-9]+", topic.lower()))
    for keyword, tickers in _KEYWORD_TICKERS.items():
        if keyword in tokens:
            log.info("topic %r matched %r -> %s", topic, keyword, tickers)
            return tickers

    log.warning("no ticker match for topic %r; using default watchlist %s", topic, DEFAULT_WATCHLIST)
    return DEFAULT_WATCHLIST


# --- Concurrent fetches (each total: returns a value, never raises) ---------------------------
async def _fetch_quotes(symbols: list[str], timeout: float) -> list[QuoteResult]:
    try:
        raw = await asyncio.wait_for(
            call_tool(finance_url(), "get_market_summary", {"symbols": symbols}), timeout=timeout
        )
    except Exception as exc:
        log.warning("finance fetch failed (%s); quotes section empty", exc)
        return []

    quotes: list[QuoteResult] = []
    for item in raw or []:
        try:
            quotes.append(_QUOTE_ADAPTER.validate_python(item))
        except ValidationError as exc:
            log.warning("skipping malformed quote: %s", exc.errors(include_url=False))
    return quotes


async def _fetch_media(request: BriefRequest, media_region: str, timeout: float) -> list[MediaItem]:
    if request.topic:
        tool, args = "search_media", {"query": request.topic, "limit": MEDIA_LIMIT}
    else:
        tool, args = "get_trending", {"region": media_region, "limit": MEDIA_LIMIT}

    try:
        raw = await asyncio.wait_for(call_tool(media_url(), tool, args), timeout=timeout)
    except Exception as exc:
        log.warning("media fetch failed (%s); media section empty", exc)
        return []

    items: list[MediaItem] = []
    for item in raw or []:
        try:
            items.append(MediaItem.model_validate(item))
        except ValidationError as exc:
            log.warning("skipping malformed media item: %s", exc.errors(include_url=False))
    return items


async def scout(request: BriefRequest) -> ScoutReport:
    """Gather context + signals concurrently within one budget and compose a ScoutReport."""
    start = time.monotonic()
    deadline = start + BUDGET
    ids = resolve_region(request.region)
    symbols = _select_symbols(request.topic)
    timeout = max(0.0, deadline - time.monotonic())

    context, quotes, media = await asyncio.gather(
        gather_context(request, deadline),  # Contextualist owns news+weather under the shared deadline
        _fetch_quotes(symbols, timeout),
        _fetch_media(request, ids.media_region, timeout),
    )

    report = ScoutReport(
        context=context,
        signals=SignalBundle(quotes=quotes, media_items=media),
        request=request,
    )
    log.info(
        "scout report: headlines=%d quotes=%d media=%d in %.2fs",
        len(context.headlines),
        len(quotes),
        len(media),
        time.monotonic() - start,
    )
    return report
