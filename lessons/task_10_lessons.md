# Task 10 — Lessons

The UI, which is also the orchestrator. The depth is in Streamlit's rerun model and how it bites
async, staged feedback, surviving reruns, and keeping testable logic out of the UI shell.

## Lesson 1 — Streamlit reruns the whole script on every interaction; internalise that first

**Concept.** Streamlit has no callbacks-and-render-tree model; it re-executes `streamlit_app.py`
top-to-bottom on every widget interaction. Widgets return their *current* value each run; local
variables are recomputed from scratch. Every design decision here follows from that one fact.

**Why it matters.** Most Streamlit bugs (vanishing state, re-running expensive work, "why did my brief
disappear when I clicked Save") are really misunderstandings of the rerun model. Once you see the script
as "runs fully, every click", the patterns (session_state, status, guards) become obvious.

**In this codebase.** `app/streamlit_app.py` is linear top-to-bottom; the `if submitted:` and
`if brief is not None:` guards decide what runs on a given rerun.

**Pitfall or alternative.** Treating it like a long-lived event-driven app (expecting variables to persist
between clicks) is the trap. State persists only in `st.session_state`; everything else is recomputed.

## Lesson 2 — `asyncio.run` is the right async pattern here, and why

**Concept.** Our agents are async, the UI is sync. There are three ways to bridge in Streamlit:
`asyncio.run(coro)` per interaction, `nest_asyncio` (patch a loop to allow re-entry), or a background
thread/executor. We use `asyncio.run` because each rerun is synchronous and there's no event loop
already running in the script thread, so a fresh loop per generation is clean and correct.

**Why it matters.** `asyncio.run` raises if a loop is already running — the reason people reach for
`nest_asyncio`. Knowing *why* it's safe here (Streamlit's script thread has no loop) means you don't
cargo-cult `nest_asyncio` and its monkeypatching risks.

**In this codebase.** `app/streamlit_app.py`: one `asyncio.run(_pipeline())` wrapping both awaits; the
module docstring documents the choice (PRD asked for it explicitly).

**Pitfall or alternative.** `nest_asyncio` is needed only if something already runs a loop in your thread
(e.g. Jupyter). A background-thread executor is the move when you want the UI thread free for true
non-blocking — overkill for a single synchronous generate click.

## Lesson 3 — "Doesn't freeze" in Streamlit means visible progress, not a non-blocking thread

**Concept.** `asyncio.run` *blocks* the script run for the full ~4s generation — and that's fine. The
"UI does not freeze" requirement is satisfied by `st.status`, which renders staged updates live: writing
"Scout…" then "Publisher…" between the awaits shows progress as it happens.

**Why it matters.** Newcomers try to make the call truly non-blocking (threads, async UI) to avoid
"freezing". In Streamlit the pragmatic answer is staged feedback via `st.status`/`st.spinner` — the user
sees motion and stage names, which is what "not frozen" means to them.

**In this codebase.** The `with st.status(...) as status:` block with `status.write(...)` between
`scout` and `publish`, then `status.update(state="complete")`.

**Pitfall or alternative.** A bare blocking call with no feedback *looks* frozen even if it's working —
the cardinal sin on a 30s LLM call. Always pair a blocking generation with `st.status`/`st.spinner`.

## Lesson 4 — Persist results in `session_state` so they survive the next rerun

**Concept.** After generation, the brief is stored in `st.session_state["brief"]`. The Save button
triggers a fresh rerun in which `submitted` is False — without session_state, the brief (a local
variable from the previous run) would be gone and Save would have nothing to write.

**Why it matters.** This is the rerun model biting in practice: any data that must outlive the
interaction that produced it has to live in session_state. The render block reads from session_state, not
from the generation block's locals.

**In this codebase.** `st.session_state["brief"] = brief` after generation; the display + Save block reads
`st.session_state.get("brief")`.

**Pitfall or alternative.** Regenerating on every rerun (no caching) would re-hit all APIs and the LLM
each time you click Save — slow and costly. session_state is the cache; `st.cache_data` is the heavier
alternative for pure-function results (not a fit for a stateful, side-effecting pipeline).

## Lesson 5 — The UI is the orchestrator; the sibling agents never call each other

**Concept.** The Streamlit layer is where `scout(request)` then `publish(report)` are sequenced. The
Scout and Publisher are siblings: neither imports or calls the other. The orchestration boundary
deliberately lives in the presentation layer.

**Why it matters.** Putting the sequence in the UI keeps the agents independently usable and testable, and
matches the A2A design (the Publisher is a pure synthesiser that never sees a `BriefRequest` or the
Scout). The "who calls whom" decision is architectural, not incidental to the UI.

**In this codebase.** `_pipeline()` in `streamlit_app.py` is the only place the two are chained.

**Pitfall or alternative.** Having the Publisher call the Scout (a chain) would couple them and break the
sibling model; having a separate "coordinator agent" is the alternative when orchestration grows beyond a
two-step sequence (and when you move off Streamlit).

## Lesson 6 — Slugify filenames: filesystem-safe, deterministic, never empty

**Concept.** `slugify` lowercases, collapses non-alphanumerics to single hyphens, strips edges, and
falls back to `"brief"` if the result is empty. The save path is `{slug}-{YYYYMMDD-HHMMSS}.md`.

**Why it matters.** Brief titles are LLM-generated free text — they can contain `/`, `:`, emoji, or be
empty. Writing those straight into a path invites path traversal, OS-illegal filenames, and collisions.
Slugging is input sanitisation at the filesystem boundary.

**In this codebase.** `app/storage.py` `slugify`; `test_slugify` pins the empty-string and punctuation
cases.

**Pitfall or alternative.** Trusting the title as a filename is the bug; over-aggressive slugging (dropping
all non-ASCII) loses information for non-Latin titles — a transliteration step is the richer fix, out of
scope here.

## Lesson 7 — Timestamped saves are append-only and testable via an injectable clock

**Concept.** Each save writes a new `{slug}-{timestamp}.md`; nothing is overwritten. `save_brief` takes
an optional `now` so tests assert the exact filename deterministically instead of fighting the wall clock.

**Why it matters.** Append-only saves mean re-saving never clobbers a previous brief (a mild idempotency:
same brief saved twice in the same second would collide, but across seconds it's safe history). The
injectable clock is the standard trick for testing time-dependent output.

**In this codebase.** `save_brief(brief, directory, now)`; `test_save_brief_filename_pattern…` passes a
fixed `datetime` and regex-matches the name.

**Pitfall or alternative.** Hardcoding `datetime.now()` makes the function untestable and non-reproducible.
For true idempotency (same brief → same file), you'd key on a content hash instead of a timestamp.

## Lesson 8 — Keep pure logic out of the UI shell so it stays unit-testable

**Concept.** The save logic lives in `app/storage.py` (pure functions, no Streamlit), tested directly;
`streamlit_app.py` is the thin UI shell, verified by booting it. UI code that calls `st.*` can't be
meaningfully unit-tested (it needs the Streamlit runtime), so the logic worth testing is extracted out.

**Why it matters.** If `save_brief`/`slugify` lived inside the Streamlit script, you couldn't test the
filename contract without spinning up Streamlit. Separating "logic" from "shell" is what makes a UI app
testable at all.

**In this codebase.** `app/storage.py` (tested in `tests/test_storage.py`) vs `app/streamlit_app.py`
(boot-verified headless).

**Pitfall or alternative.** Streamlit's `AppTest` framework can exercise the shell itself; useful for
widget-flow tests, but heavier than testing extracted pure functions. Extract first, `AppTest` second.

## Lesson 9 — `streamlit run` puts the script's dir on the path, not the project root

**Concept.** Launching `streamlit run app/streamlit_app.py` adds `app/` to `sys.path`, so `from agents...`
fails out of the box. The fix is one line at the top: insert the project root
(`Path(__file__).resolve().parent.parent`) into `sys.path` before importing project packages.

**Why it matters.** This is a real, common Streamlit footgun — code that imports fine under pytest breaks
under `streamlit run` because of the different path root. Knowing the cause saves an afternoon of
`ModuleNotFoundError`.

**In this codebase.** The `sys.path.insert(0, ...parent.parent)` at the top of `streamlit_app.py`, with
`# noqa: E402` on the subsequent imports.

**Pitfall or alternative.** Cleaner long-term: install the project as a package (`uv pip install -e .`)
so imports resolve regardless of cwd — but the sys.path shim keeps the toy runnable with zero install.

## Lesson 10 — A synchronous, request-bound UI is fine for one user and wrong at scale

**Concept.** Generation blocks the script run for the length of the slowest upstream plus the LLM call
(~4s here, potentially 30s+). For a single user that's acceptable with staged feedback. At real traffic
it isn't: each session blocks its own run, there's no queue, no shared cache, and free-tier quotas would
throttle fast.

**Why it matters.** This is the architecture's deliberate ceiling. The honest next step is a job queue +
async workers + a poll/stream for results, decoupling "request" from "compute" — which Streamlit's
rerun model is not built for.

**In this codebase.** The blocking `asyncio.run(_pipeline())` in `streamlit_app.py`; flagged here and in
the PRD/architecture "where this breaks under load" notes.

**Pitfall or alternative.** Bolting threads onto Streamlit to fake concurrency adds complexity without
fixing the real limits (no durable queue, no cross-session cache). When you outgrow this, you outgrow
request-bound Streamlit, not just `asyncio.run`.
