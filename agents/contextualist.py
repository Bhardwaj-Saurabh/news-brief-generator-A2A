"""Contextualist agent — gathers the 'what is happening right now' slice: news + weather.

Stateless per-invocation: everything it needs is in the BriefRequest. It resolves the region to
per-tool identifiers, fans out the two World Data tools concurrently, and returns a ContextBundle.
One upstream failing degrades that section to empty (with a warning); it never crashes the agent.

The optional `deadline` (an absolute time.monotonic() value) is owned by the Scout and passed down
so the per-tool timeouts derive from the parent's remaining time — nested budgets don't compound.
Called standalone, it falls back to a default ~10s budget.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from pydantic import ValidationError

from agents.config import world_data_url
from agents.contracts import BriefRequest, ContextBundle, Headline, WeatherSnapshot
from agents.mcp_client import call_tool
from agents.regions import resolve_region

log = logging.getLogger("contextualist")

DEFAULT_BUDGET = float(os.environ.get("AGENT_BUDGET_SECONDS", "10"))
HEADLINE_LIMIT = 5


def _remaining(deadline: float | None) -> float:
    """Seconds left until the shared deadline; the full default budget when called standalone."""
    if deadline is None:
        return DEFAULT_BUDGET
    return max(0.0, deadline - time.monotonic())


async def _fetch_headlines(request: BriefRequest, country_code: str, timeout: float) -> list[Headline]:
    """News fetch. A topic routes to free-text search with the lookback window; otherwise
    top-headlines for the region. Any failure degrades to an empty list (logged)."""
    if request.topic:
        args: dict[str, object] = {
            "query": request.topic,
            "since_hours": request.lookback_hours,
            "limit": HEADLINE_LIMIT,
        }
    else:
        args = {"country": country_code, "limit": HEADLINE_LIMIT}

    try:
        raw = await asyncio.wait_for(
            call_tool(world_data_url(), "get_top_headlines", args), timeout=timeout
        )
    except Exception as exc:  # timeout, tool error, server down — degrade, don't crash
        log.warning("news fetch failed (%s); headlines section empty", exc)
        return []

    headlines: list[Headline] = []
    for item in raw or []:
        try:
            headlines.append(Headline.model_validate(item))
        except ValidationError as exc:
            log.warning("skipping malformed headline: %s", exc.errors(include_url=False))
    return headlines


async def _fetch_weather(weather_city: str, timeout: float) -> WeatherSnapshot | None:
    """Weather fetch. Any failure (incl. unknown city) degrades to None (logged)."""
    try:
        raw = await asyncio.wait_for(
            call_tool(world_data_url(), "get_current_weather", {"city": weather_city}),
            timeout=timeout,
        )
        return WeatherSnapshot.model_validate(raw)
    except Exception as exc:
        log.warning("weather fetch failed (%s); weather section empty", exc)
        return None


async def gather_context(request: BriefRequest, deadline: float | None = None) -> ContextBundle:
    """Fetch news + weather for the request's region concurrently, within the time budget."""
    ids = resolve_region(request.region)
    timeout = _remaining(deadline)

    headlines, weather = await asyncio.gather(
        _fetch_headlines(request, ids.country_code, timeout),
        _fetch_weather(ids.weather_city, timeout),
    )

    log.info(
        "context region=%s headlines=%d weather=%s",
        request.region,
        len(headlines),
        "ok" if weather else "none",
    )
    return ContextBundle(headlines=headlines, weather=weather, region=request.region)
