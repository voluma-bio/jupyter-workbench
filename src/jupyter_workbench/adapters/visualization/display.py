"""Public API for serving interactive PyVista scenes via trame-vtklocal."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .extensions import CameraTrackingExtension, SceneExtension
from .runtime import (
    DisplayConfig,
    SceneHandle,
    VisualizationConfigError,
    VtkLocalRuntime,
)


class PyVistaDisplay:
    """Fluent builder for serving a PyVista scene via trame-vtklocal.

    Usage:
        scene = PyVistaDisplay.for_session(session_id, plotter).show()
    """

    def __init__(
        self,
        session_id: str,
        plotter: Any,
        *,
        event_log: Any | None = None,
        root_dir: Path | None = None,
    ) -> None:
        self._session_id = session_id
        self._plotter = plotter
        self._event_log = event_log
        self._root_dir = root_dir
        self._title: str = "jupyter-workbench — vtklocal"
        self._port: int = 0
        self._bind_host: str = "0.0.0.0"
        self._public_host: str | None = None
        self._iframe_width: str = "100%"
        self._iframe_height: str = "600px"
        self._extensions: list[SceneExtension | Any] = []
        self._consumed: bool = False

    @classmethod
    def for_session(
        cls,
        session_id: str,
        plotter: Any,
        *,
        event_log: Any | None = None,
        root_dir: Path | None = None,
    ) -> PyVistaDisplay:
        """Create a builder for a session and plotter.

        Args:
            session_id: Required session identifier.
            plotter: A PyVista plotter with a render_window.
            event_log: Optional EventLogPort for extension logging.
            root_dir: Optional root dir for session artifacts.

        Raises:
            VisualizationConfigError: If plotter has no render_window.
        """
        render_window = getattr(plotter, "render_window", None)
        if render_window is None:
            raise VisualizationConfigError("plotter has no render_window")
        return cls(session_id, plotter, event_log=event_log, root_dir=root_dir)

    def title(self, title: str) -> PyVistaDisplay:
        """Set the scene title."""
        self._title = title
        return self

    def port(self, port: int) -> PyVistaDisplay:
        """Set an explicit port (default: 0 = OS-assigned)."""
        self._port = port
        return self

    def bind_host(self, host: str) -> PyVistaDisplay:
        """Set the server bind host (default: 0.0.0.0)."""
        self._bind_host = host
        return self

    def public_host(self, host: str) -> PyVistaDisplay:
        """Set the public URL host."""
        self._public_host = host
        return self

    def iframe_size(self, width: str, height: str) -> PyVistaDisplay:
        """Set iframe dimensions."""
        self._iframe_width = width
        self._iframe_height = height
        return self

    def track_camera(self, throttle_ms: int = 500) -> PyVistaDisplay:
        """Register camera tracking extension (syntax sugar for .use(CameraTrackingExtension(...))).

        Requires event_log to be set via for_session().
        """
        if self._event_log is None:
            from .runtime import VisualizationConfigError as _VCE

            raise _VCE("track_camera() requires event_log to be set via for_session()")
        ext = CameraTrackingExtension(event_log=self._event_log, throttle_ms=throttle_ms)
        self._extensions.append(ext)
        return self

    def use(self, extension: SceneExtension | Any) -> PyVistaDisplay:
        """Register a custom SceneExtension."""
        self._extensions.append(extension)
        return self

    def show(self, *, display: bool = True) -> SceneHandle:
        """Launch the scene. Consumes this builder.

        Args:
            display: If True (default), display the iframe inline via IPython.display.

        Returns:
            SceneHandle for lifecycle management.

        Raises:
            VisualizationConfigError: If .show() was already called.
            VisualizationLaunchError: If the server fails to start.
        """
        if self._consumed:
            raise VisualizationConfigError(
                "this builder has already been consumed by .show(); "
                "construct a new PyVistaDisplay for another scene"
            )
        self._consumed = True

        config = DisplayConfig(
            session_id=self._session_id,
            title=self._title,
            port=self._port,
            bind_host=self._bind_host,
            public_host=self._public_host,
            iframe_width=self._iframe_width,
            iframe_height=self._iframe_height,
        )

        runtime = VtkLocalRuntime()
        handle = runtime.launch(config, self._plotter, extensions=self._extensions)

        if display:
            from IPython.display import display as ipy_display  # pyright: ignore[reportMissingImports]

            ipy_display(handle.iframe)

        return handle
