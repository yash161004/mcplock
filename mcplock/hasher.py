"""Stable SHA-256 hashing of normalized tool definitions.

Hash model (v0.1):

* ``content_hash`` — description + input schema. This is the "did the meaning
  of this tool change" hash, and it is what §4 of the brief calls the full hash.
* ``description_hash`` / ``schema_hash`` — per-field, so a diff can name which
  side moved rather than just reporting "changed".
* ``annotations_hash`` — **tracked separately and deliberately excluded from**
  ``content_hash``. ``destructiveHint``/``readOnlyHint`` are behavioural
  assertions an agent may gate on, so a flip is its own critical finding, not a
  wording change. Folding them in would make an annotation flip indistinguishable
  from a typo fix.

``title``, ``outputSchema``, and ``execution`` are not hashed in v0.1 — no
concrete drift scenario for them yet.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

from .normalize import NormalizedTool, canonical_json, normalize_tool

# Bumped when the hash construction changes, so old snapshots are not silently
# compared against hashes computed a different way.
HASH_MODEL_VERSION = 1

# Annotation keys carrying a behavioural promise. A change to any of these is
# critical; a change to a cosmetic annotation (e.g. `title`) is not.
BEHAVIOURAL_ANNOTATIONS = frozenset(
    {"destructiveHint", "readOnlyHint", "idempotentHint", "openWorldHint"}
)


@dataclass(frozen=True)
class ToolHashes:
    """Every hash computed for one tool."""

    name: str
    description_hash: str
    schema_hash: str
    annotations_hash: str
    content_hash: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_normalized(normalized: NormalizedTool) -> ToolHashes:
    """Hash an already-normalized tool.

    ``content_hash`` digests a canonical JSON *object* rather than concatenated
    strings, so the field boundary is unambiguous — no pair of description and
    schema values can be rearranged into the same input.
    """
    content = canonical_json(
        {
            "v": HASH_MODEL_VERSION,
            "description": normalized.description,
            "inputSchema": normalized.schema,
        }
    )

    return ToolHashes(
        name=normalized.name,
        description_hash=sha256_hex(normalized.description),
        schema_hash=sha256_hex(normalized.schema),
        annotations_hash=sha256_hex(normalized.annotations),
        content_hash=sha256_hex(content),
    )


def hash_tool(tool: dict) -> ToolHashes:
    """Normalize then hash a raw ``tools/list`` entry."""
    return hash_normalized(normalize_tool(tool))
