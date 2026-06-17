"""Streamlit UI — the orchestrator.

The UI is the only place that sequences the agents: it calls scout(request) to gather, then
publish(report) to synthesise. Scout and Publisher never call each other.

Async choice: Streamlit reruns the script top-to-bottom on each interaction, and there is no asyncio
loop running in that script thread, so `asyncio.run(...)` is safe here — no nest_asyncio needed. We
wrap the two awaits in one coroutine and a single asyncio.run, updating st.status between them so the
user sees Scout -> Publisher progress live (the page shows staged feedback, it doesn't freeze).

Prereq: start the three MCP servers first (world_data 8801, finance 8802, media 8803) and set .env.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make the project root importable when launched as `streamlit run app/streamlit_app.py`
# (Streamlit puts the script's own dir on sys.path, not the project root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from agents.contracts import BriefRequest  # noqa: E402
from agents.publisher import publish  # noqa: E402
from agents.regions import available_regions  # noqa: E402
from agents.scout import scout  # noqa: E402
from app.storage import save_brief  # noqa: E402

load_dotenv()

AUDIENCES = ["general", "executives", "investors", "students", "engineers"]

st.set_page_config(page_title="Daily Brief Generator", page_icon="📰", layout="centered")
st.title("📰 Daily News Brief Generator")
st.caption("MCP tools → A2A agents → one Azure LLM call. Start the three MCP servers before generating.")

with st.form("brief_form"):
    topic = st.text_input("Topic (optional)", placeholder="e.g. AI, energy, UK economy")
    col1, col2 = st.columns(2)
    region = col1.selectbox("Region", available_regions())
    audience = col2.selectbox("Audience", AUDIENCES)
    lookback = st.slider("News lookback (hours)", min_value=6, max_value=72, value=24, step=6)
    submitted = st.form_submit_button("Generate brief", type="primary")

if submitted:
    request = BriefRequest(
        topic=topic.strip() or None, region=region, audience=audience, lookback_hours=lookback
    )
    try:
        with st.status("Generating brief…", expanded=True) as status:

            async def _pipeline() -> object:
                status.write("🔭 **Scout** — gathering news, weather, markets, media…")
                report = await scout(request)  # step 1: gather
                status.write(
                    f"✓ {len(report.context.headlines)} headlines · "
                    f"{len(report.signals.quotes)} quotes · {len(report.signals.media_items)} media"
                )
                status.write("✍️ **Publisher** — writing the brief…")
                return await publish(report)  # step 2: synthesise

            brief = asyncio.run(_pipeline())
            status.update(label="Brief ready ✓", state="complete")
        # Persist across reruns so the Save button (which triggers a rerun) still has the brief.
        st.session_state["brief"] = brief
    except Exception as exc:  # surface any failure without crashing the app
        st.error(f"Generation failed: {exc}")

brief = st.session_state.get("brief")
if brief is not None:
    st.divider()
    st.markdown(brief.markdown)

    if brief.sources:
        with st.expander(f"Sources ({len(brief.sources)})"):
            for s in brief.sources:
                st.markdown(f"- [{s.title}]({s.url}) — `{s.domain}`")

    if st.button("💾 Save brief"):
        path = save_brief(brief)
        st.success(f"Saved to `{path}`")
