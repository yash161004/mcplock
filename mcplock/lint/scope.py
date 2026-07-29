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
#
# `drop`, `upload`, and `transfer` were removed after they fired on the real
# Playwright server: "drop" there is the drag-and-drop gesture, not deletion.
# A verb whose destructive reading depends on its object belongs in
# CONTEXTUAL_VERBS, and moving data is not the same as destroying it.
DESTRUCTIVE_VERBS = frozenset(
    """delete remove destroy purge truncate erase wipe overwrite write
    modify update rename move execute run spawn invoke send post publish
    grant revoke kill terminate""".split()
)

# Verbs that are only destructive next to the right object. `drop a table` is;
# `drop a file onto the page` is not. Requiring the object keeps the SQL sense
# without matching browser gestures.
CONTEXTUAL_VERBS = {
    "drop": frozenset({"table", "tables", "database", "databases", "schema",
                       "collection", "collections", "index", "indexes", "column"}),
    "flush": frozenset({"cache", "caches", "buffer", "table", "database"}),
}

# Language that explicitly widens scope rather than narrowing it.
UNBOUNDED_MARKERS = frozenset(
    """any arbitrary anywhere everything anything unrestricted unlimited global
    entire whole host system""".split()
)

# Phrases that state a boundary. Deliberately broad: a false "this tool is
# scoped" is a missed finding, but a false "unscoped" is noise that gets the
# linter ignored, and noise is the failure mode that matters here.
# Named subsystems that constitute a boundary when a tool says it acts on one.
# Deliberately excludes generic objects — "the host", "the system", "the machine"
# name no boundary at all, and must keep failing this check.
_SUBSYSTEM = (
    r"(?:graph|database|repository|repo|workspace|project|page|browser|session|"
    r"directory|directories|folder|index|store|collection|namespace|container|"
    r"bucket|notebook|document|sheet|channel|queue)\b"
)

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
    # A named subsystem is a boundary statement too. "from the knowledge graph"
    # and "on the SQLite database" say where the tool acts just as precisely as
    # "within allowed directories" does — the earlier pattern list only knew how
    # to recognise filesystem phrasing, and flagged in-memory and browser servers
    # for omitting a sentence they had no reason to write.
    #
    # Deliberately requires a *named* subsystem. Generic objects ("on the host",
    # "in the system") state no boundary and must keep failing this check.
    r"\b(?:from|on|in|to|within|inside|against)\s+(?:the|this|its|your)\s+"
    r"(?:\w+[\s-]+){0,2}" + _SUBSYSTEM,
    # …or as a direct object: "Read the entire knowledge graph" bounds itself
    # just as well as "read from the knowledge graph", and requiring the
    # preposition flagged the one memory tool phrased the other way.
    r"\bthe\s+(?:\w+[\s-]+){0,2}" + _SUBSYSTEM,
)

_SCOPE_RE = re.compile("|".join(SCOPE_PATTERNS), re.IGNORECASE)

# Fraction of a server's tools that must state a boundary before a tool that
# omits one is treated as departing from a convention rather than as normal.
CONVENTION_MAJORITY = 0.6

# A "convention" inferred from a handful of tools is noise: on a three-tool
# server, two agreeing is 67% and indicts the third. Only one convention
# departure survived verification across 85 real tools — `read_file` on the
# 14-tool filesystem server — so requiring a reasonable sample costs nothing
# real and removes the small-server false positives.
MIN_TOOLS_FOR_CONVENTION = 8


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


def destructive_verbs_in(tool: dict[str, Any]) -> list[str]:
    """Destructive verbs this tool uses, resolving ambiguous ones by object.

    A contextual verb counts only when a qualifying object appears somewhere in
    the same text: ``drop the users table`` is destructive, ``drop a file onto
    the page`` is not. Without this, the browser drag-and-drop tools read as
    deletions.
    """
    tokens = _verbs_in(tool)
    found = set(tokens & DESTRUCTIVE_VERBS)

    for verb, objects in CONTEXTUAL_VERBS.items():
        if verb in tokens and tokens & objects:
            found.add(verb)

    return sorted(found)


def find_scope_issues(tools: list[dict[str, Any]]) -> list[ScopeFinding]:
    """Flag tools whose descriptions do not bound what they act on."""
    findings: list[ScopeFinding] = []

    scoped = [states_scope(t.get("description")) for t in tools]
    scoped_share = (sum(scoped) / len(tools)) if tools else 0.0
    convention = len(tools) >= MIN_TOOLS_FOR_CONVENTION and scoped_share >= CONVENTION_MAJORITY

    for tool, has_scope in zip(tools, scoped, strict=True):
        name = tool.get("name", "")

        if has_scope or _describes_own_scope(tool):
            continue

        tokens = _verbs_in(tool)
        destructive = destructive_verbs_in(tool)
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
