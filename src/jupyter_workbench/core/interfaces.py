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


class VisualizationPort(Protocol):
    """Port for durable visualization metadata and artifacts."""

    def register_scene(
        self,
        session_id: str,
        viz_id: str | None,
        plotter_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist scene metadata and return the registered manifest."""
        ...

    def get_active_scene(self, session_id: str) -> dict[str, Any] | None:
        """Return the active scene for a session, if any."""
        ...

    def list_scenes(self, session_id: str) -> list[dict[str, Any]]:
        """Return persisted scene manifests for a session."""
        ...

    def detect_scene_from_display_data(self, display_data: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Extract scene metadata from execution display payloads."""
        ...

    def screenshot_paths(self, session_id: str) -> list[str]:
        """Return screenshot artifact paths for a session."""
        ...

    def update_scene_revision(self, session_id: str, viz_id: str) -> dict[str, Any]:
        """Increment and persist scene revision metadata."""
        ...


class EventLogPort(Protocol):
    """Port for durable visualization event logs."""

    def append(self, event_type: str, payload: dict[str, Any]) -> int:
        """Append an event and return its sequence number."""
        ...

    def read(self, cursor: int = 0) -> tuple[list[dict[str, Any]], int]:
        """Read events from a caller-managed byte cursor."""
        ...

    def wait(self, cursor: int, timeout: float = 30.0) -> tuple[list[dict[str, Any]], int, bool]:
        """Wait for events or timeout."""
        ...


class NotebookPort(Protocol):
    """Port for durable notebook storage."""

    def create(self, path: Path) -> None:
        """Create an empty notebook at path."""
        ...

    def append_code_cell(
        self,
        path: Path,
        source: str,
        outputs: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Append a code cell and return its cell index."""
        ...

    def update_code_cell_outputs(
        self,
        path: Path,
        cell_index: int,
        outputs: list[dict[str, Any]],
        execution_count: int | None = None,
    ) -> None:
        """Update outputs for an existing code cell."""
        ...

    def append_markdown_cell(self, path: Path, source: str) -> int:
        """Append a markdown cell and return its cell index."""
        ...

    def read_cells(self, path: Path) -> list[dict[str, Any]]:
        """Read notebook cells as serializable dictionaries."""
        ...

    def clear_code_outputs(self, path: Path) -> None:
        """Clear outputs and execution counts from all code cells."""
        ...

    def cell_count(self, path: Path) -> int:
        """Return the number of cells in a notebook."""
        ...
