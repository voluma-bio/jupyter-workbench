"""Notebook lineage service."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jupyter_workbench.core.execution_service import ExecutionService
from jupyter_workbench.core.interfaces import KernelPort, NotebookPort
from jupyter_workbench.core.models import (
    CompactionResult,
    DerivationResult,
    LineageInfo,
    ReplayResult,
)
from jupyter_workbench.core.session_lock import SessionLock
from jupyter_workbench.core.session_service import SessionNotFoundError


class LineageService:
    """Transport-agnostic notebook lineage and recovery operations."""

    def __init__(
        self,
        kernel: KernelPort,
        notebook: NotebookPort,
        root_dir: Path | None = None,
    ) -> None:
        self.kernel = kernel
        self.notebook = notebook
        self.root_dir = root_dir or Path(".jupyter-workbench")
        self.locks = SessionLock(self.root_dir)

    def lineage(self, session_id: str) -> LineageInfo:
        """Inspect notebook lineage for a session."""
        manifest = self._read_manifest(session_id)
        notebook_path = self._notebook_path(manifest)
        metadata = self._read_lineage(session_id, notebook_path)
        notebooks_dir = self._session_dir(session_id) / "notebooks"
        revisions = self._revision_records(metadata)
        revision_count = len(revisions)
        if revision_count == 0:
            revision_count = len(list(notebooks_dir.glob("revision_*.ipynb")))
        derived_notebooks = [self._rooted_path(str(path)) for path in metadata.get("derived_notebooks", [])]
        active_notebook = str(notebook_path)
        return LineageInfo(
            session_id=session_id,
            source_notebook=self._rooted_path(str(metadata["source_notebook"])),
            derived_notebooks=derived_notebooks,
            revision_count=revision_count,
            revisions=revisions,
            active_notebook=active_notebook,
            is_derived=active_notebook in derived_notebooks,
        )

    def replay(self, session_id: str) -> ReplayResult:
        """Explicitly replay notebook lineage into a fresh runtime."""
        with self.locks.acquire(session_id):
            manifest = self._read_manifest(session_id)
            notebook_path = self._notebook_path(manifest)
            if not notebook_path.exists():
                raise SessionNotFoundError(f"notebook not found for session: {session_id}")
            cells = self.notebook.read_cells(notebook_path)
            lineage = self._read_lineage(session_id, notebook_path)
            revision = self._next_revision(lineage)
            revision_path = notebook_path.parent / f"revision_{revision}.ipynb"
            shutil.copy2(notebook_path, revision_path)

            self.kernel.shutdown(session_id)
            try:
                self.kernel.start(session_id)
            except Exception as error:
                artifact = self._write_replay_error(session_id, -1, str(error))
                revision_path.unlink(missing_ok=True)
                manifest["status"] = "replay_failed"
                manifest["visualization_status"] = "visualization_absent"
                self._write_manifest(session_id, manifest)
                return ReplayResult(
                    session_id=session_id,
                    status="replay_failed",
                    new_revision=None,
                    failed_cell=None,
                    error_artifact=artifact,
                )
            manifest["visualization_status"] = "visualization_absent"
            self.notebook.clear_code_outputs(notebook_path)

            executor = ExecutionService(
                kernel=self.kernel,
                notebook=self.notebook,
                root_dir=self.root_dir,
            )
            for cell_index, cell in enumerate(cells):
                if cell.get("cell_type") != "code":
                    continue
                source = str(cell.get("source", ""))
                execution = self.kernel.execute(session_id, source)
                outputs = executor._notebook_outputs(execution)
                self.notebook.update_code_cell_outputs(
                    notebook_path,
                    cell_index,
                    outputs,
                    execution_count=cell_index,
                )
                if execution.error:
                    artifact = self._write_replay_error(session_id, cell_index, execution.error)
                    shutil.copy2(revision_path, notebook_path)
                    revision_path.unlink(missing_ok=True)
                    self.kernel.shutdown(session_id)
                    manifest["status"] = "replay_failed"
                    manifest["visualization_status"] = "visualization_absent"
                    self._write_manifest(session_id, manifest)
                    return ReplayResult(
                        session_id=session_id,
                        status="replay_failed",
                        new_revision=None,
                        failed_cell=cell_index,
                        error_artifact=artifact,
                    )

            lineage.setdefault("revisions", []).append(
                {
                    "revision": revision,
                    "created_at": self._now(),
                    "type": "replay",
                    "source": "active.ipynb",
                    "backup": revision_path.name,
                }
            )
            self._write_lineage(session_id, lineage)
            manifest["status"] = "active"
            manifest["notebook_revision"] = revision
            self._write_manifest(session_id, manifest)
            return ReplayResult(
                session_id=session_id,
                status="ok",
                new_revision=revision,
                failed_cell=None,
                error_artifact=None,
            )

    def derive(self, session_id: str) -> DerivationResult:
        """Create a derived notebook for a session."""
        with self.locks.acquire(session_id):
            manifest = self._read_manifest(session_id)
            source_path = self._notebook_path(manifest)
            if not source_path.exists():
                raise SessionNotFoundError(f"notebook not found for session: {session_id}")
            lineage = self._read_lineage(session_id, source_path)
            derived_path = self._next_derived_path(session_id, "derived")
            cells = self.notebook.read_cells(source_path)
            self.notebook.write_cells(
                derived_path,
                cells,
                metadata=self._lineage_notebook_metadata(session_id, source_path, "derive"),
            )
            relative_derived = self._relative_to_root(derived_path)
            lineage.setdefault("derived_notebooks", []).append(relative_derived)
            lineage.setdefault("revisions", []).append(
                {
                    "created_at": self._now(),
                    "type": "derive",
                    "source": self._relative_to_root(source_path),
                    "derived": relative_derived,
                    "cell_count": len(cells),
                }
            )
            self._write_lineage(session_id, lineage)
            manifest["notebook_path"] = relative_derived
            manifest["status"] = "active"
            self._write_manifest(session_id, manifest)
            return DerivationResult(
                session_id=session_id,
                derived_notebook_path=str(derived_path),
                source_notebook=str(source_path),
                active_notebook=str(derived_path),
            )

    def compact(self, session_id: str, cells_to_remove: list[int] | None = None) -> CompactionResult:
        """Compact notebook history for a session."""
        with self.locks.acquire(session_id):
            manifest = self._read_manifest(session_id)
            source_path = self._notebook_path(manifest)
            if not source_path.exists():
                raise SessionNotFoundError(f"notebook not found for session: {session_id}")
            cells = self.notebook.read_cells(source_path)
            remove_indexes = self._normalize_cells_to_remove(cells, cells_to_remove)
            compacted_cells = [cell for index, cell in enumerate(cells) if index not in remove_indexes]
            compacted_path = self._next_derived_path(session_id, "compacted")
            self.notebook.write_cells(
                compacted_path,
                compacted_cells,
                metadata=self._lineage_notebook_metadata(session_id, source_path, "compact"),
            )

            lineage = self._read_lineage(session_id, source_path)
            relative_compacted = self._relative_to_root(compacted_path)
            lineage.setdefault("derived_notebooks", []).append(relative_compacted)
            lineage.setdefault("revisions", []).append(
                {
                    "created_at": self._now(),
                    "type": "compact",
                    "source": self._relative_to_root(source_path),
                    "derived": relative_compacted,
                    "cells_removed": sorted(remove_indexes),
                    "cells_kept": len(compacted_cells),
                }
            )
            self._write_lineage(session_id, lineage)
            manifest["notebook_path"] = relative_compacted
            manifest["status"] = "active"
            self._write_manifest(session_id, manifest)
            return CompactionResult(
                session_id=session_id,
                compacted_notebook_path=str(compacted_path),
                cells_removed=len(remove_indexes),
                cells_kept=len(compacted_cells),
                source_notebook=str(source_path),
            )

    def _session_dir(self, session_id: str) -> Path:
        return self.root_dir / "sessions" / session_id

    def _read_manifest(self, session_id: str) -> dict[str, Any]:
        manifest_path = self._session_dir(session_id) / "manifest.json"
        if not manifest_path.exists():
            raise SessionNotFoundError(f"session not found: {session_id}")
        return json.loads(manifest_path.read_text())

    def _write_manifest(self, session_id: str, manifest: dict[str, Any]) -> None:
        path = self._session_dir(session_id) / "manifest.json"
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        tmp_path.replace(path)

    def _notebook_path(self, manifest: dict[str, Any]) -> Path:
        notebook_path = Path(str(manifest["notebook_path"]))
        if notebook_path.is_absolute():
            return notebook_path
        return self.root_dir / notebook_path

    def _lineage_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "lineage.json"

    def _read_lineage(self, session_id: str, notebook_path: Path) -> dict[str, Any]:
        path = self._lineage_path(session_id)
        if path.exists():
            return dict(json.loads(path.read_text()))
        lineage: dict[str, Any] = {
            "session_id": session_id,
            "source_notebook": self._relative_to_root(notebook_path),
            "derived_notebooks": [],
            "revisions": [],
        }
        return lineage

    def _write_lineage(self, session_id: str, lineage: dict[str, Any]) -> None:
        path = self._lineage_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n")
        tmp_path.replace(path)

    def _next_revision(self, lineage: dict[str, Any]) -> int:
        revisions = lineage.get("revisions", [])
        existing = [
            int(revision.get("revision", 0))
            for revision in revisions
            if isinstance(revision, dict)
        ]
        return max(existing, default=0) + 1

    def _next_derived_path(self, session_id: str, prefix: str) -> Path:
        notebooks_dir = self._session_dir(session_id) / "notebooks"
        notebooks_dir.mkdir(parents=True, exist_ok=True)
        index = 1
        while True:
            path = notebooks_dir / f"{prefix}_{index}.ipynb"
            if not path.exists():
                return path
            index += 1

    def _lineage_notebook_metadata(self, session_id: str, source_path: Path, operation: str) -> dict[str, Any]:
        return {
            "jupyter_workbench": {
                "lineage": {
                    "session_id": session_id,
                    "operation": operation,
                    "source_notebook": self._relative_to_root(source_path),
                    "created_at": self._now(),
                }
            }
        }

    def _normalize_cells_to_remove(
        self,
        cells: list[dict[str, Any]],
        cells_to_remove: list[int] | None,
    ) -> set[int]:
        if cells_to_remove is not None:
            invalid = [index for index in cells_to_remove if index < 0 or index >= len(cells)]
            if invalid:
                raise IndexError(f"cell index out of range: {invalid[0]}")
            return set(cells_to_remove)
        return self._dead_end_cell_indexes(cells)

    def _dead_end_cell_indexes(self, cells: list[dict[str, Any]]) -> set[int]:
        code_indexes = [index for index, cell in enumerate(cells) if cell.get("cell_type") == "code"]
        successful_code_after: set[int] = set()
        seen_success = False
        for index in reversed(code_indexes):
            if seen_success:
                successful_code_after.add(index)
            if not self._cell_has_error(cells[index]):
                seen_success = True
        return {
            index
            for index in code_indexes
            if self._cell_has_error(cells[index]) and index in successful_code_after
        }

    def _cell_has_error(self, cell: dict[str, Any]) -> bool:
        return any(
            isinstance(output, dict) and output.get("output_type") == "error"
            for output in cell.get("outputs", [])
        )

    def _revision_records(self, lineage: dict[str, Any]) -> list[dict[str, Any]]:
        return [dict(revision) for revision in lineage.get("revisions", []) if isinstance(revision, dict)]

    def _rooted_path(self, path: str) -> str:
        candidate = Path(path)
        if candidate.is_absolute():
            return str(candidate)
        return str(self.root_dir / candidate)

    def _write_replay_error(self, session_id: str, cell_index: int, content: str) -> str:
        output_dir = self._session_dir(session_id) / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"replay_failed_cell_{cell_index}.txt"
        tmp_path = path.with_suffix(".txt.tmp")
        tmp_path.write_text(content)
        tmp_path.replace(path)
        return str(path)

    def _relative_to_root(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root_dir))
        except ValueError:
            return str(path)

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
