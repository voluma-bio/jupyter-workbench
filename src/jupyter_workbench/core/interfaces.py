"""Abstract ports for kernel and notebook adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ExecutionOutput:
    """Raw execution output returned by a kernel adapter."""

    stdout: str
    stderr: str
    display_data: list[dict[str, Any]]
    error: str | None


class KernelPort(Protocol):
    """Port for persistent Jupyter kernel lifecycle and execution."""

    def start(self, session_id: str) -> None:
        """Start a kernel for a session."""
        ...

    def connect(self, session_id: str, connection_file: str) -> None:
        """Connect to an existing kernel for a session."""
        ...

    def execute(self, session_id: str, code: str) -> ExecutionOutput:
        """Execute code in a session kernel."""
        ...

    def is_alive(self, session_id: str) -> bool:
        """Return whether a session kernel is reachable."""
        ...

    def probe_alive(self, session_id: str) -> bool:
        """Probe kernel reachability without retaining client state."""
        ...

    def shutdown(self, session_id: str) -> bool:
        """Stop a session kernel if it is running; return whether it stopped."""
        ...


class NotebookPort(Protocol):
    """Port for durable notebook storage."""

    def create(self, path: Path) -> None:
        """Create an empty notebook at path."""
        ...

    def append_code_cell(self, path: Path, source: str, outputs: list[dict[str, Any]]) -> int:
        """Append a code cell and return its cell index."""
        ...

    def append_markdown_cell(self, path: Path, source: str) -> int:
        """Append a markdown cell and return its cell index."""
        ...

    def read_cells(self, path: Path) -> list[dict[str, Any]]:
        """Read notebook cells as serializable dictionaries."""
        ...

    def cell_count(self, path: Path) -> int:
        """Return the number of cells in a notebook."""
        ...
