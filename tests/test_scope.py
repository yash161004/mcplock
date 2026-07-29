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


class TestVerifiedFalsePositives:
    """Cases that fired against real servers and turned out to be wrong.

    Verified upstream on 2026-07-29. Every string here is the real description
    text, not an invented example. The constraint these encode: silence these
    *without* silencing `read_file` on the filesystem server, which was the one
    finding that survived verification (PR #4569).
    """

    def test_named_subsystem_is_a_boundary(self) -> None:
        """server-memory: 0 of 9 tools use filesystem phrasing, and none need to."""
        for description in (
            "Delete multiple entities and their associated relations from the knowledge graph",
            "Delete specific observations from entities in the knowledge graph",
            "Delete multiple relations from the knowledge graph",
            "Execute a SELECT query on the SQLite database",
        ):
            assert states_scope(description), f"named subsystem not recognised: {description!r}"

    def test_memory_server_style_tools_are_not_flagged(self) -> None:
        tools = [
            tool("delete_entities", "Delete multiple entities and their associated "
                                    "relations from the knowledge graph"),
            tool("create_entities", "Create multiple new entities in the knowledge graph"),
            tool("read_graph", "Read the entire knowledge graph"),
        ]

        assert find_scope_issues(tools) == []

    def test_drag_and_drop_is_not_deletion(self) -> None:
        """@playwright/mcp: 'drop' matched the gesture, not the SQL sense."""
        tools = [
            tool("browser_drag", "Perform drag and drop between two elements on the page"),
            tool("browser_drop", "Drop dragged data onto the target element on the page"),
            tool("browser_file_upload", "Upload one or more files to the page"),
        ]

        assert find_scope_issues(tools) == []

    def test_drop_is_still_destructive_with_a_qualifying_object(self) -> None:
        """The SQL sense must survive the fix, or the fix went too far."""
        findings = find_scope_issues([tool("drop_table", "Drop the users table permanently")])

        assert [f.tool_name for f in findings] == ["drop_table"]
        assert "drop" in findings[0].signals["destructive_verbs"]

    def test_generic_objects_are_not_boundaries(self) -> None:
        """'on the host' names no boundary — it is the opposite of one."""
        for description in (
            "Delete files on the host",
            "Execute a command in the system",
            "Remove data from the machine",
        ):
            assert not states_scope(description), f"wrongly treated as scoped: {description!r}"

    def test_the_surviving_finding_still_fires(self, filesystem_tools: list[dict]) -> None:
        """F-001 is the regression that matters: both fixes must leave it alone."""
        assert flagged(filesystem_tools) == {"read_file"}


class TestFindingShape:
    def test_record_matches_the_documented_shape(self, filesystem_tools: list[dict]) -> None:
        record = find_scope_issues(filesystem_tools)[0].to_dict()

        assert record["finding_type"] == "missing_scope"
        assert set(record) >= {"tool_name", "finding_type", "explanation"}

    def test_empty_server_reports_nothing(self) -> None:
        assert find_scope_issues([]) == []
