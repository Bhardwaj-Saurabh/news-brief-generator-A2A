# Task 0 — Lessons

Project setup, but with a real-world twist: the PRD's `openai` SDK was swapped for Azure AI
Foundry via the Microsoft Agent Framework (MAF), which turned a routine `uv add` into a
dependency-resolution and library-verification exercise. Most lessons below come from that.

## Lesson 1 — A lockfile is the pin; the manifest is the contract

**Concept.** The PRD's acceptance criterion is `pip install -r requirements.txt`, implying pinned
`==` lines. With `uv`, the division of labour is different: `pyproject.toml` holds *ranges* that
express intent (`pydantic>=2.11,<3`), and `uv.lock` holds the *exact* resolved graph (105 packages)
that guarantees byte-identical installs. You commit both. `uv sync` rebuilds from the lock, not the
ranges.

**Why it matters.** Pinning `==` in the manifest looks reproducible but rots: every transitive dep
floats, and you can't express "stable 2.x but never an alpha." The lockfile captures the full
transitive closure including hashes — actual reproducibility — while the manifest stays readable.

**In this codebase.** `pyproject.toml` `dependencies` (ranges) + the generated `uv.lock`. The README
documents `uv sync` rather than the PRD's `pip install -r requirements.txt`.

**Pitfall or alternative.** Don't hand-edit `uv.lock`. And don't commit only the manifest — without the
lock, `uv` is free to re-resolve and you've lost the reproducibility you thought you had.

## Lesson 2 — `--prerelease=allow` is a sticky, global resolution mode, not a per-package flag

**Concept.** Reaching for `uv add --prerelease=allow agent-framework-core …` to get a beta MAF package
also told the resolver it could prefer pre-releases for *everything*. It silently pulled
`pydantic==2.14.0a1` — an alpha — even though `agent-framework-core` only requires `pydantic>=2,<3`
and a stable 2.13.4 existed. Worse, the alpha persisted in the lock across subsequent `uv add`s
because uv minimises churn and won't downgrade an already-locked version without a reason.

**Why it matters.** A transitive alpha of your core validation library is a production landmine —
pydantic-core ABI and behaviour shift across pre-releases. The blast radius of one CLI flag was the
single most safety-critical dependency in the project.

**In this codebase.** Fixed by pinning `pydantic>=2.11,<3` in `pyproject.toml` and forcing
`uv lock --upgrade-package pydantic`, which moved `2.14.0a1 -> 2.13.4`.

**Pitfall or alternative.** Prefer `tool.uv.prerelease` scoping or an explicit pre-release pin on the
*one* package that needs it (`pkg==1.0.0rc6`) over a global `allow`. Always re-assert stable bounds on
critical libraries afterward, then verify the resolved version — don't trust the flag's reach.

## Lesson 3 — Meta-packages and `[all]` extras drag the whole provider matrix into your resolution

**Concept.** `uv add agent-framework` (the meta package) failed as *unsatisfiable*: it depends on
`agent-framework-core[all]`, whose `all` extra pulls every connector — `azure-ai-search`,
`azure-cosmos`, `bedrock`, `anthropic`, … — each with its own pre-release pins that mutually conflict
across supported Python versions. The fix was to install only the two provider packages actually
needed (`agent-framework-core`, `agent-framework-openai`).

**Why it matters.** "Install the framework" is rarely the right granularity for a framework that fans
out into dozens of optional integrations. The `[all]` extra optimises for demos, not for a tight,
auditable dependency graph — and a single conflicting connector you'll never use can make the entire
resolution fail.

**In this codebase.** `pyproject.toml` lists `agent-framework-core` + `agent-framework-openai`, not
`agent-framework`. Publisher-only adoption (Lesson 9) is what makes this narrow set sufficient.

**Pitfall or alternative.** Read the meta-package's `Requires-Dist` (here, `METADATA` showed the `all`
extra) before adding it. Compose the minimal provider set; reach for the meta only when you genuinely
want the kitchen sink.

## Lesson 4 — Verify the API surface against the *installed* version, never the docs alone

**Concept.** Microsoft Learn (the ~1.0 docs) showed `from agent_framework.azure import
AzureOpenAIChatClient` with an `api_key`. The installed `agent-framework-core==1.8.1` had reorganised:
`agent_framework.azure` is now a lazy re-export namespace for *connectors only* (Search/Cosmos/
DurableTask), and the Azure-OpenAI chat path moved to `agent_framework.openai.OpenAIChatClient` with
explicit Azure routing (`azure_endpoint` + `api_key` + `api_version`). Grepping the installed package's
`__init__.py` `_IMPORTS` map and `inspect.signature` on the real ctor settled it.

**Why it matters.** Fast-moving frameworks reorganise namespaces between minor versions; doc sites lag
or pin to an older line. Writing Task 9's Publisher against the doc's class name would have failed at
import time, after building on a false premise.

**In this codebase.** The verified ctor params (`model, api_key, azure_endpoint, api_version, …`) are
captured in `.env.example` and the CLAUDE.md LLM note; Task 9 will consume `AZURE_OPENAI_CHAT_DEPLOYMENT`
as the `model`.

**Pitfall or alternative.** The `agent-framework-azure==0.0.0` "package" is the trap here — a near-empty
stub that *looks* like the right dependency. Confirm a class actually imports (`uv run python -c "from … import X"`) before believing a package name; a 0.0.0 version is itself a red flag.

## Lesson 5 — Adapt acceptance criteria to a changed toolchain by preserving *intent*, not letter

**Concept.** Two PRD Task-0 criteria assumed the original stack: `pip install -r requirements.txt`
(no such file — we use `uv`) and `import … openai …` (swapped for MAF). Rather than fabricate a
`requirements.txt` or skip the check, each was mapped to its intent: "deps install reproducibly" →
`uv sync`; "the core stack imports" → import `agent_framework` + `OpenAIChatClient` (with `openai`
still present transitively).

**Why it matters.** A spec written before a decision shouldn't be followed off a cliff, but it also
shouldn't be silently ignored. Mapping criterion→intent keeps the safety check meaningful and leaves an
auditable trail of *why* the literal command changed.

**In this codebase.** The Task-0 acceptance run substitutes `uv run python -c "import fastmcp, httpx,
pydantic, streamlit, dotenv, agent_framework, openai"` for the PRD's `python -c "… openai …"`.

**Pitfall or alternative.** The opposite failure is "the PRD says pip, so I'll add a `requirements.txt`
too" — now you maintain two manifests that drift. Pick one source of truth (`pyproject.toml` + lock)
and reinterpret the criterion against it.

## Lesson 6 — Treat a pre-populated `.env.example` as the owner's interface, not a draft to overwrite

**Concept.** Mid-task the user populated `.env.example` with their org's Azure conventions
(`AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5.4-mini`, `AZURE_OPENAI_API_VERSION=2025-04-01-preview`, plus eval/
embedding deployments). The correct move was to *append* the missing upstream keys and ports and adopt
their variable names downstream — not impose my own `AZURE_OPENAI_DEPLOYMENT` scheme.

**Why it matters.** Env var names are a contract between the app and whatever provisions secrets (CI,
Key Vault, a teammate's shell). Renaming them to suit code is a silent breaking change to that contract;
the code is the cheap thing to bend.

**In this codebase.** `.env.example` keeps the user's Azure block verbatim; Task 9's Publisher will read
`AZURE_OPENAI_CHAT_DEPLOYMENT`. The four upstream keys + three ports + `LOG_LEVEL` were appended below.

**Pitfall or alternative.** Don't blow away a non-empty file with a `Write`; the tool correctly refused
until I re-read it. Read-then-Edit when a file may have changed under you — especially config the human
edits directly.

## Lesson 7 — "Keep the directory, ignore its contents" is a specific gitignore idiom

**Concept.** `saved_briefs/` must exist in a fresh clone (the Save button writes into it) but its output
must never be committed. Git doesn't track empty dirs, so the pattern is `saved_briefs/*` +
`!saved_briefs/.gitkeep` — ignore everything, re-include a single tracked sentinel.

**Why it matters.** The naive `saved_briefs/*.md` (what the PRD text suggested) only ignores markdown;
the day someone saves a `.json` or `.html` brief, it gets committed. Ignoring contents by default and
allow-listing the sentinel is forward-proof against output-format changes.

**In this codebase.** `.gitignore` `saved_briefs/*` + `!saved_briefs/.gitkeep`, with an empty
`saved_briefs/.gitkeep` committed (`git check-ignore` confirms `.gitkeep` is tracked while
`saved_briefs/test.md` is ignored).

**Pitfall or alternative.** `.gitkeep` is a convention, not a git feature — any tracked file works.
Avoid committing a real `.md` "example brief" as the keeper; it muddies the ignore rule and invites
exactly the format-specific leak above.

## Lesson 8 — The `__init__.py` decision is about import semantics, not ceremony

**Concept.** `servers/`, `agents/`, and `tests/` get `__init__.py` (regular packages); `app/`,
`lessons/`, `saved_briefs/` do not. Reasoning: `servers`/`agents` are imported as `servers.world_data_server`
/ `agents.contracts` and run with `python -m`, so explicit packages avoid the ambiguity of implicit
namespace packages. `tests/` gets one so pytest's rootdir/import resolution is unambiguous. `app/` is a
Streamlit *script* (`streamlit run app/streamlit_app.py`), never imported, so a package marker would be noise.

**Why it matters.** Implicit namespace packages (PEP 420) work until two directories accidentally merge
into one namespace, or `python -m` resolves the wrong thing. Being explicit where you do package imports
prevents a class of "works on my machine" import bugs.

**In this codebase.** `servers/__init__.py`, `agents/__init__.py` carry one-line docstrings stating each
layer's responsibility; `tests/__init__.py` is empty; `app/` has none.

**Pitfall or alternative.** Don't cargo-cult `__init__.py` into every folder (markdown dirs like
`lessons/` gain nothing). The modern alternative — a `src/` layout with packages declared in
`pyproject.toml` — is cleaner for distributables, but overkill for a flat learning project run via `-m`.

## Lesson 9 — Adopt a framework at the altitude that preserves your architecture's invariants

**Concept.** MAF offers agents, MCP clients, and a real A2A protocol — tempting to dissolve the PRD's
hand-rolled layers into it. But a MAF `Agent` is LLM-backed by definition, and the PRD's spine is
"the Publisher is the only LLM call" (Scout/Contextualist are deterministic). Full adoption would have
forced an LLM into every agent, breaking that invariant. The decision: adopt MAF *Publisher-only* — it
powers the one synthesis call; the FastMCP servers, Pydantic A2A contracts, and plain-async agents stay.

**Why it matters.** "The framework supports X" is not a reason to route X through it. Frameworks pull
your design toward their defaults (here, agent==LLM); choosing the integration altitude deliberately is
how you keep a framework as a tool rather than letting it become the architecture.

**In this codebase.** Recorded as an explicit deviation in the CLAUDE.md LLM note and `.env.example`
header; `agents/` will still hold hand-rolled contracts (Task 6) and non-LLM Scout/Contextualist
(Tasks 7–8). Only `agents/publisher.py` (Task 9) touches MAF.

**Pitfall or alternative.** The alternative — full MAF + real A2A over HTTP (agent cards,
`A2AExecutor`) — is the right call when agents are genuinely distributed and independently deployed.
For an in-process toy whose learning goal is the contracts themselves, it would hide the very thing
being taught.

## Lesson 10 — Every dependency is supply-chain surface; narrow deps shrink it

**Concept.** Adding `agent-framework-openai` + `streamlit` pulled ~90 transitive packages in one shot:
`openai`, `pandas`, `pyarrow`, `numpy`, `uvicorn`, `starlette`, `protobuf`, `pillow`, `pyjwt`, and more.
Each is code that runs in your process and a node in your audit/CVE surface. The narrow-provider choice
(Lesson 3) and a committed lockfile (Lesson 1) are what keep this auditable.

**Why it matters.** Transitive bloat is invisible until a CVE, a yanked release, or a licence audit
forces you to enumerate it. A 105-package closure for a "toy" is normal precisely because UI + LLM SDKs
are heavy — which is the argument for *seeing* the closure (lockfile) and minimising direct deps.

**In this codebase.** `uv.lock` is the full enumerated graph; `pyproject.toml` keeps only 7 direct deps.

**Pitfall or alternative.** For a service you actually ship, run `uv tree` / a vulnerability scan in CI
and consider whether Streamlit's transitive weight (pandas, pyarrow) belongs in the same environment as
your servers — splitting UI deps from server deps via dependency groups is the production move, flagged
but out of scope here.
