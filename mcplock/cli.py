"""Command-line entrypoint (typer).

Commands: ``snapshot`` (save baseline), ``check`` (diff, non-zero exit on
high-severity drift), ``lint`` (ambiguity + scope findings).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from . import report, store
from .connector import ServerTarget, fetch_tools
from .diff import HIGH, SEVERITY_ORDER, diff_snapshots, severity_rank
from .store import IncomparableSnapshotsError

app = typer.Typer(
    name="mcplock",
    help="Pin, diff, and lint MCP tool definitions.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)


@app.callback()
def main() -> None:
    """Keeps subcommand dispatch explicit.

    Without a callback, typer collapses a single-command app into a bare
    entrypoint, so ``mcplock snapshot <server>`` would parse "snapshot" as the
    server argument. ``check`` and ``lint`` land in later phases.
    """


def fetch_or_exit(target: ServerTarget) -> list[dict]:
    """Pull the live tool list, turning any transport failure into exit 2."""
    try:
        return asyncio.run(fetch_tools(target))
    except Exception as exc:  # noqa: BLE001 — surface any transport failure plainly
        err_console.print(f"[red]Failed to reach server:[/red] {exc}")
        raise typer.Exit(code=2) from exc


def parse_env(pairs: list[str] | None) -> dict[str, str]:
    """Parse repeated ``--env KEY=VALUE`` options."""
    parsed: dict[str, str] = {}
    for pair in pairs or []:
        key, separator, value = pair.partition("=")
        if not separator or not key:
            raise typer.BadParameter(f"--env expects KEY=VALUE, got {pair!r}")
        parsed[key] = value
    return parsed


def resolve_target(server: str, transport: str, env: list[str] | None = None) -> ServerTarget:
    """Build a ServerTarget from the CLI's ``server`` argument.

    ``server`` alone determines ``server_id``, so ``--env`` can differ between a
    snapshot and a later check without looking like a different server.
    """
    if transport == "auto":
        transport = "http" if server.startswith(("http://", "https://")) else "stdio"

    if transport == "http":
        if env:
            raise typer.BadParameter("--env only applies to stdio servers")
        return ServerTarget.from_url(server)
    if transport == "stdio":
        return ServerTarget.from_command(server, env=parse_env(env))
    raise typer.BadParameter(f"unsupported transport: {transport}")


ENV_OPTION = typer.Option(
    None,
    "--env",
    help="KEY=VALUE passed to a stdio server (repeatable). The MCP SDK inherits "
    "only a small safe allowlist, so anything else must be named here. Never "
    "written to the snapshot.",
)


@app.command()
def snapshot(
    server: str = typer.Argument(
        ...,
        help='Server command (e.g. "npx -y @modelcontextprotocol/server-filesystem ./data") '
        "or a streamable-HTTP URL.",
    ),
    transport: str = typer.Option(
        "auto", "--transport", help="stdio | http | auto (infer from the argument)."
    ),
    env: list[str] = ENV_OPTION,
) -> None:
    """Fetch a server's tools and save them as the pinned baseline."""
    target = resolve_target(server, transport, env)
    tools = fetch_or_exit(target)

    previous = store.load(target.server_id)
    document = store.build_snapshot(target, tools, previous=previous)
    path = store.save(document)

    verb = "Updated" if previous else "Created"
    console.print(
        f"{verb} baseline for [bold]{target.server_id}[/bold] "
        f"— {len(document['tools'])} tools"
    )
    console.print(f"[dim]{path}[/dim]")


@app.command()
def check(
    server: str = typer.Argument(..., help="Server command or streamable-HTTP URL."),
    transport: str = typer.Option(
        "auto", "--transport", help="stdio | http | auto (infer from the argument)."
    ),
    fail_on: str = typer.Option(
        HIGH,
        "--fail-on",
        help=f"Lowest severity that exits non-zero. One of: {', '.join(SEVERITY_ORDER)}.",
    ),
    json_report: Path | None = typer.Option(
        None, "--json", help="Also write the machine-readable report here."
    ),
    env: list[str] = ENV_OPTION,
) -> None:
    """Re-scan a server and fail if it drifted from its pinned baseline.

    Exit codes: 0 clean, 1 drift at or above ``--fail-on``, 2 could not check
    (unreachable server, no baseline, incomparable snapshots). A missing
    baseline is an error rather than a pass — exiting 0 there would silently
    green-light an unpinned server in CI.
    """
    if fail_on not in SEVERITY_ORDER:
        raise typer.BadParameter(f"--fail-on must be one of: {', '.join(SEVERITY_ORDER)}")

    target = resolve_target(server, transport, env)

    try:
        baseline = store.load(target.server_id)
    except IncomparableSnapshotsError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    if baseline is None:
        err_console.print(
            f"[red]No baseline for[/red] {target.server_id}\n"
            f"Run `mcplock snapshot` against this server first."
        )
        raise typer.Exit(code=2)

    tools = fetch_or_exit(target)
    current = store.build_snapshot(target, tools, previous=baseline)

    try:
        result = diff_snapshots(baseline, current)
    except IncomparableSnapshotsError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    report.render_diff(result, console)

    if json_report is not None:
        report.write_json(result, json_report)
        console.print(f"[dim]wrote {json_report}[/dim]")

    breaching = result.at_or_above(fail_on)
    if breaching:
        console.print(
            f"\n[bold red]{len(breaching)} finding(s) at or above "
            f"{fail_on}[/bold red] — failing."
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
