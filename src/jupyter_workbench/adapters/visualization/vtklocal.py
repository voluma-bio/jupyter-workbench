"""Helpers for VTK.wasm-backed trame local rendering."""

from __future__ import annotations

from typing import Any, Callable


def resolve_public_host(bind_host: str, public_host: str | None = None) -> str:
    """Resolve the host to embed in a browser-facing URL."""
    if public_host:
        return public_host
    if bind_host == "0.0.0.0":
        return "127.0.0.1"
    return bind_host


def make_server_ready_update(view: Any) -> Callable[..., None]:
    """Return an on_server_ready callback that ignores trame state kwargs."""

    def callback(**_: Any) -> None:
        view.update()

    return callback


def launch_vtklocal_view(
    plotter: Any,
    *,
    server_name: str = "jupyter-workbench-vtklocal",
    title: str = "jupyter-workbench — vtklocal",
    bind_host: str = "0.0.0.0",
    public_host: str | None = None,
    port: int = 9000,
    iframe_width: str = "100%",
    iframe_height: str = "600px",
    progress: Callable[[dict[str, Any]], None] | None = None,
    progress_delay: int = 500,
    display_view: bool = True,
) -> dict[str, Any]:
    """Launch a trame-vtklocal scene for a PyVista plotter and optionally display an iframe.

    This is a compatibility shim that delegates to VtkLocalRuntime. The returned
    dict shape is preserved for backward compatibility.
    """
    from IPython.display import display as ipy_display  # pyright: ignore[reportMissingImports]

    from .runtime import DisplayConfig, VtkLocalRuntime

    config = DisplayConfig(
        session_id=server_name,
        title=title,
        port=port,
        bind_host=bind_host,
        public_host=public_host,
        iframe_width=iframe_width,
        iframe_height=iframe_height,
        progress_delay=progress_delay,
    )

    runtime = VtkLocalRuntime()
    handle = runtime.launch(config, plotter)

    if display_view:
        ipy_display(handle.iframe)

    return {
        "url": handle.url,
        "bind_host": bind_host,
        "public_host": resolve_public_host(bind_host, public_host),
        "port": handle.port,
        "server_name": handle.viz_id,
        "iframe": handle.iframe,
        "task": handle.task,
        "server": handle.server,
        "view": handle.view,
        "interactor_fix": handle.interactor_fix,
    }
