"""Machine-readable snapshot service."""

from __future__ import annotations

from jupyter_workbench.core.interfaces import NotebookPort
from jupyter_workbench.core.models import SnapshotResult


class SnapshotService:
    """Transport-agnostic session observation operations."""

    def __init__(self, notebook: NotebookPort) -> None:
        self.notebook = notebook

    def snapshot(self, session_id: str | None = None) -> SnapshotResult:
        """Return a machine-readable snapshot for a session."""
        raise NotImplementedError
