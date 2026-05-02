"""Durable metadata helpers for PyVista + trame scenes."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from jupyter_workbench.core.interfaces import EventLogPort
from uuid import uuid4

URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+")
TRAME_MARKERS = ("trame", "wslink", "vtk", "pyvista", "jupyter-server-proxy")
LOGGER = logging.getLogger(__name__)


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
            "scene_revision": int(existing.get("scene_revision", -1)) + 1,
            "status": plotter_info.get("status") or "healthy",
            "updated_at": self._now(),
        }
        for key, value in plotter_info.items():
            if key not in manifest and value is not None:
                manifest[key] = value
        self._write_scene(session_id, resolved_viz_id, manifest)
        return manifest

    def register_pick_callback(self, session_id: str, plotter: Any, event_log: EventLogPort) -> None:
        """Register durable point and cell picking callbacks for a plotter."""

        def point_callback(point: Any, picker: Any | None = None) -> None:
            try:
                payload: dict[str, Any] = {"point": self._as_float_list(point)}
                point_id = self._picker_point_id(picker)
                if point_id is not None:
                    payload["point_id"] = point_id
                event_log.append("pick.point", payload)
            except Exception as exc:
                LOGGER.warning("failed to record point-pick event for %s: %s", session_id, exc)

        try:
            plotter.enable_point_picking(callback=point_callback, use_picker=True, show_message=False)
        except Exception as exc:
            LOGGER.warning("failed to register point-pick callback for %s: %s", session_id, exc)

        def cell_callback(mesh: Any) -> None:
            try:
                blocks = self._extract_cell_blocks(mesh)
                event_log.append("pick.cells", {"blocks": blocks})
            except Exception as exc:
                LOGGER.warning("failed to record cell-pick event for %s: %s", session_id, exc)

        try:
            plotter.enable_cell_picking(callback=cell_callback, through=False, show_message=False)
        except Exception as exc:
            LOGGER.warning("failed to register cell-pick callback for %s: %s", session_id, exc)

    def register_slider_callback(
        self,
        session_id: str,
        plotter: Any,
        event_log: EventLogPort,
        rng: tuple[float, float],
        label: str,
    ) -> Any:
        """Register a slider callback that skips PyVista's initial creation fire."""
        seen_initial = False

        def callback(value: Any) -> None:
            nonlocal seen_initial
            if not seen_initial:
                seen_initial = True
                return
            try:
                event_log.append("widget.slider", {"value": float(value), "label": label})
            except Exception as exc:
                LOGGER.warning("failed to record slider event for %s: %s", session_id, exc)

        return plotter.add_slider_widget(callback, rng=rng, title=label)

    def register_key_callback(self, session_id: str, plotter: Any, event_log: EventLogPort, keys: list[str] | None = None) -> None:
        """Register durable key logging using a generic VTK key observer."""

        def callback(obj: Any, _event: Any) -> None:
            try:
                key = obj.GetKeySym() if hasattr(obj, "GetKeySym") else None
                if key is None or (keys is not None and key not in keys):
                    return
                event_log.append("key", {"key": str(key)})
            except Exception as exc:
                LOGGER.warning("failed to record key event for %s: %s", session_id, exc)

        try:
            interactor = getattr(plotter, "iren", None) or getattr(plotter, "interactor", None)
            if interactor is None:
                return
            if hasattr(interactor, "add_observer"):
                interactor.add_observer("KeyPressEvent", callback)
            elif hasattr(interactor, "AddObserver"):
                interactor.AddObserver("KeyPressEvent", callback)
        except Exception as exc:
            LOGGER.warning("failed to register key callback for %s: %s", session_id, exc)

    def register_camera_callback(
        self,
        session_id: str,
        plotter: Any,
        event_log: EventLogPort,
        throttle_ms: int = 500,
    ) -> None:
        """Register throttled camera ModifiedEvent logging."""
        last_emit = 0.0
        last_payload: dict[str, Any] | None = None

        def callback(_obj: Any, _event: Any) -> None:
            nonlocal last_emit, last_payload
            try:
                camera = getattr(plotter, "camera", None)
                if camera is None:
                    return
                payload = {
                    "position": self._as_float_list(camera.GetPosition()),
                    "focal_point": self._as_float_list(camera.GetFocalPoint()),
                    "view_up": self._as_float_list(camera.GetViewUp()),
                }
                now = time.monotonic()
                if payload == last_payload or now - last_emit < throttle_ms / 1000:
                    return
                last_payload = payload
                last_emit = now
                event_log.append("camera.modified", payload)
            except Exception as exc:
                LOGGER.warning("failed to record camera event for %s: %s", session_id, exc)

        try:
            camera = getattr(plotter, "camera", None)
            if camera is not None and hasattr(camera, "AddObserver"):
                camera.AddObserver("ModifiedEvent", callback)
        except Exception as exc:
            LOGGER.warning("failed to register camera callback for %s: %s", session_id, exc)

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

    def _as_float_list(self, value: Any) -> list[float]:
        try:
            return [float(item) for item in value]
        except TypeError:
            return [float(value)]

    def _picker_point_id(self, picker: Any | None) -> int | None:
        if picker is None:
            return None
        for name in ("GetPointId", "point_id"):
            attr = getattr(picker, name, None)
            if attr is None:
                continue
            value = attr() if callable(attr) else attr
            try:
                point_id = int(cast(Any, value))
                if point_id >= 0:
                    return point_id
            except (TypeError, ValueError):
                continue
        return None

    def _extract_cell_blocks(self, mesh: Any) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        if hasattr(mesh, "items"):
            items = list(mesh.items())
        else:
            items = [(0, mesh)]
        for block_index, block in items:
            cell_ids = self._original_cell_ids(block)
            try:
                resolved_block_index = int(block_index)
            except (TypeError, ValueError):
                resolved_block_index = len(blocks)
            blocks.append({"block_index": resolved_block_index, "original_cell_ids": cell_ids})
        return blocks

    def _original_cell_ids(self, block: Any) -> list[int]:
        ids = None
        try:
            ids = block.cell_data.get("vtkOriginalCellIds") or block.cell_data.get("original_cell_ids")
        except Exception:
            ids = None
        if ids is None:
            return []
        return [int(value) for value in list(ids)]

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
