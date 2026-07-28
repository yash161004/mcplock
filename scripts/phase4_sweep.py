"""Phase 4 (brief §3): snapshot + lint real public MCP servers.

Zero-cost — talks to servers over stdio and runs the local linters. No LLM, no
API key. Servers that fail to start are recorded as failures rather than
skipped; "we could not reach it" is a result too.

    python scripts/phase4_sweep.py

Writes docs/phase4_runs/sweep.json (raw, per-server) and prints a summary.
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from mcplock.connector import ServerTarget, fetch_tools  # noqa: E402
from mcplock.lint.ambiguity import find_ambiguities  # noqa: E402
from mcplock.lint.scope import find_scope_issues, states_scope  # noqa: E402

OUT = REPO / "docs" / "phase4_runs"
SANDBOX = REPO / "sandbox" / "phase4"

# Public servers reachable with no credentials. Official reference servers
# first, then community ones from the registry.
SERVERS: list[tuple[str, str]] = [
    ("filesystem", f'npx -y @modelcontextprotocol/server-filesystem "{SANDBOX}"'),
    ("memory", "npx -y @modelcontextprotocol/server-memory"),
    ("sequential-thinking", "npx -y @modelcontextprotocol/server-sequential-thinking"),
    ("everything", "npx -y @modelcontextprotocol/server-everything"),
    ("git", "uvx mcp-server-git"),
    ("fetch", "uvx mcp-server-fetch"),
    ("time", "uvx mcp-server-time"),
    ("context7", "npx -y @upstash/context7-mcp"),
    ("duckduckgo", "npx -y duckduckgo-mcp-server"),
    ("playwright", "npx -y @playwright/mcp@latest"),
    ("sqlite", "uvx mcp-server-sqlite --db-path :memory:"),
    ("brave-search", "npx -y @modelcontextprotocol/server-brave-search"),
]


async def probe(name: str, command: str) -> dict:
    record: dict = {"name": name, "command": command}
    try:
        target = ServerTarget.from_command(command)
        tools = await asyncio.wait_for(fetch_tools(target), timeout=120)
    except Exception as exc:
        record["reachable"] = False
        record["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        return record

    ambiguities = find_ambiguities(tools)
    scope_issues = find_scope_issues(tools)
    scoped = sum(1 for t in tools if states_scope(t.get("description")))

    record.update(
        {
            "reachable": True,
            "server_id": target.server_id,
            "tool_count": len(tools),
            "tools_stating_scope": scoped,
            "tool_names": [t.get("name") for t in tools],
            "ambiguity": [f.to_dict() for f in ambiguities],
            "missing_scope": [f.to_dict() for f in scope_issues],
        }
    )
    return record


async def main() -> int:
    SANDBOX.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    records = []
    for name, command in SERVERS:
        print(f"--- {name} ---", flush=True)
        try:
            record = await probe(name, command)
        except Exception:
            record = {"name": name, "command": command, "reachable": False,
                      "error": traceback.format_exc()[-300:]}
        records.append(record)

        if record.get("reachable"):
            print(
                f"  {record['tool_count']} tools | "
                f"{len(record['ambiguity'])} ambiguity | "
                f"{len(record['missing_scope'])} missing_scope",
                flush=True,
            )
        else:
            print(f"  unreachable: {record['error'][:120]}", flush=True)

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "servers": records,
    }
    (OUT / "sweep.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )

    reached = [r for r in records if r.get("reachable")]
    print(f"\n=== {len(reached)}/{len(records)} servers reached ===")
    print(f"total tools linted: {sum(r['tool_count'] for r in reached)}")
    print(f"ambiguity findings: {sum(len(r['ambiguity']) for r in reached)}")
    print(f"missing_scope findings: {sum(len(r['missing_scope']) for r in reached)}")
    print(f"raw: {OUT / 'sweep.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
