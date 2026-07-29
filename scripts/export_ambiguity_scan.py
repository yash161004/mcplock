"""Export pairwise ambiguity evaluation data for the filesystem server tools.

Computes TF-IDF cosine similarity, schema substitutability, name affinity,
opposing verb vetoes, and final scores across all 91 tool pairs of
@modelcontextprotocol/server-filesystem.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

from mcplock.lint.ambiguity import (
    DEFAULT_THRESHOLD,
    name_affinity,
    opposing,
    substitutable,
    tfidf_cosines,
)

ROOT = Path(__file__).parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "filesystem_server.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "filesystem-server-ambiguity-scan.json"


def main() -> None:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    tools = data.get("tools", [])
    n_tools = len(tools)
    documents = [f"{t.get('name', '')} {t.get('description') or ''}" for t in tools]
    cosines = tfidf_cosines(documents)

    records = []

    for i, j in itertools.combinations(range(n_tools), 2):
        left, right = tools[i], tools[j]
        left_name, right_name = left.get("name", ""), right.get("name", "")

        is_substitutable = substitutable(left, right)
        opposed_pair = opposing(left_name, right_name)
        veto_triggered = opposed_pair is not None
        affinity = name_affinity(left_name, right_name)
        cosine_sim = cosines[i][j]
        score = max(affinity, cosine_sim)

        flagged = (
            is_substitutable and (not veto_triggered) and (score >= DEFAULT_THRESHOLD)
        )

        records.append(
            {
                "tool_a": left_name,
                "tool_b": right_name,
                "cosine_similarity": round(cosine_sim, 3),
                "schema_substitutable": is_substitutable,
                "name_affinity_score": round(affinity, 3),
                "final_score": round(score, 3),
                "veto_triggered": veto_triggered,
                "flagged": flagged,
            }
        )

    # Sort records by final_score descending, then tool_a, tool_b
    records.sort(key=lambda r: (-r["final_score"], r["tool_a"], r["tool_b"]))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "server_id": data.get("server_id"),
                "total_tools": n_tools,
                "total_pairs": len(records),
                "threshold": DEFAULT_THRESHOLD,
                "summary": {
                    "substitutable_pairs": sum(
                        1 for r in records if r["schema_substitutable"]
                    ),
                    "eliminated_by_schema_gate": sum(
                        1 for r in records if not r["schema_substitutable"]
                    ),
                    "veto_triggered_pairs": sum(
                        1 for r in records if r["veto_triggered"]
                    ),
                    "flagged_pairs": sum(1 for r in records if r["flagged"]),
                },
                "pairs": records,
            },
            f,
            indent=2,
        )
        f.write("\n")

    print(
        f"Successfully exported {len(records)} pairs to {OUTPUT_PATH.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
