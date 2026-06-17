"""Streamlit UI — the orchestrator.

The UI is the only place that sequences the agents: scout(request) to gather, then publish(report)
to synthesise. Scout and Publisher never call each other. Regenerate-with-tweaks re-runs ONLY
publish on the cached ScoutReport (length/audience change the synthesis, not the gathered data) —
faster and cheaper than re-fetching.

Async choice: Streamlit reruns the script top-to-bottom on each interaction with no asyncio loop in
that thread, so `asyncio.run(...)` is safe (no nest_asyncio). st.status shows Scout->Publisher
progress live so the page never looks frozen.

Prereq: start the three MCP servers (8801/8802/8803) and set .env before generating.
"""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

# Make the project root importable under `streamlit run app/streamlit_app.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from agents.contracts import BriefRequest, PublishedBrief, ScoutReport  # noqa: E402
from agents.publisher import publish  # noqa: E402
from agents.regions import available_regions  # noqa: E402
from agents.scout import scout  # noqa: E402
from app.storage import save_brief  # noqa: E402

load_dotenv()

AUDIENCES = ["general", "executives", "investors", "students", "engineers"]
LENGTHS = ["short", "medium", "long"]

st.set_page_config(page_title="Daily Brief Generator", page_icon="📰", layout="centered")

# Sparing CSS: comfortable reading width + line height, a touch more heading air.
st.markdown(
    """
    <style>
      .block-container { max-width: 820px; }
      [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { line-height: 1.65; }
      [data-testid="stMarkdownContainer"] h2 { margin-top: 0.4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📰 Daily News Brief Generator")
st.caption("MCP tools → A2A agents → one Azure LLM call. Start the three MCP servers before generating.")


def _store(report: ScoutReport, brief: PublishedBrief) -> None:
    st.session_state["report"] = report
    st.session_state["brief"] = brief
    st.session_state["request"] = report.request


def _generate_full(request: BriefRequest) -> tuple[ScoutReport, PublishedBrief]:
    """Full pipeline: gather (Scout) then synthesise (Publisher), with live progress."""
    with st.status("Generating brief…", expanded=True) as status:

        async def _pipeline():
            status.write("🔭 **Scout** — gathering news, weather, markets, media…")
            report = await scout(request)
            status.write(
                f"✓ {len(report.context.headlines)} headlines · "
                f"{len(report.signals.quotes)} quotes · {len(report.signals.media_items)} media"
            )
            status.write("✍️ **Publisher** — writing the brief…")
            return report, await publish(report)

        report, brief = asyncio.run(_pipeline())
        status.update(label="Brief ready ✓", state="complete")
    return report, brief


def _republish(report: ScoutReport, new_request: BriefRequest) -> tuple[ScoutReport, PublishedBrief]:
    """Re-synthesise from the SAME gathered data with a tweaked request (no re-fetch)."""
    new_report = report.model_copy(update={"request": new_request})
    with st.status("Rewriting brief…", expanded=True) as status:
        status.write("✍️ **Publisher** — rewriting with your tweaks (same gathered data)…")
        brief = asyncio.run(publish(new_report))
        status.update(label="Brief updated ✓", state="complete")
    return new_report, brief


# --- Generation form -------------------------------------------------------------------------
with st.form("brief_form"):
    topic = st.text_input("Topic (optional)", placeholder="e.g. AI, energy, UK economy")
    col1, col2, col3 = st.columns(3)
    region = col1.selectbox("Region", available_regions())
    audience = col2.selectbox("Audience", AUDIENCES)
    length = col3.selectbox("Length", LENGTHS, index=1)
    lookback = st.slider("News lookback (hours)", min_value=6, max_value=72, value=24, step=6)
    submitted = st.form_submit_button("Generate brief", type="primary")

if submitted:
    request = BriefRequest(
        topic=topic.strip() or None, region=region, audience=audience, length=length, lookback_hours=lookback
    )
    try:
        report, brief = _generate_full(request)
        _store(report, brief)
    except Exception as exc:
        st.error(f"Generation failed: {exc}")


# --- Display + readability polish ------------------------------------------------------------
brief: PublishedBrief | None = st.session_state.get("brief")
report: ScoutReport | None = st.session_state.get("report")

if brief is not None and report is not None:
    st.divider()

    # Title + trust signals (region, audience, length, source count, timestamp, model).
    st.markdown(f"# {brief.title}")
    req = brief.request
    st.caption(
        f"Region **{req.region}** · audience **{req.audience}** · length **{req.length}** · "
        f"{len(brief.sources)} sources · generated {brief.generated_at:%Y-%m-%d %H:%M UTC}"
    )

    # Render from the typed sections (a field read, not a re-parse of markdown) for clear hierarchy.
    for section in brief.sections:
        st.subheader(section.heading)
        st.markdown(section.body_markdown)

    # Sources, grouped by domain, clickable.
    if brief.sources:
        by_domain: dict[str, list] = defaultdict(list)
        for src in brief.sources:
            by_domain[src.domain].append(src)
        with st.expander(f"📎 Sources ({len(brief.sources)}) — grouped by domain"):
            for domain in sorted(by_domain):
                st.markdown(f"**{domain}**")
                for src in by_domain[domain]:
                    st.markdown(f"- [{src.title}]({src.url})")

    # Copy to clipboard: st.code ships a built-in copy button.
    with st.expander("📋 Copy markdown"):
        st.code(brief.markdown, language="markdown")

    # --- Regenerate with tweaks (re-publishes on the cached report) ---
    st.divider()
    st.subheader("🔄 Regenerate with tweaks")
    st.caption("Re-writes from the same gathered data — keeps your topic and region.")

    qc1, qc2, _ = st.columns(3)
    shorter = qc1.button("✂️ Shorter", use_container_width=True)
    longer = qc2.button("➕ Longer", use_container_width=True)

    new_audience = st.selectbox(
        "Audience", AUDIENCES, index=AUDIENCES.index(req.audience) if req.audience in AUDIENCES else 0
    )
    regen_audience = st.button("Regenerate for this audience")

    new_request: BriefRequest | None = None
    idx = LENGTHS.index(req.length)
    if shorter:
        new_request = req.model_copy(update={"length": LENGTHS[max(0, idx - 1)]})
    elif longer:
        new_request = req.model_copy(update={"length": LENGTHS[min(len(LENGTHS) - 1, idx + 1)]})
    elif regen_audience and new_audience != req.audience:
        new_request = req.model_copy(update={"audience": new_audience})

    if new_request is not None:
        try:
            new_report, new_brief = _republish(report, new_request)
            _store(new_report, new_brief)
            st.rerun()  # refresh the display with the updated brief
        except Exception as exc:
            st.error(f"Regeneration failed: {exc}")

    # Save (timestamped file under saved_briefs/).
    st.divider()
    if st.button("💾 Save brief"):
        path = save_brief(brief)
        st.success(f"Saved to `{path}`")
