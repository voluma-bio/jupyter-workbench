"""Typer CLI adapter for jupyter-workbench."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from jupyter_workbench.adapters.kernel.jupyter_client_manager import JupyterClientManager
from jupyter_workbench.adapters.notebook.nbformat_store import NbformatStore
from jupyter_workbench.adapters.visualization.event_log import DurableEventLog
from jupyter_workbench.adapters.visualization.pyvista_trame import PyVistaTrameHelper

from jupyter_workbench.core.execution_service import ExecutionService
from jupyter_workbench.core.lineage_service import LineageService
from jupyter_workbench.core.models import (
    ExecResult,
    LineageInfo,
    NotebookMutationResult,
    ReplayResult,
    SessionInfo,
    SessionList,
    SnapshotResult,
)
from jupyter_workbench.core.snapshot_service import SnapshotService
from jupyter_workbench.core.session_service import SessionNotFoundError, SessionService

app = typer.Typer(help="Persistent Jupyter workbench sessions.")
console = Console()


def _adapters(root_dir: Path) -> tuple[JupyterClientManager, NbformatStore]:
    return JupyterClientManager(root_dir=root_dir), NbformatStore()


def _service(root_dir: Path) -> SessionService:
    kernel, notebook = _adapters(root_dir)
    return SessionService(kernel=kernel, notebook=notebook, root_dir=root_dir)


def _execution_service(root_dir: Path) -> ExecutionService:
    kernel, notebook = _adapters(root_dir)
    return ExecutionService(
        kernel=kernel,
        notebook=notebook,
        root_dir=root_dir,
        visualization=PyVistaTrameHelper(root_dir),
    )


def _snapshot_service(root_dir: Path) -> SnapshotService:
    kernel, notebook = _adapters(root_dir)
    return SnapshotService(
        kernel=kernel,
        notebook=notebook,
        root_dir=root_dir,
        visualization=PyVistaTrameHelper(root_dir),
        event_log=DurableEventLog(root_dir),
    )


def _lineage_service(root_dir: Path) -> LineageService:
    kernel, notebook = _adapters(root_dir)
    return LineageService(kernel=kernel, notebook=notebook, root_dir=root_dir)


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



def _print_exec(result: ExecResult) -> None:
    table = Table(show_header=False, box=None)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("session_id", result.session_id)
    table.add_row("cell_index", str(result.cell_index))
    table.add_row("status", result.status)
    table.add_row("output_size_warning", str(result.output_size_warning))
    for artifact in result.output_artifacts:
        table.add_row("artifact", artifact)
    if result.visualization_delta:
        table.add_row("visualization_delta", str(result.visualization_delta))
    console.print(table)
    if result.inline_summary:
        console.print(result.inline_summary)


def _print_mutation(result: NotebookMutationResult) -> None:
    table = Table(show_header=False, box=None)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("session_id", result.session_id)
    table.add_row("cell_index", str(result.cell_index))
    table.add_row("cell_type", result.cell_type)
    console.print(table)


def _print_snapshot(result: SnapshotResult) -> None:
    console.print_json(data=asdict(result))


def _print_replay(result: ReplayResult) -> None:
    console.print_json(data=asdict(result))


def _print_lineage(result: LineageInfo) -> None:
    console.print_json(data=asdict(result))


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
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Execute code in a workbench session."""
    try:
        _print_exec(_execution_service(root_dir).exec_code(code, session_id=session_id, file=file))
    except SessionNotFoundError as error:
        _handle_missing_session(error)


@app.command("markdown")
def markdown(
    text: Annotated[str, typer.Argument(help="Markdown text to append.")],
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", "-s", help="Session id to append to."),
    ] = None,
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Append markdown to a workbench notebook."""
    try:
        _print_mutation(_execution_service(root_dir).markdown(text, session_id=session_id))
    except SessionNotFoundError as error:
        _handle_missing_session(error)


@app.command("snapshot")
def snapshot(
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", "-s", help="Session id to snapshot."),
    ] = None,
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Report a machine-readable session snapshot."""
    try:
        _print_snapshot(_snapshot_service(root_dir).snapshot(session_id))
    except SessionNotFoundError as error:
        _handle_missing_session(error)


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
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Replay notebook lineage into a fresh runtime."""
    try:
        _print_replay(_lineage_service(root_dir).replay(session_id))
    except SessionNotFoundError as error:
        _handle_missing_session(error)


@app.command("lineage")
def lineage(
    session_id: Annotated[str, typer.Argument(help="Session id to inspect.")],
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Inspect notebook lineage."""
    try:
        _print_lineage(_lineage_service(root_dir).lineage(session_id))
    except SessionNotFoundError as error:
        _handle_missing_session(error)


@app.command("derive")
def derive(
    session_id: Annotated[str, typer.Argument(help="Session id to derive from.")],
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Create a derived notebook."""
    try:
        console.print_json(data=asdict(_lineage_service(root_dir).derive(session_id)))
    except SessionNotFoundError as error:
        _handle_missing_session(error)


@app.command("compact")
def compact(
    session_id: Annotated[str, typer.Argument(help="Session id to compact.")],
    cells: Annotated[
        list[int] | None,
        typer.Option("--cell", "-c", help="Cell index to remove. Repeat to remove multiple cells."),
    ] = None,
    root_dir: Annotated[
        Path,
        typer.Option("--root-dir", help="Durable workbench root directory."),
    ] = Path(".jupyter-workbench"),
) -> None:
    """Compact notebook history into a cleanup artifact."""
    try:
        console.print_json(data=asdict(_lineage_service(root_dir).compact(session_id, cells_to_remove=cells)))
    except SessionNotFoundError as error:
        _handle_missing_session(error)
