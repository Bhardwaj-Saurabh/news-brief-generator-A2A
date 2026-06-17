# Task 6 — Lessons

The most important task: the typed contracts that are the real API between agents. The depth is in
contract design — generics, discriminated unions, the tool/agent contract line, and naming that won't
lie in six months.

## Lesson 1 — The contracts ARE the inter-agent API; changing a field is an API change

**Concept.** `BriefRequest`, `ContextBundle`, `SignalBundle`, `ScoutReport`, `PublishedBrief` are not
DTOs that happen to pass between functions — they are the contract the agents program against. The
Contextualist promises a `ContextBundle`; the Publisher consumes a `ScoutReport`. Renaming a field or
tightening a type is a breaking change to that contract, same as editing an HTTP schema.

**Why it matters.** Treating these as "just some Pydantic models" invites casual edits that silently
break a downstream agent. Treating them as the API makes you version and evolve them deliberately
(Lesson 10), which is what keeps a multi-agent system refactorable.

**In this codebase.** `agents/contracts.py` — every model has a purpose docstring (not just field
lists), because the contract's *intent* is part of the API.

**Pitfall or alternative.** Passing dicts between agents (the thing this task exists to avoid): no
schema, no validation, every consumer re-guesses the shape, and a typo fails at runtime three agents
later instead of at construction.

## Lesson 2 — The tool-contract / agent-contract line: import the tool models, don't redefine them

**Concept.** `contracts.py` imports `Headline`, `WeatherSnapshot`, `Quote`/`QuoteError`, `MediaItem`
from the server modules rather than redefining them. A *tool contract* (a server's normalised output)
is owned by its server; an *agent contract* (`ContextBundle`, `ScoutReport`) composes those. One
definition, imported across the boundary, keeps the two layers DRY and honest about who owns what.

**Why it matters.** Redefining the models in the agent layer would create two sources of truth that
drift; the day a server adds a field, the agent's copy lies. Importing makes the dependency explicit:
agents consume servers' outputs, full stop.

**In this codebase.** `from servers.world_data_server import Headline, WeatherSnapshot` etc., re-exported
via `__all__` so consumers import the whole vocabulary from `contracts`.

**Pitfall or alternative.** The cost: importing a server module runs its top-level code (instantiates a
`FastMCP`, calls `basicConfig`) and pulls `fastmcp` into the agent layer. A cleaner alternative is a
neutral `schemas` module both servers and agents import — worth it once the side effects bite; here the
import is the pragmatic, PRD-aligned choice, accepted with eyes open.

## Lesson 3 — A generic envelope preserves payload type through serialization

**Concept.** `AgentMessage[T]` is generic in its payload. Parameterising it
(`AgentMessage[ScoutReport]`) lets `model_validate_json` reconstruct `payload` as a real `ScoutReport`,
not a bare dict — the type survives the JSON round-trip at the consumer that knows `T`.

**Why it matters.** A non-generic envelope with `payload: dict` (or `Any`) loses all structure on the
wire; the consumer gets an untyped blob and must re-validate by hand, defeating the point of typed
messages. Generics are what make a reusable envelope type-safe.

**In this codebase.** `AgentMessage(BaseModel, Generic[T])` in `contracts.py`; `test_agent_message_
roundtrips_payload_type` proves `restored.payload` is a `ScoutReport` with Decimal and union fields intact.

**Pitfall or alternative.** A *bare* `AgentMessage.model_validate_json` (no `[T]`) parses `payload` as a
dict — the type is only recovered when the consumer parameterises. The envelope can't magically know `T`;
the receiver must.

## Lesson 4 — Be honest about the transport: correlate with contextvars, not a field you can't carry

**Concept.** The decided trace strategy is a `contextvars` trace id surfaced via a logging filter, set
once per brief — **not** a `trace_id` threaded through `AgentMessage`. The reason is transport honesty:
the MCP boundary (`call_tool`) does not carry our envelope, so a `trace_id` on the message could not
follow a call into a tool server anyway.

**Why it matters.** Threading an id that silently drops at the first boundary gives false confidence in
your traces. A contextvars id picked up by every log record correlates a whole brief's work — including
the MCP calls — without pretending the protocol carries something it doesn't.

**In this codebase.** `mcp_client.call_tool` is deliberately trace-free (documented in its module
docstring); `AgentMessage.trace_id` exists as the envelope's reference field but is off the hot path.
The contextvars filter itself is wired where a brief is orchestrated (Scout/UI), not in this task — flagged.

**Pitfall or alternative.** The over-built alternative is a full context-propagation framework
(OpenTelemetry baggage) — correct at scale, overkill here. The under-built one is no correlation at all,
which makes a concurrent fan-out's logs unreadable.

## Lesson 5 — Frozen models: a gathered fact is immutable as it travels

**Concept.** Every contract is `frozen=True`. Once the Contextualist returns a `ContextBundle`, no
downstream agent can mutate a headline or the weather in place — they'd get a `ValidationError`. Facts
are read-only once gathered.

**Why it matters.** Shared mutable state across agents is the source of spooky-action bugs (agent B
mutates what agent A still holds). Immutability makes data flow one-directional and safe to pass into a
concurrent `gather` without defensive copies.

**In this codebase.** `model_config = ConfigDict(frozen=True)` on every contract; `test_frozen_models_
are_immutable` asserts a `BriefRequest.region = ...` raises.

**Pitfall or alternative.** When you genuinely need a tweaked copy, `model_copy(update=...)` returns a
new frozen instance — the "regenerate with tweaks" path (Task 11) will use this rather than mutating.

## Lesson 6 — A discriminated union carries partial success all the way into the report

**Concept.** `SignalBundle.quotes` is `list[Annotated[Quote | QuoteError, Field(discriminator="status")]]`.
The explicit `status` discriminator makes deserialisation deterministic — pydantic reads `status` and
picks the variant, no field-guessing — so the finance tool's per-symbol partial success survives into
the `ScoutReport`, not just inside the server.

**Why it matters.** Without an explicit discriminator, pydantic's smart-union *usually* guesses right but
can mis-bind ambiguous objects; with it, the round-trip is guaranteed. And keeping `QuoteError` in the
bundle means "AAPL failed" is a fact the Publisher can see and disclose, not something silently dropped
at the agent boundary.

**In this codebase.** `QuoteResult` alias in `contracts.py`; `test_full_scout_report_constructs…` and
the AgentMessage round-trip both assert `quotes[1].status == "error"` survives.

**Pitfall or alternative.** A bare `Quote | QuoteError` (no discriminator) works in memory but is fragile
on the wire. The discriminator is cheap insurance the moment the union is serialised.

## Lesson 7 — Resolve identifiers in one place, with a logged fallback

**Concept.** `resolve_region` turns one human `region` into three tool identities (`country_code`,
`weather_city`, `media_region`) via a table + alias map, falling back to the default *and logging a
warning* on an unknown region. One function to test, one place to add a country.

**Why it matters.** The alternative — each agent doing its own `"UK" -> "gb"` mapping — scatters the
translation, guarantees drift (news says `gb`, weather forgets London), and hides the fallback. Centralising
makes the mapping a single tested unit and surfaces misses instead of silently defaulting.

**In this codebase.** `agents/regions.py`: `_REGIONS` + `_ALIASES` + `resolve_region`; tests cover the
UK triple, an alias, and the unknown→default fallback.

**Pitfall or alternative.** The silent fallback is the trap — a typo'd region quietly becomes UK news
forever. The `log.warning` is what turns that into a visible signal (the same ethos as the Scout's
ticker-fallback warning in Task 8).

## Lesson 8 — Output schema design is downstream prompt and UI design, two tasks early

**Concept.** `PublishedBrief` carries typed `sections: list[Section]` and `sources: list[Source]`, not
just a `markdown` blob. That choice, made now, makes Task 9's structured-output JSON schema deterministic
(the LLM fills a known shape) and Task 11's "group sources by domain" a field read (`source.domain`)
rather than a regex over rendered markdown.

**Why it matters.** Schema decisions ripple forward. A loose `markdown`-only brief would force the UI to
re-parse prose and the LLM to invent structure freely. Designing the contract to serve consumers you
haven't built yet is what makes those later tasks small.

**In this codebase.** `Section`, `Source` (+ `Source.from_url` to populate `domain`), and
`PublishedBrief.sections/sources` in `contracts.py`.

**Pitfall or alternative.** Over-structuring is the opposite risk — a 20-field brief schema the LLM
fills unreliably. Structure exactly what a consumer reads programmatically (sections, sources); leave
prose as prose (`markdown`).

## Lesson 9 — Name temporal (and unit) fields so they can't lie later

**Concept.** The contracts have five *different* time fields with honest names: `requested_at`
(BriefRequest), `generated_at` (bundles/brief), `published_at` (Headline/MediaItem), `observed_at`
(WeatherSnapshot), `as_of` (Quote). Each names *which clock and which event* — none is a generic
`timestamp` that a future reader has to guess about.

**Why it matters.** A field named `time` or `date` becomes a lie the moment requirements shift — is it
fetch time or event time? Precise names encode intent so a maintainer in six months reads truth, not a
guess. Same discipline as `temp_c`/`wind_kph` carrying their unit.

**In this codebase.** The distinct temporal fields across `contracts.py` and the imported tool models.

**Pitfall or alternative.** Reusing one `timestamp` everywhere "for consistency" is false economy — it
makes every consumer ask which event it refers to. Consistency in *naming convention* (`*_at`/`as_of`)
beats consistency in a single vague field.

## Lesson 10 — Design for additive evolution, not one-shot perfection

**Concept.** Optional fields and defaults are everywhere: `topic: str | None`, `weather:
WeatherSnapshot | None`, list fields default empty, `requested_at`/`generated_at` auto-fill. A degraded
bundle (one upstream down) still validates, and adding a new optional field later won't break existing
messages or stored briefs.

**Why it matters.** Multi-agent contracts evolve; you cannot get them perfect on day one. Additive
changes (new optional fields, new union variants) are backward-compatible; required-field changes are
breaking. Defaulting and optionality are what make the contract survive refactors — and `AgentMessage`
is kept as the forward-compat seam for a future bus.

**In this codebase.** Defaults/optionals throughout `contracts.py`; the empty-bundle path is exactly the
graceful-degradation the Contextualist (Task 7) relies on.

**Pitfall or alternative.** The trap is making everything required for "strictness", so any partial
result fails validation and the whole brief dies because weather was down. Strict where it matters
(a Quote needs a price), lenient where degradation is valid (a bundle without weather is fine).
