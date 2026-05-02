"""Notebook-backed execution service."""

from __future__ import annotations

from pathlib import Path

from jupyter_workbench.core.interfaces import KernelPort, NotebookPort
from jupyter_workbench.core.models import ExecResult, NotebookMutationResult


class ExecutionService:
    """Transport-agnostic notebook execution and markdown operations."""

    def __init__(self, kernel: KernelPort, notebook: NotebookPort) -> None:
        self.kernel = kernel
        self.notebook = notebook

    def exec_code(
        self,
        code: str | None = None,
        *,
        session_id: str | None = None,
        file: Path | None = None,
    ) -> ExecResult:
        """Execute inline or file-backed code in a session notebook."""
        raise NotImplementedError

    def markdown(self, text: str, *, session_id: str | None = None) -> NotebookMutationResult:
        """Append markdown text to a session notebook."""
        raise NotImplementedError
