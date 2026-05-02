"""Notebook lineage service."""

from __future__ import annotations

from jupyter_workbench.core.interfaces import KernelPort, NotebookPort
from jupyter_workbench.core.models import (
    CompactionResult,
    DerivationResult,
    LineageInfo,
    ReplayResult,
)


class LineageService:
    """Transport-agnostic notebook lineage and recovery operations."""

    def __init__(self, kernel: KernelPort, notebook: NotebookPort) -> None:
        self.kernel = kernel
        self.notebook = notebook

    def lineage(self, session_id: str) -> LineageInfo:
        """Inspect notebook lineage for a session."""
        raise NotImplementedError

    def replay(self, session_id: str) -> ReplayResult:
        """Explicitly replay notebook lineage into a fresh runtime."""
        raise NotImplementedError

    def derive(self, session_id: str) -> DerivationResult:
        """Create a derived notebook for a session."""
        raise NotImplementedError

    def compact(self, session_id: str) -> CompactionResult:
        """Compact notebook history for a session."""
        raise NotImplementedError
