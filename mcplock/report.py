"""Report generation.

Human-readable terminal output (rich, colour-coded by severity) plus
``report.json`` with a stable schema for CI consumption.

v0.1 renders enough for `check` to be usable and for CI to parse; the polished
terminal report is Phase 5.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from .diff import CRITICAL, HIGH, INFORMATIONAL, MEDIUM, DiffResult

SEVERITY_STYLE = {
    CRITICAL: "bold white on red",
    HIGH: "bold red",
    MEDIUM: "yellow",
    INFORMATIONAL: "dim",
}

CHANGE_GLYPH = {"new": "+", "removed": "-", "changed": "~"}


def render_diff(result: DiffResult, console: Console) -> None:
    """Print a drift report. Severity leads, because that is what gets acted on."""
    if not result.findings:
        console.print(f"[green]No drift[/green] against the pinned baseline for {result.server_id}")
        return

    console.print(f"Drift detected for [bold]{result.server_id}[/bold]\n")

    for finding in result.findings:
        style = SEVERITY_STYLE[finding.severity]
        glyph = CHANGE_GLYPH.get(finding.change_type, "?")

        console.print(
            f"[{style}]{finding.severity.upper():>13}[/] {glyph} "
            f"[bold]{finding.tool_name}[/bold] ({finding.change_type})"
        )

        if finding.changed_fields:
            console.print(f"{'':>15} fields: {', '.join(finding.changed_fields)}")

        for reason in finding.reasons:
            console.print(f"{'':>15} - {reason}")

        if "description" in finding.changed_fields:
            _render_description_change(finding, console)

        console.print()

    counts = result.to_dict()["counts"]
    summary = "  ".join(f"{severity}: {count}" for severity, count in counts.items() if count)
    console.print(f"[bold]{len(result.findings)} finding(s)[/bold] — {summary}")


def _render_description_change(finding, console: Console) -> None:
    """Show the old and new description text.

    Full word-level diffing lands in Phase 5; showing both texts is already
    enough to judge a finding by eye, which is what v0.1 needs.
    """
    old = finding.old_value.get("description")
    new = finding.new_value.get("description")

    console.print(f"{'':>15} [red]- {old!r}[/red]")
    console.print(f"{'':>15} [green]+ {new!r}[/green]")


def render_lint(findings: list, server_id: str, tool_count: int, console: Console) -> None:
    """Print lint findings grouped by type.

    Lint findings are judgment calls, not facts like a hash mismatch, so each one
    carries the signals behind it — a reader has to be able to disagree.
    """
    if not findings:
        console.print(
            f"[green]No ambiguity or scope findings[/green] across {tool_count} tools "
            f"on {server_id}"
        )
        return

    console.print(f"Lint findings for [bold]{server_id}[/bold] ({tool_count} tools)\n")

    for finding in findings:
        record = finding.to_dict()
        related = record.get("related_tool")
        heading = f"{record['tool_name']} / {related}" if related else record["tool_name"]
        score = record.get("similarity_score")
        suffix = f"  [dim]score {score:.2f}[/dim]" if score is not None else ""

        console.print(f"[yellow]{record['finding_type']:>14}[/yellow]  [bold]{heading}[/bold]{suffix}")
        console.print(f"{'':>16}{record['explanation']}")

        signals = ", ".join(f"{k}={v}" for k, v in (record.get("signals") or {}).items())
        if signals:
            console.print(f"{'':>16}[dim]{signals}[/dim]")
        console.print()

    console.print(f"[bold]{len(findings)} finding(s)[/bold] — review each before acting on it")


def lint_report_dict(findings: list, server_id: str, tool_count: int) -> dict:
    """The machine-readable lint report."""
    return {
        "server_id": server_id,
        "tool_count": tool_count,
        "counts": {
            finding_type: sum(1 for f in findings if f.finding_type == finding_type)
            for finding_type in ("ambiguity", "missing_scope")
        },
        "findings": [f.to_dict() for f in findings],
    }


def write_json(payload, path: Path) -> Path:
    """Write a machine-readable report CI consumes.

    Accepts a DiffResult or an already-built dict, so `check` and `lint` share
    one writer and one on-disk shape.
    """
    document = payload.to_dict() if isinstance(payload, DiffResult) else payload

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
