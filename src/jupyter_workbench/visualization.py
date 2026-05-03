"""Convenience re-export surface for notebook code.

Usage:
    from jupyter_workbench.visualization import PyVistaDisplay
"""

from jupyter_workbench.adapters.visualization import (
    CameraTrackingExtension,
    PyVistaDisplay,
    SceneExtension,
    SceneHandle,
    VisualizationConfigError,
    VisualizationError,
    VisualizationExtensionError,
    VisualizationLaunchError,
)

__all__ = [
    "CameraTrackingExtension",
    "PyVistaDisplay",
    "SceneExtension",
    "SceneHandle",
    "VisualizationConfigError",
    "VisualizationError",
    "VisualizationExtensionError",
    "VisualizationLaunchError",
]
