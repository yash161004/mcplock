"""Snapshot store round-trip tests."""

from __future__ import annotations

import copy
import json

import pytest

from mcplock import store
from mcplock.connector import ServerTarget

COMMAND = "npx -y @modelcontextprotocol/server-filesystem ./data"


@pytest.fixture
def target() -> ServerTarget:
    return ServerTarget.from_command(COMMAND)


def test_snapshot_round_trips(target: ServerTarget, filesystem_tools: list[dict]) -> None:
    saved = store.save(store.build_snapshot(target, filesystem_tools))
    loaded = store.load(target.server_id)

    assert saved.exists()
    assert loaded is not None
    assert set(loaded["tools"]) == {t["name"] for t in filesystem_tools}
    assert loaded["connection"] == COMMAND


def test_load_returns_none_without_a_baseline(target: ServerTarget) -> None:
    assert store.load(target.server_id) is None


def test_record_keeps_raw_values_for_human_diffing(
    target: ServerTarget, filesystem_tools: list[dict]
) -> None:
    store.save(store.build_snapshot(target, filesystem_tools))
    record = store.load(target.server_id)["tools"]["write_file"]

    original = next(t for t in filesystem_tools if t["name"] == "write_file")
    assert record["raw_description"] == original["description"]
    assert record["raw_schema"] == original["inputSchema"]
    assert record["raw_annotations"] == original["annotations"]


def test_first_seen_survives_a_rescan(
    target: ServerTarget, filesystem_tools: list[dict]
) -> None:
    first = store.build_snapshot(target, filesystem_tools, timestamp="2026-01-01T00:00:00+00:00")
    store.save(first)

    second = store.build_snapshot(
        target,
        filesystem_tools,
        previous=store.load(target.server_id),
        timestamp="2026-06-01T00:00:00+00:00",
    )

    record = second["tools"]["write_file"]
    assert record["first_seen"] == "2026-01-01T00:00:00+00:00"
    assert record["last_verified"] == "2026-06-01T00:00:00+00:00"
    assert second["created_at"] == "2026-01-01T00:00:00+00:00"


def test_new_tool_gets_its_own_first_seen(
    target: ServerTarget, filesystem_tools: list[dict]
) -> None:
    store.save(store.build_snapshot(target, filesystem_tools, timestamp="2026-01-01T00:00:00+00:00"))

    added = copy.deepcopy(filesystem_tools)
    added.append({"name": "exfiltrate", "description": "new", "inputSchema": {"type": "object"}})

    second = store.build_snapshot(
        target, added, previous=store.load(target.server_id), timestamp="2026-06-01T00:00:00+00:00"
    )

    assert second["tools"]["exfiltrate"]["first_seen"] == "2026-06-01T00:00:00+00:00"
    assert second["tools"]["write_file"]["first_seen"] == "2026-01-01T00:00:00+00:00"


def test_refuses_a_baseline_from_a_different_hash_model(
    target: ServerTarget, filesystem_tools: list[dict]
) -> None:
    """A stale hash model must fail loudly, not silently report false drift."""
    path = store.save(store.build_snapshot(target, filesystem_tools))

    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["hash_model_version"] = store.HASH_MODEL_VERSION + 1
    path.write_text(json.dumps(stale), encoding="utf-8")

    with pytest.raises(ValueError, match="not comparable"):
        store.load(target.server_id)


def test_writes_into_isolated_home(target: ServerTarget, isolated_home) -> None:
    assert isolated_home in store.snapshot_path(target.server_id).parents
