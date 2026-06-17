# Task 1 — Lessons

Provisioning five credentials and writing a presence-checker. The interesting material is in the
*handling* — precedence, scoping, config-vs-secret, and quota economics — not in clicking "create key".

## Lesson 1 — A credential checker reports presence, never value, and returns an exit code

**Concept.** `scripts/check_keys.py` reads `os.environ.get(name, "").strip()` and prints only
`present`/`MISSING` — it never echoes the value — then returns `0`/`1` so it doubles as a CI gate.
A non-empty check (`bool(value.strip())`) treats a blank `KEY=` as missing, which matches the
`.env.example` placeholder reality.

**Why it matters.** A "did my env load?" helper is exactly the kind of script that ends up pasted into
an issue or a CI log. If it printed values, that paste is a leak. The exit code lets the same script
fail a pipeline before the app ever boots with half its config.

**In this codebase.** `scripts/check_keys.py`: the `print(f"  {'✅' if present else '❌'} …")` line and
`raise SystemExit(main())`.

**Pitfall or alternative.** The tempting "debug" version prints the first 4 chars of each key to
"prove it's the right one" — don't; a prefix still narrows a brute force and violates the no-value rule.
If you must confirm identity, print a salted hash, not a substring.

## Lesson 2 — `load_dotenv` does not override the real environment, and that precedence is a feature

**Concept.** `python-dotenv`'s `load_dotenv()` only sets variables that are *not already present* in
`os.environ`. So an exported shell var or a CI secret wins over the `.env` file. This is why the AC2
test (removing `FINNHUB_API_KEY` from `.env`) correctly reported it missing — nothing in the process
env was masking the file.

**Why it matters.** It lets the same code run unchanged across local dev (values from `.env`) and
production (values injected by the platform / Key Vault, no file present). But it also means a stale
exported var in your shell can silently shadow your `.env` and you'll chase a ghost.

**In this codebase.** `scripts/check_keys.py` calls `load_dotenv(env_path)` then reads `os.environ` —
relying on this precedence so the checker is meaningful in CI where there is no `.env`.

**Pitfall or alternative.** If you actually want the file to win (rare, usually a smell), there's
`load_dotenv(override=True)` — but reaching for it is often a sign you have a leaked export you should
clear instead.

## Lesson 3 — Distinguish config from secret, even when you check them the same way

**Concept.** The Azure block has both: `AZURE_OPENAI_API_KEY` is a secret; `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_CHAT_DEPLOYMENT`, and `AZURE_OPENAI_API_VERSION` are *required config* but not sensitive.
The checker treats them uniformly (presence only) for simplicity, but their *handling* differs: config
can be logged and committed in examples; the key cannot.

**Why it matters.** Conflating the two leads to either over-protecting config (so nobody can debug which
endpoint you hit) or under-protecting secrets. The endpoint and deployment name are things you *want*
visible in logs to diagnose "wrong region / wrong model" issues.

**In this codebase.** `.env.example` shows real-ish non-secret defaults (`AZURE_OPENAI_API_VERSION=2025-04-01-preview`,
`AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5.4-mini`) while leaving `AZURE_OPENAI_API_KEY=` blank — config is
illustrated, the secret is not.

**Pitfall or alternative.** A common mistake is putting the endpoint in code "because it's not secret"
and the key in `.env` — now rotating regions means a code change. Keep both in env; just classify them
for logging and review purposes.

## Lesson 4 — Scope keys to the smallest surface; the provider defaults are too broad

**Concept.** A fresh Google API key can call *every* enabled API on the project; a NewsAPI dev key is
implicitly restricted to localhost. Least privilege means narrowing the key to exactly what it needs —
restrict the YouTube key to "YouTube Data API v3" only — so a leak can't be replayed against other
services on the same project.

**Why it matters.** Keys leak (git history, logs, a screenshare). An unscoped Google key is a master
key to whatever else you enable later; a scoped one is a single-purpose token with a capped blast radius.

**In this codebase.** Documented in the README "API keys" notes ("Restrict keys where possible … to
limit blast radius if leaked"); not enforceable in code — it's a console setting.

**Pitfall or alternative.** Scoping is invisible until the incident, so it gets skipped. The stronger
alternative for the Azure side is **managed identity / `DefaultAzureCredential`** (no key at all) —
out of scope here since we chose key auth, but it's the real least-privilege answer (Lesson 10).

## Lesson 5 — Rate-limit tiers are an architectural input, not an afterthought

**Concept.** Free tiers differ in shape, not just size: NewsAPI is 100 req/day, Finnhub/OpenWeather are
per-minute, and YouTube uses a **weighted unit budget** — 10,000 units/day where `search.list` costs
100 and `videos.list` costs 1. That 100× asymmetry means a "search everything" design burns the day's
budget in ~100 calls, while trending-by-id is nearly free.

**Why it matters.** The quota model dictates tool design downstream. Task 5's `search_media` is the
expensive path and `get_trending` the cheap one — knowing this now prevents designing a chatty search
loop that dies at noon.

**In this codebase.** Captured in the README quota column; it will drive the Media MCP server design in
Task 5 (batch / prefer id-based lookups over repeated search).

**Pitfall or alternative.** Treating "free tier" as one number. Always read the *per-operation* cost.
The alternative when quota is tight is a short-TTL cache keyed on query (the PRD flags caching as the
first thing to add under load).

## Lesson 6 — Free tiers fail softly; you must detect throttling, not assume success

**Concept.** Paid tiers return clean `429`s; free tiers often degrade — stale data, truncated results,
or a `200` with an error body. NewsAPI's free `everything` is delayed 24h; YouTube returns `403
quotaExceeded`; OpenWeather may just rate-limit silently at the minute boundary.

**Why it matters.** Code that only checks HTTP status will treat a degraded `200` as fresh truth and
publish stale or empty briefs without warning. The "errors are data" rule (Task 2+) exists precisely so
these soft failures surface as typed entries instead of silent gaps.

**In this codebase.** Not yet implemented — flagged here as the contract the MCP servers must honour
(Tasks 2–5: quota/throttle responses become structured errors, never crashes or silent empties).

**Pitfall or alternative.** Assuming `response.raise_for_status()` is enough. You also need to validate
the *body* shape (Pydantic at the boundary) and inspect provider-specific error fields.

## Lesson 7 — `os.environ.get` for a flat script; Pydantic Settings when config grows types and validation

**Concept.** The checker uses raw `os.environ.get` because it only needs presence of flat strings. The
moment config needs typing (ports as `int`), defaults, cross-field validation (endpoint *and* key both
set), or one import-safe object passed around, `pydantic-settings` `BaseSettings` earns its place.

**Why it matters.** Flat `os.environ` reads scattered through agents become an untyped, untested mess —
a port read as a string, a missing var discovered at request time. A settings model validates once at
startup and fails loudly with field-level errors.

**In this codebase.** `scripts/check_keys.py` deliberately stays flat (`os.environ.get`); the heavier
`pydantic-settings` (already transitively installed) is the natural home for server/agent config if it
grows beyond presence checks.

**Pitfall or alternative.** Over-engineering the toy: a `BaseSettings` for a 5-line presence script is
ceremony. The line to cross is when config is *read in more than one place* or needs a non-string type.

## Lesson 8 — Put cost guardrails in before the first paid LLM call, not after the bill

**Concept.** Azure OpenAI is pay-per-token. Guardrails to set *before* Task 9 ever runs: a cheap
deployment (`gpt-5.4-mini`), a `max_tokens` cap on the Publisher call, `temperature` low for
determinism, and an Azure cost alert / budget on the resource.

**Why it matters.** The single LLM call is the only metered operation in the system. A runaway prompt
(e.g. dumping an unbounded `ScoutReport` into context) or a retry loop without a cap can multiply spend
silently. The first defence is a small model + token ceiling, not a dashboard you check weekly.

**In this codebase.** `.env.example` already points the deployment at a `-mini` model; the `max_tokens`
/ length-budget enforcement lands in `agents/publisher.py` (Task 9).

**Pitfall or alternative.** Relying on the daily quota of the *free* providers to bound cost — the LLM
has no free quota. The alternative guardrail is a hard token budget computed from the report size before
the call, refusing to send if it would blow the ceiling.

## Lesson 9 — `.env.example` is the rotation contract; rotating should never need a code change

**Concept.** Because every credential is read by name from env and the names are documented in
`.env.example`, rotating a key is "paste new value into `.env`, restart" — no code touched. The example
file is the canonical list of *what* must exist; the real `.env` holds the *current* values.

**Why it matters.** Keys must rotate (suspected leak, scheduled hygiene, employee offboarding). If a key
is hard-coded or its name undocumented, rotation becomes a code hunt and a redeploy. Name-based env
reads make rotation a config operation.

**In this codebase.** `.env.example` enumerates all eight required vars; `scripts/check_keys.py` validates
the same set post-rotation in one command.

**Pitfall or alternative.** The example drifting from reality — a new var added to code but not to
`.env.example` — so a fresh clone or a rotation misses it. Keep them in lockstep (the checker's
`REQUIRED` dict is effectively a third copy; in a larger app, generate one from another).

## Lesson 10 — A `.env` file is fine for one local dev; name the line where a secrets manager wins

**Concept.** For a single developer on one machine, `.env` + gitignore is a reasonable, honest choice.
The line where it stops being enough: more than one consumer of the secret, any shared/CI environment,
audit/rotation requirements, or a blast radius you can't accept. Then it's Azure Key Vault / managed
identity (and `DefaultAzureCredential` instead of a key string).

**Why it matters.** Cargo-culting a secrets manager into a toy is wasted complexity; pretending `.env`
scales to a team is how keys end up in a shared Slack. Knowing the threshold is the actual skill.

**In this codebase.** We deliberately chose `.env` + key auth (recorded in `.env.example` and CLAUDE.md).
The README notes managed identity as the production upgrade for the Azure side.

**Pitfall or alternative.** The half-measure — a secrets manager that still hands you a long-lived key
you stick in `.env` — gains little. The real upgrade is *keyless* auth (workload/managed identity) so
there is no secret at rest to leak or rotate.
