"""Canonicalizes tool definitions before hashing.

Rules (Phase 1): sort object keys, collapse incidental whitespace, but never
touch semantic content — a single changed word must change the hash.

Two deliberate restraints, both chosen so the failure direction is a false
positive (a noisy diff) rather than a false negative (missed drift):

* **Array order is preserved.** ``required: ["path", "content"]`` is a set
  semantically, so sorting it would be safe, but ``oneOf`` order is not, and
  telling them apart needs a JSON Schema model we do not have in v0.1. A server
  that reorders an array produces an informational diff; nothing is hidden.
* **Whitespace is collapsed only in the top-level description.** Inside the
  schema, string values stay byte-exact — collapsing runs of spaces would
  corrupt a ``pattern`` or ``const`` where whitespace is significant.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

_WORD = re.compile(r"[a-z0-9]+")


def scannable_text(text: str) -> str:
    """Drop Unicode format characters before any text analysis.

    ``de<ZWSP>lete`` reads as "delete" to a human and to an LLM, but tokenizes
    as two words. Hashing deliberately keeps zero-width characters — they *are*
    drift — while every heuristic that reads meaning ignores them, so neither
    the severity scan nor the linters can be evaded by an invisible edit.
    """
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def word_tokens(text: str | None) -> list[str]:
    """Lowercase word tokens, with format characters stripped first."""
    if not text:
        return []
    return _WORD.findall(scannable_text(text).lower())


@dataclass(frozen=True)
class NormalizedTool:
    """A tool definition reduced to the canonical strings that get hashed.

    Each field is already a canonical JSON string, so hashing is just an
    encode-and-digest — no further ordering decisions live in the hasher.
    """

    name: str
    description: str  # canonical JSON: a string, or null when absent
    schema: str  # canonical JSON of inputSchema
    annotations: str  # canonical JSON of annotations, or null when absent


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, no incidental separators, UTF-8 safe."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def normalize_description(text: str | None) -> str | None:
    """Collapse incidental whitespace without touching wording.

    Reindenting or rewrapping a description is not drift; changing a word is.
    ``None`` is preserved rather than becoming ``""`` — a tool that loses its
    description entirely is a different event from one that had none.

    ``str.split()`` splits on Unicode whitespace, so a non-breaking space is
    folded like a plain one. Zero-width characters are *not* whitespace and are
    deliberately left in place: they change the hash, which surfaces them as
    drift instead of quietly normalizing away an invisible edit.
    """
    if text is None:
        return None
    return " ".join(text.split())


def normalize_tool(tool: dict[str, Any]) -> NormalizedTool:
    """Reduce a raw ``tools/list`` entry to its canonical hashable form.

    Only ``name``, ``description``, ``inputSchema``, and ``annotations`` are
    considered. ``title``, ``outputSchema``, and ``execution`` are intentionally
    excluded from hashing in v0.1 — no concrete drift scenario for them yet.
    """
    name = tool.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"tool definition has no usable name: {tool!r}")

    return NormalizedTool(
        name=name,
        description=canonical_json(normalize_description(tool.get("description"))),
        schema=canonical_json(tool.get("inputSchema")),
        annotations=canonical_json(tool.get("annotations")),
    )


def normalize_tools(tools: list[dict[str, Any]]) -> list[NormalizedTool]:
    """Normalize a whole tool list, rejecting duplicate names.

    Snapshots are keyed by tool name, so a server advertising the same name
    twice would silently lose one — that is worth failing loudly on.
    """
    normalized = [normalize_tool(tool) for tool in tools]

    counts = Counter(t.name for t in normalized)
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"server advertises duplicate tool names: {', '.join(duplicates)}")

    return normalized
