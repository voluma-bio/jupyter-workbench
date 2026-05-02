"""Typed DTOs for the public jupyter-workbench API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionInfo:
    """Durable session state returned by lifecycle operations."""

    session_id: str
    root_dir: str
    notebook_path: str
    kernel_status: str
    visualization_status: str
    created_at: str


@dataclass(frozen=True)
class SessionList:
    """Collection of known workbench sessions."""

    sessions: list[SessionInfo]


@dataclass(frozen=True)
class ExecResult:
    """Structured result for notebook-backed code execution."""

    session_id: str
    cell_index: int
    status: str
    inline_summary: str
    output_artifacts: list[str]
    error_traceback: str | None
    visualization_delta: dict[str, Any] | None
    output_size_warning: bool


@dataclass(frozen=True)
class NotebookMutationResult:
    """Result for notebook mutations that do not execute code."""

    session_id: str
    cell_index: int
    cell_type: str


@dataclass(frozen=True)
class SnapshotResult:
    """Machine-readable observation of a session."""

    session_id: str
    root_dir: str
    kernel_status: str
    visualization_status: str
    notebook_path: str
    cell_count: int
    recent_outputs: list[dict[str, Any]]
    visualization_summary: dict[str, Any] | None
    lineage_summary: dict[str, Any] | None


@dataclass(frozen=True)
class LineageInfo:
    """Notebook lineage summary for a session."""

    session_id: str
    source_notebook: str
    derived_notebooks: list[str]
    revision_count: int


@dataclass(frozen=True)
class ReplayResult:
    """Result of explicit replay into a fresh runtime."""

    session_id: str
    status: str
    new_revision: int | None
    failed_cell: int | None
    error_artifact: str | None


@dataclass(frozen=True)
class DerivationResult:
    """Result of deriving a new notebook from a source notebook."""

    session_id: str
    derived_notebook_path: str
    source_notebook: str


@dataclass(frozen=True)
class CompactionResult:
    """Result of compacting notebook history."""

    session_id: str
    compacted_notebook_path: str
    cells_removed: int
    cells_kept: int
