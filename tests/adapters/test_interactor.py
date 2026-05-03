from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from jupyter_workbench.adapters.visualization.interactor import ensure_render_window_interactor


class FakeTrackballStyle:
    pass


class FakeRenderWindowInteractor:
    def __init__(self) -> None:
        self.render_window: Any | None = None
        self.style: Any | None = None
        self.initialized = False
        self.enabled = False
        self.set_render_window_calls: list[Any] = []
        self.set_interactor_style_calls: list[Any] = []

    def SetRenderWindow(self, render_window: Any) -> None:
        self.render_window = render_window
        self.set_render_window_calls.append(render_window)

    def SetInteractorStyle(self, style: Any) -> None:
        self.style = style
        self.set_interactor_style_calls.append(style)

    def Initialize(self) -> None:
        self.initialized = True

    def Enable(self) -> None:
        self.enabled = True

    def GetInitialized(self) -> int:
        return int(self.initialized)

    def GetEnabled(self) -> int:
        return int(self.enabled)


class vtkGenericRenderWindowInteractor:
    def GetInitialized(self) -> int:
        return 0

    def GetEnabled(self) -> int:
        return 0


class ConcreteInteractor:
    def __init__(self, *, initialized: bool = True, enabled: bool = True) -> None:
        self.initialized = initialized
        self.enabled = enabled

    def GetInitialized(self) -> int:
        return int(self.initialized)

    def GetEnabled(self) -> int:
        return int(self.enabled)


class FakeRenderWindow:
    def __init__(self, interactor: Any | None) -> None:
        self.interactor = interactor

    def GetInteractor(self) -> Any | None:
        return self.interactor


class FakePlotter:
    def __init__(self, render_window: Any | None) -> None:
        self.render_window = render_window


@pytest.fixture(autouse=True)
def fake_vtk_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_style_module = types.ModuleType("vtkmodules.vtkInteractionStyle")
    fake_render_module = types.ModuleType("vtkmodules.vtkRenderingCore")
    fake_style_module.vtkInteractorStyleTrackballCamera = FakeTrackballStyle
    fake_render_module.vtkRenderWindowInteractor = FakeRenderWindowInteractor
    monkeypatch.setitem(sys.modules, "vtkmodules.vtkInteractionStyle", fake_style_module)
    monkeypatch.setitem(sys.modules, "vtkmodules.vtkRenderingCore", fake_render_module)


def assert_replacement_metadata(
    metadata: dict[str, Any],
    *,
    old_interactor: Any | None,
    old_type: str | None,
    render_window: FakeRenderWindow,
) -> FakeRenderWindowInteractor:
    assert metadata["changed"] is True
    assert metadata["old_interactor"] is old_interactor
    assert metadata["old_type"] == old_type

    new_interactor = metadata["new_interactor"]
    assert isinstance(new_interactor, FakeRenderWindowInteractor)
    assert new_interactor is not old_interactor
    assert new_interactor.render_window is render_window
    assert new_interactor.set_render_window_calls == [render_window]
    assert len(new_interactor.set_interactor_style_calls) == 1
    assert new_interactor.initialized is True
    assert new_interactor.enabled is True
    return new_interactor


def test_replacement_when_generic_interactor() -> None:
    old = vtkGenericRenderWindowInteractor()
    render_window = FakeRenderWindow(old)
    metadata = ensure_render_window_interactor(FakePlotter(render_window))

    assert_replacement_metadata(
        metadata,
        old_interactor=old,
        old_type="vtkGenericRenderWindowInteractor",
        render_window=render_window,
    )


def test_replacement_when_none_interactor() -> None:
    render_window = FakeRenderWindow(None)
    metadata = ensure_render_window_interactor(FakePlotter(render_window))

    assert_replacement_metadata(
        metadata,
        old_interactor=None,
        old_type=None,
        render_window=render_window,
    )


def test_noop_when_concrete_initialized_enabled() -> None:
    old = ConcreteInteractor(initialized=True, enabled=True)
    metadata = ensure_render_window_interactor(FakePlotter(FakeRenderWindow(old)))

    assert metadata == {
        "changed": False,
        "old_interactor": old,
        "new_interactor": old,
        "old_type": "ConcreteInteractor",
    }


def test_replacement_when_not_initialized() -> None:
    old = ConcreteInteractor(initialized=False, enabled=True)
    render_window = FakeRenderWindow(old)
    metadata = ensure_render_window_interactor(FakePlotter(render_window))

    assert_replacement_metadata(
        metadata,
        old_interactor=old,
        old_type="ConcreteInteractor",
        render_window=render_window,
    )


def test_replacement_when_not_enabled() -> None:
    old = ConcreteInteractor(initialized=True, enabled=False)
    render_window = FakeRenderWindow(old)
    metadata = ensure_render_window_interactor(FakePlotter(render_window))

    assert_replacement_metadata(
        metadata,
        old_interactor=old,
        old_type="ConcreteInteractor",
        render_window=render_window,
    )


@pytest.mark.parametrize("plotter", [object(), FakePlotter(None)])
def test_missing_render_window_raises(plotter: Any) -> None:
    with pytest.raises(RuntimeError, match="plotter has no render_window"):
        ensure_render_window_interactor(plotter)


def test_plotter_iren_not_mutated() -> None:
    class PlotterWithForbiddenIren:
        def __init__(self) -> None:
            self.render_window = FakeRenderWindow(vtkGenericRenderWindowInteractor())

        @property
        def iren(self) -> Any:
            raise AssertionError("iren should not be touched")

    metadata = ensure_render_window_interactor(PlotterWithForbiddenIren())

    assert metadata["changed"] is True


def test_trackball_camera_style_set() -> None:
    render_window = FakeRenderWindow(vtkGenericRenderWindowInteractor())
    metadata = ensure_render_window_interactor(FakePlotter(render_window))

    assert isinstance(metadata["new_interactor"].style, FakeTrackballStyle)


def test_metadata_dict_shape() -> None:
    replacement_metadata = ensure_render_window_interactor(
        FakePlotter(FakeRenderWindow(vtkGenericRenderWindowInteractor()))
    )
    noop_metadata = ensure_render_window_interactor(
        FakePlotter(FakeRenderWindow(ConcreteInteractor()))
    )

    assert set(replacement_metadata) == {
        "changed",
        "old_interactor",
        "new_interactor",
        "old_type",
    }
    assert set(noop_metadata) == {
        "changed",
        "old_interactor",
        "new_interactor",
        "old_type",
    }
