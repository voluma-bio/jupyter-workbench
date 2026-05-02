"""Screenshot helpers intended to run inside a workbench kernel."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def capture_screenshot(
    session_id: str,
    root_dir: str | Path = ".jupyter-workbench",
    filename: str | None = None,
    plotter: Any | None = None,
) -> str:
    """Capture the current PyVista plotter to a durable screenshot artifact."""
    path = _screenshot_path(session_id, Path(root_dir), filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved_plotter = plotter if plotter is not None else _last_plotter()
    if resolved_plotter is None:
        raise RuntimeError("no PyVista plotter available; pass plotter=plotter")
    resolved_plotter.screenshot(str(path))
    if not path.exists():
        raise RuntimeError(f"screenshot was not created: {path}")
    return str(path)


def _screenshot_path(session_id: str, root_dir: Path, filename: str | None) -> Path:
    if filename is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"scene-{stamp}.png"
    if not filename.endswith(".png"):
        filename = f"{filename}.png"
    return root_dir / "sessions" / session_id / "visualizations" / "screenshots" / filename


def _last_plotter() -> Any | None:
    try:
        import pyvista as pv
    except Exception:
        return None
    plotter_cls = getattr(pv, "Plotter", None)
    candidate = getattr(plotter_cls, "last", None)
    if callable(candidate):
        try:
            return candidate()
        except Exception:
            return None
    return getattr(pv, "last_plotter", None)
