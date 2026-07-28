"""Shared fixtures.

Every test that touches the store runs against a temp ``MCPLOCK_HOME`` so a
test run can never read or clobber the developer's real ``~/.mcplock``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"
DRIFT_SERVER = Path(__file__).parent / "drift_server.py"
SERVER_COMMAND = f'"{sys.executable}" "{DRIFT_SERVER}"'


def run_cli(*args: str, home: Path, variant: str = "baseline") -> subprocess.CompletedProcess[str]:
    """Drive the real CLI against the drift server.

    The variant reaches the server through ``--env``, not through this process's
    environment: the MCP SDK deliberately inherits only a small safe allowlist
    when spawning a stdio server, so an inherited variable would never arrive.
    ``--env`` is not part of the server command, so server_id stays identical
    between a snapshot and a later check.
    """
    env = {
        **os.environ,
        "MCPLOCK_HOME": str(home),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mcplock.cli",
            *args,
            "--env",
            f"MCPLOCK_DRIFT_VARIANT={variant}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )


@pytest.fixture
def filesystem_tools() -> list[dict]:
    """The real captured tool list from @modelcontextprotocol/server-filesystem."""
    payload = json.loads((FIXTURE_DIR / "filesystem_server.json").read_text(encoding="utf-8"))
    return payload["tools"]


@pytest.fixture
def write_file_tool(filesystem_tools: list[dict]) -> dict:
    """A single real tool that carries behavioural annotations."""
    return next(t for t in filesystem_tools if t["name"] == "write_file")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "mcplock-home"
    monkeypatch.setenv("MCPLOCK_HOME", str(home))
    return home
