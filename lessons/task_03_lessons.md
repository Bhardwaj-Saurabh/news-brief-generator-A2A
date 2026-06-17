# Task 3 — Lessons

Adding weather to the world-data server. The meat here is normalisation: unit systems, where
conversion belongs, and how a second upstream with different auth rules reshapes the design.

## Lesson 1 — Encode the unit in the field name and normalise on the way out

**Concept.** `WeatherSnapshot` has `temp_c` and `wind_kph`, never a bare `temp`/`wind` plus a `units`
flag. The tool accepts `units="metric"|"imperial"` to drive the *upstream query*, but the returned
model is always metric — imperial responses are converted before they leave the server.

**Why it matters.** A number without a unit is a latent bug (the Mars Climate Orbiter was lost to exactly
this). Putting the unit in the field name makes a whole class of "whose units are these?" errors
unrepresentable — the type system carries the answer.

**In this codebase.** `servers/world_data_server.py`: `WeatherSnapshot.temp_c/wind_kph`, with
`_to_celsius`/`_to_kph` doing the conversion and `get_current_weather` always returning metric. The
test `test_weather_imperial_is_normalised_to_metric` pins 59°F → 15.0°C.

**Pitfall or alternative.** A `units` field *on the output model* just moves the ambiguity downstream —
now every consumer must branch on it. If you genuinely need both, expose `temp_c` and `temp_f` as
separate fields; never one ambiguous number.

## Lesson 2 — Normalisation is the server's job, not the agent's or the LLM's

**Concept.** The Fahrenheit→Celsius and mph→kph conversions live in the MCP server, the layer that
already knows the upstream's quirks. The Contextualist and Publisher receive clean metric data and never
learn that OpenWeatherMap can speak imperial.

**Why it matters.** If conversion leaked upward, every consumer would re-implement it (and some would get
it wrong), and swapping weather providers would ripple through the whole stack. Normalising at the
boundary keeps the upstream's unit system a private implementation detail of one server.

**In this codebase.** `_to_snapshot(data, units)` is the single normalisation point;
`get_current_weather` returns its result directly.

**Pitfall or alternative.** The tempting shortcut is "let the LLM convert if it needs to" — but the LLM
is non-deterministic and the Scout/Contextualist aren't even allowed to call it. Numeric normalisation is
deterministic plumbing; keep it out of the prompt.

## Lesson 3 — Two tools in one server is a cohesion call, not an accident

**Concept.** `get_top_headlines` and `get_current_weather` share one server because together they form a
single concept — "what's happening right now where the reader is" — and they're consumed by one agent
(the Contextualist). Finance and Media, which serve a different concern, get their own servers (Tasks 4–5).

**Why it matters.** Server boundaries are deployment and failure boundaries. Co-locating tools that are
always used together reduces moving parts; splitting tools that scale or fail independently keeps a
blast radius small. The grouping should follow who consumes them, not which API they happen to wrap.

**In this codebase.** One `FastMCP("world-data")` instance registers both tools (verified by
`test_both_tools_discoverable_in_one_server`); the architecture doc calls this the one slice worth isolating.

**Pitfall or alternative.** The anti-pattern is a single "god server" wrapping every API because "it's
less to run". The moment weather needs to scale differently from news, or one upstream's outage shouldn't
take the other down, the shared process becomes the liability.

## Lesson 4 — Auth rules differ per provider; the secret-leak mitigation must differ too

**Concept.** NewsAPI accepts a header (`X-Api-Key`), so its key stays out of the URL. OpenWeatherMap
*only* accepts the key as the `appid` query param — so it necessarily lands in the request URL, which
httpx logs at INFO. The mitigation is provider-specific: silence httpx's request logging
(`logging.getLogger("httpx").setLevel(WARNING)`).

**Why it matters.** "Put keys in headers" is good advice that some APIs make impossible. Assuming a
uniform auth pattern across providers is how a key ends up in a log. You have to read each provider's
auth contract and apply the matching defence.

**In this codebase.** `servers/world_data_server.py`: the httpx-silence line sits next to the logger
setup with a comment explaining why; the live test confirmed no `appid=` appears in any log line.

**Pitfall or alternative.** Silencing the whole `httpx` logger also hides useful request traces. A
finer alternative is a logging filter that redacts only `appid`/`apiKey` query values — more work, but it
keeps request observability while killing the leak.

## Lesson 5 — Delegate geocoding; don't quietly grow a resolver inside a weather tool

**Concept.** `get_current_weather(city)` passes the city string straight to OWM's `q` and lets OWM
resolve "London" to coordinates. The server does not own geocoding, disambiguation ("London, UK vs
London, Ontario"), or lat/long lookup — that's a separate concern it deliberately doesn't take on.

**Why it matters.** Geocoding is its own problem domain with its own failure modes and APIs. Smuggling it
into the weather tool would bloat a "dumb wrapper" into a mini-service and couple two concerns that
should evolve separately. Knowing what *not* to build is a design skill.

**In this codebase.** `get_current_weather` sends `{"q": city, "units": units}` and trusts OWM's
resolution; the region→city mapping (which *city* string to pass) is a separate concern handled later by
`agents/regions.py` (Task 6).

**Pitfall or alternative.** When ambiguity actually bites (wrong London), the right move is an explicit
geocoding step or passing coordinates — not a pile of special-case city heuristics inside the weather tool.

## Lesson 6 — One structured log line per tool call; inputs and outcome, never payloads or secrets

**Concept.** Each tool emits a single INFO line summarising the call: the input that matters and the
outcome (`get_current_weather city=London -> London (19.3°C)`; `get_top_headlines path=… returned=N/M`).
Not the full upstream payload, not the key.

**Why it matters.** When the Scout fans out to several tools concurrently, these one-liners are how you
reconstruct what happened and how long each took. Logging whole payloads buries the signal and risks
dumping untrusted text (or secrets) into logs; logging nothing leaves you blind during a degraded run.

**In this codebase.** The `log.info(...)` calls at the end of each tool; deliberately terse, no article
bodies, no `appid`.

**Pitfall or alternative.** The richer version attaches a trace/correlation id so concurrent calls are
linkable — which is exactly the `contextvars` trace strategy the PRD defers to Task 6. Per-call logs
without correlation get confusing under real concurrency.

## Lesson 7 — Upstreams are inconsistent about types; parse defensively at the success check

**Concept.** OpenWeatherMap returns `cod: 200` as an integer on success but `cod: "404"` as a *string* on
error. The success check normalises with `str(data.get("cod")) != "200"` rather than `== 200`, so a
stringly-typed error code can't slip through as success.

**Why it matters.** Trusting an upstream's type discipline is a classic source of "works until it
doesn't" bugs — the happy path returns an int, the error path a string, and a naive `== 200` treats the
error as success. Defensive coercion at the boundary absorbs the inconsistency.

**In this codebase.** `_request_owm`'s `if resp.status_code != 200 or str(data.get("cod")) != "200":`.

**Pitfall or alternative.** Over-trusting HTTP status alone is the mirror mistake — some APIs return 200
with an error body. Check both the transport status *and* the payload's own status signal.

## Lesson 8 — Precision is a domain contract: round weather, but don't round money

**Concept.** Weather is rounded to one decimal (`round(_to_celsius(...), 1)`) because sub-decimal
precision is meaningless noise to a reader. That's the *right* call for weather and the *wrong* call for
money — which is why Task 4's `Quote` will use exact handling (`Decimal`), not rounded floats.

**Why it matters.** "Round for readability" and "preserve exactness" are opposite contracts, and the
domain decides which applies. Rounding a price loses cents; not rounding a temperature spams `19.31999°C`.
Matching precision to the domain is a boundary-design decision, not a formatting afterthought.

**In this codebase.** `_to_snapshot` rounds temps and wind to 1dp. The contrast is flagged forward to
`servers/finance_server.py` (Task 4), where float rounding would be a defect.

**Pitfall or alternative.** Using `float` + `round` everywhere by habit is how money bugs are born.
Decide the precision contract per field; sometimes that means `Decimal`, sometimes `int` cents,
sometimes 1dp float.

## Lesson 9 — Idempotent GETs make retry-with-backoff safe; we left it out on purpose

**Concept.** Both tools are idempotent reads, which means a transient failure (429, 503, dropped
connection) is safe to retry — the same call again has no side effects. This server does *not* implement
retry/backoff: it makes one attempt and surfaces failure as a `ToolError`.

**Why it matters.** Free tiers throttle and networks blip; a single transient error currently fails the
whole tool call. In production the fix is bounded exponential backoff with jitter at the request seam —
but it must be bounded, because the Scout owns a ~10s overall budget and unbounded retries would blow it.

**In this codebase.** Not done — stated honestly. The natural home is inside `_request_newsapi` /
`_request_owm` (the single network seams), so retry logic lives in one place per upstream.

**Pitfall or alternative.** Retrying non-idempotent or non-transient errors is the trap: never retry a
`401` (it'll never succeed) or a `404` (the city is still missing). Retry only transient classes (timeouts,
5xx, 429), and cap attempts against the parent deadline.

## Lesson 10 — Scalar tools can't do partial success, so any shape error is a clean structural error

**Concept.** `get_top_headlines` returns a *list*, so one bad article is skipped (partial success). A
weather call returns a *single* `WeatherSnapshot`, so there is no "partial" — if the payload is malformed,
the only honest outcomes are a valid snapshot or a clear error. `_to_snapshot`'s `try/except` converts
any `KeyError`/`TypeError`/`ValidationError` into a `ToolError`.

**Why it matters.** The error strategy follows the return *cardinality*. Forcing partial-success thinking
onto a scalar tool tempts you to return a half-built snapshot with defaulted fields — silently wrong data.
A scalar result should be all-or-clean-error.

**In this codebase.** `get_current_weather` wraps `_to_snapshot` in `try/except (TypeError, KeyError,
ValidationError)` → `ToolError("unexpected weather response shape: …")`.

**Pitfall or alternative.** Defaulting missing fields (`temp_c = main.get("temp", 0.0)`) to avoid the
error is the anti-pattern — 0.0°C is a plausible-looking lie. Fail clearly instead of fabricating a value.
