"""Compares a live snapshot against the stored baseline.

Emits new / removed / changed tools, with the specific changed fields and an
old-vs-new text diff for descriptions. Severity is a deliberately simple
keyword + schema-widening heuristic in v0.1 — no scoring model.

Severity has four bands rather than the brief's two, because two could not
distinguish an annotation flip from a reworded sentence:

``critical``
    A behavioural annotation flipped (``destructiveHint``, ``readOnlyHint``,
    ``idempotentHint``, ``openWorldHint``). An agent may gate its behaviour on
    these, so the promise changing is worse than the prose changing.
``high``
    Content changed in a way that widens what the tool can do — trigger
    vocabulary entering or leaving a description, or a schema that now accepts
    calls the pinned contract rejected.
``medium``
    A pinned tool is gone. Always a real change to the capability surface, but
    not a trust escalation.
``informational``
    Everything else: cosmetic rewording, benign new tools, non-behavioural
    annotation keys.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .hasher import BEHAVIOURAL_ANNOTATIONS
from .store import IncomparableSnapshotsError

CRITICAL = "critical"
HIGH = "high"
MEDIUM = "medium"
INFORMATIONAL = "informational"

# Ascending. Index order is the comparison order.
SEVERITY_ORDER = (INFORMATIONAL, MEDIUM, HIGH, CRITICAL)

# Brief §2, Phase 2. Kept to exactly these five — resist growing this into a
# scoring model in v0.1.
TRIGGER_WORDS = frozenset({"execute", "delete", "send", "all", "admin"})

_WORD = re.compile(r"[a-z0-9]+")


def severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.index(severity)


def max_severity(severities) -> str:
    return max(severities, key=severity_rank, default=INFORMATIONAL)


@dataclass(frozen=True)
class DiffFinding:
    """One tool's drift. Mirrors §4's diff record, with two extensions.

    ``old_value``/``new_value`` are keyed by field name rather than being bare
    scalars: a tool can drift in description and schema at once, and collapsing
    that into one pair would lose which value belonged to which field.
    ``annotation_changes`` carries the per-hint direction, which is what makes a
    critical finding actionable instead of just "annotations changed".
    """

    tool_name: str
    change_type: str  # "new" | "removed" | "changed"
    severity: str
    changed_fields: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    old_value: dict[str, Any] = field(default_factory=dict)
    new_value: dict[str, Any] = field(default_factory=dict)
    annotation_changes: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "change_type": self.change_type,
            "severity": self.severity,
            "changed_fields": list(self.changed_fields),
            "reasons": list(self.reasons),
            "old_value": self.old_value,
            "new_value": self.new_value,
            "annotation_changes": [dict(change) for change in self.annotation_changes],
        }


@dataclass(frozen=True)
class DiffResult:
    server_id: str
    findings: tuple[DiffFinding, ...] = ()

    @property
    def max_severity(self) -> str:
        return max_severity(f.severity for f in self.findings)

    def at_or_above(self, threshold: str) -> tuple[DiffFinding, ...]:
        cutoff = severity_rank(threshold)
        return tuple(f for f in self.findings if severity_rank(f.severity) >= cutoff)

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "max_severity": self.max_severity,
            "counts": {
                severity: sum(1 for f in self.findings if f.severity == severity)
                for severity in reversed(SEVERITY_ORDER)
            },
            "findings": [f.to_dict() for f in self.findings],
        }


def _scannable(text: str) -> str:
    """Drop Unicode format characters before keyword scanning.

    ``de<ZWSP>lete`` reads as "delete" to a human and to an LLM, but tokenizes
    as two words. Hashing deliberately keeps zero-width characters (they *are*
    drift); the keyword scan deliberately ignores them, so the severity
    heuristic cannot be evaded by an invisible edit.
    """
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return set(_WORD.findall(_scannable(text).lower()))


def _triggered(*texts: str | None) -> set[str]:
    words: set[str] = set()
    for text in texts:
        words |= _tokens(text)
    return words & TRIGGER_WORDS


def _description_reasons(old: str | None, new: str | None) -> list[str]:
    """Trigger words entering *or leaving* a description are both notable.

    Compares word sets, so a trigger word that merely moves within an otherwise
    unchanged sentence does not fire. That is a known v0.1 gap: "delete one
    file" -> "delete all files" is caught by "all", not by "delete".
    """
    touched = (_tokens(old) ^ _tokens(new)) & TRIGGER_WORDS
    if not touched:
        return []
    listed = ", ".join(sorted(touched))
    return [f"description gained or lost trigger vocabulary: {listed}"]


def _schema_reasons(old: Any, new: Any) -> list[str]:
    """Detect the two widenings the brief calls out, on top-level properties.

    Nested schemas are not walked in v0.1; a widening buried in a sub-object
    still shows up as an informational schema change rather than being missed.
    """
    if not isinstance(old, dict) or not isinstance(new, dict):
        return []

    reasons = []

    relaxed = set(old.get("required") or []) - set(new.get("required") or [])
    for name in sorted(relaxed):
        reasons.append(f"parameter '{name}' is no longer required")

    old_props = set(old.get("properties") or {})
    new_props = set(new.get("properties") or {})
    for name in sorted(new_props - old_props):
        if _tokens(name) & TRIGGER_WORDS:
            reasons.append(f"new parameter '{name}' uses destructive vocabulary")

    return reasons


def _annotation_changes(old: Any, new: Any) -> list[dict[str, Any]]:
    old = old if isinstance(old, dict) else {}
    new = new if isinstance(new, dict) else {}

    return [
        {"key": key, "old": old.get(key), "new": new.get(key)}
        for key in sorted(set(old) | set(new))
        if old.get(key) != new.get(key)
    ]


def _diff_changed_tool(name: str, before: dict, after: dict) -> DiffFinding | None:
    changed_fields: list[str] = []
    reasons: list[str] = []
    old_value: dict[str, Any] = {}
    new_value: dict[str, Any] = {}
    severities: list[str] = [INFORMATIONAL]
    annotation_changes: list[dict[str, Any]] = []

    if before["description_hash"] != after["description_hash"]:
        changed_fields.append("description")
        old_value["description"] = before.get("raw_description")
        new_value["description"] = after.get("raw_description")

        field_reasons = _description_reasons(
            before.get("raw_description"), after.get("raw_description")
        )
        reasons += field_reasons
        severities.append(HIGH if field_reasons else INFORMATIONAL)

    if before["schema_hash"] != after["schema_hash"]:
        changed_fields.append("schema")
        old_value["schema"] = before.get("raw_schema")
        new_value["schema"] = after.get("raw_schema")

        field_reasons = _schema_reasons(before.get("raw_schema"), after.get("raw_schema"))
        reasons += field_reasons
        severities.append(HIGH if field_reasons else INFORMATIONAL)

    if before["annotations_hash"] != after["annotations_hash"]:
        changed_fields.append("annotations")
        old_value["annotations"] = before.get("raw_annotations")
        new_value["annotations"] = after.get("raw_annotations")

        annotation_changes = _annotation_changes(
            before.get("raw_annotations"), after.get("raw_annotations")
        )
        behavioural = [c for c in annotation_changes if c["key"] in BEHAVIOURAL_ANNOTATIONS]

        for change in behavioural:
            reasons.append(
                f"behavioural annotation '{change['key']}' changed "
                f"{change['old']!r} -> {change['new']!r}"
            )
        severities.append(CRITICAL if behavioural else INFORMATIONAL)

    if not changed_fields:
        return None

    return DiffFinding(
        tool_name=name,
        change_type="changed",
        severity=max_severity(severities),
        changed_fields=tuple(changed_fields),
        reasons=tuple(reasons),
        old_value=old_value,
        new_value=new_value,
        annotation_changes=tuple(annotation_changes),
    )


def diff_snapshots(baseline: dict[str, Any], current: dict[str, Any]) -> DiffResult:
    """Compare two snapshot documents field by field.

    Refuses to compare snapshots that are not actually comparable, rather than
    emitting a diff in which every tool looks changed.
    """
    if baseline.get("hash_model_version") != current.get("hash_model_version"):
        raise IncomparableSnapshotsError(
            f"baseline uses hash model v{baseline.get('hash_model_version')} but the current "
            f"scan uses v{current.get('hash_model_version')} — their hashes are not comparable. "
            f"Re-run `mcplock snapshot` to establish a fresh baseline."
        )

    if baseline.get("server_id") != current.get("server_id"):
        raise IncomparableSnapshotsError(
            f"refusing to diff a baseline for {baseline.get('server_id')!r} against a scan of "
            f"a different server, {current.get('server_id')!r}."
        )

    before_tools: dict[str, Any] = baseline.get("tools", {})
    after_tools: dict[str, Any] = current.get("tools", {})

    findings: list[DiffFinding] = []

    for name in sorted(set(before_tools) - set(after_tools)):
        record = before_tools[name]
        findings.append(
            DiffFinding(
                tool_name=name,
                change_type="removed",
                severity=MEDIUM,
                reasons=("a pinned tool is no longer offered by this server",),
                old_value={
                    "description": record.get("raw_description"),
                    "schema": record.get("raw_schema"),
                },
            )
        )

    for name in sorted(set(after_tools) - set(before_tools)):
        record = after_tools[name]
        triggered = _triggered(name, record.get("raw_description"))
        reasons = ["a tool that was not in the baseline is now offered"]
        if triggered:
            reasons.append(f"new tool uses trigger vocabulary: {', '.join(sorted(triggered))}")

        findings.append(
            DiffFinding(
                tool_name=name,
                change_type="new",
                severity=HIGH if triggered else INFORMATIONAL,
                reasons=tuple(reasons),
                new_value={
                    "description": record.get("raw_description"),
                    "schema": record.get("raw_schema"),
                },
            )
        )

    for name in sorted(set(before_tools) & set(after_tools)):
        finding = _diff_changed_tool(name, before_tools[name], after_tools[name])
        if finding:
            findings.append(finding)

    findings.sort(key=lambda f: (-severity_rank(f.severity), f.tool_name))

    return DiffResult(server_id=current.get("server_id", ""), findings=tuple(findings))
