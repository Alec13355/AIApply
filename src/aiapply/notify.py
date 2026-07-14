from __future__ import annotations

from datetime import date
from pathlib import Path

from .paths import DATA_DIR
from .store import RunSummary


def format_summary(summary: RunSummary, run_date: date | None = None) -> str:
    run_date = run_date or date.today()
    lines = [f"# AIApply summary -- {run_date.isoformat()}", ""]

    lines.append(f"## Applied ({len(summary.applied)})")
    lines.extend(f"- {p.title} at {p.company} -- {p.url}" for p in summary.applied)
    if not summary.applied:
        lines.append("- none")
    lines.append("")

    lines.append(f"## Surfaced for your review ({len(summary.surfaced)})")
    for p in summary.surfaced:
        score = f" (fit {p.fit_score})" if p.fit_score is not None else ""
        lines.append(f"- {p.title} at {p.company}{score} -- {p.url}")
    if not summary.surfaced:
        lines.append("- none")
    lines.append("")

    lines.append(f"## Errors / needs manual follow-up ({len(summary.failed)})")
    for p, reason in summary.failed:
        lines.append(f"- {p.title} at {p.company} -- {reason} -- {p.url}")
    if not summary.failed:
        lines.append("- none")

    return "\n".join(lines)


def write_summary(summary: RunSummary, run_date: date | None = None) -> Path:
    run_date = run_date or date.today()
    out_dir = DATA_DIR / "summaries"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_date.isoformat()}.md"
    path.write_text(format_summary(summary, run_date))
    return path


def print_summary(summary: RunSummary, run_date: date | None = None) -> None:
    print(format_summary(summary, run_date))
