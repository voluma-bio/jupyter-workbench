"""Session lifecycle service."""

from __future__ import annotations

from pathlib import Path

from jupyter_workbench.core.interfaces import KernelPort, NotebookPort
from jupyter_workbench.core.models import SessionInfo, SessionList


class SessionService:
    """Transport-agnostic session lifecycle operations."""

    def __init__(
        self,
        kernel: KernelPort,
        notebook: NotebookPort,
        root_dir: Path | None = None,
    ) -> None:
        self.kernel = kernel
        self.notebook = notebook
        self.root_dir = root_dir or Path(".jupyter-workbench")

    def open(self, session_id: str | None = None) -> SessionInfo:
        """Open or attach to a workbench session."""
        raise NotImplementedError

    def close(self, session_id: str) -> SessionInfo:
        """Close live resources for a session while preserving artifacts."""
        raise NotImplementedError

    def status(self, session_id: str) -> SessionInfo:
        """Return status for one session."""
        raise NotImplementedError

    def list(self) -> SessionList:
        """List sessions under the configured root."""
        raise NotImplementedError
