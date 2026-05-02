"""Typer CLI adapter for jupyter-workbench."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from jupyter_workbench.adapters.kernel.jupyter_client_manager import JupyterClientManager
from jupyter_workbench.adapters.notebook.nbformat_store import NbformatStore
from jupyter_workbench.core.models import SessionInfo, SessionList
from jupyter_workbench.core.session_service import SessionNotFoundError, SessionService

app = typer.Typer(help="Persistent Jupyter workbench sessions.")
console = Console()


def _service(root_dir: Path) -> SessionService:
    kernel = JupyterClientManager(root_dir=root_dir)
    notebook = NbformatStore()
    return SessionService(kernel=kernel, notebook=notebook, root_dir=root_dir)


def _print_session(info: SessionInfo) -> None:
    table = Table(show_header=False, box=None)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("session_id", info.session_id)
    table.add_row("root_dir", info.root_dir)
    table.add_row("notebook_path", info.notebook_path)
    table.add_row("kernel_status", info.kernel_status)
    table.add_row("visualization_status", info.visualization_status)
    table.add_row("created_at", info.created_at)
    if info.warning:
        table.add_row("warning", info.warning)
    console.print(table)


def _print_session_list(session_list: SessionList) -> None:
    table = Table(title="Jupyter Workbench Sessions")
    table.add_column("Session ID")
    table.add_column("Kernel")
    table.add_column("Visualization")
    table.add_column("Notebook")
    table.add_column("Created")
    for info in session_list.sessions:
        table.add_row(
            info.session_id,
            info.kernel_status,
            info.visualization_status,
            info.notebook_path,
            info.created_at,
        )
    console.print(table)


def _handle_missing_session(error: SessionNotFoundError) -> None:
    raise typer.BadParameter(str(error)) from error


def _not_implemented() -> None:
    console.print("Not yet implemented")


@app.command("open")
def open_session(
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", "-s", help="Session id to open or attach."),
    ] = None,
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Open or attach to a workbench session."""
    _print_session(_service(root_dir).open(session_id))


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
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Report one session status."""
    try:
        _print_session(_service(root_dir).status(session_id))
    except SessionNotFoundError as error:
        _handle_missing_session(error)


@app.command("list")
def list_sessions(
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """List workbench sessions."""
    _print_session_list(_service(root_dir).list())


@app.command("close")
def close(
    session_id: Annotated[str, typer.Argument(help="Session id to close.")],
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Close a workbench session while preserving artifacts."""
    try:
        _print_session(_service(root_dir).close(session_id))
    except SessionNotFoundError as error:
        _handle_missing_session(error)


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
