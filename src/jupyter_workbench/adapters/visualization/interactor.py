"""Render-window interactor normalization helpers for local VTK rendering."""

from __future__ import annotations

from typing import Any


def ensure_render_window_interactor(plotter: Any) -> dict[str, Any]:
    """Ensure the render window has a concrete initialized interactor for vtklocal.

    Replaces vtkGenericRenderWindowInteractor (or None) with a real
    vtkRenderWindowInteractor with TrackballCamera style. Does NOT mutate
    plotter.iren — only the render window's interactor is replaced.

    Returns metadata dict: changed, old_interactor, new_interactor, old_type.
    """
    from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
    from vtkmodules.vtkRenderingCore import vtkRenderWindowInteractor

    render_window = getattr(plotter, "render_window", None)
    if render_window is None:
        raise RuntimeError("plotter has no render_window")

    old_interactor = render_window.GetInteractor()
    old_type = type(old_interactor).__name__ if old_interactor is not None else None
    old_initialized = bool(old_interactor and old_interactor.GetInitialized())
    old_enabled = bool(old_interactor and old_interactor.GetEnabled())

    # No-op when the render window already has a concrete live interactor.
    if (
        old_interactor is not None
        and old_type != "vtkGenericRenderWindowInteractor"
        and old_initialized
        and old_enabled
    ):
        return {
            "changed": False,
            "old_interactor": old_interactor,
            "new_interactor": old_interactor,
            "old_type": old_type,
        }

    new_interactor = vtkRenderWindowInteractor()
    new_interactor.SetRenderWindow(render_window)
    new_interactor.SetInteractorStyle(vtkInteractorStyleTrackballCamera())
    new_interactor.Initialize()
    new_interactor.Enable()

    return {
        "changed": True,
        "old_interactor": old_interactor,
        "new_interactor": new_interactor,
        "old_type": old_type,
    }
