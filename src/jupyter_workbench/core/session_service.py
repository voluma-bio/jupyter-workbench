"""Session lifecycle service."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from jupyter_workbench.core.interfaces import KernelPort, NotebookPort
from jupyter_workbench.core.models import SessionInfo, SessionList
from jupyter_workbench.core.session_lock import SessionLock


class SessionNotFoundError(FileNotFoundError):
    """Raised when a requested workbench session does not exist."""


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
        self.locks = SessionLock(self.root_dir)

    def open(self, session_id: str | None = None) -> SessionInfo:
        """Open or attach to a workbench session."""
        resolved_session_id = session_id or uuid4().hex[:8]
        manifest_path = self._manifest_path(resolved_session_id)
        if manifest_path.exists():
            manifest = self._read_manifest(resolved_session_id)
            manifest_status = str(manifest.get("status", "active"))
            if manifest_status == "closed":
                return self._start_existing_session(resolved_session_id, manifest)
            if manifest_status in {"close_failed", "creating", "create_failed", "replay_failed"}:
                self.kernel.shutdown(resolved_session_id)
                return self._start_existing_session(resolved_session_id, manifest)
            if self._is_kernel_alive(resolved_session_id):
                manifest["status"] = "active"
                return self._info_from_manifest(manifest, "active")
            manifest["status"] = "kernel_degraded"
            return self._info_from_manifest(manifest, "kernel_degraded")

        with self.locks.acquire(resolved_session_id):
            if manifest_path.exists():
                manifest = self._read_manifest(resolved_session_id)
                if self._is_kernel_alive(resolved_session_id):
                    manifest["status"] = "active"
                    return self._info_from_manifest(manifest, "active")
                manifest["status"] = "kernel_degraded"
                return self._info_from_manifest(manifest, "kernel_degraded")
            session_dir = self._session_dir(resolved_session_id)
            notebook_path = session_dir / "notebooks" / "active.ipynb"
            self._create_layout(session_dir)
            self.notebook.create(notebook_path)
            manifest = {
                "session_id": resolved_session_id,
                "root_dir": str(self.root_dir),
                "notebook_path": self._relative_to_root(notebook_path),
                "created_at": self._now(),
                "status": "creating",
                "visualization_status": "visualization_absent",
                "notebook_revision": 0,
            }
            self._write_manifest(resolved_session_id, manifest)
            self._write_initial_lineage(resolved_session_id, notebook_path)
            try:
                self.kernel.start(resolved_session_id)
            except Exception:
                manifest["status"] = "create_failed"
                self._write_manifest(resolved_session_id, manifest)
                self.kernel.shutdown(resolved_session_id)
                raise
            manifest["status"] = "active"
            self._write_manifest(resolved_session_id, manifest)
            return self._info_from_manifest(manifest, "active")

    def close(self, session_id: str) -> SessionInfo:
        """Close live resources for a session while preserving artifacts."""
        with self.locks.acquire(session_id):
            manifest = self._read_manifest(session_id)
            shutdown_succeeded = self.kernel.shutdown(session_id)
            if shutdown_succeeded:
                manifest["status"] = "closed"
                warning = None
            else:
                manifest["status"] = "close_failed"
                warning = "kernel shutdown failed; session resources may still be running"
            manifest["visualization_status"] = "visualization_absent"
            self._write_manifest(session_id, manifest)
            return self._info_from_manifest(manifest, str(manifest["status"]), warning=warning)

    def status(self, session_id: str) -> SessionInfo:
        """Return status for one session."""
        manifest = self._read_manifest(session_id)
        manifest_status = str(manifest.get("status", "active"))
        if manifest_status == "closed":
            kernel_status = "closed"
        elif manifest_status in {"creating", "create_failed", "replay_failed"}:
            kernel_status = manifest_status
        elif self._is_kernel_alive(session_id):
            kernel_status = "active"
        else:
            kernel_status = "kernel_degraded"
        return self._info_from_manifest(manifest, kernel_status)

    def list(self) -> SessionList:
        """List sessions under the configured root."""
        sessions_dir = self.root_dir / "sessions"
        if not sessions_dir.exists():
            return SessionList(sessions=[])
        sessions: list[SessionInfo] = []
        for manifest_path in sorted(sessions_dir.glob("*/manifest.json")):
            try:
                sessions.append(self.status(manifest_path.parent.name))
            except (OSError, json.JSONDecodeError, KeyError):
                continue
        return SessionList(sessions=sessions)

    @staticmethod
    def resolve_session_id(root_dir: Path, session_id: str | None = None) -> str:
        """Resolve an explicit or most-recent active session id."""
        if session_id is not None:
            return session_id
        sessions_dir = root_dir / "sessions"
        candidates: list[tuple[float, str]] = []
        for manifest_path in sessions_dir.glob("*/manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if str(manifest.get("status")) == "closed":
                continue
            candidates.append((manifest_path.stat().st_mtime, manifest_path.parent.name))
        if not candidates:
            raise SessionNotFoundError("no active sessions found; pass --session-id or run 'jupyter-workbench open'")
        return max(candidates)[1]

    def _create_layout(self, session_dir: Path) -> None:
        (session_dir / "notebooks").mkdir(parents=True, exist_ok=True)
        (session_dir / "outputs").mkdir(parents=True, exist_ok=True)
        (session_dir / "visualizations" / "manifests").mkdir(parents=True, exist_ok=True)
        (session_dir / "visualizations" / "screenshots").mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        return self.root_dir / "sessions" / session_id

    def _manifest_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "manifest.json"

    def _start_existing_session(self, session_id: str, manifest: dict[str, Any]) -> SessionInfo:
        """Start a fresh kernel for a session with an existing manifest."""
        manifest["status"] = "creating"
        manifest["visualization_status"] = "visualization_absent"
        self._write_manifest(session_id, manifest)
        try:
            self.kernel.start(session_id)
        except Exception:
            manifest["status"] = "create_failed"
            self._write_manifest(session_id, manifest)
            self.kernel.shutdown(session_id)
            raise
        manifest["status"] = "active"
        self._write_manifest(session_id, manifest)
        return self._info_from_manifest(manifest, "active")

    def _read_manifest(self, session_id: str) -> dict[str, Any]:
        manifest_path = self._manifest_path(session_id)
        if not manifest_path.exists():
            raise SessionNotFoundError(f"session not found: {session_id}")
        return json.loads(manifest_path.read_text())

    def _write_manifest(self, session_id: str, manifest: dict[str, Any]) -> None:
        manifest_path = self._manifest_path(session_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = manifest_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        tmp_path.replace(manifest_path)

    def _write_initial_lineage(self, session_id: str, notebook_path: Path) -> None:
        lineage_path = self._session_dir(session_id) / "lineage.json"
        lineage = {
            "session_id": session_id,
            "source_notebook": self._relative_to_root(notebook_path),
            "derived_notebooks": [],
            "revisions": [],
        }
        tmp_path = lineage_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n")
        tmp_path.replace(lineage_path)

    def _info_from_manifest(
        self,
        manifest: dict[str, Any],
        kernel_status: str,
        warning: str | None = None,
    ) -> SessionInfo:
        return SessionInfo(
            session_id=str(manifest["session_id"]),
            root_dir=str(manifest.get("root_dir", self.root_dir)),
            notebook_path=str(self.root_dir / str(manifest["notebook_path"])),
            kernel_status=kernel_status,
            visualization_status=str(manifest.get("visualization_status", "visualization_absent")),
            created_at=str(manifest["created_at"]),
            warning=warning,
        )

    def _is_kernel_alive(self, session_id: str) -> bool:
        try:
            return self.kernel.probe_alive(session_id)
        except Exception:
            return False

    def _relative_to_root(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root_dir))
        except ValueError:
            return str(path)

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def session_info_dict(info: SessionInfo) -> dict[str, Any]:
    """Return a serializable representation of a session DTO."""
    return asdict(info)
