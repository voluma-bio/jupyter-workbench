from __future__ import annotations

import sys
import types
from typing import Any

from jupyter_workbench.adapters.visualization.vtklocal import (
    launch_vtklocal_view,
    make_server_ready_update,
    resolve_public_host,
)


class FakeSetText:
    def __init__(self) -> None:
        self.value: str | None = None

    def set_text(self, value: str) -> None:
        self.value = value


class FakeContent:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class FakeLayout:
    def __init__(self, server: Any) -> None:
        self.server = server
        self.title = FakeSetText()
        self.content = FakeContent()

    def __enter__(self) -> "FakeLayout":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
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

    def start(self, **kwargs: Any) -> str:
        self.start_calls.append(kwargs)
        return 'task-1'


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


def test_resolve_public_host_defaults() -> None:
    assert resolve_public_host('0.0.0.0') == '127.0.0.1'
    assert resolve_public_host('127.0.0.1') == '127.0.0.1'
    assert resolve_public_host('0.0.0.0', '10.0.0.5') == '10.0.0.5'


def test_make_server_ready_update_ignores_trame_kwargs() -> None:
    view = FakeLocalView(render_window=object())
    callback = make_server_ready_update(view)
    callback(trame__scripts=['x'], another='y')
    assert view.update_calls == 1


def test_launch_vtklocal_view_displays_iframe(monkeypatch: Any) -> None:
    display_calls: list[Any] = []
    server = FakeServer()
    interactor_fix = {"changed": False}

    trame_app = types.ModuleType('trame.app')
    trame_app.get_server = lambda name: server

    trame_vuetify3 = types.ModuleType('trame.ui.vuetify3')
    trame_vuetify3.SinglePageLayout = FakeLayout

    trame_widgets = types.ModuleType('trame.widgets')
    trame_widgets.vtklocal = types.SimpleNamespace(LocalView=FakeLocalView)

    ipy_display = types.ModuleType('IPython.display')
    ipy_display.IFrame = FakeIFrame
    ipy_display.display = lambda value: display_calls.append(value)

    monkeypatch.setitem(sys.modules, 'trame.app', trame_app)
    monkeypatch.setitem(sys.modules, 'trame.ui.vuetify3', trame_vuetify3)
    monkeypatch.setitem(sys.modules, 'trame.widgets', trame_widgets)
    monkeypatch.setitem(sys.modules, 'IPython.display', ipy_display)

    from jupyter_workbench.adapters.visualization import interactor

    monkeypatch.setattr(
        interactor,
        'ensure_render_window_interactor',
        lambda plotter: interactor_fix,
    )

    class FakePlotter:
        def __init__(self) -> None:
            self.render_window = object()
            self.render_calls = 0

        def render(self) -> None:
            self.render_calls += 1

    plotter = FakePlotter()
    launch = launch_vtklocal_view(
        plotter,
        bind_host='0.0.0.0',
        public_host='viewer.example',
        port=9123,
    )

    assert plotter.render_calls == 1
    assert launch['url'] == 'http://viewer.example:9123/'
    assert launch['task'] == 'task-1'
    assert launch['interactor_fix'] == interactor_fix
    assert isinstance(launch['iframe'], FakeIFrame)
    assert launch['iframe'].src == 'http://viewer.example:9123/'
    assert len(display_calls) == 1
    assert server.start_calls == [{'exec_mode': 'task', 'host': '0.0.0.0', 'port': 9123}]
    assert len(server.controller.on_server_ready.callbacks) == 1
    server.controller.on_server_ready.callbacks[0](trame__scripts=['x'])
    assert launch['view'].update_calls == 1
