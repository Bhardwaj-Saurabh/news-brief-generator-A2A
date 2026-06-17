# Task 7 — Lessons

The first agent. The depth is in coordination: a passed-down deadline that doesn't compound, `gather`
vs `TaskGroup` for partial success, and why a data-gathering agent touches no LLM.

## Lesson 1 — Pass an absolute deadline down; don't start a fresh budget at each layer

**Concept.** `gather_context(request, deadline)` takes an *absolute* `time.monotonic()` deadline owned by
the caller (the Scout). It computes `remaining = deadline - now` and uses that as the per-tool timeout.
If instead each layer started its own fresh 10s, the budgets would compound — Scout 10s + Contextualist
10s = a 20s worst case the Scout never agreed to.

**Why it matters.** Nested independent timeouts are a classic latency bug: the top-level SLA quietly
becomes the *sum* of every layer's timeout. A single deadline threaded down keeps the whole tree inside
one bound, no matter how deep.

**In this codebase.** `agents/contextualist.py`: `_remaining(deadline)` returns `max(0, deadline -
monotonic())` (or `DEFAULT_BUDGET` standalone); `test_expired_deadline_degrades_without_hanging` proves a
~50ms deadline cuts off a 5s call.

**Pitfall or alternative.** Using wall-clock (`datetime.now`) for deadlines breaks if the clock steps
(NTP, DST); `time.monotonic()` only moves forward, which is exactly what a timeout needs. Passing
"seconds remaining" instead of an absolute deadline drifts as it's re-passed; an absolute value doesn't.

## Lesson 2 — `gather` with total sub-functions for partial success; `TaskGroup` would cancel siblings

**Concept.** The two fetches run under `asyncio.gather`, and each sub-function (`_fetch_headlines`,
`_fetch_weather`) catches its own errors and *always returns a value* (`[]` or `None`). So one failing
fetch never disturbs the other. `asyncio.TaskGroup` (3.11+) is the wrong tool here: it cancels all
siblings the moment one task raises — all-or-nothing, the opposite of graceful degradation.

**Why it matters.** The agent's contract is "return what you could get". `TaskGroup`'s structured
all-or-cancel semantics are right when partial results are useless (a transaction), wrong when a partial
bundle is valuable (news without weather is still a brief).

**In this codebase.** `gather_context`'s `asyncio.gather(_fetch_headlines(...), _fetch_weather(...))`;
the per-section degradation tests confirm one failure leaves the other intact.

**Pitfall or alternative.** `gather(..., return_exceptions=True)` is the other way to avoid a poisoned
gather, but it hands you `Exception | result` to post-process. Making each sub-function total (never
raises) is cleaner — the gather just returns values.

## Lesson 3 — The context-bundle pattern: return one typed aggregate where empty sections are valid

**Concept.** The agent returns a single `ContextBundle`, not loose `(headlines, weather)`. Degraded
sections are first-class: `headlines=[]` and `weather=None` are valid states, not errors. The bundle's
schema *is* the Scout's input contract.

**Why it matters.** A typed aggregate gives the next agent one thing to consume and validate, and encodes
"this section may be absent" in the type (`weather: WeatherSnapshot | None`). Returning a tuple or dict
pushes shape-knowledge onto every caller and loses the "absent is OK" signal.

**In this codebase.** `gather_context` returns `ContextBundle(headlines=..., weather=..., region=...)`;
the optional/defaulted fields (Task 6) are what make a degraded bundle still valid.

**Pitfall or alternative.** Raising when a section is empty would force the Scout to handle exceptions for
a normal, expected condition. Reserve exceptions for "couldn't produce a bundle at all", not "weather was
down".

## Lesson 4 — Re-validate tool output at the agent boundary; the untyped dict stops here

**Concept.** `call_tool` returns raw dicts. The agent runs `Headline.model_validate(item)` /
`WeatherSnapshot.model_validate(raw)` before anything enters the bundle — a second validation boundary,
even though the server already validated on the way out. The untyped dict never crosses into the typed
A2A layer.

**Why it matters.** It's defence in depth and a contract-enforcement point: if a server is swapped,
mis-deployed, or returns an unexpected shape, the agent catches it here rather than letting a malformed
dict masquerade as a `Headline` three agents downstream. Per-item validation also lets one bad headline
be skipped without losing the rest.

**In this codebase.** The `for item in raw: try: Headline.model_validate(item)` loop in
`_fetch_headlines`; `WeatherSnapshot.model_validate(raw)` in `_fetch_weather`.

**Pitfall or alternative.** Trusting `call_tool`'s output as already-typed (it isn't — it's plain dicts)
and stuffing it into the bundle would defer the failure to a confusing `AttributeError` later. Validate at
the boundary you control.

## Lesson 5 — Split Contextualist from Scout so the aggregator doesn't become a god-object

**Concept.** The Contextualist owns exactly one slice — "what's happening right now" (news + weather) —
and knows nothing about finance, media, or the other agents. The Scout (Task 8) orchestrates; the
Contextualist gathers a bounded concern it could be reused or evolved independently.

**Why it matters.** If the Scout fetched everything directly it would become a god-object that's hard to
test and change. Carving out the one cohesive slice (the news+weather pairing) keeps each agent small and
gives the architecture a seam to grow along (promote finance/media to their own agents later).

**In this codebase.** `agents/contextualist.py` only ever calls the World Data server; the Scout will
call the Contextualist plus Finance/Media (Task 8). The asymmetry is deliberate (per ARCHITECTURE §3).

**Pitfall or alternative.** Over-splitting (an agent per tool) adds coordination overhead for no cohesion
gain. The unit is a *concern* the consumers treat as one thing — news and weather travel together, so
they're one agent.

## Lesson 6 — A data-gathering agent calls no LLM, by design

**Concept.** The Contextualist is pure deterministic plumbing: resolve region, call tools, validate,
aggregate. It never invokes the model. Only the Publisher does. There is no "ask the LLM what to fetch"
step at this layer.

**Why it matters.** Keeping the LLM out of gathering preserves the project's core invariant (one LLM
call), keeps this layer deterministic and unit-testable, avoids paying tokens for plumbing, and shrinks
the prompt-injection surface (untrusted headlines never reach a model here). An LLM in the fetch path
would make the agent non-deterministic and expensive for no benefit.

**In this codebase.** No `agent_framework`/LLM import anywhere in `contextualist.py`; the only "decision"
(topic → search vs top-headlines) is a plain `if`.

**Pitfall or alternative.** The tempting anti-pattern is letting the LLM "decide what's relevant" while
fetching. That belongs (if anywhere) in the single synthesis step, not smeared across the data layer.

## Lesson 7 — A broad `except Exception` is the right resilience boundary — and it lets cancellation through

**Concept.** Each fetch wraps its call in `except Exception` because the requirement is "any single
upstream problem degrades, never crashes" — timeout, tool error, server down, malformed payload all map
to the same outcome. Crucially, `asyncio.CancelledError` inherits from `BaseException`, not `Exception`,
so this broad catch does **not** swallow cancellation — `wait_for`'s timeout cancellation still works.

**Why it matters.** Broad catches are usually a smell, but at a degradation boundary they're correct:
the agent's job is to be total. Knowing that `CancelledError` escapes `except Exception` is what makes the
broad catch safe — otherwise you'd deadlock your own timeouts.

**In this codebase.** `_fetch_headlines`/`_fetch_weather` `except Exception as exc: log.warning(...)`;
the deadline test relies on cancellation propagating past these handlers.

**Pitfall or alternative.** `except:` (bare) or `except BaseException` *would* swallow `CancelledError`
and break timeouts/shutdown — never do that. Scope broad catches to `Exception` and only at a genuine
resilience boundary, not around ordinary logic.

## Lesson 8 — Test an agent by faking the whole tool layer at one seam

**Concept.** Every test monkeypatches `agents.contextualist.call_tool` with a fake that dispatches by
tool name — returning canned payloads, raising `ToolError`, or sleeping to test the budget. No MCP
servers run, no keys are needed, and degradation/timeout paths are exercised deterministically.

**Why it matters.** Agents are coordination logic; their bugs are in routing, aggregation, and failure
handling — none of which need a live network to test. Faking the single `call_tool` seam turns "needs
three servers and five API keys" into a sub-second unit test.

**In this codebase.** `tests/test_contextualist.py` `_patch_calls(...)`; injecting a `ToolError` tests
degradation, injecting `asyncio.sleep(5)` tests the deadline.

**Pitfall or alternative.** Patching deeper (httpx, the MCP Client) couples tests to transport details
and makes them brittle. Patch the agent's own dependency boundary (`call_tool`), the same discipline as
mocking the server's `_request_*` seam — one layer up.

## Lesson 9 — Logging discipline: one summary line per run, a warning per degraded section

**Concept.** The agent logs exactly one INFO summary (`region`, headline count, `weather=ok|none`) and a
WARNING only when a section degrades. Not payloads, not every item. The `weather=none` in the summary is
itself a degradation signal.

**Why it matters.** Under concurrent fan-out, terse structured lines are how you reconstruct a run; the
"none" tells you a section was empty *and whether that was a failure* (paired with the warning) vs simply
no data. Logging payloads would bury the signal and risk dumping untrusted text.

**In this codebase.** `gather_context`'s single `log.info("context region=%s headlines=%d weather=%s")`
plus the per-fetch `log.warning` on failure.

**Pitfall or alternative.** No correlation id yet means concurrent briefs interleave in the logs — the
contextvars trace id (decided in Task 6) is what fixes that when wired at the orchestration layer.

## Lesson 10 — Resolve server URLs from env at call time, so agent and server agree by construction

**Concept.** `agents/config.py` exposes `world_data_url()` as a *function* that reads `WORLD_DATA_PORT`
(the same env var the server binds to) when called — not a module-level constant captured at import. An
explicit `WORLD_DATA_URL` can override for non-localhost.

**Why it matters.** Functions read the env after `load_dotenv()` has run and after any test override,
avoiding stale import-time capture. Reading the *same* env var the server uses means the two can't drift
onto different ports by accident.

**In this codebase.** `agents/config.py` `_server_url(...)`; `contextualist` calls `world_data_url()`
inside each fetch.

**Pitfall or alternative.** `WORLD_DATA_URL = os.environ[...]` at import time captures whatever was set
before the module loaded — brittle under `.env` loading order and impossible to override per-test. A
function defers the read to when it's actually needed.
