"""Saving briefs to disk — pure helpers, importable without Streamlit (so they're unit-testable).

The Save button writes a self-contained markdown file (brief body + a Sources appendix) to
saved_briefs/ as `{slug}-{YYYYMMDD-HHMMSS}.md`. `now` is injectable for deterministic tests.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from agents.contracts import PublishedBrief

SAVED_DIR = Path(__file__).resolve().parent.parent / "saved_briefs"


def slugify(text: str) -> str:
    """Lowercase, hyphen-separated, filesystem-safe slug; never empty."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "brief"


def _sources_appendix(brief: PublishedBrief) -> str:
    if not brief.sources:
        return ""
    lines = [f"- [{s.title}]({s.url}) — {s.domain}" for s in brief.sources]
    return "\n\n## Sources\n\n" + "\n".join(lines) + "\n"


def save_brief(brief: PublishedBrief, directory: Path = SAVED_DIR, now: datetime | None = None) -> Path:
    """Write the brief (+ sources appendix) and return the file path."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    path = directory / f"{slugify(brief.title)}-{stamp}.md"
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(brief.markdown + _sources_appendix(brief), encoding="utf-8")
    return path
