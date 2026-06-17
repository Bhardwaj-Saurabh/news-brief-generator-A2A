"""Tests for the Save helper (Task 10) — pure, no Streamlit, no servers."""

from __future__ import annotations

import re
from datetime import datetime

from app.storage import save_brief, slugify
from agents.contracts import BriefRequest, PublishedBrief, Section, Source


def _brief(title="Daily Brief: UK Economy"):
    return PublishedBrief(
        title=title,
        markdown=f"# {title}\n\n## World\n\nStuff happened.",
        sections=[Section(heading="World", body_markdown="Stuff happened.")],
        sources=[Source.from_url("BBC", "https://www.bbc.co.uk/news/1")],
        request=BriefRequest(topic="uk economy", region="UK"),
    )


def test_slugify():
    assert slugify("Daily Brief: UK Economy!") == "daily-brief-uk-economy"
    assert slugify("   ") == "brief"  # never empty
    assert slugify("AI & Markets") == "ai-markets"


def test_save_brief_filename_pattern_and_content(tmp_path):
    now = datetime(2026, 6, 18, 9, 30, 15)
    path = save_brief(_brief(), directory=tmp_path, now=now)

    # Pattern: {slug}-{YYYYMMDD-HHMMSS}.md
    assert path.parent == tmp_path
    assert re.fullmatch(r"daily-brief-uk-economy-20260618-093015\.md", path.name)
    assert path.exists()

    content = path.read_text(encoding="utf-8")
    assert content.startswith("# Daily Brief: UK Economy")
    assert "## Sources" in content  # appendix written
    assert "https://www.bbc.co.uk/news/1" in content


def test_save_brief_creates_directory(tmp_path):
    target = tmp_path / "nested" / "saved"
    path = save_brief(_brief(), directory=target, now=datetime(2026, 1, 1, 0, 0, 0))
    assert path.exists() and path.parent == target
