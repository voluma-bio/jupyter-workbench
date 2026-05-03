"""Extension protocol and built-in extensions for PyVista display scenes."""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class BuildContext:
    """State available during the prepare phase."""

    plotter: Any
    render_window: Any
    session_id: str
    config: Any  # DisplayConfig


@dataclass
class RuntimeContext(BuildContext):
    """State available during bind_view phase."""

    view: Any  # trame LocalView
    server: Any  # trame server


@runtime_checkable
class SceneExtension(Protocol):
    """Lifecycle hooks for scene extensions."""

    name: str
    critical: bool  # if True, hook failure aborts launch

    def prepare(self, ctx: BuildContext) -> None:
        """Called after interactor fix, before LocalView creation."""
        ...

    def bind_view(self, ctx: RuntimeContext) -> None:
        """Called after LocalView creation, before server start."""
        ...

    def after_start(self, handle: Any) -> None:
        """Called after server is running."""
        ...

    def close(self, handle: Any) -> None:
        """Called during handle.close(), reverse order."""
        ...


class CameraTrackingExtension:
    """Logs throttled camera.modified events to the session event log.

    Non-critical: failures log warnings but do not abort launch.
    """

    name: str = "camera_tracking"
    critical: bool = False

    def __init__(self, event_log: Any, throttle_ms: int = 500) -> None:
        self._event_log = event_log
        self._throttle_ms = throttle_ms
        self._last_emit: float = 0.0
        self._last_payload: dict[str, Any] | None = None
        self._observer_id: Any = None

    def prepare(self, ctx: BuildContext) -> None:
        """No-op — camera tracking is set up during bind_view."""

    def bind_view(self, ctx: RuntimeContext) -> None:
        """Register a throttled camera.modified observer on the plotter's camera."""
        try:
            camera = getattr(ctx.plotter, "camera", None)
            if camera is None:
                warnings.warn(
                    "camera_tracking: plotter has no camera attribute",
                    stacklevel=2,
                )
                return
            if not hasattr(camera, "AddObserver"):
                warnings.warn(
                    "camera_tracking: camera does not support AddObserver",
                    stacklevel=2,
                )
                return

            def on_modified(_obj: Any, _event: Any) -> None:
                try:
                    self._handle_camera_event(ctx.plotter)
                except Exception as exc:
                    warnings.warn(f"camera_tracking: event handler error: {exc}", stacklevel=2)

            self._observer_id = camera.AddObserver("ModifiedEvent", on_modified)
        except Exception as exc:
            warnings.warn(f"camera_tracking: failed to register observer: {exc}", stacklevel=2)

    def after_start(self, handle: Any) -> None:
        """No-op."""

    def close(self, handle: Any) -> None:
        """No-op — observer lifetime tied to camera object."""

    def _handle_camera_event(self, plotter: Any) -> None:
        """Throttle and deduplicate camera events before logging."""
        camera = getattr(plotter, "camera", None)
        if camera is None:
            return

        payload = {
            "position": self._as_float_list(camera.GetPosition()),
            "focal_point": self._as_float_list(camera.GetFocalPoint()),
            "view_up": self._as_float_list(camera.GetViewUp()),
        }

        now = time.monotonic()
        if payload == self._last_payload:
            return  # duplicate suppression
        if now - self._last_emit < self._throttle_ms / 1000:
            return  # throttle

        self._last_payload = payload
        self._last_emit = now
        self._event_log.append("camera.modified", payload)

    def _as_float_list(self, value: Any) -> list[float]:
        try:
            return [float(item) for item in value]
        except TypeError:
            return [float(value)]
