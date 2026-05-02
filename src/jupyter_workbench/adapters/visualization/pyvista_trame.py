"""Durable metadata helpers for PyVista + trame scenes."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+")
TRAME_MARKERS = ("trame", "wslink", "vtk", "pyvista", "jupyter-server-proxy")


class PyVistaTrameHelper:
    """Manage visualization metadata under a workbench session root."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or Path(".jupyter-workbench")

    def register_scene(
        self,
        session_id: str,
        viz_id: str | None,
        plotter_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist scene metadata and return the registered manifest."""
        resolved_viz_id = viz_id or str(plotter_info.get("viz_id") or f"scene-{uuid4().hex[:8]}")
        existing = self._read_scene(session_id, resolved_viz_id)
        manifest = {
            "viz_id": resolved_viz_id,
            "browser_url": plotter_info.get("browser_url") or existing.get("browser_url"),
            "scene_revision": int(existing.get("scene_revision", 0)),
            "status": plotter_info.get("status") or "healthy",
            "updated_at": self._now(),
        }
        for key, value in plotter_info.items():
            if key not in manifest and value is not None:
                manifest[key] = value
        self._write_scene(session_id, resolved_viz_id, manifest)
        return manifest

    def get_active_scene(self, session_id: str) -> dict[str, Any] | None:
        """Return the most recently updated non-absent scene for a session."""
        scenes = [scene for scene in self.list_scenes(session_id) if scene.get("status") != "absent"]
        if not scenes:
            return None
        return max(scenes, key=lambda scene: str(scene.get("updated_at", "")))

    def update_scene_revision(self, session_id: str, viz_id: str) -> dict[str, Any]:
        """Increment and persist a scene revision."""
        manifest = self._read_scene(session_id, viz_id)
        if not manifest:
            manifest = {"viz_id": viz_id, "browser_url": None, "status": "healthy"}
        manifest["scene_revision"] = int(manifest.get("scene_revision", 0)) + 1
        manifest["updated_at"] = self._now()
        self._write_scene(session_id, viz_id, manifest)
        return manifest

    def list_scenes(self, session_id: str) -> list[dict[str, Any]]:
        """Return all persisted scene manifests for a session."""
        manifests_dir = self._manifests_dir(session_id)
        scenes: list[dict[str, Any]] = []
        for path in sorted(manifests_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                scenes.append(data)
        return scenes

    def detect_scene_from_display_data(self, display_data: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Extract trame/PyVista URL metadata from Jupyter display payloads."""
        for payload in display_data:
            blob = json.dumps(payload, sort_keys=True, default=str)
            lowered = blob.lower()
            urls = URL_PATTERN.findall(blob)
            has_trame_marker = any(marker in lowered for marker in TRAME_MARKERS)
            has_iframe_url = bool(urls) and "iframe" in lowered
            if not has_trame_marker and not has_iframe_url:
                continue
            return {
                "viz_id": "active",
                "browser_url": urls[0].rstrip("\\") if urls else None,
                "status": "healthy" if urls else "degraded",
                "source": "jupyter_display_data",
            }
        return None

    def screenshot_paths(self, session_id: str) -> list[str]:
        """Return persisted screenshot artifact paths for a session."""
        screenshots_dir = self.root_dir / "sessions" / session_id / "visualizations" / "screenshots"
        if not screenshots_dir.exists():
            return []
        return [str(path) for path in sorted(screenshots_dir.glob("*.png"))]

    def _manifests_dir(self, session_id: str) -> Path:
        return self.root_dir / "sessions" / session_id / "visualizations" / "manifests"

    def _scene_path(self, session_id: str, viz_id: str) -> Path:
        return self._manifests_dir(session_id) / f"{viz_id}.json"

    def _read_scene(self, session_id: str, viz_id: str) -> dict[str, Any]:
        path = self._scene_path(session_id, viz_id)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_scene(self, session_id: str, viz_id: str, manifest: dict[str, Any]) -> None:
        path = self._scene_path(session_id, viz_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        tmp_path.replace(path)

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
