"""FastMCP adapter for jupyter-workbench service parity."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    from fastmcp import FastMCP  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
    raise RuntimeError("Install jupyter-workbench with the mcp extra to use MCP support") from exc

from jupyter_workbench.adapters.kernel.jupyter_client_manager import JupyterClientManager
from jupyter_workbench.adapters.notebook.nbformat_store import NbformatStore
from jupyter_workbench.adapters.visualization.pyvista_trame import PyVistaTrameHelper
from jupyter_workbench.core.execution_service import ExecutionService
from jupyter_workbench.core.lineage_service import LineageService
from jupyter_workbench.core.session_service import SessionService
from jupyter_workbench.core.snapshot_service import SnapshotService

mcp = FastMCP("jupyter-workbench")


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
    )


def _lineage_service(root_dir: Path) -> LineageService:
    kernel, notebook = _adapters(root_dir)
    return LineageService(kernel=kernel, notebook=notebook, root_dir=root_dir)


@mcp.tool
def open_session(session_id: str | None = None, root_dir: str = ".jupyter-workbench") -> dict[str, Any]:
    """Open or attach to a workbench session."""
    return asdict(_service(Path(root_dir)).open(session_id))


@mcp.tool
def exec_code(
    code: str | None = None,
    session_id: str | None = None,
    file: str | None = None,
    root_dir: str = ".jupyter-workbench",
) -> dict[str, Any]:
    """Execute code in a workbench session."""
    result = _execution_service(Path(root_dir)).exec_code(
        code,
        session_id=session_id,
        file=Path(file) if file is not None else None,
    )
    return asdict(result)


@mcp.tool
def markdown(
    text: str,
    session_id: str | None = None,
    root_dir: str = ".jupyter-workbench",
) -> dict[str, Any]:
    """Append markdown to a session notebook."""
    return asdict(_execution_service(Path(root_dir)).markdown(text, session_id=session_id))


@mcp.tool
def snapshot(
    session_id: str | None = None,
    root_dir: str = ".jupyter-workbench",
) -> dict[str, Any]:
    """Report a machine-readable session snapshot."""
    return asdict(_snapshot_service(Path(root_dir)).snapshot(session_id))


@mcp.tool
def status(session_id: str, root_dir: str = ".jupyter-workbench") -> dict[str, Any]:
    """Report one session status."""
    return asdict(_service(Path(root_dir)).status(session_id))


@mcp.tool
def list_sessions(root_dir: str = ".jupyter-workbench") -> dict[str, Any]:
    """List workbench sessions."""
    return asdict(_service(Path(root_dir)).list())


@mcp.tool
def close(session_id: str, root_dir: str = ".jupyter-workbench") -> dict[str, Any]:
    """Close a workbench session while preserving artifacts."""
    return asdict(_service(Path(root_dir)).close(session_id))


@mcp.tool
def replay(session_id: str, root_dir: str = ".jupyter-workbench") -> dict[str, Any]:
    """Replay notebook lineage into a fresh runtime."""
    return asdict(_lineage_service(Path(root_dir)).replay(session_id))


@mcp.tool
def lineage(session_id: str, root_dir: str = ".jupyter-workbench") -> dict[str, Any]:
    """Inspect notebook lineage."""
    return asdict(_lineage_service(Path(root_dir)).lineage(session_id))


def main() -> None:
    """Run the FastMCP server."""
    mcp.run()
