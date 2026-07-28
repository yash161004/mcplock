"""Local snapshot store — flat JSON, one file per server.

``~/.mcplock/snapshots/<server-id>.json``. No SQLite in v0.1; there are no
concurrent-access needs.

The store is the baseline a later ``check`` diffs against, so it keeps both the
hashes and the raw description/schema/annotations — the raw values are what make
a diff human-readable.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .connector import ServerTarget
from .hasher import HASH_MODEL_VERSION, hash_normalized
from .normalize import normalize_tools

SCHEMA_VERSION = 1


class IncomparableSnapshotsError(ValueError):
    """Two snapshots cannot be meaningfully diffed.

    Raised instead of returning a diff in which every tool looks changed —
    a false "everything drifted" report is worse than a hard failure, because
    it trains people to ignore the tool.
    """


def mcplock_home() -> Path:
    """Root for local state. ``MCPLOCK_HOME`` overrides it, which tests rely on."""
    override = os.environ.get("MCPLOCK_HOME")
    return Path(override) if override else Path.home() / ".mcplock"


def snapshots_dir() -> Path:
    return mcplock_home() / "snapshots"


def snapshot_path(server_id: str) -> Path:
    return snapshots_dir() / f"{server_id}.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_snapshot(
    target: ServerTarget,
    tools: list[dict[str, Any]],
    previous: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Turn a live tool list into a snapshot document.

    ``first_seen`` is carried over from ``previous`` for tools already known, so
    it keeps meaning "when mcplock first saw this tool" across re-snapshots.
    """
    timestamp = timestamp or now_iso()
    previous_tools = (previous or {}).get("tools", {})

    records: dict[str, Any] = {}
    for normalized, raw in zip(normalize_tools(tools), tools, strict=True):
        hashes = hash_normalized(normalized)
        prior = previous_tools.get(normalized.name, {})

        records[normalized.name] = {
            "tool_name": normalized.name,
            "description_hash": hashes.description_hash,
            "schema_hash": hashes.schema_hash,
            "annotations_hash": hashes.annotations_hash,
            "content_hash": hashes.content_hash,
            "raw_description": raw.get("description"),
            "raw_schema": raw.get("inputSchema"),
            "raw_annotations": raw.get("annotations"),
            "first_seen": prior.get("first_seen", timestamp),
            "last_verified": timestamp,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "hash_model_version": HASH_MODEL_VERSION,
        "server_id": target.server_id,
        "transport": target.transport,
        "connection": target.source,
        "created_at": (previous or {}).get("created_at", timestamp),
        "updated_at": timestamp,
        "tools": records,
    }


def load(server_id: str) -> dict[str, Any] | None:
    """Read a stored snapshot, or ``None`` if this server has no baseline yet."""
    path = snapshot_path(server_id)
    if not path.exists():
        return None

    snapshot = json.loads(path.read_text(encoding="utf-8"))

    stored_model = snapshot.get("hash_model_version")
    if stored_model != HASH_MODEL_VERSION:
        raise IncomparableSnapshotsError(
            f"{path} was written with hash model v{stored_model}, but this build uses "
            f"v{HASH_MODEL_VERSION}. Its hashes are not comparable — re-run `mcplock "
            f"snapshot` to establish a fresh baseline."
        )

    return snapshot


def save(snapshot: dict[str, Any]) -> Path:
    """Write a snapshot atomically, so an interrupted run cannot truncate a baseline."""
    path = snapshot_path(snapshot["server_id"])
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)

    return path
