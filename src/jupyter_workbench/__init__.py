"""Public package surface for jupyter-workbench."""

from typing import Any

from jupyter_workbench.core.execution_service import ExecutionService
from jupyter_workbench.core.interfaces import EventLogPort, ExecutionOutput, KernelPort, NotebookPort
from jupyter_workbench.core.lineage_service import LineageService
from jupyter_workbench.core.models import (
    CompactionResult,
    DerivationResult,
    EventPollResult,
    EventRecord,
    ExecResult,
    LineageInfo,
    NotebookMutationResult,
    ReplayResult,
    SessionInfo,
    SessionList,
    SnapshotResult,
)
from jupyter_workbench.core.session_service import SessionService
from jupyter_workbench.core.snapshot_service import SnapshotService

mcp: Any


def __getattr__(name: str) -> Any:
    if name == "mcp":
        from jupyter_workbench.mcp import mcp

        return mcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "CompactionResult",
    "DerivationResult",
    "EventLogPort",
    "EventPollResult",
    "EventRecord",
    "ExecResult",
    "ExecutionOutput",
    "ExecutionService",
    "KernelPort",
    "LineageInfo",
    "LineageService",
    "NotebookMutationResult",
    "mcp",
    "NotebookPort",
    "ReplayResult",
    "SessionInfo",
    "SessionList",
    "SessionService",
    "SnapshotResult",
    "SnapshotService",
]
