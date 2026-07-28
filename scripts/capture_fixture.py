"""Capture a real server's raw ``tools/list`` output as a test fixture.

    python scripts/capture_fixture.py <name> "<server command>"

Writes ``tests/fixtures/<name>.json`` with the raw tool list plus the command
and capture date, so fixtures stay traceable to where they came from.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcplock.connector import ServerTarget, fetch_tools  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


async def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    name, command = sys.argv[1], sys.argv[2]
    target = ServerTarget.from_command(command)
    tools = await fetch_tools(target)

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "server_command": command,
        "server_id": target.server_id,
        "tools": tools,
    }

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    out = FIXTURE_DIR / f"{name}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out} — {len(tools)} tools")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
