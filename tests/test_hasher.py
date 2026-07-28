"""Hash model tests.

The load-bearing property: ``content_hash`` must move for any semantic change to
description or schema, and must *not* move for an annotation flip — annotations
are tracked by their own hash so the diff can raise them as a separate,
critical finding.
"""

from __future__ import annotations

import copy
import textwrap

import pytest

from mcplock.hasher import hash_tool
from mcplock.normalize import normalize_description, normalize_tool, normalize_tools


class TestContentHash:
    def test_is_stable_across_runs(self, write_file_tool: dict) -> None:
        assert hash_tool(write_file_tool) == hash_tool(copy.deepcopy(write_file_tool))

    def test_is_insensitive_to_key_order(self, write_file_tool: dict) -> None:
        reordered = dict(reversed(list(write_file_tool.items())))
        assert hash_tool(reordered).content_hash == hash_tool(write_file_tool).content_hash

    def test_catches_a_single_changed_word(self, write_file_tool: dict) -> None:
        tampered = copy.deepcopy(write_file_tool)
        tampered["description"] = tampered["description"].replace(
            "Only works within allowed directories.",
            "Only works within accessible directories.",
        )

        before, after = hash_tool(write_file_tool), hash_tool(tampered)
        assert after.description_hash != before.description_hash
        assert after.content_hash != before.content_hash
        assert after.schema_hash == before.schema_hash

    def test_ignores_reindented_description(self, write_file_tool: dict) -> None:
        rewrapped = copy.deepcopy(write_file_tool)
        # textwrap splits on whitespace only, so every word and mark survives.
        rewrapped["description"] = "\n    ".join(textwrap.wrap(rewrapped["description"], 30))

        # Same words, different wrapping — not drift.
        assert rewrapped["description"] != write_file_tool["description"]
        assert normalize_description(rewrapped["description"]) == normalize_description(
            write_file_tool["description"]
        )
        assert hash_tool(rewrapped).content_hash == hash_tool(write_file_tool).content_hash

    def test_catches_a_widened_schema(self, write_file_tool: dict) -> None:
        widened = copy.deepcopy(write_file_tool)
        widened["inputSchema"]["required"] = ["path"]  # "content" becomes optional

        before, after = hash_tool(write_file_tool), hash_tool(widened)
        assert after.schema_hash != before.schema_hash
        assert after.content_hash != before.content_hash
        assert after.description_hash == before.description_hash

    def test_distinguishes_absent_from_empty_description(self, write_file_tool: dict) -> None:
        absent = copy.deepcopy(write_file_tool)
        absent.pop("description")

        empty = copy.deepcopy(write_file_tool)
        empty["description"] = ""

        assert hash_tool(absent).description_hash != hash_tool(empty).description_hash

    def test_excluded_fields_do_not_move_any_hash(self, write_file_tool: dict) -> None:
        """title / outputSchema / execution are deliberately unhashed in v0.1."""
        noisy = copy.deepcopy(write_file_tool)
        noisy["title"] = "Totally Different Title"
        noisy["outputSchema"] = {"type": "object"}
        noisy["execution"] = {"taskSupport": "optional"}

        assert hash_tool(noisy) == hash_tool(write_file_tool)


class TestAnnotationTracking:
    """Annotations get their own hash and stay out of ``content_hash``."""

    @pytest.mark.parametrize(
        "hint, flipped",
        [
            ("destructiveHint", False),
            ("readOnlyHint", True),
            ("idempotentHint", False),
            ("openWorldHint", True),
        ],
    )
    def test_flip_moves_annotations_hash_only(
        self, write_file_tool: dict, hint: str, flipped: bool
    ) -> None:
        tampered = copy.deepcopy(write_file_tool)
        assert tampered["annotations"][hint] != flipped, "fixture drifted; pick a real flip"
        tampered["annotations"][hint] = flipped

        before, after = hash_tool(write_file_tool), hash_tool(tampered)

        assert after.annotations_hash != before.annotations_hash, "flip must be detectable"
        assert after.content_hash == before.content_hash, (
            "an annotation flip must stay distinguishable from a wording/schema change"
        )
        assert after.description_hash == before.description_hash
        assert after.schema_hash == before.schema_hash

    def test_dropping_annotations_entirely_is_detectable(self, write_file_tool: dict) -> None:
        stripped = copy.deepcopy(write_file_tool)
        stripped.pop("annotations")

        after = hash_tool(stripped)
        assert after.annotations_hash != hash_tool(write_file_tool).annotations_hash
        assert after.content_hash == hash_tool(write_file_tool).content_hash

    def test_absent_annotations_differ_from_empty_annotations(
        self, write_file_tool: dict
    ) -> None:
        absent = copy.deepcopy(write_file_tool)
        absent.pop("annotations")

        empty = copy.deepcopy(write_file_tool)
        empty["annotations"] = {}

        assert hash_tool(absent).annotations_hash != hash_tool(empty).annotations_hash


class TestNormalizeGuards:
    def test_rejects_a_tool_without_a_name(self) -> None:
        with pytest.raises(ValueError, match="no usable name"):
            normalize_tool({"description": "x", "inputSchema": {}})

    def test_rejects_duplicate_tool_names(self, write_file_tool: dict) -> None:
        with pytest.raises(ValueError, match="duplicate tool names"):
            normalize_tools([write_file_tool, copy.deepcopy(write_file_tool)])

    def test_real_server_tools_all_hash_uniquely(self, filesystem_tools: list[dict]) -> None:
        hashes = {hash_tool(t).content_hash for t in filesystem_tools}
        assert len(hashes) == len(filesystem_tools)
