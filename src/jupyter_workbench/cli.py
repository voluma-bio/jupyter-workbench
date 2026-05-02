"""Typer CLI adapter for jupyter-workbench."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(help="Persistent Jupyter workbench sessions.")
console = Console()


def _not_implemented() -> None:
    console.print("Not yet implemented")


@app.command("open")
def open_session(
    session_id: Annotated[str | None, typer.Argument(help="Session id to open or attach.")] = None,
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Open or attach to a workbench session."""
    _not_implemented()


@app.command("exec")
def exec_code(
    code: Annotated[str | None, typer.Argument(help="Inline Python code to execute.")] = None,
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", "-s", help="Session id to execute in."),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("--file", help="Python file to execute as one notebook cell."),
    ] = None,
) -> None:
    """Execute code in a workbench session."""
    _not_implemented()


@app.command("markdown")
def markdown(
    text: Annotated[str, typer.Argument(help="Markdown text to append.")],
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", "-s", help="Session id to append to."),
    ] = None,
) -> None:
    """Append markdown to a workbench notebook."""
    _not_implemented()


@app.command("snapshot")
def snapshot(
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", "-s", help="Session id to snapshot."),
    ] = None,
) -> None:
    """Report a machine-readable session snapshot."""
    _not_implemented()


@app.command("status")
def status(
    session_id: Annotated[str, typer.Argument(help="Session id to inspect.")],
) -> None:
    """Report one session status."""
    _not_implemented()


@app.command("list")
def list_sessions(
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """List workbench sessions."""
    _not_implemented()


@app.command("close")
def close(
    session_id: Annotated[str, typer.Argument(help="Session id to close.")],
) -> None:
    """Close a workbench session while preserving artifacts."""
    _not_implemented()


@app.command("replay")
def replay(
    session_id: Annotated[str, typer.Argument(help="Session id to replay.")],
) -> None:
    """Replay notebook lineage into a fresh runtime."""
    _not_implemented()


@app.command("lineage")
def lineage(
    session_id: Annotated[str, typer.Argument(help="Session id to inspect.")],
) -> None:
    """Inspect notebook lineage."""
    _not_implemented()


@app.command("derive")
def derive(
    session_id: Annotated[str, typer.Argument(help="Session id to derive from.")],
) -> None:
    """Create a derived notebook."""
    _not_implemented()


@app.command("compact")
def compact(
    session_id: Annotated[str, typer.Argument(help="Session id to compact.")],
) -> None:
    """Compact notebook history into a cleanup artifact."""
    _not_implemented()
