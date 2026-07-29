"""Guards on what ships to PyPI.

An sdist is world-readable forever — yanking a release does not delete its
files, and mirrors cache them. Hatchling's default is to sweep the working tree,
which once pulled `docs/INTERNAL_FINDINGS.md` (undisclosed third-party
findings), `docs/disclosure_drafts/` (unsent private reports), `AGENT_BRIEF.md`, and
a stale `.agent/worktrees/` copy into the distribution.

Publishing any of those would breach `docs/DISCLOSURE.md` irreversibly. These
tests fail if the allowlist is removed, widened to the sensitive paths, or
inverted into an exclude list.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = REPO / "pyproject.toml"

# Paths that must never reach a published artifact.
FORBIDDEN = (
    "docs",
    "AGENT_BRIEF.md",
    "HANDOFF.md",
    ".agent",
    "scripts",
    "sandbox",
)


@pytest.fixture(scope="module")
def config() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def sdist_config(config: dict) -> dict:
    return config["tool"]["hatch"]["build"]["targets"]["sdist"]


def test_sdist_target_is_configured(config: dict) -> None:
    """Without this section hatchling sweeps the whole working tree."""
    targets = config["tool"]["hatch"]["build"]["targets"]

    assert "sdist" in targets, (
        "pyproject.toml has no [tool.hatch.build.targets.sdist] section. "
        "Without it the sdist includes docs/, AGENT_BRIEF.md, and .agent/ worktrees."
    )


def test_sdist_uses_an_allowlist_not_an_exclude_list(config: dict) -> None:
    """An exclude list ships new sensitive files by default; an allowlist does not."""
    sdist = sdist_config(config)

    assert "only-include" in sdist or "include" in sdist, (
        "sdist config must allowlist paths. `exclude` is not acceptable here — "
        "a newly added sensitive file would ship by default."
    )


@pytest.mark.parametrize("path", FORBIDDEN)
def test_forbidden_paths_are_not_shipped(config: dict, path: str) -> None:
    sdist = sdist_config(config)
    allowed = sdist.get("only-include", sdist.get("include", []))

    offenders = [entry for entry in allowed if entry.strip("/").split("/")[0] == path]

    assert not offenders, (
        f"{path!r} is in the sdist allowlist. It must not be published — see the "
        f"comment above the section in pyproject.toml. Offending entries: {offenders}"
    )


def test_the_package_itself_is_shipped(config: dict) -> None:
    """Guard the guard: an empty allowlist would pass every check above."""
    sdist = sdist_config(config)
    allowed = sdist.get("only-include", sdist.get("include", []))

    assert any(entry.strip("/") == "mcplock" for entry in allowed)


def test_license_file_exists_when_license_is_declared(config: dict) -> None:
    """Metadata claims MIT; a published package should carry the text."""
    declared = config["project"].get("license")

    if declared:
        assert (REPO / "LICENSE").exists(), (
            "pyproject declares a license but no LICENSE file exists to ship."
        )
