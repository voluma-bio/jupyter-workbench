"""Machine-readable snapshot service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jupyter_workbench.core.interfaces import EventLogPort, KernelPort, NotebookPort, VisualizationPort
from jupyter_workbench.core.models import SnapshotResult
from jupyter_workbench.core.session_service import SessionNotFoundError


class SnapshotService:
    """Transport-agnostic session observation operations."""

    def __init__(
        self,
        notebook: NotebookPort,
        kernel: KernelPort | None = None,
        root_dir: Path | None = None,
        visualization: VisualizationPort | None = None,
        event_log: EventLogPort | None = None,
    ) -> None:
        self.notebook = notebook
        self.kernel = kernel
        self.root_dir = root_dir or Path(".jupyter-workbench")
        self.visualizations = visualization
        self.event_log = event_log

    def snapshot(self, session_id: str | None = None) -> SnapshotResult:
        """Return a machine-readable snapshot for a session."""
        resolved_session_id = self._resolve_session_id(session_id)
        manifest = self._read_manifest(resolved_session_id)
        notebook_path = self._notebook_path(manifest)
        cells = self.notebook.read_cells(notebook_path)
        kernel_status = self._kernel_status(resolved_session_id, manifest)
        visualization_summary = self._visualization_summary(resolved_session_id, manifest)
        return SnapshotResult(
            session_id=resolved_session_id,
            root_dir=str(self.root_dir),
            kernel_status=kernel_status,
            visualization_status=str(visualization_summary["status"]),
            notebook_path=str(notebook_path),
            cell_count=len(cells),
            recent_outputs=self._recent_outputs(cells[-5:], len(cells) - min(len(cells), 5)),
            visualization_summary=visualization_summary,
            lineage_summary={
                "active_notebook": str(notebook_path),
                "revision": manifest.get("notebook_revision", 0),
                "source_notebook": str(notebook_path),
            },
            event_summary=self._event_summary(resolved_session_id),
        )


    def _visualization_summary(
        self,
        session_id: str,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        if self.visualizations is None:
            scenes: list[dict[str, Any]] = []
            screenshots: list[str] = []
            active = None
            degraded = False
        else:
            scenes = self.visualizations.list_scenes(session_id)
            screenshots = self.visualizations.screenshot_paths(session_id)
            active = self.visualizations.get_active_scene(session_id)
            degraded = self.visualizations.detect_degradation(session_id)
        status = str(manifest.get("visualization_status", "visualization_absent"))
        if degraded:
            status = "visualization_degraded"
        degraded_scenes = [scene for scene in scenes if scene.get("status") == "degraded"]
        summary: dict[str, Any] = {
            "status": status,
            "active_scene": active,
            "items": scenes,
            "degraded_scenes": degraded_scenes,
            "screenshots": screenshots,
            "scene_revision": active.get("scene_revision") if active else None,
        }
        if degraded:
            summary["recovery_guidance"] = (
                "re-execute scene setup code through jupyter-workbench exec to reconstruct"
            )
        return summary

    def _event_summary(self, session_id: str) -> dict[str, Any]:
        if self.event_log is None:
            return {
                "recent_events": [],
                "total_event_count": 0,
                "cursor": 0,
            }
        events, cursor = self.event_log.for_session(session_id).read(0)
        return {
            "recent_events": events[-10:],
            "total_event_count": len(events),
            "cursor": cursor,
        }

    def _recent_outputs(self, cells: list[dict[str, Any]], start_index: int) -> list[dict[str, Any]]:
        recent: list[dict[str, Any]] = []
        for offset, cell in enumerate(cells):
            index = start_index + offset
            cell_type = str(cell.get("cell_type", "unknown"))
            summary: dict[str, Any] = {"cell_index": index, "cell_type": cell_type}
            if cell_type == "code":
                outputs = cell.get("outputs", [])
                summary["status"] = "error" if any(o.get("output_type") == "error" for o in outputs) else "ok"
                summary["summary"] = self._bounded_cell_summary(outputs)
                summary["artifact_refs"] = self._artifact_refs(index)
                metadata = cell.get("metadata", {})
                if metadata:
                    summary["metadata"] = metadata
            else:
                source = str(cell.get("source", ""))
                summary["summary"] = source[:512]
                summary["artifact_refs"] = []
            recent.append(summary)
        return recent

    def _bounded_cell_summary(self, outputs: Any) -> str:
        parts: list[str] = []
        if isinstance(outputs, list):
            for output in outputs:
                if not isinstance(output, dict):
                    continue
                output_type = output.get("output_type")
                if output_type == "stream":
                    parts.append(str(output.get("text", "")))
                elif output_type in {"display_data", "execute_result"}:
                    parts.append(json.dumps(output.get("data", {}), sort_keys=True))
                elif output_type == "error":
                    parts.append("\n".join(str(line) for line in output.get("traceback", [])))
        text = "\n".join(part for part in parts if part)
        encoded = text.encode("utf-8")
        if len(encoded) <= 4096:
            return text
        return encoded[:4096].decode("utf-8", errors="ignore") + "\n[truncated]"

    def _artifact_refs(self, cell_index: int) -> list[str]:
        output_dir = self.root_dir / "sessions" / self._current_session_id / "outputs"
        if not output_dir.exists():
            return []
        return [str(path) for path in sorted(output_dir.glob(f"cell_{cell_index}_*"))]

    def _kernel_status(self, session_id: str, manifest: dict[str, Any]) -> str:
        manifest_status = str(manifest.get("status", "active"))
        if manifest_status == "closed":
            return "closed"
        if self.kernel is None:
            return manifest_status
        try:
            return "active" if self.kernel.probe_alive(session_id) else "kernel_degraded"
        except Exception:
            return "kernel_degraded"

    def _resolve_session_id(self, session_id: str | None) -> str:
        if session_id is not None:
            self._current_session_id = session_id
            return session_id
        sessions_dir = self.root_dir / "sessions"
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
        resolved = max(candidates)[1]
        self._current_session_id = resolved
        return resolved

    def _read_manifest(self, session_id: str) -> dict[str, Any]:
        manifest_path = self.root_dir / "sessions" / session_id / "manifest.json"
        if not manifest_path.exists():
            raise SessionNotFoundError(f"session not found: {session_id}")
        return json.loads(manifest_path.read_text())

    def _notebook_path(self, manifest: dict[str, Any]) -> Path:
        notebook_path = Path(str(manifest["notebook_path"]))
        if notebook_path.is_absolute():
            return notebook_path
        return self.root_dir / notebook_path
