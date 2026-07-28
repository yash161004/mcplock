"""Command-line entrypoint (typer).

Commands: ``snapshot`` (save baseline), ``check`` (diff, non-zero exit on
high-severity drift), ``lint`` (ambiguity + scope findings).
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from . import store
from .connector import ServerTarget, fetch_tools

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


def resolve_target(server: str, transport: str) -> ServerTarget:
    """Build a ServerTarget from the CLI's ``server`` argument."""
    if transport == "auto":
        transport = "http" if server.startswith(("http://", "https://")) else "stdio"

    if transport == "http":
        return ServerTarget.from_url(server)
    if transport == "stdio":
        return ServerTarget.from_command(server)
    raise typer.BadParameter(f"unsupported transport: {transport}")


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
) -> None:
    """Fetch a server's tools and save them as the pinned baseline."""
    target = resolve_target(server, transport)

    try:
        tools = asyncio.run(fetch_tools(target))
    except Exception as exc:  # noqa: BLE001 — surface any transport failure plainly
        err_console.print(f"[red]Failed to reach server:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    previous = store.load(target.server_id)
    document = store.build_snapshot(target, tools, previous=previous)
    path = store.save(document)

    verb = "Updated" if previous else "Created"
    console.print(
        f"{verb} baseline for [bold]{target.server_id}[/bold] "
        f"— {len(document['tools'])} tools"
    )
    console.print(f"[dim]{path}[/dim]")


if __name__ == "__main__":
    app()
