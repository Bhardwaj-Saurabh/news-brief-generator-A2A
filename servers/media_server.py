"""Media MCP server — wraps the YouTube Data API v3 (trending + search).

Independent process on its own port ($MEDIA_PORT, default 8803). Stateless and "dumb": it
normalises YouTube responses into validated MediaItem models, deterministically truncating long
descriptions so a brief never carries a wall of text. Quota-exceeded is surfaced as a typed error.

Run:  uv run python -m servers.media_server
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("media_server")

# YouTube takes its key as the `key` query param (no header auth) — silence httpx URL logging.
logging.getLogger("httpx").setLevel(logging.WARNING)

YOUTUBE_BASE = "https://www.googleapis.com/youtube/v3"
REQUEST_TIMEOUT = httpx.Timeout(10.0)
MAX_RESULTS = 50  # YouTube hard cap on maxResults
SUMMARY_MAX = 200  # description budget — long enough to inform, short enough for a brief

mcp = FastMCP(
    name="media",
    instructions="Trending and searched YouTube videos, normalised for a news brief.",
)


class MediaItem(BaseModel):
    """A normalised video. `summary` is a deterministically truncated description; `views` is
    optional because the search endpoint doesn't return statistics (we backfill when we can)."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    url: HttpUrl
    published_at: datetime
    views: int | None = None
    summary: str = ""


def _truncate(text: str | None, limit: int = SUMMARY_MAX) -> str:
    """Deterministically shorten a description to `limit` chars, adding an ellipsis if cut."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _to_int(value: object) -> int | None:
    """YouTube returns viewCount as a string; coerce to int, or None if absent/non-numeric."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


async def _request_youtube(path: str, params: dict[str, object]) -> dict:
    """GET a YouTube Data API endpoint and return parsed JSON, or raise ToolError.

    Quota exhaustion comes back as HTTP 403 with reason 'quotaExceeded' — surfaced as a typed
    ToolError so callers degrade gracefully rather than crash.
    """
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise ToolError("YOUTUBE_API_KEY is not configured")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(f"{YOUTUBE_BASE}{path}", params={**params, "key": key})
    except httpx.HTTPError as exc:
        raise ToolError(f"media upstream unreachable: {exc}") from exc

    if resp.status_code != 200:
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        reason = (err.get("errors") or [{}])[0].get("reason", "")
        message = err.get("message", resp.text[:200])
        raise ToolError(f"media upstream error [{reason or resp.status_code}]: {message}")

    try:
        return resp.json()
    except ValueError as exc:
        raise ToolError(f"media upstream returned non-JSON (HTTP {resp.status_code})") from exc


def _to_media_item(video_id: str, snippet: dict, views: int | None) -> MediaItem:
    """Build a MediaItem from a YouTube snippet (raises ValidationError if malformed)."""
    return MediaItem.model_validate(
        {
            "title": snippet.get("title"),
            "channel": snippet.get("channelTitle"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "published_at": snippet.get("publishedAt"),
            "views": views,
            "summary": _truncate(snippet.get("description")),
        }
    )


def _collect(items: list, view_of) -> list[MediaItem]:
    """Map raw items -> MediaItem, skipping malformed ones (partial success)."""
    out: list[MediaItem] = []
    for video_id, snippet in items:
        try:
            out.append(_to_media_item(video_id, snippet, view_of(video_id)))
        except ValidationError as exc:
            log.warning("skipping malformed video %s: %s", video_id, exc.errors(include_url=False))
    return out


@mcp.tool
async def get_trending(region: str = "GB", limit: int = 5) -> list[MediaItem]:
    """Most-popular (trending) videos for a region (ISO code, e.g. 'GB'). Includes view counts."""
    n = max(1, min(limit, MAX_RESULTS))
    data = await _request_youtube(
        "/videos",
        {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": region, "maxResults": n},
    )
    raw = data.get("items")
    if not isinstance(raw, list):
        raise ToolError("unexpected media response shape: 'items' missing or not a list")

    views: dict[str, int | None] = {}
    pairs: list[tuple[str, dict]] = []
    for it in raw:
        vid = it.get("id")
        if not isinstance(vid, str):
            continue
        pairs.append((vid, it.get("snippet") or {}))
        views[vid] = _to_int((it.get("statistics") or {}).get("viewCount"))

    result = _collect(pairs, views.get)
    log.info("get_trending region=%s returned=%d/%d", region, len(result), len(raw))
    return result


@mcp.tool
async def search_media(query: str, limit: int = 5) -> list[MediaItem]:
    """Search videos by free text. Backfills view counts with one batched videos.list call."""
    n = max(1, min(limit, MAX_RESULTS))
    sdata = await _request_youtube(
        "/search", {"part": "snippet", "q": query, "type": "video", "maxResults": n}
    )
    sitems = sdata.get("items")
    if not isinstance(sitems, list):
        raise ToolError("unexpected media response shape: 'items' missing or not a list")

    pairs: list[tuple[str, dict]] = []
    for it in sitems:
        vid = (it.get("id") or {}).get("videoId")
        if isinstance(vid, str):
            pairs.append((vid, it.get("snippet") or {}))

    # One batched videos.list (1 quota unit) fetches statistics for every found id at once —
    # YouTube *has* a batch endpoint, unlike Finnhub, so we don't fan out per video.
    views: dict[str, int | None] = {}
    if pairs:
        vdata = await _request_youtube(
            "/videos", {"part": "statistics", "id": ",".join(vid for vid, _ in pairs)}
        )
        for it in vdata.get("items") or []:
            views[it.get("id")] = _to_int((it.get("statistics") or {}).get("viewCount"))

    result = _collect(pairs, lambda vid: views.get(vid))
    log.info("search_media q=%r returned=%d/%d", query, len(result), len(sitems))
    return result


if __name__ == "__main__":
    host = "127.0.0.1"
    port = int(os.environ.get("MEDIA_PORT", "8803"))
    tool_names = ", ".join(t.name for t in asyncio.run(mcp.list_tools()))
    log.info("starting MCP server '%s' on http://%s:%d | tools: %s", mcp.name, host, port, tool_names)
    mcp.run(transport="http", host=host, port=port)
