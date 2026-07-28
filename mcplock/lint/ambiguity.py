"""Description-overlap detection.

Pairwise text similarity across all tool descriptions on one server; pairs
above the threshold are flagged as "an agent may confuse these".

Why this is not description similarity alone
--------------------------------------------
The brief starts from TF-IDF cosine at ~85%. Measured against the 14 real tools
of the official filesystem server, that flags **0 of 91 pairs** — while the
server has at least three genuine confusion clusters. Worse, the classes are not
separable by any single cosine threshold: ``read_file``/``read_media_file`` are
plainly confusable yet score *level with completely unrelated pairs*, because
their descriptions share almost no vocabulary.

The reason is structural. Prose overlap is not what makes an agent pick the
wrong tool. Confusability is:

1. **Substitutability** — can one call satisfy both tools? If a set of arguments
   is valid for A and also valid for B, an agent can silently swap them. This is
   the gate: pairs that fail it are never reported, however similar the prose.
2. **Name affinity** — agents select heavily on the name. ``read_file`` and
   ``read_media_file`` share a verb and an object noun.
3. **Description similarity** — still useful, and the only signal that catches
   near-duplicate prose like ``list_directory`` /
   ``list_directory_with_sizes``.

A verb-opposition veto suppresses the obvious true negatives: ``read`` versus
``write`` on the same object is a pair of opposites, not a confusion risk.

TF-IDF is implemented here in a few lines rather than pulling in scikit-learn.
The corpus is a handful of short strings; a 100 MB dependency for one cosine is
not a trade a security CLI should make.
"""

from __future__ import annotations

import itertools
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from ..normalize import word_tokens

# Tuned against the labelled filesystem-server pairs: the widest gap sits
# between the most-similar distinct pair and the least-similar ambiguous pair.
# Re-tune against real data before trusting it on a new class of server.
DEFAULT_THRESHOLD = 0.40

# Words that carry no selection signal in tool descriptions.
STOP_WORDS = frozenset(
    """a an and are as at be by can for from has have if in into is it its of on
    only or that the this to use used uses using when will with within you your
    tool file files""".split()
)

# Verb pairs that mean opposite things. A pair separated by one of these is a
# complement, not a confusion: an agent picking between them is making a
# direction decision, not a disambiguation error.
OPPOSING_VERBS = (
    frozenset({"read", "write"}),
    frozenset({"read", "delete"}),
    frozenset({"get", "set"}),
    frozenset({"get", "put"}),
    frozenset({"create", "delete"}),
    frozenset({"add", "remove"}),
    frozenset({"enable", "disable"}),
    frozenset({"start", "stop"}),
    frozenset({"open", "close"}),
    frozenset({"grant", "revoke"}),
)


@dataclass(frozen=True)
class AmbiguityFinding:
    """§4's lint finding record, for ``finding_type == "ambiguity"``."""

    tool_name: str
    related_tool: str
    similarity_score: float
    explanation: str
    signals: dict[str, Any]
    finding_type: str = "ambiguity"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "finding_type": self.finding_type,
            "related_tool": self.related_tool,
            "similarity_score": round(self.similarity_score, 3),
            "explanation": self.explanation,
            "signals": self.signals,
        }


def _content_tokens(text: str | None) -> list[str]:
    return [t for t in word_tokens(text) if t not in STOP_WORDS and len(t) > 1]


def tfidf_cosines(documents: list[str]) -> list[list[float]]:
    """Pairwise cosine similarity of TF-IDF vectors.

    The vectorizer is fitted on *this server's* tools only, which is what makes
    it work without a stop-word list for boilerplate: a sentence repeated by
    almost every tool ("Only works within allowed directories") lands in nearly
    every document, so its IDF collapses toward zero on its own.
    """
    corpus = [_content_tokens(doc) for doc in documents]
    total = len(corpus)

    document_frequency = Counter()
    for tokens in corpus:
        document_frequency.update(set(tokens))

    vectors: list[dict[str, float]] = []
    for tokens in corpus:
        counts = Counter(tokens)
        longest = max(counts.values(), default=1)

        vector = {
            term: (count / longest) * math.log(total / (1 + document_frequency[term]) + 1)
            for term, count in counts.items()
        }
        norm = math.sqrt(sum(weight * weight for weight in vector.values())) or 1.0
        vectors.append({term: weight / norm for term, weight in vector.items()})

    return [
        [sum(a.get(term, 0.0) * weight for term, weight in b.items()) for b in vectors]
        for a in vectors
    ]


def name_affinity(left: str, right: str) -> float:
    """Jaccard overlap of the underscore-separated parts of two tool names."""
    a, b = set(word_tokens(left.replace("_", " "))), set(word_tokens(right.replace("_", " ")))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _schema_parts(tool: dict[str, Any]) -> tuple[set[str], dict[str, Any]]:
    schema = tool.get("inputSchema") or {}
    properties = schema.get("properties") or {}
    return set(schema.get("required") or []), properties


def substitutable(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Could one set of arguments satisfy a call to either tool?

    Requires it in *both* directions: everything the left tool demands must be
    accepted by the right, and vice versa. One-way substitutability is a superset
    relationship, not a confusion — a tool that needs an argument the other has
    never heard of cannot be silently swapped in.
    """
    left_required, left_properties = _schema_parts(left)
    right_required, right_properties = _schema_parts(right)

    if not (left_required <= set(right_properties) and right_required <= set(left_properties)):
        return False

    # A shared parameter name that means different types is not really shared.
    for name in set(left_properties) & set(right_properties):
        left_type = (left_properties[name] or {}).get("type")
        right_type = (right_properties[name] or {}).get("type")
        if left_type and right_type and left_type != right_type:
            return False

    return True


def opposing(left: str, right: str) -> frozenset[str] | None:
    """Return the opposing verb pair separating two tools, if any."""
    left_tokens, right_tokens = set(word_tokens(left.replace("_", " "))), set(
        word_tokens(right.replace("_", " "))
    )
    for pair in OPPOSING_VERBS:
        if pair & left_tokens and pair & right_tokens and pair & (left_tokens ^ right_tokens):
            return pair
    return None


def find_ambiguities(
    tools: list[dict[str, Any]], threshold: float = DEFAULT_THRESHOLD
) -> list[AmbiguityFinding]:
    """Flag pairs of tools an agent could plausibly confuse."""
    if len(tools) < 2:
        return []

    documents = [f"{t.get('name', '')} {t.get('description') or ''}" for t in tools]
    cosines = tfidf_cosines(documents)

    findings: list[AmbiguityFinding] = []

    for i, j in itertools.combinations(range(len(tools)), 2):
        left, right = tools[i], tools[j]
        left_name, right_name = left.get("name", ""), right.get("name", "")

        if not substitutable(left, right):
            continue

        opposed = opposing(left_name, right_name)
        if opposed:
            continue

        affinity = name_affinity(left_name, right_name)
        description_similarity = cosines[i][j]
        score = max(affinity, description_similarity)

        if score < threshold:
            continue

        findings.append(
            AmbiguityFinding(
                tool_name=left_name,
                related_tool=right_name,
                similarity_score=score,
                explanation=_explain(left_name, right_name, affinity, description_similarity),
                signals={
                    "name_affinity": round(affinity, 3),
                    "description_similarity": round(description_similarity, 3),
                    "schema_substitutable": True,
                },
            )
        )

    findings.sort(key=lambda f: (-f.similarity_score, f.tool_name, f.related_tool))
    return findings


def _explain(left: str, right: str, affinity: float, similarity: float) -> str:
    if affinity >= similarity:
        driver = f"their names share a verb and object ({affinity:.0%} overlap)"
    else:
        driver = f"their descriptions are {similarity:.0%} similar"

    return (
        f"'{left}' and '{right}' accept the same arguments, and {driver}. "
        f"An agent choosing between them has nothing in the name or schema to go on, "
        f"so the choice rests entirely on wording that may not state the difference."
    )
