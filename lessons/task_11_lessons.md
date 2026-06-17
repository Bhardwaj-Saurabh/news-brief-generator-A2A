# Task 11 — Lessons

The final polish: making the brief readable and tweakable. The depth is in how typed structured
output pays off at the UI, what "trust signals" mean for AI content, and the regenerate-without-refetch
loop — plus the line between presentational and editorial polish.

## Lesson 1 — Render from the typed sections, not the markdown blob

**Concept.** The UI renders the brief by iterating `brief.sections` (`st.subheader(heading)` +
`st.markdown(body)`), not by dumping `brief.markdown` as one block. This is the payoff of the typed
`sections` field designed back in Task 6 — Task 11 is a *field read*, not a re-parse of prose.

**Why it matters.** Visual hierarchy (a header, then sub-headed sections) is what makes a brief scannable.
Getting it from a typed field is reliable and free; deriving it by regexing `##` out of markdown is the
brittle alternative the structured schema exists to avoid.

**In this codebase.** `app/streamlit_app.py`: the `for section in brief.sections: st.subheader(...)` loop;
contrast the earlier Task-10 version that rendered `st.markdown(brief.markdown)` wholesale.

**Pitfall or alternative.** Rendering the raw markdown blob still *works* (it has `#`/`##`), but you lose
the ability to style, reorder, or collapse sections independently. Typed structure is what makes those
affordances possible.

## Lesson 2 — Structured output is what lets the UI beat the wall-of-text failure mode

**Concept.** The classic LLM-UI failure is a monolithic wall of prose the eye can't navigate. Because the
Publisher emits *structured* output (title + sections + sources), the UI can impose hierarchy, group
sources, and add a copy affordance — none of which are possible over an opaque text blob.

**Why it matters.** "Better prompt" rarely fixes scannability; *structure* does. The decision to make the
LLM fill a schema (Task 9) is precisely what enables presentational quality here. Schema-first generation
is a UI investment, not just a parsing convenience.

**In this codebase.** The whole display block in `streamlit_app.py` is a consumer of
`PublishedBrief`'s typed fields; the sparing CSS only adjusts width/line-height, it doesn't manufacture
structure.

**Pitfall or alternative.** Asking the model for "nicely formatted markdown" and hoping is the
non-structured path — inconsistent and unstyleable. Structure first, then style.

## Lesson 3 — Trust signals make AI content credible: provenance, time, and sources

**Concept.** The brief shows a caption with region, audience, length, source count, and a UTC timestamp,
plus a sources list. These are *trust signals* — they let a reader judge freshness and provenance rather
than taking generated prose on faith.

**Why it matters.** AI-generated content without provenance invites either blind trust or blanket
distrust. Surfacing "as of HH:MM, N sources, this region/audience" turns an opaque artifact into an
auditable one — the UI-level complement to the Publisher deriving sources from real data (Task 9).

**In this codebase.** The `st.caption(f"Region … {len(brief.sources)} sources · generated …")` line and
the grouped sources expander in `streamlit_app.py`.

**Pitfall or alternative.** Burying or omitting timestamps/sources is the anti-pattern — it's how stale or
unsourced briefs get mistaken for authoritative. Trust signals are a feature, not chrome.

## Lesson 4 — Grouping sources by domain is another field read the schema pre-paid for

**Concept.** Sources are grouped with `defaultdict(list)` keyed on `src.domain` — a field stored at
creation (`Source.from_url` derived it in Task 6), not re-extracted from URLs at render time.

**Why it matters.** "Group sources by domain" (the AC) is a one-liner because the domain was computed once,
at the boundary, and carried on the typed model. Had `Source` stored only a URL, every render would
re-parse hosts — the re-parse tax the typed field exists to avoid.

**In this codebase.** `by_domain[src.domain].append(src)` in `streamlit_app.py`; `Source.domain` populated
by `Source.from_url` in `agents/contracts.py`.

**Pitfall or alternative.** Re-deriving the domain in the UI (`urlparse(str(src.url)).hostname`) would
work but duplicates logic and risks divergence from how the Publisher computed it. Compute once, read many.

## Lesson 5 — Regenerate-with-tweaks re-publishes on the cached report; it doesn't re-fetch

**Concept.** Length/audience changes affect *synthesis*, not the gathered data — so regenerate re-runs
only `publish` on the cached `ScoutReport` (via `report.model_copy(update={"request": new_request})`),
skipping the Scout entirely. The expensive, quota-burning fetch happens once.

**Why it matters.** This is the architectural payoff of separating gathering (Scout) from synthesis
(Publisher): a tweak loop costs one LLM call, not a full re-fetch of news/weather/markets/media. Live, a
"make it longer" went from 220→407 words by re-publishing the same report — no API quota spent.

**In this codebase.** `_republish` in `streamlit_app.py` does `report.model_copy(...)` then `publish`;
`_generate_full` (Scout+Publisher) runs only on the initial submit.

**Pitfall or alternative.** Re-running the whole pipeline on every tweak is the naive approach — slower,
costlier, and it would change the underlying facts between tweaks (a moving target). Re-synthesising the
same data keeps tweaks comparable.

## Lesson 6 — Additive contract evolution, demonstrated: adding `length` broke nothing

**Concept.** Supporting shorter/longer needed a new `BriefRequest.length` field. Because it's optional with
a default (`"medium"`), every existing message, test, and stored brief stayed valid — no migration, no
breakage. The Task-6 "design for additive evolution" principle paid off two tasks later.

**Why it matters.** This is the concrete proof that contract discipline compounds: a thoughtfully
optional-by-default schema absorbs new requirements as additions, not rewrites. The 50-test suite passed
unchanged except the new behaviour's own tests.

**In this codebase.** `length: Literal["short","medium","long"] = "medium"` in `BriefRequest`; the
Publisher's `_LENGTH_WORDS` map turns it into a word budget; `test_length_controls_word_budget` pins it.

**Pitfall or alternative.** A required `length` field would have broken every existing `BriefRequest(...)`
construction. Default-and-optional is what makes additive change safe.

## Lesson 7 — A form + regenerate loop fits a brief better than a chat UI

**Concept.** The interaction is "specify parameters → get an artifact → tweak it", not a conversation. So
the UI is a form plus discrete regenerate controls (shorter/longer/audience), not a chat box. The shape of
the UI matches the shape of the task.

**Why it matters.** Chat is the reflexive default for LLM apps, but it's wrong for a one-shot artifact with
a few structured knobs — it would force users to phrase tweaks as prose and re-read scrollback. A form
makes the levers explicit and the output stable.

**In this codebase.** `st.form` for generation + the "Regenerate with tweaks" buttons/selectbox in
`streamlit_app.py`; no chat component anywhere.

**Pitfall or alternative.** Where free-form iteration genuinely helps (open-ended editing), a chat or an
instruction box earns its place. Match the affordance to whether the user's intent is structured or open.

## Lesson 8 — CSS in Streamlit: a few lines for reading comfort, then stop

**Concept.** A small `<style>` block sets a comfortable max content width and line-height. That's worth
it — Streamlit's defaults run wide and dense for long-form reading. But it stays minimal; no layout
overrides or component restyling that would fight Streamlit's own rendering.

**Why it matters.** Long-form text needs a readable measure (line length) and leading; a 4-line CSS block
materially improves a brief's readability. Heavy CSS, by contrast, breaks on Streamlit upgrades and
fights the framework — high cost, low payoff.

**In this codebase.** The `st.markdown("<style>…</style>", unsafe_allow_html=True)` block (width +
line-height + heading margin) at the top of `streamlit_app.py`.

**Pitfall or alternative.** Reaching for `unsafe_allow_html` to build whole layouts is the smell — if you
need that much control, Streamlit may be the wrong tool. Keep CSS to typography-level tweaks.

## Lesson 9 — session_state turns the rerun model into a cheap iteration loop

**Concept.** Caching `report` and `brief` in `session_state` is what makes the tweak loop fast: regenerate
reads the cached report, save reads the cached brief, and neither recomputes the pipeline. The rerun model
plus session_state = an iteration loop without recomputation.

**Why it matters.** Without the cache, every regenerate or save click would re-run the script's generation
path (or lose the brief entirely). session_state is the difference between "tweak in 3s on cached data"
and "re-fetch everything on every click".

**In this codebase.** `_store(report, brief)` writes `session_state["report"/"brief"/"request"]`; the
display, regenerate, and save blocks all read from there.

**Pitfall or alternative.** `st.cache_data` caches pure-function results by input — wrong for a stateful,
side-effecting pipeline whose output you also mutate (regenerate). session_state is the right primitive for
"the current artifact".

## Lesson 10 — Presentational polish is not editorial polish; know what the UI can't fix

**Concept.** This task improves *presentation* — hierarchy, clickable grouped sources, copy, a tweak loop.
It does not fact-check, rewrite, or edit the brief's content; that's *editorial* work, and in this system
it's owned by the Publisher's prompt (and ultimately a human). A prettier layout cannot make a wrong brief
right.

**Why it matters.** Conflating the two leads to polishing a brief into looking authoritative while its
substance is unverified — the most dangerous failure mode for AI content. Presentation builds trust;
substance must earn it. Keeping the line clear stops the UI from laundering bad content as good.

**In this codebase.** `streamlit_app.py` only formats and re-requests; correctness lives upstream (the
Publisher's grounding in real data, derived sources, injection defence — Task 9).

**Pitfall or alternative.** The temptation is to "fix" content issues with UI band-aids (hide errors,
truncate awkward bits). The right move is to fix them at the source (the prompt, the data) and let the UI
present honestly — including showing when a section is thin because the data was.
