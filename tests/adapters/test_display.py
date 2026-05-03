from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from jupyter_workbench.adapters.visualization.display import PyVistaDisplay
from jupyter_workbench.adapters.visualization.extensions import CameraTrackingExtension
from jupyter_workbench.adapters.visualization.runtime import SceneHandle, VisualizationConfigError


class FakeTrackballStyle:
    pass


class FakeVtkRWI:
    def __init__(self) -> None:
        self.render_window: Any | None = None
        self.style: Any | None = None
        self._initialized = False
        self._enabled = False

    def SetRenderWindow(self, rw: Any) -> None:
        self.render_window = rw

    def SetInteractorStyle(self, style: Any) -> None:
        self.style = style

    def Initialize(self) -> None:
        self._initialized = True

    def Enable(self) -> None:
        self._enabled = True

    def GetInitialized(self) -> int:
        return int(self._initialized)

    def GetEnabled(self) -> int:
        return int(self._enabled)


class FakeGenericInteractor:
    def __init__(self) -> None:
        self.__class__.__name__ = "vtkGenericRenderWindowInteractor"

    def GetInitialized(self) -> int:
        return 0

    def GetEnabled(self) -> int:
        return 0


class FakeRenderWindow:
    def __init__(self) -> None:
        self._interactor: Any = FakeGenericInteractor()

    def GetInteractor(self) -> Any:
        return self._interactor

    def SetInteractor(self, interactor: Any) -> None:
        self._interactor = interactor


class FakePlotter:
    def __init__(self) -> None:
        self.render_window = FakeRenderWindow()
        self.render_calls = 0

    def render(self) -> None:
        self.render_calls += 1


class FakeSetText:
    def __init__(self) -> None:
        self.value: str | None = None

    def set_text(self, value: str) -> None:
        self.value = value


class FakeContent:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: Any) -> None:
        return None


class FakeLayout:
    def __init__(self, server: Any) -> None:
        self.server = server
        self.title = FakeSetText()
        self.content = FakeContent()

    def __enter__(self) -> FakeLayout:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class FakeReady:
    def __init__(self) -> None:
        self.callbacks: list[Any] = []

    def add(self, callback: Any) -> None:
        self.callbacks.append(callback)


class FakeServer:
    def __init__(self) -> None:
        self.controller = types.SimpleNamespace(on_server_ready=FakeReady())
        self.start_calls: list[dict[str, Any]] = []
        self.port = 0
        self.stopped = False

    def start(self, **kwargs: Any) -> str:
        self.start_calls.append(kwargs)
        if kwargs.get("port", 0) == 0:
            self.port = 54321
        else:
            self.port = kwargs["port"]
        return "task-1"

    async def stop(self) -> None:
        self.stopped = True


class FakeLocalView:
    def __init__(self, render_window: Any, **kwargs: Any) -> None:
        self.render_window = render_window
        self.kwargs = kwargs
        self.update_calls = 0

    def update(self) -> None:
        self.update_calls += 1


class FakeIFrame:
    def __init__(self, src: str, width: str, height: str) -> None:
        self.src = src
        self.width = width
        self.height = height


@pytest.fixture(autouse=True)
def mock_deps(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """Monkeypatch trame/VTK/IPython modules for all tests."""
    display_calls: list[Any] = []
    servers: dict[str, FakeServer] = {}

    def get_server(name: str) -> FakeServer:
        if name not in servers:
            servers[name] = FakeServer()
        return servers[name]

    trame_app = types.ModuleType("trame.app")
    trame_app.get_server = get_server
    trame_vuetify3 = types.ModuleType("trame.ui.vuetify3")
    trame_vuetify3.SinglePageLayout = FakeLayout
    trame_widgets = types.ModuleType("trame.widgets")
    trame_widgets.vtklocal = types.SimpleNamespace(LocalView=FakeLocalView)
    ipy_mod = types.ModuleType("IPython.display")
    ipy_mod.IFrame = FakeIFrame
    ipy_mod.display = lambda x: display_calls.append(x)
    vtk_style = types.ModuleType("vtkmodules.vtkInteractionStyle")
    vtk_style.vtkInteractorStyleTrackballCamera = FakeTrackballStyle
    vtk_render = types.ModuleType("vtkmodules.vtkRenderingCore")
    vtk_render.vtkRenderWindowInteractor = FakeVtkRWI

    monkeypatch.setitem(sys.modules, "trame.app", trame_app)
    monkeypatch.setitem(sys.modules, "trame.ui.vuetify3", trame_vuetify3)
    monkeypatch.setitem(sys.modules, "trame.widgets", trame_widgets)
    monkeypatch.setitem(sys.modules, "IPython.display", ipy_mod)
    monkeypatch.setitem(sys.modules, "vtkmodules.vtkInteractionStyle", vtk_style)
    monkeypatch.setitem(sys.modules, "vtkmodules.vtkRenderingCore", vtk_render)

    return types.SimpleNamespace(display_calls=display_calls, servers=servers)


@pytest.fixture
def plotter() -> FakePlotter:
    return FakePlotter()


def test_for_session_returns_builder(plotter: FakePlotter) -> None:
    builder = PyVistaDisplay.for_session("sid", plotter)

    assert isinstance(builder, PyVistaDisplay)


def test_for_session_raises_on_no_render_window() -> None:
    plotter = types.SimpleNamespace()

    with pytest.raises(VisualizationConfigError, match="plotter has no render_window"):
        PyVistaDisplay.for_session("sid", plotter)


def test_chaining_returns_self(plotter: FakePlotter) -> None:
    builder = PyVistaDisplay.for_session("sid", plotter)

    result = builder.title("x").port(9000).bind_host("h").public_host("p").iframe_size("w", "h")

    assert result is builder


def test_show_returns_scene_handle(plotter: FakePlotter) -> None:
    handle = PyVistaDisplay.for_session("sid", plotter).show(display=False)

    assert isinstance(handle, SceneHandle)


def test_second_show_raises(plotter: FakePlotter) -> None:
    builder = PyVistaDisplay.for_session("sid", plotter)
    builder.show(display=False)

    with pytest.raises(VisualizationConfigError, match="already been consumed"):
        builder.show(display=False)


def test_show_with_display_true_calls_ipy_display(
    plotter: FakePlotter,
    mock_deps: types.SimpleNamespace,
) -> None:
    handle = PyVistaDisplay.for_session("sid", plotter).show()

    assert mock_deps.display_calls == [handle.iframe]


def test_show_with_display_false_no_ipy_display(
    plotter: FakePlotter,
    mock_deps: types.SimpleNamespace,
) -> None:
    PyVistaDisplay.for_session("sid", plotter).show(display=False)

    assert mock_deps.display_calls == []


def test_track_camera_sugar(plotter: FakePlotter) -> None:
    event_log = types.SimpleNamespace(append=lambda _event, _payload: None)
    builder = PyVistaDisplay.for_session("sid", plotter, event_log=event_log)

    result = builder.track_camera()

    assert result is builder
    assert len(builder._extensions) == 1
    assert isinstance(builder._extensions[0], CameraTrackingExtension)


def test_track_camera_requires_event_log(plotter: FakePlotter) -> None:
    builder = PyVistaDisplay.for_session("sid", plotter)

    with pytest.raises(VisualizationConfigError, match=r"track_camera\(\) requires event_log"):
        builder.track_camera()


def test_use_adds_extension(plotter: FakePlotter) -> None:
    builder = PyVistaDisplay.for_session("sid", plotter)
    ext = object()

    result = builder.use(ext)

    assert result is builder
    assert builder._extensions == [ext]


def test_port_default_zero(plotter: FakePlotter) -> None:
    handle = PyVistaDisplay.for_session("sid", plotter).show(display=False)

    assert handle.port == 54321


def test_explicit_port_propagates(plotter: FakePlotter) -> None:
    handle = PyVistaDisplay.for_session("sid", plotter).port(9005).show(display=False)

    assert handle.port == 9005


def test_public_import_path() -> None:
    from jupyter_workbench.visualization import PyVistaDisplay as PublicPyVistaDisplay

    assert PublicPyVistaDisplay is PyVistaDisplay


def test_no_track_picks_attribute() -> None:
    assert not hasattr(PyVistaDisplay, "track_picks")
