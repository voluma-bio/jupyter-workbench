from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from jupyter_workbench.adapters.visualization.runtime import (
    DisplayConfig,
    SceneHandle,
    VisualizationConfigError,
    VisualizationError,
    VisualizationExtensionError,
    VisualizationLaunchError,
    VtkLocalRuntime,
)


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

    def __enter__(self) -> "FakeLayout":
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
def mock_trame_and_vtk(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """Monkeypatch trame/VTK/IPython modules for all tests."""
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
    ipy_display_mod = types.ModuleType("IPython.display")
    ipy_display_mod.IFrame = FakeIFrame
    ipy_display_mod.display = lambda x: None
    vtk_style = types.ModuleType("vtkmodules.vtkInteractionStyle")
    vtk_style.vtkInteractorStyleTrackballCamera = FakeTrackballStyle
    vtk_render = types.ModuleType("vtkmodules.vtkRenderingCore")
    vtk_render.vtkRenderWindowInteractor = FakeVtkRWI

    monkeypatch.setitem(sys.modules, "trame.app", trame_app)
    monkeypatch.setitem(sys.modules, "trame.ui.vuetify3", trame_vuetify3)
    monkeypatch.setitem(sys.modules, "trame.widgets", trame_widgets)
    monkeypatch.setitem(sys.modules, "IPython.display", ipy_display_mod)
    monkeypatch.setitem(sys.modules, "vtkmodules.vtkInteractionStyle", vtk_style)
    monkeypatch.setitem(sys.modules, "vtkmodules.vtkRenderingCore", vtk_render)

    return types.SimpleNamespace(servers=servers, get_server=get_server)


@pytest.fixture
def runtime() -> VtkLocalRuntime:
    return VtkLocalRuntime()


@pytest.fixture
def plotter() -> FakePlotter:
    return FakePlotter()


def test_launch_returns_scene_handle(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    config = DisplayConfig(session_id="session-a", port=8123)

    handle = runtime.launch(config, plotter)

    assert isinstance(handle, SceneHandle)
    assert handle.url == "http://127.0.0.1:8123/"
    assert handle.port == 8123
    assert isinstance(handle.view, FakeLocalView)
    assert isinstance(handle.server, FakeServer)
    assert isinstance(handle.iframe, FakeIFrame)
    assert handle.iframe.src == handle.url
    assert handle.task == "task-1"
    assert handle.session_id == "session-a"
    assert handle.viz_id.startswith("session-a-jw-session-a-")
    assert handle.interactor_fix["changed"] is True


def test_server_name_monotonic(runtime: VtkLocalRuntime) -> None:
    first = runtime.launch(DisplayConfig(session_id="same", port=9001), FakePlotter())
    second = runtime.launch(DisplayConfig(session_id="same", port=9002), FakePlotter())

    assert first.viz_id != second.viz_id


def test_port_zero_resolves_to_os_assigned(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    handle = runtime.launch(DisplayConfig(session_id="port-zero", port=0), plotter)

    assert handle.port == 54321


def test_explicit_port_passthrough(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    handle = runtime.launch(DisplayConfig(session_id="explicit", port=9000), plotter)

    assert handle.port == 9000


def test_public_host_resolution(runtime: VtkLocalRuntime) -> None:
    localhost = runtime.launch(DisplayConfig(session_id="host-a", bind_host="0.0.0.0", port=9003), FakePlotter())
    public = runtime.launch(
        DisplayConfig(session_id="host-b", bind_host="0.0.0.0", public_host="viewer.example", port=9004),
        FakePlotter(),
    )

    assert localhost.url == "http://127.0.0.1:9003/"
    assert public.url == "http://viewer.example:9004/"


def test_plotter_render_called_before_interactor_swap(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    runtime.launch(DisplayConfig(session_id="render", port=9005), plotter)

    assert plotter.render_calls == 1


def test_interactor_fix_in_handle(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    handle = runtime.launch(DisplayConfig(session_id="interactor", port=9006), plotter)

    assert handle.interactor_fix["changed"] is True
    assert handle.interactor_fix["old_type"] == "vtkGenericRenderWindowInteractor"
    assert isinstance(handle.interactor_fix["new_interactor"], FakeVtkRWI)


def test_scene_handle_refresh(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    handle = runtime.launch(DisplayConfig(session_id="refresh", port=9007), plotter)

    handle.refresh()

    assert handle.view.update_calls == 1


def test_scene_handle_close_schedules_stop(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    async def run() -> None:
        handle = runtime.launch(DisplayConfig(session_id="close", port=9008), plotter)
        handle.close()
        handle.close()
        await asyncio.sleep(0)
        assert handle.server.stopped is True

    asyncio.run(run())


def test_scene_handle_context_manager(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    async def run() -> None:
        handle = runtime.launch(DisplayConfig(session_id="ctx", port=9009), plotter)
        with handle as entered:
            assert entered is handle
        await asyncio.sleep(0)
        assert handle.server.stopped is True

    asyncio.run(run())


def test_scene_handle_async_context_manager(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    async def run() -> None:
        handle = runtime.launch(DisplayConfig(session_id="async-ctx", port=9010), plotter)
        async with handle as entered:
            assert entered is handle
        assert handle.server.stopped is True

    asyncio.run(run())


def test_launch_error_on_server_start_failure(
    runtime: VtkLocalRuntime,
    plotter: FakePlotter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_start(self: FakeServer, **kwargs: Any) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(FakeServer, "start", fail_start)

    with pytest.raises(VisualizationLaunchError, match="trame server failed to start: boom"):
        runtime.launch(DisplayConfig(session_id="fail"), plotter)


def test_extension_prepare_called(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    class Extension:
        def __init__(self) -> None:
            self.context: dict[str, Any] | None = None

        def prepare(self, context: dict[str, Any]) -> None:
            self.context = context

    ext = Extension()
    config = DisplayConfig(session_id="prepare", port=9011)
    runtime.launch(config, plotter, extensions=[ext])

    assert ext.context is not None
    assert ext.context["plotter"] is plotter
    assert ext.context["render_window"] is plotter.render_window
    assert ext.context["session_id"] == "prepare"
    assert ext.context["config"] is config


def test_extension_bind_view_called(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    class Extension:
        def __init__(self) -> None:
            self.context: dict[str, Any] | None = None

        def bind_view(self, context: dict[str, Any]) -> None:
            self.context = context

    ext = Extension()
    runtime.launch(DisplayConfig(session_id="bind", port=9012), plotter, extensions=[ext])

    assert ext.context is not None
    assert ext.context["plotter"] is plotter
    assert ext.context["view"].render_window is plotter.render_window
    assert isinstance(ext.context["server"], FakeServer)


def test_extension_after_start_called(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    class Extension:
        def __init__(self) -> None:
            self.handle: SceneHandle | None = None

        def after_start(self, handle: SceneHandle) -> None:
            self.handle = handle

    ext = Extension()
    handle = runtime.launch(DisplayConfig(session_id="after", port=9013), plotter, extensions=[ext])

    assert ext.handle is handle


def test_critical_extension_failure_aborts(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    class Extension:
        critical = True
        name = "critical-ext"

        def prepare(self, context: dict[str, Any]) -> None:
            raise RuntimeError("bad prepare")

    with pytest.raises(VisualizationExtensionError, match="critical extension critical-ext failed in prepare: bad prepare"):
        runtime.launch(DisplayConfig(session_id="critical", port=9014), plotter, extensions=[Extension()])


def test_noncritical_extension_failure_warns(runtime: VtkLocalRuntime, plotter: FakePlotter) -> None:
    class Extension:
        critical = False
        name = "warning-ext"

        def prepare(self, context: dict[str, Any]) -> None:
            raise RuntimeError("soft fail")

    with pytest.warns(UserWarning, match="extension warning-ext prepare failed: soft fail"):
        handle = runtime.launch(DisplayConfig(session_id="warning", port=9015), plotter, extensions=[Extension()])

    assert isinstance(handle, SceneHandle)
    assert handle.port == 9015


def test_display_config_defaults() -> None:
    config = DisplayConfig(session_id="defaults")

    assert config.session_id == "defaults"
    assert config.title == "jupyter-workbench — vtklocal"
    assert config.port == 0
    assert config.bind_host == "0.0.0.0"
    assert config.public_host is None
    assert config.iframe_width == "100%"
    assert config.iframe_height == "600px"
    assert config.progress_delay == 500


def test_error_hierarchy() -> None:
    assert issubclass(VisualizationConfigError, VisualizationError)
    assert issubclass(VisualizationLaunchError, VisualizationError)
    assert issubclass(VisualizationExtensionError, VisualizationError)
