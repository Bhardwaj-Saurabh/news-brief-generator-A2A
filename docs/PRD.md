# PRD — Multi-Agent News Brief Generator (MCP + A2A)

> **Project:** A small AI-driven daily brief generator that fetches real-time data from multiple APIs via MCP servers, orchestrates agents through explicit message passing, and renders a generated article in a Streamlit UI.
> **Audience for the code:** Senior Python developer learning agent architecture patterns hands-on.
> **Estimated time:** 6–10 focused hours, spread across the task list.

---

## 0. Working Agreement with Claude Code — READ FIRST, NON-NEGOTIABLE

This PRD is consumed by Claude Code. The following rules govern execution and override any instinct to be efficient or batch work:

1. **Read this entire PRD before writing any code.** Do not skim. Confirm understanding by summarising the architecture in 5–8 lines before starting Task 0.
2. **Execute tasks strictly sequentially.** Task 0 → Task 1 → … → Task 11. Do **not** skip ahead. Do **not** batch multiple tasks into one turn.
3. **After completing each task, STOP.** Do the following four things, then wait for explicit user approval before starting the next task:
   - (a) State which task was completed and list the files created or modified.
   - (b) Show the acceptance-criteria check (each criterion → ✅ or ❌ with one-line evidence).
   - (c) **Write the 10 lessons file** for that task — see Section 7 for the exact format. This is a deliverable, not optional commentary.
   - (d) Propose a one-line conventional commit message.
4. **Lessons are mandatory.** A task is not "done" until `lessons/task_NN_lessons.md` exists with exactly 10 well-formed lessons matching the spec in Section 7. If you find yourself wanting to skip them "to save context," stop — the lessons are the point of the exercise for the user.
5. **Audience-calibrated content.** The user is a senior practitioner (Lead AI Architect). Skip beginner explanations (what a function is, what JSON is, what async means). Lessons focus on patterns, tradeoffs, design decisions, and production gotchas.
6. **If blocked, ask one focused question and wait.** Do not invent API choices, fabricate keys, or stub past failures silently.
7. **Be honest about uncertainty.** If a library API has changed or you're unsure of the current FastMCP signature, say so and verify before writing dependent code.
8. **No "I'll come back to this later" debt.** If a task says implement X, implement X. Don't leave TODOs and proceed.

---

## 1. Project Overview

### What we're building
A daily brief generator that:
1. Pulls live data from four domains (world news, weather, finance, media) through **MCP servers** exposed over HTTP.
2. Coordinates three agents (**Contextualist**, **Scout**, **Publisher**) using an explicit **A2A message-passing protocol**.
3. Generates a structured article using an LLM with validated input context.
4. Surfaces the brief through a **Streamlit** UI that supports generating, viewing, and saving reports.

### Why this architecture (the learning point)
The project is a deliberately small but production-shaped slice of an agentic system. It exercises:
- **MCP as a tool layer** (decoupled, language-agnostic, transport-explicit).
- **A2A as a coordination layer** (typed messages, no shared mutable state, explicit contracts).
- **Schema validation at every boundary** (API → MCP → Agent → LLM → UI).
- **Separation of concerns between data fetchers, aggregators, and synthesisers.**

### Out of scope (do not build)
- Authentication / multi-tenant logic.
- Persistent storage beyond local JSON / markdown file saves.
- Streaming responses, server-sent events.
- Deployment, containerisation, CI.
- Observability beyond standard library logging.

---

## 2. Learning Objectives

By the end of the project, the user should be able to:
1. Stand up an MCP server with FastMCP and expose tools over HTTP.
2. Reason about MCP tool granularity, idempotency, and error semantics.
3. Design A2A message contracts that survive refactors.
4. Orchestrate multiple agents with bounded context and clear handoffs.
5. Integrate third-party REST APIs behind a normalising layer.
6. Use Pydantic v2 to validate at boundaries without leaking schema everywhere.
7. Prompt an LLM for structured output and parse it defensively.
8. Build a Streamlit UI that triggers async work without freezing the event loop.
9. Apply secure environment-variable handling and key rotation hygiene.
10. Identify where this toy architecture would break under production load.

---

## 3. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | Use `from __future__ import annotations` and modern typing |
| MCP framework | `fastmcp` | HTTP transport, not stdio |
| HTTP client | `httpx` | Async, with timeouts on every call |
| Schema validation | `pydantic` v2 | Use `model_validate`, `Field`, `ConfigDict` |
| LLM | `openai` (>=1.0) | Use the Responses or Chat Completions API; structured outputs via `response_format` |
| UI | `streamlit` | Latest stable |
| Env management | `python-dotenv` | `.env` never committed; `.env.example` is committed |
| Logging | stdlib `logging` | INFO default, DEBUG via env var |

### Default API choices (swap if the original tutorial specifies otherwise)
- **Weather:** OpenWeatherMap (Current Weather Data)
- **News / World Data:** NewsAPI.org (top-headlines)
- **Finance:** Finnhub (quote + company news)
- **Media:** YouTube Data API v3 (search.list, trending)
- **LLM:** OpenAI `gpt-4o-mini` or `gpt-4o` for the publisher

---

## 4. Repository Layout (target)

```
news-brief/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── pyproject.toml
├── servers/
│   ├── __init__.py
│   ├── world_data_server.py     # News + Weather tools
│   ├── finance_server.py        # Quote, market summary
│   └── media_server.py          # Trending video, search
├── agents/
│   ├── __init__.py
│   ├── contracts.py             # Pydantic A2A message models
│   ├── mcp_client.py            # Thin wrapper for MCP HTTP calls
│   ├── contextualist.py
│   ├── scout.py
│   └── publisher.py
├── app/
│   └── streamlit_app.py
├── lessons/
│   ├── task_00_lessons.md
│   ├── task_01_lessons.md
│   └── ...                      # one per task
├── tests/
│   └── (minimal smoke tests as tasks dictate)
└── saved_briefs/                # output target for "Save" button
```

---

## 5. Architecture Overview

```
┌─────────────┐
│  Streamlit  │  ← user clicks "Generate Brief"; the UI orchestrates the two steps below
└──────┬──────┘
       │ step 1: scout(request) ──────────────► ScoutReport
       │ step 2: publish(report) ─────────────► PublishedBrief
       │
       ├──────────────────────────────┐
       ▼ (step 1)                      ▼ (step 2)
┌─────────────────────────────┐  ┌─────────────────────────────────────┐
│   Scout Agent (aggregator)  │  │   Publisher Agent (LLM synth)       │
│  receives: BriefRequest     │  │  receives: ScoutReport              │
│  emits:    ScoutReport      │  │  emits:    PublishedBrief           │
│  calls: Contextualist,      │  │  (the ONLY LLM call; never calls    │
│         Finance, Media      │  │   the Scout)                        │
└──┬───────────┬──────────┬───┘  └─────────────────────────────────────┘
   │           │          │
   ▼           ▼          ▼
┌─────────────┐ ┌──────────┐ ┌──────────┐
│Contextualist│ │Finance   │ │ Media    │
│   Agent     │ │MCP Server│ │MCP Server│
│ (news+wx)   │ └──────────┘ └──────────┘
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ World Data  │
│ MCP Server  │
└─────────────┘
```

The **UI is the orchestrator**: it calls `scout(request)` to gather, then `publish(report)` to synthesise. The Scout and Publisher are siblings that never call each other — this matches the agent signatures in Tasks 9 and 10.

**Key design decisions** (the user should be able to defend these by end of project):
- MCP servers are **stateless and dumb** — they wrap APIs and normalise outputs. They do not interpret.
- Agents are **stateless per-invocation** — context is in the message, not in the agent.
- Messages are **Pydantic models, not dicts** — schemas live in `contracts.py` and are the inter-agent API.
- The Publisher is the **only LLM call** — keep the synthesis step isolated.

---

## 6. Task Specifications

> **Note on task count:** The original course description says "13 tasks" but lists Task 0 through Task 11 (12 tasks). This PRD covers all 12 visible tasks. If the course later reveals a Task 12, append it.

> For **every** task: after coding is complete, write `lessons/task_NN_lessons.md` per Section 7, then stop and wait for approval.

---

### Task 0 — Project Setup

**Goal:** Create the repository skeleton, dependency manifest, env scaffolding, and README stub.

**Deliverables:**
- `requirements.txt` or `pyproject.toml` with pinned versions.
- `.env.example` listing all required keys (placeholders only).
- `.gitignore` covering `.env`, `__pycache__`, `.venv`, `saved_briefs/*.md` (keep dir, ignore contents).
- `README.md` with: project description, setup steps, run instructions placeholder.
- Empty `servers/`, `agents/`, `app/`, `lessons/`, `tests/`, `saved_briefs/` directories with `__init__.py` where applicable.

**Acceptance criteria:**
- `pip install -r requirements.txt` succeeds in a clean venv.
- `python -c "import fastmcp, httpx, pydantic, openai, streamlit"` exits 0.
- No real secrets in any committed file.

**Lesson themes for this task (pick any 10):** dependency pinning vs. ranges; venv hygiene; `.env` separation patterns; gitignore patterns for ML/AI projects; project layout conventions for small services; pyproject vs requirements; how to introspect installed package versions; the `__init__.py` decision; Streamlit dev vs prod deps; reproducibility risks.

---

### Task 1 — Get API Keys

**Goal:** Provision keys for all upstream services and wire them into `.env` safely.

**Deliverables:**
- `.env.example` updated with: `OPENWEATHER_API_KEY`, `NEWSAPI_KEY`, `FINNHUB_API_KEY`, `YOUTUBE_API_KEY`, `OPENAI_API_KEY`, plus any server ports.
- `README.md` section documenting where to obtain each key (links, free-tier limits, expected approval time).
- A tiny `scripts/check_keys.py` that loads `.env` and prints which keys are present (never the values) and which are missing.

**Acceptance criteria:**
- Running `python scripts/check_keys.py` against a populated `.env` reports all 5 keys present, none redacted in source.
- Removing any key from `.env` causes the script to report exactly that one as missing.

**Lesson themes:** API key rotation cadence; key scoping and rate-limit tiers; why never to print key values in logs; the difference between secrets management for local dev vs. cloud; checked-in vs. local config; choosing between `os.environ.get` and Pydantic Settings; what happens when a free tier silently throttles; provider-specific gotchas (NewsAPI dev key restrictions, OpenAI org IDs); cost guardrails before first LLM call; the case for a secrets manager even in a toy project.

---

### Task 2 — World Data MCP Server (scaffold + News tool)

**Goal:** Stand up the first FastMCP server with a `get_top_headlines` tool wrapping NewsAPI.

**Deliverables:**
- `servers/world_data_server.py` exposing one tool: `get_top_headlines(country: str = "gb", category: str | None = None, query: str | None = None, since_hours: int | None = None, limit: int = 5) -> list[Headline]`.
  - `query` gives `BriefRequest.topic` a consumer. When `query` is set, route to NewsAPI's `everything` endpoint (which supports free-text `q` plus `from`/`to`); when it is absent, use `top-headlines`. `since_hours` maps `BriefRequest.lookback_hours` to the `from`/`to` window on the `everything` path. This closes the orphaned-field gap (G2) — without these params `topic` and `lookback_hours` cannot reach the news layer.
- Pydantic models for `Headline` (title, source, url, published_at, summary).
- HTTP transport configured on a chosen port (e.g. 8801).
- Startup log line stating the server name, port, and registered tools.

**Acceptance criteria:**
- Server starts with `python -m servers.world_data_server` and binds to localhost.
- An MCP client (curl-based smoke test or short `tests/` script) lists the tool and successfully invokes it.
- Output is a list of validated `Headline` objects; malformed upstream data is rejected with a clear error, not a 500.

**Lesson themes:** MCP tool granularity decisions; why HTTP over stdio for multi-language ecosystems; Pydantic at the MCP boundary; idempotency expectations of MCP tools; error semantics (raise vs. return error envelope); rate-limit handling at the tool layer; timeouts on every external call; thread/event-loop ownership in FastMCP; tool naming conventions; what *not* to put in tool descriptions.

---

### Task 3 — Weather MCP Tool + Run the Server

**Goal:** Add a `get_current_weather` tool to the world data server and verify both tools work together.

**Deliverables:**
- New tool `get_current_weather(city: str, units: str = "metric") -> WeatherSnapshot` wrapping OpenWeatherMap.
- Pydantic model `WeatherSnapshot` (city, country, temp_c, feels_like_c, conditions, wind_kph, observed_at).
- Unit normalisation: server accepts `metric` or `imperial`, always returns metric internally.
- README updated with run command and tool list.

**Acceptance criteria:**
- Both tools discoverable in one MCP server instance.
- Calling `get_current_weather("London")` returns a validated `WeatherSnapshot`.
- Invalid city returns a structured error, not an unhandled exception.

**Lesson themes:** server-side normalisation vs. trusting upstream; the unit-system trap; treating geocoding as a separate concern; why "errors are data" at the MCP boundary; how to test an MCP server without a full client; observability (what to log per tool call); the cost of putting two unrelated tools in one server (and when it's fine); MCP tool docstrings as LLM-facing UX; choosing between sync and async tool handlers; backoff on transient upstream failures.

---

### Task 4 — Finance MCP Server

**Goal:** Build a second, independent MCP server for finance data.

**Deliverables:**
- `servers/finance_server.py` on a different port (e.g. 8802).
- Tools: `get_quote(symbol: str) -> Quote` and `get_market_summary(symbols: list[str]) -> list[Quote]`.
- Pydantic `Quote` model (symbol, name, price, change, change_pct, as_of).
- Graceful handling of unknown tickers.

**Acceptance criteria:**
- Server runs independently of the world data server.
- Both servers can run simultaneously without port conflict.
- `get_market_summary(["AAPL", "MSFT", "INVALID"])` returns 2 valid quotes and a structured error entry for the invalid one — never raises out of the tool.

**Lesson themes:** when to split MCP servers vs. combine; partial-success patterns in batch tools; clock skew and `as_of` timestamps; numeric precision (`Decimal` vs `float`) for money; symbol normalisation as a server concern; the case against returning enums as strings; how rate-limit budgets influence tool design; designing `get_market_summary` as fan-out vs. single batched upstream call; testing strategies for finance APIs without burning quota; the "stale data" disclosure responsibility.

---

### Task 5 — Media Engine MCP Server

**Goal:** Third MCP server for media data, wrapping YouTube Data API.

**Deliverables:**
- `servers/media_server.py` on a third port (e.g. 8803).
- Tools: `get_trending(region: str = "GB", limit: int = 5) -> list[MediaItem]` and `search_media(query: str, limit: int = 5) -> list[MediaItem]`.
- Pydantic `MediaItem` model (title, channel, url, published_at, views, summary).
- Strip or summarise long descriptions to fit a brief.

**Acceptance criteria:**
- Both tools return validated `MediaItem` lists.
- Description truncation is deterministic and tested with a fixed input.
- YouTube quota-exceeded responses are surfaced as a typed error, not a crash.

**Lesson themes:** content-length budgets at the tool boundary; deterministic truncation vs. LLM-based summarisation tradeoff; designing for the LLM consumer (what does the Publisher actually need?); region/locale handling in media APIs; the YouTube quota model and why batch design matters; URL hygiene and tracking-param stripping; metadata staleness; choosing a representative "view count" timeframe; when a tool description doubles as prompt scaffolding; multi-tenancy implications of region defaults.

---

### Task 6 — Agent Messaging Protocol

**Goal:** Define the A2A contracts. This is the most important task in the project — get the schemas right.

**Deliverables:**
- `agents/contracts.py` containing Pydantic models for:
  - `BriefRequest` (topic, region, lookback_hours, audience, requested_at)
  - `ContextBundle` (headlines, weather, region, generated_at)
  - `SignalBundle` (quotes, media_items, generated_at)
  - `ScoutReport` (context: ContextBundle, signals: SignalBundle, request: BriefRequest)
  - `Section` (heading, body_markdown) and `Source` (title, url, domain) — supporting types so the brief's body and attribution are typed, not loose strings/dicts.
  - `PublishedBrief` (markdown, title, `sections: list[Section]`, `sources: list[Source]`, generated_at, request: BriefRequest). **Typed `sections`/`sources` (G7)** make the Task 9 structured-output JSON schema deterministic and the Task 11 "group sources by domain" UI a field read, not a re-parse.
  - `AgentMessage[T]` (generic envelope: id, from_agent, to_agent, payload: T, trace_id, timestamp). **Defined as the typed-envelope reference but kept OFF the hot path (G4):** agent functions pass bare payloads, not envelopes. See the trace-strategy note below.
- `agents/regions.py` — a small `resolve_region(region) -> RegionIds` lookup util mapping one `BriefRequest.region` into `{country_code, weather_city, media_region}` (G2). One place to translate, one place to test.
- A short `agents/mcp_client.py` with a single `async def call_tool(server_url, tool, args) -> dict` helper. It stays **trace-free** (no trace param) because the MCP boundary does not propagate it; the agent immediately `model_validate`s the returned dict into the relevant contract so the untyped dict never leaks past the agent boundary.

**Trace strategy (decided, G4):** request correlation uses a stdlib `logging` trace id stored in a `contextvars.ContextVar`, set once per brief generation and injected into every log record via a logging filter — not the `AgentMessage[T]` envelope. This is honest about the transport (nothing has to carry a trace across a boundary the MCP protocol doesn't support) and keeps the envelope available as a contract for a future message bus.

**Acceptance criteria:**
- All models validate on construction with realistic fixture data (provide one fixture file or inline test).
- The generic `AgentMessage[T]` round-trips JSON without losing the payload type information at the consumer.
- `resolve_region("UK")` (or your canonical input) returns the expected `country_code` / `weather_city` / `media_region` triple.
- Schema docstrings explain *purpose*, not just fields.

**Lesson themes:** contracts as the real API between agents; why generics matter for envelopes; trace IDs and correlation; immutability via `model_config = ConfigDict(frozen=True)`; designing for *evolution* (additive change) rather than perfection; the cost of dict-passing between agents; what belongs in the envelope vs. the payload; how schema design constrains LLM prompts downstream; choosing field names that won't lie in six months; the line between agent contract and tool contract.

---

### Task 7 — Contextualist Agent

**Goal:** First agent — fetches context (news + weather) and returns a `ContextBundle`.

**Deliverables:**
- `agents/contextualist.py` with `async def gather_context(request: BriefRequest, deadline: float | None = None) -> ContextBundle`. The optional `deadline` (a monotonic remaining-time budget passed down by the Scout) bounds the per-tool timeouts so nested budgets don't compound (G6); when called standalone it falls back to the default ~10s.
- Uses `resolve_region(request.region)` (from `agents/regions.py`) to derive the news `country_code` and weather `weather_city`, and passes `request.topic` / `request.lookback_hours` through as the news `query` / `since_hours` (G2).
- Calls the world data MCP server (both tools) via `mcp_client`.
- Aggregates and normalises the responses into the bundle.
- Concurrent fetching with `asyncio.gather`, with per-tool timeouts.

**Acceptance criteria:**
- Calling `gather_context(BriefRequest(...))` against a running world data server returns a populated `ContextBundle`.
- Failure of one upstream tool (e.g. weather down) does not crash the agent — the bundle is returned with that section empty and a logged warning.
- All MCP calls complete within a configurable overall budget (default 10s).

**Lesson themes:** `asyncio.gather` vs. `TaskGroup` (3.11+); partial success in agents; the "context bundle" pattern; agent-level vs tool-level retry; bounded time budgets per agent; the difference between a contextualist and a scout (why split them); how an agent's output schema constrains the next agent's prompt; logging discipline inside agents; testing agents without running real MCP servers (fake clients); the case against agents calling LLMs directly at this layer.

---

### Task 8 — Scout Agent

**Goal:** Aggregator agent — calls Contextualist, Finance MCP, and Media MCP, returns a `ScoutReport`.

**Deliverables:**
- `agents/scout.py` with `async def scout(request: BriefRequest) -> ScoutReport`.
- Concurrent fan-out: Contextualist call + Finance MCP calls + Media MCP calls all in parallel.
- Owns the single overall time budget (default ~10s) and passes the remaining-time `deadline` down to `gather_context(...)` so nested budgets do not compound (G6).
- Composes `ScoutReport` from the responses.
- Symbol selection — **deliberately LLM-free (G3)**: a static keyword→ticker map (e.g. "tech" → AAPL/MSFT/NVDA, "energy" → XOM/CVX) applied to `request.topic`, falling back to a default watchlist (e.g. SPY, AAPL, MSFT) when nothing matches. The policy is explicit code, not a prompt, and **logs a warning on fallback** so silent misses are visible. Richer topic→symbol resolution (LLM or a symbol-search API) is explicitly out of scope — it would break the "Publisher is the only LLM call" invariant.

**Acceptance criteria:**
- End-to-end run of `scout(...)` against all three MCP servers returns a fully populated `ScoutReport`.
- Total wall time under the configured budget even with all upstreams hit.
- Any single upstream failure degrades gracefully (empty section + logged warning, not a crash).

**Lesson themes:** fan-out patterns in agents; the scout/aggregator role in agentic architectures; explicit defaults vs. magic; selection policies as code (not prompt); error degradation philosophy; the trap of "let the LLM handle errors"; how to keep an aggregator from becoming a god-object; testing aggregators with fakes; how this design would scale to N MCP servers; what observability hooks belong here (traces, span attributes).

---

### Task 9 — Publisher Agent

**Goal:** LLM synthesis — turn a `ScoutReport` into a `PublishedBrief`.

**Deliverables:**
- `agents/publisher.py` with `async def publish(report: ScoutReport) -> PublishedBrief`.
- One LLM call using OpenAI structured outputs (`response_format` with a JSON schema or Pydantic model).
- Prompt template that includes: role, audience, length budget, structure requirements, the `ScoutReport` as JSON.
- Defensive parsing: validate the LLM response against `PublishedBrief` schema; on failure, one retry with a corrective prompt, then surface error.
- Source attribution: every claim section references the underlying items (URLs from the report).

**Acceptance criteria:**
- Given a fixture `ScoutReport`, `publish(...)` returns a valid `PublishedBrief` with non-empty markdown.
- Structured output validation works — try a deliberately bad prompt to confirm the retry path triggers.
- No prompt injection vector from upstream data fields (test: a headline with `"ignore previous instructions"` does not derail the brief).

**Lesson themes:** prompting for structure (schema-first vs. example-first); the one-shot retry pattern; treating LLM output as untrusted input; prompt injection at the data-ingestion boundary; token budgets and trimming strategy; where the system/developer/user message boundary actually lies; deterministic vs. stochastic settings (temperature); response_format vs. tools for structured output; cost telemetry at the publisher; why the publisher should be the *only* LLM call in this design.

---

### Task 10 — Streamlit Interface

**Goal:** UI to trigger generation, view the brief, and save it.

**Deliverables:**
- `app/streamlit_app.py` with: form (topic, region, audience), Generate button, output area, Save button.
- Async invocation pattern: call `asyncio.run(scout(...))` then `asyncio.run(publish(...))` — or wire properly via `nest_asyncio` if needed. Document the choice.
- Save action: write `saved_briefs/{slug}-{timestamp}.md` and surface the path.
- Progress feedback: show which agent is currently running (Scout → Publisher).

**Acceptance criteria:**
- `streamlit run app/streamlit_app.py` launches and produces a brief end-to-end against running MCP servers.
- Save button creates a file with the correct filename pattern.
- UI does not freeze during generation; progress feedback updates.

**Lesson themes:** Streamlit's execution model (script-rerun) and why it bites async; `st.status` and `st.spinner` for staged feedback; session state for caching the last brief; the cost of running async work in Streamlit (and the three patterns to handle it); never blocking the UI thread on a 30s LLM call without feedback; filename slugging hygiene; idempotent saves; thinking about UX in agentic apps (what does "loading" mean when 6 things are happening?); when to move to a job queue (out of scope here, but flag it); accessibility basics in Streamlit.

---

### Task 11 — Improve Article Readability in the UI

**Goal:** Polish the rendered brief — sections, hierarchy, source links, copy-to-clipboard.

**Deliverables:**
- Render the `PublishedBrief.markdown` with proper section breaks (use `st.markdown` and CSS sparingly).
- Show source list as a collapsible expander.
- Add a "Copy to clipboard" button (Streamlit's `st.code` or a small component).
- Add a regenerate-with-tweaks affordance (e.g. shorter / longer / change audience).

**Acceptance criteria:**
- Headings render with visual hierarchy.
- Sources are clickable and grouped by domain.
- Regenerate button uses the previous request as a starting point.

**Lesson themes:** content hierarchy in generated artifacts; the "wall of text" failure mode of LLM output; why structured output enables better UI; trust signals in AI-generated content (sources, timestamps, models used); the case for *not* using a chat UI for this; designing a "regenerate with tweaks" loop; markdown-in-Streamlit gotchas; when CSS in Streamlit is worth it; differentiating between editorial polish (done by humans) and presentational polish (the job here); how UI shapes how users trust the system.

---

## 7. Lessons File Format Specification

Every task ends with a file at `lessons/task_NN_lessons.md` containing **exactly 10 lessons**. Each lesson uses this structure:

```markdown
## Lesson N — <concise concept name>

**Concept.** 2–4 sentences explaining the pattern, decision, or idea at a senior-practitioner level. No basics.

**Why it matters.** 1–2 sentences linking the lesson to production reality — failure mode it prevents, scale concern it addresses, or refactor it enables.

**In this codebase.** Reference to the specific file and roughly where it appears (e.g. `servers/finance_server.py`, the `get_market_summary` tool). If the lesson is about something *not* done, say so explicitly.

**Pitfall or alternative.** 1–2 sentences. What would you do differently in a real system, or what's the common mistake.
```

### Quality bar for lessons
- **Specific, not generic.** "Use timeouts" is not a lesson. "Why per-call timeouts beat global timeouts in fan-out aggregators" is a lesson.
- **Opinionated where warranted.** It's fine — preferred — to take a position.
- **Reference real code in the repo.** Vague handwaving doesn't help the user learn.
- **No duplication across tasks.** If lesson 4 of Task 2 was about Pydantic at the MCP boundary, don't repeat it in Task 3 — go deeper or pick something else.

### What lessons should NOT be
- Restatements of the task description.
- Generic Python tutorial content (async basics, what JSON is).
- Marketing for tools ("FastMCP is great because…").
- Vague best-practices listicles.

---

## 8. Definition of Done — Per Task Checklist

A task is done when **all** of these are true:

- [ ] Code implements the deliverables.
- [ ] All acceptance criteria pass (Claude Code lists evidence per criterion).
- [ ] `lessons/task_NN_lessons.md` exists with 10 lessons meeting Section 7's bar.
- [ ] `README.md` updated if commands or env vars changed.
- [ ] No silent TODOs or skipped requirements.
- [ ] Proposed conventional commit message stated.
- [ ] Explicit "TASK NN COMPLETE — awaiting approval to proceed to TASK NN+1" message to the user.

---

## 9. Persona Note for Claude Code

The user is a Lead AI Architect at a consultancy, building this for their own learning. They already know:
- Python, async, REST, JSON, logging, venv, pip.
- The general shape of MCP and what an LLM does.
- How a Streamlit app works at the surface level.

They want to learn:
- The *architectural decisions* in agentic systems — not the syntax.
- Where this design will break under load.
- Tradeoffs they'd defend in a TAF review.
- Production patterns disguised as a tutorial.

Calibrate accordingly. If a lesson feels like it could be in a beginner blog post, replace it.

---

## 10. Final Reminder

The lessons are the deliverable. The code is the scaffolding the lessons hang off. If you ever feel tempted to skip the lessons file "to keep momentum," that's the signal to slow down — the user has explicitly asked for them at every task boundary.

Begin with Task 0. Confirm the architecture summary first, then proceed.