"""Ambiguity linting, tuned against both sides from the start.

A noisy linter trains people to ignore it, exactly as a false drift report
would. So the true negatives come first: the threshold has to earn its keep by
staying silent on pairs that are similar on the surface but obviously distinct,
before it is allowed to claim credit for the pairs it catches.

All of these run against the real captured filesystem server, not invented
fixtures.
"""

from __future__ import annotations

import pytest

from mcplock.lint.ambiguity import (
    DEFAULT_THRESHOLD,
    find_ambiguities,
    name_affinity,
    opposing,
    substitutable,
)


def by_name(tools: list[dict], name: str) -> dict:
    return next(t for t in tools if t["name"] == name)


def flagged_pairs(tools: list[dict]) -> set[frozenset[str]]:
    return {frozenset({f.tool_name, f.related_tool}) for f in find_ambiguities(tools)}


class TestTrueNegatives:
    """Written first. These must stay quiet or the linter is not worth running."""

    @pytest.mark.parametrize(
        "left, right, why",
        [
            ("read_file", "write_file", "same object, opposite direction"),
            ("read_text_file", "write_file", "same object, opposite direction"),
            ("write_file", "edit_file", "both mutate, different granularity"),
            ("read_text_file", "get_file_info", "content vs metadata"),
            ("list_directory", "directory_tree", "flat vs recursive"),
            ("write_file", "list_allowed_directories", "unrelated"),
            ("create_directory", "list_directory", "same object, different action"),
            ("move_file", "search_files", "unrelated"),
        ],
    )
    def test_distinct_pairs_are_not_flagged(
        self, filesystem_tools: list[dict], left: str, right: str, why: str
    ) -> None:
        assert frozenset({left, right}) not in flagged_pairs(filesystem_tools), (
            f"false positive on {left}/{right} — {why}"
        )

    def test_opposite_direction_is_vetoed_even_with_identical_wording(self) -> None:
        """The strongest false-positive case: same prose, opposite verb."""
        shared = "Operate on a note in the configured notes directory."
        schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }
        tools = [
            {"name": "read_note", "description": shared, "inputSchema": schema},
            {"name": "delete_note", "description": shared, "inputSchema": schema},
        ]

        assert find_ambiguities(tools) == []

    def test_incompatible_schemas_are_never_flagged(self) -> None:
        """Prose can be identical; if one call cannot satisfy both, stay quiet."""
        shared = "Store a note in the configured notes directory as text."
        tools = [
            {
                "name": "stash_note",
                "description": shared,
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "save_note",
                "description": shared,
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "body": {"type": "string"}},
                    "required": ["path", "body"],
                },
            },
        ]

        assert find_ambiguities(tools) == []

    def test_same_parameter_name_with_different_types_is_not_substitutable(self) -> None:
        left = {
            "name": "fetch_one",
            "inputSchema": {"properties": {"target": {"type": "string"}}, "required": ["target"]},
        }
        right = {
            "name": "fetch_many",
            "inputSchema": {"properties": {"target": {"type": "array"}}, "required": ["target"]},
        }

        assert not substitutable(left, right)

    def test_a_single_tool_server_reports_nothing(self, filesystem_tools: list[dict]) -> None:
        assert find_ambiguities(filesystem_tools[:1]) == []


class TestTruePositives:
    @pytest.mark.parametrize(
        "left, right",
        [
            ("read_file", "read_text_file"),
            ("read_file", "read_media_file"),
            ("read_text_file", "read_media_file"),
            ("list_directory", "list_directory_with_sizes"),
        ],
    )
    def test_confusable_pairs_are_flagged(
        self, filesystem_tools: list[dict], left: str, right: str
    ) -> None:
        assert frozenset({left, right}) in flagged_pairs(filesystem_tools)

    def test_the_read_cluster_is_reported_as_three_pairs(
        self, filesystem_tools: list[dict]
    ) -> None:
        """All three read_* tools take {path}; every pairing is confusable."""
        reads = {"read_file", "read_text_file", "read_media_file"}
        found = {pair for pair in flagged_pairs(filesystem_tools) if pair <= reads}

        assert len(found) == 3

    def test_finding_explains_itself(self, filesystem_tools: list[dict]) -> None:
        finding = next(
            f
            for f in find_ambiguities(filesystem_tools)
            if {f.tool_name, f.related_tool} == {"read_text_file", "read_media_file"}
        )

        assert finding.finding_type == "ambiguity"
        assert finding.signals["schema_substitutable"] is True
        assert "same arguments" in finding.explanation

    def test_finding_record_matches_the_documented_shape(
        self, filesystem_tools: list[dict]
    ) -> None:
        record = find_ambiguities(filesystem_tools)[0].to_dict()

        assert set(record) >= {
            "tool_name",
            "finding_type",
            "related_tool",
            "similarity_score",
            "explanation",
        }


class TestThresholdMargin:
    """The threshold must not sit on top of either class."""

    def test_a_real_gap_separates_the_two_classes(self, filesystem_tools: list[dict]) -> None:
        from mcplock.lint.ambiguity import tfidf_cosines

        documents = [f"{t['name']} {t.get('description') or ''}" for t in filesystem_tools]
        cosines = tfidf_cosines(documents)
        index = {t["name"]: i for i, t in enumerate(filesystem_tools)}

        def score(left: str, right: str) -> float:
            i, j = index[left], index[right]
            return max(name_affinity(left, right), cosines[i][j])

        ambiguous = [
            score("read_file", "read_text_file"),
            score("read_file", "read_media_file"),
            score("read_text_file", "read_media_file"),
            score("list_directory", "list_directory_with_sizes"),
        ]
        # Distinct pairs that survive the substitutability gate, so only the
        # score keeps them quiet — the ones that would break first.
        distinct = [
            score("list_directory", "directory_tree"),
            score("read_text_file", "get_file_info"),
            score("create_directory", "list_directory"),
            score("read_media_file", "get_file_info"),
        ]

        assert min(ambiguous) > max(distinct), (
            f"classes overlap: ambiguous min {min(ambiguous):.3f} "
            f"<= distinct max {max(distinct):.3f}"
        )
        assert max(distinct) < DEFAULT_THRESHOLD < min(ambiguous)


class TestSignals:
    def test_name_affinity_is_symmetric(self) -> None:
        assert name_affinity("read_file", "read_text_file") == name_affinity(
            "read_text_file", "read_file"
        )

    def test_identical_names_score_one(self) -> None:
        assert name_affinity("read_file", "read_file") == 1.0

    def test_opposing_detects_read_write(self) -> None:
        assert opposing("read_file", "write_file") == frozenset({"read", "write"})

    def test_opposing_ignores_a_shared_verb(self) -> None:
        assert opposing("read_file", "read_media_file") is None
