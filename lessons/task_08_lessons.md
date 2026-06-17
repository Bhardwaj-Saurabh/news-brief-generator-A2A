# Task 8 — Lessons

The aggregator. The depth is in owning the budget, fanning out across heterogeneous layers,
encoding selection as code (not a prompt), and composing a valid whole from degraded parts.

## Lesson 1 — Heterogeneous fan-out: a sub-agent and raw tool calls in one gather

**Concept.** The Scout's single `asyncio.gather` runs three different *kinds* of work concurrently: a
call to another agent (`gather_context`, which itself fans out), and two direct MCP tool calls
(`get_market_summary`, media). The aggregator composes across layers, not just across sibling tools.

**Why it matters.** Real aggregators mix granularities — some work is already an agent, some is a bare
tool call. Treating them uniformly in one `gather` keeps the orchestration flat and the total latency the
max of the three, not their sum.

**In this codebase.** `agents/scout.py` `scout()`: `gather(gather_context(...), _fetch_quotes(...),
_fetch_media(...))`.

**Pitfall or alternative.** Awaiting them sequentially "because one is an agent and two are tools" throws
away the concurrency. The call's *shape* (returns a value, takes the budget) matters; its *layer* doesn't.

## Lesson 2 — The outermost caller owns the budget and passes a deadline down

**Concept.** The Scout creates the one deadline (`start + BUDGET`) and both *uses* it for its own
Finance/Media timeouts and *passes it down* to `gather_context`. The Contextualist (Task 7) received a
deadline; the Scout is the half that creates it. Budget ownership lives at the top of the call tree.

**Why it matters.** If every layer minted its own budget, the top-level SLA would be the sum of all of
them. One owner, one deadline threaded down, means the whole tree — agent and tools — finishes inside a
single bound (verified live: full report in 0.59s, budget 10s).

**In this codebase.** `scout()`: `deadline = start + BUDGET`; `timeout = max(0, deadline - monotonic())`
for the local fetches; `gather_context(request, deadline)`.

**Pitfall or alternative.** Passing the budget as "seconds" down each layer lets it silently reset; an
absolute monotonic deadline is invariant under re-passing. (See Task 7 Lesson 1 for the receiving side.)

## Lesson 3 — Encode selection as code, not a prompt; keep the LLM out of the fetch path

**Concept.** Topic→ticker selection is a static keyword map (`_KEYWORD_TICKERS`), not an LLM call. It's
deterministic, instant, free, and unit-testable. The explicit decision is to *not* ask the model "which
stocks relate to this topic", which would break the project's one-LLM-call invariant.

**Why it matters.** "Let the LLM pick the tickers" is a tempting way to smear intelligence into
plumbing — but it makes the aggregator non-deterministic, adds latency and cost to every brief, and
creates a prompt-injection surface in the data layer. A lookup table is the honest tool for a
classification this small.

**In this codebase.** `_select_symbols` over `_KEYWORD_TICKERS`; richer resolution (an LLM or symbol-
search API) is explicitly out of scope, noted in the module docstring.

**Pitfall or alternative.** The map is coarse (it won't know an obscure ticker) — that's the accepted
trade for determinism. The real upgrade is a symbol-search *API* (still no LLM), not a prompt.

## Lesson 4 — Token-exact matching beats substring for keyword heuristics

**Concept.** `_select_symbols` tokenises the topic (`re.findall(r"[a-z0-9]+", ...)`) and matches whole
tokens against the keyword table. A naive `if keyword in topic` substring check would fire `"ai"` on
`"retail"` (r-e-t-**a-i**-l) and mis-select AI tickers for a retail story.

**Why it matters.** Substring matching on short keywords is a classic false-positive generator. Tokenising
first makes the match mean "the topic contains this word", which is what you actually intend. The test
pins exactly this (`_select_symbols("retail") != AI tickers`).

**In this codebase.** `_select_symbols`'s `tokens = set(re.findall(...))` then `if keyword in tokens`.

**Pitfall or alternative.** Stemming/aliases (the map has `tech` and `technology` as separate keys)
handles morphology without resurrecting substring matching. For real NLP you'd reach further, but for a
fixed keyword set, token-exact + aliases is the right amount.

## Lesson 5 — A fallback with a warning turns a silent miss into a visible signal

**Concept.** `_select_symbols` distinguishes two fallbacks: *no topic* (expected — `debug` log, use the
watchlist) versus *topic given but unmatched* (a real miss — `warning`, use the watchlist). The outcome is
the same default list; the log severity encodes whether something noteworthy happened.

**Why it matters.** Silent defaults hide coverage gaps — you'd never learn that "quantum computing" briefs
always fall back to SPY/AAPL/MSFT. The warning makes the miss observable so the keyword table can grow;
the debug-on-no-topic avoids crying wolf when there was nothing to match.

**In this codebase.** The `log.debug` (no topic) vs `log.warning` (unmatched topic) branches in
`_select_symbols`. Same ethos as the region resolver's fallback warning (Task 6).

**Pitfall or alternative.** Warning on *every* default (including no-topic) trains operators to ignore the
warning. Severity should track "is this surprising?", not just "did we take the fallback?".

## Lesson 6 — Keep the aggregator thin: it composes, it doesn't fetch details

**Concept.** The Scout delegates news+weather wholesale to the Contextualist and makes only two direct
tool calls (finance, media). It doesn't reach into the World Data server itself. Its job is selection +
fan-out + composition, not knowing how every section is fetched.

**Why it matters.** An aggregator that fetches everything directly becomes a god-object: untestable,
coupled to every upstream's quirks, impossible to evolve. Delegating the one cohesive slice (news+weather)
to its own agent keeps the Scout small and gives the system a seam to grow (promote finance/media to
agents if they gain logic).

**In this codebase.** `scout()` calls `gather_context(...)` (agent) but `call_tool(finance_url(), ...)` /
`call_tool(media_url(), ...)` directly — the deliberate asymmetry from ARCHITECTURE §3.

**Pitfall or alternative.** The asymmetry is a judgment call: finance/media are simple enough to call
directly today. The moment either grows selection logic of its own, it earns an agent — the same reason
the Contextualist exists.

## Lesson 7 — Composition of degraded parts yields a degraded-but-valid whole

**Concept.** The `ScoutReport` is valid whether or not each section succeeded: `quotes` may carry
`QuoteError` entries, `media_items` may be empty, the `ContextBundle` may have no weather. The Scout never
inspects success to decide whether to build a report — it always composes what it got.

**Why it matters.** Partial success only works if it propagates through *every* layer. If the aggregator
raised when any section was empty, the Contextualist's careful degradation would be wasted. "Always return
the best available report" is the contract the UI depends on.

**In this codebase.** `scout()` builds `ScoutReport(context, SignalBundle(quotes, media), request)`
unconditionally; the degradation tests confirm a failed section becomes empty, not an exception.

**Pitfall or alternative.** Adding a "fail if everything is empty" guard is tempting but premature — an
all-empty report is still honest data the Publisher can render as "nothing notable today". Decide that
policy at the UI, not by crashing the aggregator.

## Lesson 8 — Test an aggregator by mocking both seams: the sub-agent and the tool layer

**Concept.** Scout tests monkeypatch *two* things: `gather_context` (the sub-agent) and `call_tool` (the
finance/media tool seam). That isolates the Scout's own logic — selection, fan-out, composition, budget —
from how its dependencies actually fetch.

**Why it matters.** If a test let the real `gather_context` run, a Scout test would secretly be a
Contextualist test too (and need World Data mocked). Mocking the sub-agent at its function boundary keeps
each layer's tests about that layer. Two clean seams, two independent test suites.

**In this codebase.** `tests/test_scout.py` `_patch(...)` sets both `scout_mod.gather_context` and
`scout_mod.call_tool`; the budget test additionally shrinks `scout_mod.BUDGET`.

**Pitfall or alternative.** Patching `agents.contextualist.call_tool` from a Scout test would be reaching
through a layer — brittle. Patch the Scout's *own* reference to `gather_context`; each module owns its
dependency names.

## Lesson 9 — The fan-out pattern scales to N sources structurally, but per-process asyncio has a ceiling

**Concept.** Adding a fourth source is mechanical: a `_fetch_x` helper plus one more entry in the
`gather`. The shape generalises. What doesn't is the runtime — all fan-out is in-process `asyncio`, every
call opens its own `httpx`/MCP client, and there's no connection pooling or backpressure.

**Why it matters.** The code reads like it scales, and structurally it does; the operational limits
(socket churn, no pooling, one event loop, free-tier quotas hit in bursts) are where it breaks under real
traffic. Knowing the difference between "scales in code" and "scales in production" is the lesson.

**In this codebase.** The uniform `_fetch_*` helpers + single `gather` in `scout.py`; the ceilings are the
ones the PRD's "where this breaks under load" section names (job queue, caching, pooling).

**Pitfall or alternative.** The next step at scale isn't more `gather` entries — it's a shared pooled
client, a cache keyed on (topic, region), and moving fan-out behind a real orchestrator/queue.

## Lesson 10 — The aggregator is the natural root for correlation; that's where the trace id is set

**Concept.** `scout()` owns the whole brief's gather lifecycle, so it's the right place to *set* the
per-brief correlation id — the `contextvars` trace id decided in Task 6 — so every downstream log
(Contextualist, tool calls) shares one id. One `scout()` call == one trace.

**Why it matters.** Correlation must be established at the entry of a unit of work; set it deeper and the
earliest logs miss it, set it shallower (per process) and concurrent briefs blur together. The aggregator
is the lifecycle owner, hence the span root.

**In this codebase.** Not yet wired — flagged honestly. `scout()` (or the UI that calls it, Task 10) is
where `trace_id` gets stamped into a `ContextVar` and a logging filter; `mcp_client` stays trace-free
because the boundary can't carry it (Task 6 Lesson 4).

**Pitfall or alternative.** Threading the id as a function argument through every layer (and into
`call_tool`) is the brittle alternative the contextvars approach avoids — the id rides ambient context,
not the signature.
