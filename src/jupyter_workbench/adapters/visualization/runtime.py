"""Launch orchestration for VTK.wasm-backed trame local rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count as _count
from typing import Any

_server_counter = _count(1)


def _next_server_id() -> int:
    return next(_server_counter)


class VisualizationError(Exception):
    """Base visualization error."""


class VisualizationConfigError(VisualizationError):
    """Invalid builder/configuration state."""


class VisualizationLaunchError(VisualizationError):
    """Server/interactor startup failure."""


class VisualizationExtensionError(VisualizationError):
    """Extension hook failure."""


@dataclass(frozen=True)
class DisplayConfig:
    session_id: str
    title: str = "jupyter-workbench — vtklocal"
    port: int = 0
    bind_host: str = "0.0.0.0"
    public_host: str | None = None
    iframe_width: str = "100%"
    iframe_height: str = "600px"
    progress_delay: int = 500


@dataclass
class SceneHandle:
    url: str
    port: int
    view: Any
    server: Any
    iframe: Any
    task: Any
    session_id: str
    viz_id: str
    interactor_fix: dict[str, Any]
    _extensions: list[Any] = field(default_factory=list, repr=False)
    _closed: bool = field(default=False, repr=False)

    def refresh(self) -> None:
        """Call view.update() to sync browser display."""
        self.view.update()

    def close(self) -> None:
        """Initiate server shutdown without blocking."""
        if self._closed:
            return
        self._closed = True
        self._close_extensions()

        import asyncio
        import warnings

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._async_stop())
            else:
                warnings.warn(
                    "no running event loop for server.stop(); server may not shut down cleanly",
                    stacklevel=2,
                )
        except Exception as exc:
            warnings.warn(f"failed to schedule server shutdown: {exc}", stacklevel=2)

    async def aclose(self) -> None:
        """Await full server shutdown."""
        if self._closed:
            return
        self._closed = True
        self._close_extensions()
        await self._async_stop()

    async def _async_stop(self) -> None:
        import warnings

        try:
            await self.server.stop()
        except Exception as exc:
            warnings.warn(f"server stop failed: {exc}", stacklevel=2)

    def _close_extensions(self) -> None:
        for ext in reversed(self._extensions):
            try:
                if hasattr(ext, "close"):
                    ext.close(self)
            except Exception:
                pass

    def __enter__(self) -> SceneHandle:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    async def __aenter__(self) -> SceneHandle:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()


class VtkLocalRuntime:
    """Launch orchestrator for trame-vtklocal scenes."""

    def launch(self, config: DisplayConfig, plotter: Any, extensions: list[Any] | None = None) -> SceneHandle:
        """Execute the full launch sequence and return a SceneHandle."""
        from IPython.display import IFrame  # pyright: ignore[reportMissingImports]
        from trame.app import get_server  # pyright: ignore[reportMissingImports]
        from trame.ui.vuetify3 import SinglePageLayout  # pyright: ignore[reportMissingImports]
        from trame.widgets import vtklocal  # pyright: ignore[reportMissingImports]

        from .interactor import ensure_render_window_interactor
        from .vtklocal import make_server_ready_update, resolve_public_host

        exts = extensions or []

        plotter.render()
        interactor_fix = ensure_render_window_interactor(plotter)

        server_name = f"jw-{config.session_id}-{_next_server_id()}"
        server: Any = get_server(server_name)

        with SinglePageLayout(server) as layout:
            layout.title.set_text(config.title)
            with layout.content:
                kwargs: dict[str, Any] = {"progress_delay": config.progress_delay}
                view = vtklocal.LocalView(plotter.render_window, **kwargs)
                server.controller.on_server_ready.add(make_server_ready_update(view))

        build_ctx = {
            "plotter": plotter,
            "render_window": plotter.render_window,
            "session_id": config.session_id,
            "config": config,
        }
        self._call_extension_hook(exts, "prepare", build_ctx)

        runtime_ctx = {
            **build_ctx,
            "view": view,
            "server": server,
        }
        self._call_extension_hook(exts, "bind_view", runtime_ctx)

        try:
            task = server.start(
                exec_mode="task",
                host=config.bind_host,
                port=config.port,
            )
        except Exception as exc:
            raise VisualizationLaunchError(f"trame server failed to start: {exc}") from exc

        actual_port = self._resolve_actual_port(config, server)
        public_host = resolve_public_host(config.bind_host, config.public_host)
        viz_id = f"{config.session_id}-{server_name}"
        url = f"http://{public_host}:{actual_port}/"
        iframe = IFrame(src=url, width=config.iframe_width, height=config.iframe_height)

        handle = SceneHandle(
            url=url,
            port=actual_port,
            view=view,
            server=server,
            iframe=iframe,
            task=task,
            session_id=config.session_id,
            viz_id=viz_id,
            interactor_fix=interactor_fix,
            _extensions=exts,
        )

        self._call_extension_hook(exts, "after_start", handle)
        return handle

    def _resolve_actual_port(self, config: DisplayConfig, server: Any) -> int:
        actual_port = config.port
        if config.port == 0:
            actual_port = getattr(server, "port", None) or config.port
            if actual_port == 0:
                state = getattr(server, "state", None)
                if state and hasattr(state, "port"):
                    actual_port = state.port
        return actual_port

    def _call_extension_hook(self, extensions: list[Any], hook_name: str, context: Any) -> None:
        import warnings

        for ext in extensions:
            try:
                if hasattr(ext, hook_name):
                    getattr(ext, hook_name)(context)
            except Exception as exc:
                critical = getattr(ext, "critical", False)
                if critical:
                    raise VisualizationExtensionError(
                        f"critical extension {getattr(ext, 'name', ext)} failed in {hook_name}: {exc}"
                    ) from exc
                warnings.warn(
                    f"extension {getattr(ext, 'name', ext)} {hook_name} failed: {exc}",
                    stacklevel=2,
                )
