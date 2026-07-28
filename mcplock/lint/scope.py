"""Missing scope / boundary heuristics.

Does a tool state *what* it operates on (path, repo, resource), or does it
describe a destructive verb unboundedly? Keyword/regex pass — surfaces
candidates for manual verification, not a verdict.

Two checks, because the interesting real-world cases split in two:

``unbounded_action``
    The brief's rule: a destructive verb with no boundary language anywhere in
    the description. Strengthened when the description also uses an explicitly
    unbounded quantifier ("arbitrary", "anywhere", "any file on the host").

``convention_departure``
    A tool that omits a boundary statement *the rest of its own server makes*.
    On its own a missing sentence proves nothing; against twelve sibling tools
    that all end "Only works within allowed directories", it is a strong signal
    that a boundary was dropped rather than never intended. This is what catches
    a deprecated alias whose scope sentence was lost in the rewrite.

Neither check inspects behaviour. A tool can enforce a boundary perfectly and
still fail these — the finding is that the *description* does not tell the agent
the boundary exists, which is the information the agent actually reasons over.
Report them as documentation gaps, never as vulnerabilities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..normalize import scannable_text, word_tokens

# Verbs implying an action with consequences beyond returning data.
DESTRUCTIVE_VERBS = frozenset(
    """delete remove destroy drop purge truncate erase wipe overwrite write
    modify update rename move execute run spawn invoke send post publish
    upload transfer grant revoke kill terminate""".split()
)

# Language that explicitly widens scope rather than narrowing it.
UNBOUNDED_MARKERS = frozenset(
    """any arbitrary anywhere everything anything unrestricted unlimited global
    entire whole host system""".split()
)

# Phrases that state a boundary. Deliberately broad: a false "this tool is
# scoped" is a missed finding, but a false "unscoped" is noise that gets the
# linter ignored, and noise is the failure mode that matters here.
SCOPE_PATTERNS = (
    r"\bonly\s+works?\s+(?:with)?in\b",
    r"\b(?:with)?in\s+(?:the\s+)?(?:allowed|permitted|configured|specified|given|current)\b",
    r"\ballowed\s+director",
    r"\brestricted\s+to\b",
    r"\blimited\s+to\b",
    r"\bconfined\s+to\b",
    r"\bscoped\s+to\b",
    r"\brelative\s+to\b",
    r"\bmust\s+be\s+(?:with)?in\b",
    r"\bsandbox",
    r"\bworkspace\b",
    r"\bwithin\s+the\b",
)

_SCOPE_RE = re.compile("|".join(SCOPE_PATTERNS), re.IGNORECASE)

# Fraction of a server's tools that must state a boundary before a tool that
# omits one is treated as departing from a convention rather than as normal.
CONVENTION_MAJORITY = 0.6


@dataclass(frozen=True)
class ScopeFinding:
    """§4's lint finding record, for ``finding_type == "missing_scope"``."""

    tool_name: str
    explanation: str
    signals: dict[str, Any]
    finding_type: str = "missing_scope"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "finding_type": self.finding_type,
            "explanation": self.explanation,
            "signals": self.signals,
        }


def states_scope(description: str | None) -> bool:
    """Does this description say anything about where the tool may operate?"""
    if not description:
        return False
    return bool(_SCOPE_RE.search(scannable_text(description)))


def _describes_own_scope(tool: dict[str, Any]) -> bool:
    """Tools whose whole job is reporting the boundary are not missing it.

    ``list_allowed_directories`` has no boundary sentence because it *is* the
    boundary; flagging it would be the linter misreading its own subject matter.
    """
    name_tokens = set(word_tokens((tool.get("name") or "").replace("_", " ")))
    return bool(name_tokens & {"allowed", "permitted", "roots"})


def _verbs_in(tool: dict[str, Any]) -> set[str]:
    tokens = set(word_tokens((tool.get("name") or "").replace("_", " ")))
    tokens |= set(word_tokens(tool.get("description")))
    return tokens


def find_scope_issues(tools: list[dict[str, Any]]) -> list[ScopeFinding]:
    """Flag tools whose descriptions do not bound what they act on."""
    findings: list[ScopeFinding] = []

    scoped = [states_scope(t.get("description")) for t in tools]
    scoped_share = (sum(scoped) / len(tools)) if tools else 0.0
    convention = scoped_share >= CONVENTION_MAJORITY

    for tool, has_scope in zip(tools, scoped, strict=True):
        name = tool.get("name", "")

        if has_scope or _describes_own_scope(tool):
            continue

        tokens = _verbs_in(tool)
        destructive = sorted(tokens & DESTRUCTIVE_VERBS)
        unbounded = sorted(tokens & UNBOUNDED_MARKERS)

        if destructive:
            explanation = (
                f"'{name}' describes a destructive action ({', '.join(destructive)}) "
                f"without stating any boundary on what it may act on."
            )
            if unbounded:
                explanation += (
                    f" It also uses explicitly unbounded language: {', '.join(unbounded)}."
                )
            findings.append(
                ScopeFinding(
                    tool_name=name,
                    explanation=explanation,
                    signals={
                        "check": "unbounded_action",
                        "destructive_verbs": destructive,
                        "unbounded_markers": unbounded,
                        "states_scope": False,
                    },
                )
            )
            continue

        if convention:
            findings.append(
                ScopeFinding(
                    tool_name=name,
                    explanation=(
                        f"'{name}' states no boundary, while {sum(scoped)} of {len(tools)} "
                        f"tools on this server do. A boundary the siblings state and this one "
                        f"omits is more likely to have been dropped than never intended. "
                        f"The server may still enforce it — this is a documentation gap, "
                        f"not proof of unrestricted access."
                    ),
                    signals={
                        "check": "convention_departure",
                        "server_tools_stating_scope": sum(scoped),
                        "server_tool_count": len(tools),
                        "states_scope": False,
                    },
                )
            )

    return findings
