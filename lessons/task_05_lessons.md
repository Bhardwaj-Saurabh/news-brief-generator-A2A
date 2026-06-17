# Task 5 — Lessons

The last MCP server. The depth is in designing for the *consumer* (an LLM brief), the YouTube quota
model, and when a second call is worth it — plus deterministic truncation as a tested contract.

## Lesson 1 — Truncation is a deterministic, tested contract, not a display detail

**Concept.** `_truncate` cuts a description to a fixed char budget and appends an ellipsis only when it
actually cut. It's a pure function with an exact, asserted output — `"x"*250` → `"x"*200 + "…"` (length
201). Determinism is the point: same input, same byte-for-byte output, every run.

**Why it matters.** Truncation that varies (word-boundary heuristics, locale-dependent, "about 200")
makes output untestable and briefs subtly inconsistent. A deterministic budget is something you can pin
in a test and reason about for token-cost downstream.

**In this codebase.** `servers/media_server.py` `_truncate`; `tests/test_media_server.py`
`test_truncation_is_deterministic` asserts the exact string and the `None`/whitespace cases.

**Pitfall or alternative.** The ellipsis adds one char *past* the limit — if a hard cap matters (a strict
column width), budget for it (`limit-1` + ellipsis). Word-boundary truncation reads nicer but is harder to
test exactly; only reach for it if readability beats determinism.

## Lesson 2 — Design the tool's output for its consumer, which here is an LLM prompt

**Concept.** `MediaItem` carries exactly what a brief needs — title, channel, url, date, views, a *short*
summary — and nothing else. YouTube descriptions can be thousands of chars of hashtags and links; dumping
them raw would bloat the Publisher's prompt and bury signal. The server trims to fit the consumer.

**Why it matters.** The Publisher pays tokens for every char it receives, and untrimmed descriptions are
mostly noise (and untrusted text — a prompt-injection surface). Shaping at the tool boundary is cheaper
and safer than asking the LLM to ignore junk.

**In this codebase.** `_to_media_item` applies `_truncate(snippet.get("description"))`; the live trending
call showed `summary` capped at 201 chars regardless of the source length.

**Pitfall or alternative.** The other extreme — dropping the description entirely — loses context the
brief could use. A bounded summary is the middle path; LLM-based summarisation would be richer but
violates "the Publisher is the only LLM call" and costs tokens at the wrong layer.

## Lesson 3 — Know the quota *unit* per operation; it dictates which endpoint you reach for

**Concept.** YouTube bills by weighted units: `videos.list` (trending) costs 1, `search.list` costs 100.
So `get_trending` is cheap and `search_media` is the expensive tool — and `search_media` adds just 1 more
unit by backfilling stats with `videos.list`, a rounding error next to the 100 it already spent.

**Why it matters.** A naive design that searches on every brief burns the 10,000/day budget in ~100
calls; trending is effectively free by comparison. The cost model should steer defaults (prefer trending,
search only when a topic demands it) — exactly the kind of decision the Scout makes upstream.

**In this codebase.** `get_trending` → `/videos?chart=mostPopular` (1 unit); `search_media` →
`/search` (100) + one `/videos` (1). Documented in code comments and the README quota table.

**Pitfall or alternative.** Treating all calls as equal-cost. The mitigation under load is a cache keyed
on (query/region) with a short TTL so repeated briefs don't re-pay the 100-unit search — flagged by the
PRD as the first scaling step.

## Lesson 4 — Use the batch endpoint when it exists; this is the mirror of finance's forced fan-out

**Concept.** `search` returns video ids without statistics, so views must come from a second call. Because
`videos.list` accepts a comma-separated `id` list, *one* call fetches stats for all results at once —
`/videos?id=a,b,c` — not N parallel calls. The test asserts exactly two upstream calls: `["/search",
"/videos"]`.

**Why it matters.** This is the deliberate contrast with Task 4: Finnhub had no batch quote endpoint, so
`get_market_summary` fanned out; YouTube *does*, so we batch. Same goal (enrich N items), opposite
mechanics, driven by what the upstream offers.

**In this codebase.** `search_media`'s single `_request_youtube("/videos", {"id": ",".join(ids)})` and the
`views` map it builds; `test_search_backfills_views_with_batched_call` pins the call sequence.

**Pitfall or alternative.** Looping a `get_quote`-style call per id would be N× the quota and latency for
no benefit. Always check for a batch/`id`-list endpoint before fanning out.

## Lesson 5 — Two endpoints, two response shapes; normalise both into one model at the boundary

**Concept.** `search` items nest the id as `id.videoId`; `videos` items have a bare string `id`; only
`videos` carries `statistics`. Both are reduced to the same `MediaItem` via a shared `_to_media_item`,
with each tool extracting the id/views in its own way before handing `(video_id, snippet, views)` to the
builder.

**Why it matters.** Consumers get one stable shape no matter which endpoint served the data. The
shape-difference is absorbed in the server, so a future endpoint swap or a third source can plug into the
same `MediaItem` contract.

**In this codebase.** `get_trending` reads `it["id"]` + `it["statistics"]`; `search_media` reads
`it["id"]["videoId"]`; both call `_collect`/`_to_media_item`.

**Pitfall or alternative.** Leaking the raw YouTube shapes upward would force every consumer to branch on
"did this come from search or videos?" — the exact coupling normalisation exists to prevent.

## Lesson 6 — `views` is optional because the data sometimes isn't there; model the absence honestly

**Concept.** `views: int | None`. Search results have no statistics until backfilled, some videos hide
their counts, and `_to_int` returns `None` for absent/non-numeric values. The model says "this may be
unknown" rather than defaulting to `0`.

**Why it matters.** `0 views` and `unknown views` are different facts; defaulting absence to 0 fabricates
data (a video with hidden counts isn't unwatched). `None` lets the UI/Publisher say "views unavailable"
honestly — the same principle as finance's `as_of` and the news empty-vs-error distinction.

**In this codebase.** `MediaItem.views: int | None`; `_to_int` coerces the string `viewCount` or yields
`None`; the backfill map leaves ids absent if stats are missing.

**Pitfall or alternative.** `views: int = 0` looks tidier and lies. Reserve `0` for a genuine zero; use
`None` for "not reported".

## Lesson 7 — Surface provider error *reasons*, not just status codes

**Concept.** YouTube returns failures as HTTP 403/400 with a structured body
(`error.errors[0].reason`). `_request_youtube` extracts that reason (`quotaExceeded`, `keyInvalid`, …)
into the `ToolError` message, so the caller learns *why*, not just "403".

**Why it matters.** "quotaExceeded" and "keyInvalid" demand different responses — back off and retry
later vs fix configuration now. A bare status code forces the caller to guess; the reason makes graceful
degradation (and on-call triage) actionable.

**In this codebase.** `_request_youtube`'s error branch parses `err["errors"][0]["reason"]`; the test
asserts the `ToolError` carries `quotaExceeded`.

**Pitfall or alternative.** Assuming the error body shape is stable — it can vary or be empty, so the code
falls back to the status code and `resp.text[:200]`. Parse defensively; never index `errors[0]` without a
guard.

## Lesson 8 — Treat upstream text as untrusted from the moment it enters the server

**Concept.** Video titles and descriptions are user-generated and arbitrary — they can contain anything,
including "ignore previous instructions". Truncation already limits the volume; the deeper point is that
this text is *untrusted input* the instant it crosses the boundary, long before the Publisher's prompt.

**Why it matters.** The prompt-injection defence the PRD requires at the LLM boundary (Task 9) is cheaper
and more robust if the data layer already bounds and treats this text as data, not instructions. Defence
starts at ingestion, not just at the prompt.

**In this codebase.** `_truncate` bounds description length in `media_server.py`; the actual injection
hardening (delimiting/escaping untrusted fields in the prompt) is Task 9 — flagged here, not yet done.

**Pitfall or alternative.** Relying solely on the LLM prompt to neutralise hostile text is brittle.
Bounding and structurally separating untrusted fields at every layer is defence in depth.

## Lesson 9 — Region/locale is a parameter with consequences, not a cosmetic default

**Concept.** `get_trending(region="GB")` changes *what content exists* — trending in GB ≠ US ≠ IN. The
default encodes an editorial assumption about the reader. It's a real knob the region resolver will drive
in Task 6, not a throwaway default.

**Why it matters.** A hardcoded region silently biases every brief toward one locale; making it a
first-class parameter keeps the system honest about whose "trending" it's showing and lets the
`BriefRequest.region` flow through to media the same way it flows to news and weather.

**In this codebase.** `get_trending`'s `regionCode=region`; the live `region="GB"` run returned
UK-trending content. The region→media mapping is the resolver's job (Task 6, `agents/regions.py`).

**Pitfall or alternative.** `search_media` has *no* region filter (search is global by default) — a real
asymmetry to remember: trending is localised, search is not, so a "UK tech videos" request via search
won't be UK-scoped without an explicit `regionCode`/`relevanceLanguage`.

## Lesson 10 — The three-server tool layer is done; statelessness is what lets them compose

**Concept.** World-data, finance, and media now run as three independent processes on 8801/8802/8803,
verified up simultaneously. None shares state with another; each is a pure read wrapper. That isolation is
precisely what lets the Scout (Task 8) fan out to all three concurrently and treat any one's failure as a
degraded section.

**Why it matters.** Three stateless HTTP services are independently startable, restartable, and
fail-isolated — the property the whole A2A coordination layer assumes. If any server held cross-request
state, concurrent fan-out and graceful degradation would both be unsafe.

**In this codebase.** Confirmed by running all three and hitting 8801/8802/8803; each server's tools are
idempotent reads with no module-level mutable state.

**Pitfall or alternative.** The cost of three processes is operational (three things to launch/monitor) —
fine for a learning project, but at scale you'd want supervision, health checks, and a gateway. Flagged by
the PRD as out of scope; the statelessness is what would make that migration straightforward.
