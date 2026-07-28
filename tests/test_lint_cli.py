"""End-to-end coverage of `mcplock lint` against a real MCP server."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import SERVER_COMMAND, run_cli


@pytest.mark.e2e
class TestLintCommand:
    def test_clean_server_reports_nothing(self, tmp_path: Path) -> None:
        """The drift server's baseline tools are scoped and mutually distinct."""
        result = run_cli("lint", SERVER_COMMAND, home=tmp_path, variant="baseline")

        assert result.returncode == 0, result.stderr
        assert "No ambiguity or scope findings" in result.stdout

    def test_needs_no_baseline(self, tmp_path: Path) -> None:
        """Unlike `check`, lint reads the live server only — nothing pinned."""
        result = run_cli("lint", SERVER_COMMAND, home=tmp_path, variant="baseline")

        assert result.returncode == 0
        assert not (tmp_path / "snapshots").exists()

    def test_reports_an_unscoped_destructive_tool(self, tmp_path: Path) -> None:
        result = run_cli("lint", SERVER_COMMAND, home=tmp_path, variant="added_destructive")

        assert result.returncode == 0, "findings alone must not fail the build"
        assert "run_command" in result.stdout
        assert "missing_scope" in result.stdout

    def test_strict_exits_non_zero_on_findings(self, tmp_path: Path) -> None:
        clean = run_cli("lint", SERVER_COMMAND, "--strict", home=tmp_path, variant="baseline")
        assert clean.returncode == 0

        dirty = run_cli(
            "lint", SERVER_COMMAND, "--strict", home=tmp_path, variant="added_destructive"
        )
        assert dirty.returncode == 1, dirty.stdout

    def test_writes_machine_readable_report(self, tmp_path: Path) -> None:
        report = tmp_path / "lint.json"

        run_cli(
            "lint",
            SERVER_COMMAND,
            "--json",
            str(report),
            home=tmp_path,
            variant="added_destructive",
        )

        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["tool_count"] == 4
        assert payload["counts"]["missing_scope"] == 1

        finding = next(f for f in payload["findings"] if f["tool_name"] == "run_command")
        assert finding["finding_type"] == "missing_scope"
        assert finding["signals"]["unbounded_markers"] == ["arbitrary", "host"]

    def test_threshold_controls_ambiguity_sensitivity(self, tmp_path: Path) -> None:
        """A threshold of 0 flags every substitutable pair; the default does not."""
        default = run_cli("lint", SERVER_COMMAND, home=tmp_path, variant="baseline")
        assert "No ambiguity or scope findings" in default.stdout

        loose = run_cli(
            "lint", SERVER_COMMAND, "--threshold", "0.0", home=tmp_path, variant="baseline"
        )
        # read_note and archive_note both take only {path}, so they survive the
        # substitutability gate and are separated purely by score.
        assert "read_note / archive_note" in loose.stdout
        assert "finding(s)" in loose.stdout
