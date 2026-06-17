# Task 2 — Lessons

The first MCP server. The decisions worth keeping are about tool *shape*, the error contract at
the tool boundary, and the seams that make a server testable without hitting the real API.

## Lesson 1 — Tool granularity: one tool that routes beats two tools that overlap

**Concept.** `get_top_headlines` fronts *two* NewsAPI endpoints — `top-headlines` (country/category)
and `everything` (free-text `q` + time window) — switching on whether `query` is set. They could have
been two tools, but they answer the same question ("recent headlines") with the same return type, and
the caller (Contextualist) shouldn't care which endpoint served it.

**Why it matters.** Tool count is the surface an LLM (or agent) must reason over. Two near-duplicate
tools force a selection decision and invite the wrong pick; one tool with a clear parameter contract
keeps the surface small and the routing logic in code where it's testable.

**In this codebase.** `servers/world_data_server.py`, `get_top_headlines`: the `if query:` branch picks
`/everything` vs `/top-headlines` and shapes params accordingly.

**Pitfall or alternative.** The line to split is *different return shapes or semantics*. If `everything`
later needed to return relevance scores that `top-headlines` lacks, one tool returning a union type
would start lying — that's when you split.

## Lesson 2 — Put the network behind one seam; it's both your test boundary and your security boundary

**Concept.** All HTTP lives in `_request_newsapi(path, params)`. Nothing else in the module touches
`httpx`. That one function is where the API key is attached, timeouts are set, and upstream failures
become `ToolError`s — and it's the single thing tests monkeypatch to run quota-free.

**Why it matters.** A seam like this means the tool's *logic* (routing, validation, partial success) is
tested deterministically with zero network and zero key, while the I/O concern is isolated for the rare
live check. Without it, every test either hits the real API (burning quota, flaky) or mocks `httpx`
internals (brittle).

**In this codebase.** `tests/test_world_data_server.py` does `monkeypatch.setattr(wd, "_request_newsapi", fake_req)`
for all three tests; only the optional manual run exercises the real function.

**Pitfall or alternative.** Mocking at the `httpx` layer instead (patching `AsyncClient.get`) couples
tests to the HTTP library. Patch your *own* seam, not your dependency's internals.

## Lesson 3 — "Errors are data" has two modes: structural failure raises, per-item failure degrades

**Concept.** The tool uses two distinct error strategies. A *structural* problem — bad key, upstream
down, `articles` not a list — raises `ToolError`, which the MCP layer turns into a clean error response
the client re-raises (never a 500). A *per-item* problem — one malformed article — is swallowed with a
logged warning, and the remaining valid items are returned (partial success).

**Why it matters.** Collapsing these is the classic mistake: raise on one bad article and a single junk
record nukes the whole brief; silently return `[]` on an auth failure and you hide a real outage as
"no news today". The distinction is "can the caller still get a useful, honest answer?"

**In this codebase.** `_request_newsapi` raises `ToolError`; the `for article in articles` loop catches
`ValidationError` per item and continues. The test asserts both: 2-of-3 partial success, and a clean
`ToolError` on upstream failure.

**Pitfall or alternative.** Returning a `{"error": ...}` envelope *inside* a `list[Headline]` return type
would break the type contract. For batch tools where the caller wants per-item status (Task 4's
`get_market_summary`), an explicit error-entry type in the list is the right call — but that's a typed
choice, not a stringly-typed escape hatch.

## Lesson 4 — The server owns normalisation; the contract never mirrors the upstream shape

**Concept.** NewsAPI returns nested `source.name`, `publishedAt`, and `description`. `Headline` is flat:
`source`, `published_at`, `summary`. `_to_headline` does the flattening and `Headline.model_validate`
enforces it (frozen model, required `title`/`source`/`url`, `HttpUrl`, parsed `datetime`).

**Why it matters.** If the agent layer saw raw NewsAPI JSON, every consumer would re-learn NewsAPI's
quirks and a provider swap would ripple upward. Normalising at the boundary means the upstream API is an
implementation detail of *one* server.

**In this codebase.** `Headline` + `_to_headline` in `servers/world_data_server.py`. `model_config =
ConfigDict(frozen=True)` makes the returned objects immutable — a fetched fact shouldn't be mutated downstream.

**Pitfall or alternative.** Leaking `HttpUrl` vs `str` matters at serialization: FastMCP emits it as a
string in the tool output, but in-process it's a validated `AnyUrl`. If a consumer does string ops,
`str(h.url)` is explicit; assuming it's already `str` is the trap.

## Lesson 5 — A tool's docstring is its public API description, read by the model, not by you

**Concept.** FastMCP turns the function docstring into the MCP tool `description` that an LLM/agent sees
when choosing and calling the tool. So the docstring documents *behaviour and parameter routing*
("with `query` set, searches `everything`…") — not implementation notes, and never anything sensitive.

**Why it matters.** This is prompt scaffolding. A vague or wrong description causes wrong calls; an
overlong one wastes context; leaking internals (endpoints, keys) into it is both noise and a security
smell. The docstring is UX for a non-human caller.

**In this codebase.** `get_top_headlines`'s docstring describes the two paths and the `limit` cap; the
`_request_newsapi` docstring (impl detail, never exposed as a tool) is free to discuss the header trick.

**Pitfall or alternative.** Don't restate types the schema already carries ("`limit` is an int"). Do
state semantics the schema can't ("1-100", "defaults to UK", "query switches endpoints").

## Lesson 6 — HTTP transport (not stdio) is what makes three independent servers possible

**Concept.** The server runs `mcp.run(transport="http", host="127.0.0.1", port=8801)`. HTTP (FastMCP's
streamable-HTTP) lets each domain server be its own process on its own port, started/scaled/crashed
independently, and callable by anything that speaks HTTP — not just a parent that spawned it over a pipe.

**Why it matters.** stdio couples a server to a single parent process and a single machine; it's great
for a one-shot local tool, wrong for three long-lived services an agent fans out to concurrently. The
cost is real: a network hop and JSON serialization per call versus an in-process function.

**In this codebase.** `servers/world_data_server.py` `__main__` block; ports come from `WORLD_DATA_PORT`
(8801), with Finance/Media on 8802/8803 in Tasks 4–5 — three processes, no port conflict.

**Pitfall or alternative.** For tests we *don't* pay the HTTP cost: `Client(wd.mcp)` uses an in-memory
transport against the server object directly. Same MCP semantics, no socket — the right tool for a unit test.

## Lesson 7 — MCP tools should be idempotent, stateless reads; this one is, by construction

**Concept.** `get_top_headlines` holds no state between calls and is a pure function of its arguments
plus the (changing) upstream. Calling it twice with the same args is safe and side-effect-free — a
read. The server object has no mutable per-request state.

**Why it matters.** Statelessness is what lets the agent layer retry on timeout, fan out concurrently,
and run N instances behind a load balancer without coordination. The moment a tool caches into instance
state or mutates shared data, all of that breaks.

**In this codebase.** No module-level mutable state is read/written per call; `httpx.AsyncClient` is
created and closed inside `_request_newsapi`, owned by the call, not the server.

**Pitfall or alternative.** Creating one `AsyncClient` per call (as here) is simple and correct but
forgoes connection pooling. A shared client is the perf optimisation — but it introduces lifecycle state
you must own (open at startup, close at shutdown), so it's deferred until the call volume justifies it.

## Lesson 8 — Timeout every external call, and own the event loop explicitly

**Concept.** `_request_newsapi` sets `httpx.Timeout(10.0)` on the client — no call can hang forever.
The tool is `async def`, so it runs on FastMCP's event loop; `httpx.AsyncClient` keeps the call
non-blocking, which matters once the Contextualist fans out several tool calls with `asyncio.gather`.

**Why it matters.** A single hung upstream without a timeout stalls the whole brief (the Scout owns a
~10s budget downstream). Async + per-call timeout is what makes "one slow source degrades, doesn't
freeze everything" achievable later.

**In this codebase.** `REQUEST_TIMEOUT = httpx.Timeout(10.0)` and the `async with httpx.AsyncClient(...)`
in `_request_newsapi`.

**Pitfall or alternative.** A blocking `requests` call inside an async tool would block the event loop
and silently serialize the Scout's "concurrent" fan-out. If you must use sync I/O, push it to a thread
(`run_in_thread` / `asyncio.to_thread`) — but async-native httpx is the cleaner fit here.

## Lesson 9 — Send credentials in headers, never query params; your logs are watching

**Concept.** The key goes in `headers={"X-Api-Key": key}`, not the query string. This isn't cosmetic:
httpx's INFO log prints the full request URL including query params. During the live test the log showed
`GET https://newsapi.org/v2/top-headlines?country=gb&pageSize=3` — had the key been a `params` entry, it
would be sitting in that log line (and any proxy/access log) in plaintext.

**Why it matters.** URLs leak — into logs, browser history, proxy caches, error trackers. Headers are
not immune but are far less likely to be logged verbatim. This is the concrete mechanism behind Task 1's
"never print key values".

**In this codebase.** `_request_newsapi`'s `headers={"X-Api-Key": key}`; the visible httpx URL log
confirms only non-secret params appear.

**Pitfall or alternative.** Some APIs only accept the key as a query param (NewsAPI also allows
`?apiKey=`). When forced, scrub it from logs (a logging filter) or lower httpx's log level — don't just
hope no one reads the logs.

## Lesson 10 — Empty is data, not an error; don't manufacture failures from valid silence

**Concept.** Live `top-headlines?country=gb` returned `status:ok` with zero articles — a real NewsAPI
free-tier coverage gap. The tool correctly returns `[]`, not a `ToolError`. "No headlines right now" is
a valid, honest answer; only a *failure to ask* (auth/transport/shape) is an error.

**Why it matters.** Conflating empty with error makes the system cry wolf — the Contextualist would log
a warning and the brief would imply an outage when the truth is "quiet news in this region". Correct
modelling lets downstream degrade gracefully (an empty news section) without alarm.

**In this codebase.** The `for article in articles` loop over an empty list simply yields `[]`; the
`returned=0/0` log line records it as normal. Flagged for Task 7: the default `country="gb"` can be
empty, so region→news mapping needs awareness (or a fallback) there.

**Pitfall or alternative.** The opposite over-correction — treating any `[]` as "retry / try another
source" — burns quota chasing data that isn't there. Distinguish "asked successfully, got nothing" from
"couldn't ask"; only the latter is worth a retry.
