# Task 4 — Lessons

A second, independent server. The depth here is in the batch contract: a typed union for partial
success, money as Decimal, fan-out economics, and detecting "not found" from an API that never says 404.

## Lesson 1 — Return errors as typed data when the caller asked for specific items

**Concept.** `get_market_summary` returns `list[Quote | QuoteError]` — a discriminated union keyed on a
`status` literal. This differs sharply from Task 2's news tool, which silently *drops* malformed
articles. The deciding factor is intent: a news caller wants "some headlines" and doesn't care which
were dropped; a finance caller asked for *AAPL, MSFT, INVALID by name* and must learn that INVALID
failed and why.

**Why it matters.** Silently dropping a requested symbol is a lie of omission — the caller can't tell
"INVALID is down" from "you forgot to ask". Returning a `QuoteError` entry keyed by symbol preserves the
1:1 mapping between request and response that the caller depends on.

**In this codebase.** `servers/finance_server.py`: `Quote`/`QuoteError` with `status: Literal["ok"]`/
`Literal["error"]`; `get_market_summary` returns the mixed list. Verified by `test_market_summary_partial_success`.

**Pitfall or alternative.** Returning a parallel `errors: list[str]` alongside `quotes: list[Quote]`
breaks positional/keyed correspondence and forces the caller to re-join. One list of tagged entries keeps
request and result aligned.

## Lesson 2 — Money is Decimal, and you build it with `Decimal(str(x))`

**Concept.** Prices are `Decimal`, never `float`. Crucially, the coercion goes through `str`:
`Decimal(str(189.95))` yields exactly `189.95`, whereas `Decimal(189.95)` captures the float's binary
artefact (`189.9500000000000028...`). The `_dec` helper centralises this and maps `None` → `Decimal("0")`.

**Why it matters.** Float arithmetic on money accumulates rounding error that eventually shows up as a
cent that doesn't reconcile. Going through `str` pins the human-readable decimal the API actually sent.

**In this codebase.** `_dec()` in `servers/finance_server.py`; `Quote.price/change/change_pct: Decimal`.
Note the boundary reality: over MCP the Decimal serialises to a JSON *string* (`"189.95"`) — FastMCP even
warns its regex pattern isn't client-enforceable — so consumers parse it back with `Decimal(value)`.

**Pitfall or alternative.** `Decimal(some_float)` is the trap that looks correct and isn't. For storage,
integer minor units (cents) is an even stricter alternative; Decimal is the pragmatic choice for a quote
you're displaying, not summing.

## Lesson 3 — Fan-out is forced when there's no batch endpoint, and it multiplies your quota

**Concept.** Finnhub has no "many quotes in one call" endpoint, so `get_market_summary` fans out:
N symbols × 2 calls each (`/quote` + `/stock/profile2`) run concurrently via `asyncio.gather`. Three
symbols = six upstream calls. Concurrency wins on latency but the quota cost is linear in symbols × calls.

**Why it matters.** The free tier is 60 calls/min; a 20-symbol summary is 40 calls in one burst. Tool
design and quota budget are coupled — "summarise my watchlist" can blow the minute budget if you don't
account for the per-symbol multiplier.

**In this codebase.** `get_market_summary` does `asyncio.gather(*(_fetch_one(s) ...))`, and each
`_fetch_one` itself `gather`s the quote+profile pair.

**Pitfall or alternative.** When an upstream *does* offer a batch endpoint, prefer it — one call for N
symbols beats N parallel calls on both quota and rate-limit headroom. Fanning out should be the fallback,
not the reflex. Caching quotes with a short TTL is the other lever the PRD flags.

## Lesson 4 — Encode "not found" from each provider's actual behaviour, not from HTTP status

**Concept.** Finnhub does **not** 404 an unknown ticker. `/quote` returns all-zeros (`c:0, t:0`) and
`/stock/profile2` returns `{}`, both with HTTP 200. So invalidity is detected from the *payload* — an
empty profile (no `name`) — not the status code.

**Why it matters.** A status-only check would treat "INVALID" as a successful zero-priced stock and emit
a Quote of `$0.00` — a plausible-looking fabrication. You have to learn each provider's "no data" tell and
encode it explicitly.

**In this codebase.** `_fetch_one`: `name = (profile or {}).get("name"); if not name: return
QuoteError(..., "unknown symbol")`. The test fixtures capture Finnhub's real zeros/empty-profile shapes.

**Pitfall or alternative.** The zero-price heuristic (`c == 0`) is fragile — some instruments legitimately
report 0 intraday. The empty-profile signal is the more reliable "this symbol doesn't exist" tell here.

## Lesson 5 — Split a server when the concern, scaling, or quota differs — finance earns its own process

**Concept.** Finance is a separate `FastMCP("finance")` on its own port (8802), not another tool bolted
onto world-data. It's a distinct concern (markets, not "what's happening here"), with its own provider,
its own quota, and its own failure mode — so it gets its own process.

**Why it matters.** This is the mirror of Task 3's "combine news+weather" call. The criterion is the
same in both directions: group by who consumes them and how they scale/fail. A Finnhub outage or rate-limit
shouldn't take news and weather down with it.

**In this codebase.** `servers/finance_server.py` runs independently; both servers were verified listening
on 8801/8802 simultaneously with no conflict (`FINANCE_PORT` default 8802).

**Pitfall or alternative.** Splitting *too* eagerly (a server per tool) multiplies processes and ports to
operate. The unit is the *concern*, not the tool — finance has two tools in one server for the same reason
world-data has two.

## Lesson 6 — Canonicalise identifiers at the server boundary

**Concept.** The server normalises symbols with `.strip().upper()` before use, so `" aapl "` and `AAPL`
resolve identically, and the returned `Quote.symbol` is the canonical form. Callers don't have to know
Finnhub wants uppercase.

**Why it matters.** Identifier hygiene at the boundary prevents a class of "works for AAPL, fails for
aapl" bugs and keeps the canonicalisation rule in one place. It mirrors unit normalisation (Task 3) but
for identity rather than magnitude.

**In this codebase.** `_fetch_one`: `sym = symbol.strip().upper()`; the empty-after-strip case returns a
`QuoteError("empty symbol")` rather than calling upstream with junk.

**Pitfall or alternative.** Over-normalising can corrupt case-sensitive identifiers (some tickers/feeds
*are* case-sensitive, e.g. crypto pairs). Know your namespace before uppercasing blindly.

## Lesson 7 — Carry the upstream's timestamp; never stamp "now", and let the consumer disclose staleness

**Concept.** Every `Quote` carries `as_of`, derived from Finnhub's `t` (the quote's own observation time),
not from the server's wall clock. A delayed or stale quote is then self-describing — the Publisher can
honestly render "as of 14:02" instead of implying real-time freshness.

**Why it matters.** Free finance tiers serve delayed data. Stamping `datetime.now()` would launder stale
data as fresh — a trust and even compliance problem for anything money-adjacent. The data should declare
its own age.

**In this codebase.** `_fetch_one`: `as_of: datetime.fromtimestamp(quote.get("t") or 0, tz=timezone.utc)`,
always tz-aware UTC.

**Pitfall or alternative.** A `t` of 0 (the invalid case) would map to the Unix epoch — handled here
because empty-profile catches invalid symbols first. For valid-but-stale quotes, surfacing `as_of`
prominently in the UI is the disclosure; hiding it is the anti-pattern.

## Lesson 8 — Use a `Literal` discriminator, not a bare bool or a free-form string

**Concept.** The union is tagged with `status: Literal["ok"] | Literal["error"]`. Not a bool `is_error`
(which can't grow a third state), not an untyped `str` (which a typo can silently break). The literal is
both the Pydantic discriminator and human-readable.

**Why it matters.** It's type-checkable (a mismatched literal fails validation), self-documenting in the
JSON, and extensible — adding a `"stale"` state later is a literal addition, not a refactor of every
boolean check. This is the disciplined version of "return enums", avoiding stringly-typed status.

**In this codebase.** `Quote.status` / `QuoteError.status` literals in `servers/finance_server.py`; the
client round-trip exposes `r.status` for branching.

**Pitfall or alternative.** Serialising a Python `Enum` to its name also works, but a `Literal[str]` keeps
the wire format obvious and avoids enum-deserialization friction at the MCP boundary. Either beats a bare
boolean.

## Lesson 9 — Make test fixtures mirror the provider's real (weird) shapes, mocked at your own seam

**Concept.** Tests monkeypatch `_request_finnhub` and feed canned payloads that match Finnhub's actual
shapes — including the unintuitive invalid-ticker response (zeros + `{}` profile). So the partial-success
path is exercised deterministically, with no key and no quota burned.

**Why it matters.** A mock that returns clean, idealised data tests a fantasy API. The value is in
capturing the provider's quirks (zeros-not-404) in the fixture, so the code that handles those quirks is
actually covered. Finance APIs are exactly where you must not burn live quota on every test run.

**In this codebase.** `tests/test_finance_server.py`: `QUOTES`/`PROFILES` fixtures incl. the `INVALID`
shape; `_install_fake` patches the seam.

**Pitfall or alternative.** Recording a real response once (a VCR-style cassette) is the higher-fidelity
alternative when shapes are complex — but hand-written fixtures that encode the *failure* shapes are often
more honest than a cassette of only the happy path.

## Lesson 10 — Put the failure-isolation boundary at the per-item function, so a batch can't be poisoned

**Concept.** `_fetch_one` is the isolation boundary: it catches transport `ToolError`s internally and
returns a `QuoteError` — it never raises. That's what lets the outer `asyncio.gather` in
`get_market_summary` complete even if one symbol's upstream 429s, without `return_exceptions=True`
gymnastics.

**Why it matters.** Where you put the try/except decides the blast radius. Catch at the batch level and
one failure still aborts the gather (or you litter it with exception handling); catch at the per-item
function and each item's failure is contained to its own entry. Isolation belongs at the unit of work.

**In this codebase.** `_fetch_one`'s `try/except ToolError -> QuoteError`; `get_market_summary`'s
`gather` therefore needs no exception handling and simply returns the list.

**Pitfall or alternative.** `asyncio.gather(..., return_exceptions=True)` is the alternative, but it yields
a list of `Exception | Quote` you must post-process and re-key to symbols — messier than making the unit of
work total (always returns a value). Prefer total functions over exception-laden gathers.
