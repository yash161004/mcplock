"""Drift-detection tests (brief §6, first bullet).

Written before `check` was trusted against any real server. The end-to-end
tests at the bottom inject a known drift into a live MCP server and assert the
CLI catches it; everything above them pins the severity model.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from drift_server import BASELINE, variant_tools

from mcplock import store
from mcplock.connector import ServerTarget
from mcplock.diff import CRITICAL, HIGH, INFORMATIONAL, MEDIUM, diff_snapshots
from mcplock.store import IncomparableSnapshotsError

DRIFT_SERVER = Path(__file__).parent / "drift_server.py"
SERVER_COMMAND = f'"{sys.executable}" "{DRIFT_SERVER}"'


def snapshot_for(variant: str, timestamp: str = "2026-01-01T00:00:00+00:00") -> dict:
    target = ServerTarget.from_command(SERVER_COMMAND)
    return store.build_snapshot(target, variant_tools(variant), timestamp=timestamp)


def finding_for(result, tool_name: str):
    return next(f for f in result.findings if f.tool_name == tool_name)


class TestNoDrift:
    def test_identical_snapshots_produce_nothing(self) -> None:
        result = diff_snapshots(snapshot_for("baseline"), snapshot_for("baseline"))
        assert result.findings == ()
        assert result.max_severity == INFORMATIONAL

    def test_rescanning_the_same_server_is_clean(self) -> None:
        """A later timestamp is not drift."""
        result = diff_snapshots(
            snapshot_for("baseline", timestamp="2026-01-01T00:00:00+00:00"),
            snapshot_for("baseline", timestamp="2026-09-09T00:00:00+00:00"),
        )
        assert result.findings == ()


class TestThreeDistinctSeverities:
    """A removal, a content change, and an annotation flip must not collapse."""

    def test_removed_tool(self) -> None:
        result = diff_snapshots(snapshot_for("baseline"), snapshot_for("removed"))
        finding = finding_for(result, "archive_note")

        assert finding.change_type == "removed"
        assert finding.severity == MEDIUM

    def test_content_change(self) -> None:
        result = diff_snapshots(snapshot_for("baseline"), snapshot_for("destructive_word"))
        finding = finding_for(result, "read_note")

        assert finding.change_type == "changed"
        assert finding.changed_fields == ("description",)
        assert finding.severity == HIGH

    def test_annotation_flip(self) -> None:
        result = diff_snapshots(snapshot_for("baseline"), snapshot_for("annotation_flip"))
        finding = finding_for(result, "write_note")

        assert finding.change_type == "changed"
        assert finding.changed_fields == ("annotations",)
        assert finding.severity == CRITICAL

    def test_all_three_severities_differ(self) -> None:
        severities = {
            finding_for(
                diff_snapshots(snapshot_for("baseline"), snapshot_for("removed")), "archive_note"
            ).severity,
            finding_for(
                diff_snapshots(snapshot_for("baseline"), snapshot_for("destructive_word")),
                "read_note",
            ).severity,
            finding_for(
                diff_snapshots(snapshot_for("baseline"), snapshot_for("annotation_flip")),
                "write_note",
            ).severity,
        }
        assert len(severities) == 3, f"severities collapsed: {severities}"


class TestSeverityHeuristic:
    def test_cosmetic_rewording_is_informational(self) -> None:
        result = diff_snapshots(snapshot_for("baseline"), snapshot_for("cosmetic"))
        finding = finding_for(result, "read_note")

        assert finding.changed_fields == ("description",)
        assert finding.severity == INFORMATIONAL

    def test_widened_schema_is_high(self) -> None:
        result = diff_snapshots(snapshot_for("baseline"), snapshot_for("schema_widened"))
        finding = finding_for(result, "write_note")

        assert finding.changed_fields == ("schema",)
        assert finding.severity == HIGH
        assert any("content" in reason for reason in finding.reasons)

    def test_new_benign_tool_is_informational(self) -> None:
        result = diff_snapshots(snapshot_for("baseline"), snapshot_for("added_benign"))
        finding = finding_for(result, "count_notes")

        assert finding.change_type == "new"
        assert finding.severity == INFORMATIONAL

    def test_new_destructive_tool_is_high(self) -> None:
        result = diff_snapshots(snapshot_for("baseline"), snapshot_for("added_destructive"))
        finding = finding_for(result, "run_command")

        assert finding.change_type == "new"
        assert finding.severity == HIGH

    def test_zero_width_space_does_not_hide_a_trigger_word(self) -> None:
        """The keyword scan must not be evadable by an invisible character."""
        drifted = variant_tools("zero_width_evasion")
        assert "​" in next(t for t in drifted if t["name"] == "read_note")["description"]

        result = diff_snapshots(snapshot_for("baseline"), snapshot_for("zero_width_evasion"))
        assert finding_for(result, "read_note").severity == HIGH

    def test_annotation_flip_reports_direction(self) -> None:
        result = diff_snapshots(snapshot_for("baseline"), snapshot_for("annotation_flip"))
        finding = finding_for(result, "write_note")

        assert finding.annotation_changes == (
            {"key": "destructiveHint", "old": True, "new": False},
        )

    def test_cosmetic_annotation_change_is_not_critical(self) -> None:
        """Only behavioural hints are critical; a stray non-hint key is not."""
        baseline = snapshot_for("baseline")
        tools = copy.deepcopy(BASELINE)
        next(t for t in tools if t["name"] == "write_note")["annotations"]["title"] = "Write Note"
        current = store.build_snapshot(ServerTarget.from_command(SERVER_COMMAND), tools)

        finding = finding_for(diff_snapshots(baseline, current), "write_note")
        assert finding.changed_fields == ("annotations",)
        assert finding.severity == INFORMATIONAL


class TestHashModelGuard:
    """Snapshots from different hash models must refuse to diff, not fake drift."""

    def test_diff_refuses_mismatched_hash_models(self) -> None:
        baseline = snapshot_for("baseline")
        current = snapshot_for("baseline")
        current["hash_model_version"] = baseline["hash_model_version"] + 1

        with pytest.raises(IncomparableSnapshotsError, match="not comparable"):
            diff_snapshots(baseline, current)

    def test_refusal_is_not_reported_as_drift(self) -> None:
        """The failure mode this guards against: every tool looking 'changed'."""
        baseline = snapshot_for("baseline")
        current = snapshot_for("baseline")
        current["hash_model_version"] = 99

        with pytest.raises(IncomparableSnapshotsError) as excinfo:
            diff_snapshots(baseline, current)

        assert "re-run" in str(excinfo.value).lower()

    def test_diff_refuses_mismatched_server_ids(self) -> None:
        baseline = snapshot_for("baseline")
        current = snapshot_for("baseline")
        current["server_id"] = "some-other-server"

        with pytest.raises(IncomparableSnapshotsError, match="different server"):
            diff_snapshots(baseline, current)


def run_cli(*args: str, home: Path, variant: str) -> subprocess.CompletedProcess[str]:
    """Drive the real CLI.

    The variant reaches the server through ``--env``, not through this process's
    environment: the MCP SDK deliberately inherits only a small safe allowlist
    when spawning a stdio server, so an inherited variable would never arrive.
    ``--env`` is not part of the server command, so server_id stays identical
    between the snapshot and the check.
    """
    env = {
        **os.environ,
        "MCPLOCK_HOME": str(home),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mcplock.cli",
            *args,
            "--env",
            f"MCPLOCK_DRIFT_VARIANT={variant}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )


@pytest.mark.e2e
class TestEndToEndDrift:
    """Brief §6: inject a known drift into a real server, confirm `check` catches it."""

    def test_check_passes_when_nothing_changed(self, tmp_path: Path) -> None:
        assert run_cli("snapshot", SERVER_COMMAND, home=tmp_path, variant="baseline").returncode == 0

        result = run_cli("check", SERVER_COMMAND, home=tmp_path, variant="baseline")
        assert result.returncode == 0, result.stderr

    def test_check_fails_on_injected_description_drift(self, tmp_path: Path) -> None:
        run_cli("snapshot", SERVER_COMMAND, home=tmp_path, variant="baseline")

        result = run_cli("check", SERVER_COMMAND, home=tmp_path, variant="destructive_word")

        assert result.returncode == 1, result.stdout + result.stderr
        assert "read_note" in result.stdout

    def test_check_fails_on_injected_annotation_flip(self, tmp_path: Path) -> None:
        run_cli("snapshot", SERVER_COMMAND, home=tmp_path, variant="baseline")

        result = run_cli("check", SERVER_COMMAND, home=tmp_path, variant="annotation_flip")

        assert result.returncode == 1, result.stdout + result.stderr
        assert "write_note" in result.stdout
        assert "destructiveHint" in result.stdout

    def test_check_writes_machine_readable_report(self, tmp_path: Path) -> None:
        run_cli("snapshot", SERVER_COMMAND, home=tmp_path, variant="baseline")
        report = tmp_path / "report.json"

        run_cli(
            "check",
            SERVER_COMMAND,
            "--json",
            str(report),
            home=tmp_path,
            variant="annotation_flip",
        )

        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["max_severity"] == CRITICAL
        finding = next(f for f in payload["findings"] if f["tool_name"] == "write_note")
        assert finding["annotation_changes"] == [
            {"key": "destructiveHint", "old": True, "new": False}
        ]

    def test_check_without_a_baseline_is_an_error_not_a_pass(self, tmp_path: Path) -> None:
        """Exit 0 here would silently green-light an unpinned server in CI."""
        result = run_cli("check", SERVER_COMMAND, home=tmp_path, variant="baseline")

        assert result.returncode == 2
        assert "snapshot" in (result.stdout + result.stderr)

    def test_removal_alone_does_not_fail_the_default_threshold(self, tmp_path: Path) -> None:
        run_cli("snapshot", SERVER_COMMAND, home=tmp_path, variant="baseline")

        result = run_cli("check", SERVER_COMMAND, home=tmp_path, variant="removed")
        assert result.returncode == 0, result.stdout

        stricter = run_cli(
            "check", SERVER_COMMAND, "--fail-on", MEDIUM, home=tmp_path, variant="removed"
        )
        assert stricter.returncode == 1, stricter.stdout
