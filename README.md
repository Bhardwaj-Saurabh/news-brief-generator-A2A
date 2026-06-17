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

## Running

> Run instructions are filled in as the tasks are built (servers in Tasks 2–5, UI in Task 10).

```bash
# MCP servers (one per terminal, once implemented)
uv run python -m servers.world_data_server     # :8801
uv run python -m servers.finance_server         # :8802
uv run python -m servers.media_server           # :8803

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
