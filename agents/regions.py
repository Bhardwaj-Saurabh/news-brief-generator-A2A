"""Region resolution — one place to translate a BriefRequest.region into per-tool identifiers.

`BriefRequest` carries a single human `region` ("UK"), but the three tools want three different
shapes: a lowercase country code for NewsAPI, a city for OpenWeatherMap, an uppercase region code
for YouTube. Centralising the mapping here keeps the translation testable in one spot instead of
smuggled into each agent. Unknown regions fall back to the default and log a warning (no silent miss).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict

log = logging.getLogger("regions")

DEFAULT_REGION = "UK"


class RegionIds(BaseModel):
    """The three identifiers a single region resolves to, one per downstream tool."""

    model_config = ConfigDict(frozen=True)

    country_code: str  # NewsAPI top-headlines `country`, lowercase (e.g. 'gb')
    weather_city: str  # OpenWeatherMap `q` (e.g. 'London')
    media_region: str  # YouTube `regionCode`, uppercase (e.g. 'GB')


# Canonical region key -> identifiers. Add rows here to support more regions.
_REGIONS: dict[str, RegionIds] = {
    "UK": RegionIds(country_code="gb", weather_city="London", media_region="GB"),
    "US": RegionIds(country_code="us", weather_city="New York", media_region="US"),
    "IN": RegionIds(country_code="in", weather_city="Mumbai", media_region="IN"),
    "CA": RegionIds(country_code="ca", weather_city="Toronto", media_region="CA"),
    "AU": RegionIds(country_code="au", weather_city="Sydney", media_region="AU"),
    "DE": RegionIds(country_code="de", weather_city="Berlin", media_region="DE"),
    "FR": RegionIds(country_code="fr", weather_city="Paris", media_region="FR"),
}

# Common aliases -> canonical key, so user-facing labels need not match the table exactly.
_ALIASES: dict[str, str] = {
    "GB": "UK",
    "UNITED KINGDOM": "UK",
    "ENGLAND": "UK",
    "BRITAIN": "UK",
    "USA": "US",
    "UNITED STATES": "US",
    "AMERICA": "US",
    "INDIA": "IN",
    "CANADA": "CA",
    "AUSTRALIA": "AU",
    "GERMANY": "DE",
    "FRANCE": "FR",
}


def resolve_region(region: str) -> RegionIds:
    """Map a human region label to its per-tool identifiers, falling back to the default."""
    key = (region or "").strip().upper()
    key = _ALIASES.get(key, key)
    ids = _REGIONS.get(key)
    if ids is None:
        log.warning("unknown region %r; falling back to %s", region, DEFAULT_REGION)
        return _REGIONS[DEFAULT_REGION]
    return ids
