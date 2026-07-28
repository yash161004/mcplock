"""Shared fixtures.

Every test that touches the store runs against a temp ``MCPLOCK_HOME`` so a
test run can never read or clobber the developer's real ``~/.mcplock``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


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
