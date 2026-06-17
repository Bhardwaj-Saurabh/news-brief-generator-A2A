"""World Data MCP server — wraps NewsAPI (and, from Task 3, OpenWeatherMap).

Stateless and "dumb": it normalises one upstream API into validated Pydantic models and
returns them. It does not interpret. Errors are surfaced as clean tool errors, never a 500.

Run:  uv run python -m servers.world_data_server   (binds 127.0.0.1:$WORLD_DATA_PORT, default 8801)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

# Agent Framework / our code do not auto-load .env — do it explicitly at import.
load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("world_data_server")

NEWSAPI_BASE = "https://newsapi.org/v2"
REQUEST_TIMEOUT = httpx.Timeout(10.0)  # timeout on every external call (cross-cutting rule)
MAX_PAGE_SIZE = 100  # NewsAPI hard cap on pageSize

mcp = FastMCP(
    name="world-data",
    instructions="Live world context: top news headlines (and weather from Task 3).",
)


class Headline(BaseModel):
    """One normalised news headline. The validated shape the Contextualist consumes —
    upstream NewsAPI fields (nested source, publishedAt, description) are flattened here."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    source: str = Field(min_length=1, description="Publisher name, e.g. 'BBC News'")
    url: HttpUrl
    published_at: datetime
    summary: str | None = Field(default=None, description="Short article description, if any")


async def _request_newsapi(path: str, params: dict[str, object]) -> dict:
    """GET a NewsAPI endpoint and return parsed JSON, or raise ToolError.

    This is the single network seam (tests monkeypatch it). The API key travels in the
    X-Api-Key header, never the URL/query, so it cannot leak into request logs.
    """
    key = os.environ.get("NEWSAPI_KEY", "").strip()
    if not key:
        raise ToolError("NEWSAPI_KEY is not configured")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(
                f"{NEWSAPI_BASE}{path}", params=params, headers={"X-Api-Key": key}
            )
    except httpx.HTTPError as exc:  # timeout, connect error, etc.
        raise ToolError(f"news upstream unreachable: {exc}") from exc

    # NewsAPI signals failure both via HTTP status and a JSON {"status":"error",...} body.
    try:
        data = resp.json()
    except ValueError as exc:
        raise ToolError(f"news upstream returned non-JSON (HTTP {resp.status_code})") from exc

    if resp.status_code != 200 or data.get("status") != "ok":
        code = data.get("code", resp.status_code)
        message = data.get("message", "unknown error")
        raise ToolError(f"news upstream error [{code}]: {message}")

    return data


def _to_headline(article: dict) -> Headline:
    """Flatten one NewsAPI article into a Headline (raises ValidationError if malformed)."""
    return Headline.model_validate(
        {
            "title": article.get("title"),
            "source": (article.get("source") or {}).get("name"),
            "url": article.get("url"),
            "published_at": article.get("publishedAt"),
            "summary": article.get("description"),
        }
    )


@mcp.tool
async def get_top_headlines(
    country: str = "gb",
    category: str | None = None,
    query: str | None = None,
    since_hours: int | None = None,
    limit: int = 5,
) -> list[Headline]:
    """Fetch recent news headlines.

    With `query` set, searches NewsAPI's `everything` endpoint (free-text `q` plus an optional
    `since_hours` time window). Without `query`, returns `top-headlines` for `country`
    (optionally filtered by `category`). `limit` caps the number returned (1-100).
    """
    page_size = max(1, min(limit, MAX_PAGE_SIZE))

    if query:
        params: dict[str, object] = {
            "q": query,
            "sortBy": "publishedAt",
            "language": "en",  # simplification: search path is English-only
            "pageSize": page_size,
        }
        if since_hours and since_hours > 0:
            now = datetime.now(timezone.utc)
            params["from"] = (now - timedelta(hours=since_hours)).isoformat()
            params["to"] = now.isoformat()
        if country or category:
            log.debug("country/category ignored on the 'everything' (query) path")
        path = "/everything"
    else:
        params = {"country": country, "pageSize": page_size}
        if category:
            params["category"] = category
        path = "/top-headlines"

    data = await _request_newsapi(path, params)

    articles = data.get("articles")
    if not isinstance(articles, list):
        raise ToolError("unexpected news response shape: 'articles' missing or not a list")

    headlines: list[Headline] = []
    for article in articles:
        try:
            headlines.append(_to_headline(article))
        except ValidationError as exc:
            # Partial success: skip one malformed article, keep the rest.
            log.warning("skipping malformed article: %s", exc.errors(include_url=False))

    log.info("get_top_headlines path=%s returned=%d/%d", path, len(headlines), len(articles))
    return headlines


if __name__ == "__main__":
    host = "127.0.0.1"
    port = int(os.environ.get("WORLD_DATA_PORT", "8801"))
    tool_names = ", ".join(t.name for t in asyncio.run(mcp.list_tools()))
    log.info("starting MCP server '%s' on http://%s:%d | tools: %s", mcp.name, host, port, tool_names)
    mcp.run(transport="http", host=host, port=port)
