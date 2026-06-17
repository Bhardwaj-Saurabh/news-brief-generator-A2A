"""A2A message contracts — the real, typed API between agents.

These Pydantic models are what flows agent-to-agent (never loose dicts). The *tool* contracts
(`Headline`, `WeatherSnapshot`, `Quote`/`QuoteError`, `MediaItem`) are owned by their MCP servers
and imported here; the *agent* contracts below compose them. That import is the deliberate line
between a tool contract (a server's output) and an agent contract (a message between agents).

All models are frozen: a fact, once gathered, is immutable as it travels downstream. Timestamps
default to UTC-now and ids to uuid4, so a message is valid the moment it is constructed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Generic, TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

# Tool contracts (owned by the MCP servers) — imported, not redefined.
from servers.finance_server import Quote, QuoteError
from servers.media_server import MediaItem
from servers.world_data_server import Headline, WeatherSnapshot

__all__ = [
    "BriefRequest",
    "ContextBundle",
    "SignalBundle",
    "ScoutReport",
    "Section",
    "Source",
    "PublishedBrief",
    "AgentMessage",
    # re-export tool contracts so consumers import the whole vocabulary from one place
    "Headline",
    "WeatherSnapshot",
    "Quote",
    "QuoteError",
    "MediaItem",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# A quote result is either a Quote or a QuoteError, discriminated on `status` so it deserialises
# deterministically (no guessing which variant a JSON object is).
QuoteResult = Annotated[Quote | QuoteError, Field(discriminator="status")]


class BriefRequest(BaseModel):
    """What the user asked for. The single input the Scout fans out from.

    `topic` is free text (None -> general headlines); `region` is a human label resolved to
    per-tool identifiers by `agents/regions.py`; `lookback_hours` bounds the news search window.
    """

    model_config = ConfigDict(frozen=True)

    topic: str | None = None
    region: str = "UK"
    lookback_hours: int = Field(default=24, ge=1, le=24 * 14)
    audience: str = "general"
    requested_at: datetime = Field(default_factory=_utcnow)


class ContextBundle(BaseModel):
    """The 'what is happening right now' slice the Contextualist produces: news + weather.

    `weather` is optional and `headlines` defaults empty so a degraded fetch (one upstream down)
    still yields a valid bundle with that section empty.
    """

    model_config = ConfigDict(frozen=True)

    headlines: list[Headline] = Field(default_factory=list)
    weather: WeatherSnapshot | None = None
    region: str
    generated_at: datetime = Field(default_factory=_utcnow)


class SignalBundle(BaseModel):
    """The market + media slice the Scout gathers directly.

    `quotes` keeps `QuoteError` entries (not just successes) so per-symbol partial success is
    visible all the way into the report, not silently dropped at the agent boundary.
    """

    model_config = ConfigDict(frozen=True)

    quotes: list[QuoteResult] = Field(default_factory=list)
    media_items: list[MediaItem] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)


class ScoutReport(BaseModel):
    """Everything the Scout gathered, plus the originating request. The Publisher's sole input.

    Carrying `request` makes the report self-describing: the Publisher can shape tone/length from
    `audience` without ever seeing a separate BriefRequest.
    """

    model_config = ConfigDict(frozen=True)

    context: ContextBundle
    signals: SignalBundle
    request: BriefRequest


class Section(BaseModel):
    """One titled block of the finished brief. Typed so the UI renders structure, not a blob."""

    model_config = ConfigDict(frozen=True)

    heading: str = Field(min_length=1)
    body_markdown: str


class Source(BaseModel):
    """An attribution link. `domain` is stored (not re-parsed) so the UI can group by domain cheaply."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    url: HttpUrl
    domain: str = Field(min_length=1)

    @classmethod
    def from_url(cls, title: str, url: str) -> "Source":
        """Build a Source, deriving `domain` from the URL host (sans leading 'www.')."""
        host = (urlparse(url).hostname or "").removeprefix("www.")
        return cls(title=title, url=url, domain=host or "unknown")


class PublishedBrief(BaseModel):
    """The Publisher's output. `sections`/`sources` are typed so Task 11's UI is a field read,
    not a re-parse of `markdown`. `markdown` is the rendered whole; `sections` is its structure."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    markdown: str = Field(min_length=1)
    sections: list[Section] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)
    request: BriefRequest


T = TypeVar("T")


class AgentMessage(BaseModel, Generic[T]):
    """Generic typed envelope: identity + routing + a typed `payload`.

    Defined as the reference contract for a future message bus but kept OFF the hot path — agent
    functions pass bare payloads (BriefRequest, ScoutReport), not envelopes, because the MCP
    boundary cannot carry a `trace_id` across it anyway (correlation uses a contextvars trace id
    + logging filter instead). Parameterise it (`AgentMessage[ScoutReport]`) to round-trip the
    payload type through JSON.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str
    to_agent: str
    payload: T
    trace_id: str | None = None
    timestamp: datetime = Field(default_factory=_utcnow)
