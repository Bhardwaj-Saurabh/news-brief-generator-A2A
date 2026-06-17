# News Brief Generator (MCP + A2A)

A learning project: a multi-agent daily news brief generator. It pulls live data from four
domains (news, weather, finance, media) through **MCP servers** over HTTP, coordinates three
agents via an explicit **A2A message-passing protocol**, synthesises an article with a single
LLM call, and renders it in **Streamlit**.

See [docs/PRD.md](docs/PRD.md) for the task-by-task build plan and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for how the pieces fit together.

## Architecture at a glance

```
Streamlit UI → Publisher agent → Scout agent → { Contextualist agent, Finance MCP, Media MCP }
                                                  └→ World Data MCP
```

- **MCP servers** (`servers/`) — stateless wrappers over one upstream API each, over HTTP:
  World Data :8801 (news + weather), Finance :8802, Media :8803.
- **Agents** (`agents/`) — Contextualist (news + weather), Scout (fan-out aggregator),
  Publisher (the only LLM call).
- **LLM** — Azure AI Foundry via the **Microsoft Agent Framework** (`agent-framework-openai`),
  used only by the Publisher.

## Setup

This project uses [`uv`](https://docs.astral.sh/uv/) (Python 3.12, pinned via `.python-version`).

```bash
uv sync                       # install dependencies from the lockfile
cp .env.example .env          # then fill in your real keys (see Task 1)
```

Required secrets live in `.env` (never committed). The `.env.example` template lists every key:
the four upstream API keys (NewsAPI, OpenWeatherMap, Finnhub, YouTube), the Azure OpenAI
settings for the Publisher, and the three MCP server ports.

After filling in `.env`, verify everything is wired up (this prints presence only, never values):

```bash
uv run python scripts/check_keys.py
```

## API keys — where to get each

All five are free or use an existing subscription. Set each in `.env` (copy from `.env.example`).

| Service | `.env` variable(s) | Where to get it | Free tier | Approval |
|---|---|---|---|---|
| **NewsAPI.org** | `NEWSAPI_KEY` | [newsapi.org/register](https://newsapi.org/register) | 100 req/day; **dev key is localhost-only** and `everything` results are delayed 24h | Instant |
| **OpenWeatherMap** | `OPENWEATHER_API_KEY` | [openweathermap.org/api](https://openweathermap.org/api) → *API keys* tab | 60 calls/min, 1M/month (Current Weather) | Instant, but the key can take **up to ~2h to activate** |
| **Finnhub** | `FINNHUB_API_KEY` | [finnhub.io/register](https://finnhub.io/register) | 60 calls/min; quotes + company news on free | Instant |
| **YouTube Data API v3** | `YOUTUBE_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) → create project → *enable* "YouTube Data API v3" → *Credentials* → API key | 10,000 units/day (`search.list` = 100 units, `videos.list` = 1) | Instant |
| **Azure OpenAI** (Publisher LLM) | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION` | [Azure AI Foundry](https://ai.azure.com/) / Azure portal: create an Azure OpenAI resource, deploy a chat model, copy *Keys & Endpoint* + deployment name | Pay-per-token (uses your Azure subscription) | Generally available; deployment is immediate |

Notes:
- **Never print or commit key values.** `.env` is gitignored; `scripts/check_keys.py` reports presence only.
- **Restrict keys where possible** (e.g. restrict the YouTube key to the YouTube Data API) to limit blast radius if leaked.
- The free NewsAPI dev key works for local development only — fine for this project, not for deployment.

## Running

> Run instructions are filled in as the tasks are built (servers in Tasks 2–5, UI in Task 10).

```bash
# MCP servers (one per terminal)
uv run python -m servers.world_data_server     # :8801  tools: get_top_headlines, get_current_weather
uv run python -m servers.finance_server         # :8802  (Task 4)
uv run python -m servers.media_server           # :8803  (Task 5)

# Streamlit UI (once implemented)
uv run streamlit run app/streamlit_app.py

# Tests
uv run pytest tests/
```

## Project layout

| Path | Purpose |
|---|---|
| `servers/` | FastMCP tool servers (one per domain) |
| `agents/` | A2A contracts, MCP client, and the three agents |
| `app/` | Streamlit UI |
| `lessons/` | Per-task lesson files (the deliverable of each task) |
| `tests/` | Smoke tests |
| `saved_briefs/` | Output of the UI "Save" button (contents gitignored) |
