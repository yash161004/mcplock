"""Scope linting, true negatives first.

The real filesystem server is the calibration set: 13 of its 14 tools state a
boundary, so a linter that flags any of those 13 is producing noise on a
well-written server — the fastest way to get itself ignored.
"""

from __future__ import annotations

import pytest
from drift_server import variant_tools

from mcplock.lint.scope import find_scope_issues, states_scope

SCOPED = "Only works within allowed directories."


def flagged(tools: list[dict]) -> set[str]:
    return {f.tool_name for f in find_scope_issues(tools)}


def tool(name: str, description: str, **schema) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": schema or {"type": "object", "properties": {"path": {"type": "string"}}},
    }


class TestTrueNegatives:
    def test_only_one_tool_is_flagged_on_the_real_server(
        self, filesystem_tools: list[dict]
    ) -> None:
        assert flagged(filesystem_tools) == {"read_file"}

    @pytest.mark.parametrize(
        "name",
        [
            "write_file",
            "edit_file",
            "move_file",
            "create_directory",
            "search_files",
            "read_text_file",
            "get_file_info",
        ],
    )
    def test_scoped_destructive_tools_are_not_flagged(
        self, filesystem_tools: list[dict], name: str
    ) -> None:
        """write_file overwrites without warning — but it says where it may do so."""
        assert name not in flagged(filesystem_tools)

    def test_the_boundary_reporting_tool_is_exempt(self, filesystem_tools: list[dict]) -> None:
        """list_allowed_directories has no boundary sentence because it is the boundary."""
        assert "list_allowed_directories" not in flagged(filesystem_tools)

    def test_a_benign_unscoped_tool_is_not_flagged_without_a_convention(self) -> None:
        """Two tools, neither scoped: no convention exists to depart from."""
        tools = [
            tool("count_notes", "Count the notes available to this server."),
            tool("ping", "Return a health check response."),
        ]

        assert find_scope_issues(tools) == []

    @pytest.mark.parametrize(
        "phrasing",
        [
            "Delete a note. Only works within allowed directories.",
            "Delete a note within the configured notes directory.",
            "Delete a note. Paths are relative to the workspace root.",
            "Delete a note. Access is restricted to the sandbox.",
            "Delete a note; the path must be within the project root.",
        ],
    )
    def test_boundary_phrasings_are_recognised(self, phrasing: str) -> None:
        assert states_scope(phrasing)


class TestTruePositives:
    def test_destructive_verb_without_a_boundary(self) -> None:
        tools = [
            tool("purge_notes", "Delete every note. This cannot be undone."),
            tool("read_note", f"Read a note. {SCOPED}"),
        ]

        findings = find_scope_issues(tools)
        assert [f.tool_name for f in findings] == ["purge_notes"]
        assert findings[0].signals["check"] == "unbounded_action"
        assert "delete" in findings[0].signals["destructive_verbs"]

    def test_unbounded_language_is_reported_alongside_the_verb(self) -> None:
        findings = find_scope_issues(variant_tools("added_destructive"))
        finding = next(f for f in findings if f.tool_name == "run_command")

        assert finding.signals["unbounded_markers"] == ["arbitrary", "host"]
        assert "arbitrary" in finding.explanation

    def test_convention_departure_is_detected(self, filesystem_tools: list[dict]) -> None:
        finding = next(f for f in find_scope_issues(filesystem_tools) if f.tool_name == "read_file")

        assert finding.signals["check"] == "convention_departure"
        assert finding.signals["server_tools_stating_scope"] == 13
        assert finding.signals["server_tool_count"] == 14

    def test_convention_finding_does_not_claim_a_vulnerability(
        self, filesystem_tools: list[dict]
    ) -> None:
        """The server may still enforce the boundary. Wording must say so."""
        finding = next(f for f in find_scope_issues(filesystem_tools) if f.tool_name == "read_file")

        assert "documentation gap" in finding.explanation
        assert "not proof" in finding.explanation

    def test_zero_width_characters_cannot_hide_a_destructive_verb(self) -> None:
        tools = [
            tool("purge_notes", "De​lete every note permanently."),
            tool("read_note", f"Read a note. {SCOPED}"),
        ]

        findings = find_scope_issues(tools)
        assert [f.tool_name for f in findings] == ["purge_notes"]

    def test_a_missing_description_is_flagged_when_the_server_has_a_convention(
        self, filesystem_tools: list[dict]
    ) -> None:
        tools = [*filesystem_tools, {"name": "mystery_tool", "inputSchema": {"type": "object"}}]

        assert "mystery_tool" in flagged(tools)


class TestFindingShape:
    def test_record_matches_the_documented_shape(self, filesystem_tools: list[dict]) -> None:
        record = find_scope_issues(filesystem_tools)[0].to_dict()

        assert record["finding_type"] == "missing_scope"
        assert set(record) >= {"tool_name", "finding_type", "explanation"}

    def test_empty_server_reports_nothing(self) -> None:
        assert find_scope_issues([]) == []
