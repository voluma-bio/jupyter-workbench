from __future__ import annotations

from dataclasses import fields
from typing import Any

import pytest

from jupyter_workbench.adapters.visualization.extensions import (
    BuildContext,
    CameraTrackingExtension,
    RuntimeContext,
    SceneExtension,
)


class FakeCamera:
    def __init__(self) -> None:
        self.observers: dict[str, Any] = {}
        self._position = (1.0, 2.0, 3.0)
        self._focal = (0.0, 0.0, 0.0)
        self._up = (0.0, 1.0, 0.0)

    def AddObserver(self, event: str, callback: Any) -> int:
        self.observers[event] = callback
        return 1

    def GetPosition(self) -> tuple[float, float, float]:
        return self._position

    def GetFocalPoint(self) -> tuple[float, float, float]:
        return self._focal

    def GetViewUp(self) -> tuple[float, float, float]:
        return self._up


class FakePlotter:
    def __init__(self) -> None:
        self.camera = FakeCamera()
        self.render_window = object()


class FakeEventLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, list[float]]]] = []

    def append(self, event_type: str, payload: dict[str, list[float]]) -> int:
        self.events.append((event_type, payload))
        return len(self.events)


@pytest.fixture
def plotter() -> FakePlotter:
    return FakePlotter()


@pytest.fixture
def event_log() -> FakeEventLog:
    return FakeEventLog()


def build_context(plotter: FakePlotter) -> BuildContext:
    return BuildContext(
        plotter=plotter,
        render_window=plotter.render_window,
        session_id="session-1",
        config=object(),
    )


def runtime_context(plotter: FakePlotter) -> RuntimeContext:
    return RuntimeContext(
        plotter=plotter,
        render_window=plotter.render_window,
        session_id="session-1",
        config=object(),
        view=object(),
        server=object(),
    )


def fire_modified(camera: FakeCamera) -> None:
    camera.observers["ModifiedEvent"](camera, "ModifiedEvent")


def test_scene_extension_protocol_shape() -> None:
    assert getattr(SceneExtension, "_is_runtime_protocol", False) is True
    assert SceneExtension.__annotations__["name"] in {str, "str"}
    assert SceneExtension.__annotations__["critical"] in {bool, "bool"}
    for method_name in ("prepare", "bind_view", "after_start", "close"):
        assert callable(getattr(SceneExtension, method_name))


def test_camera_tracking_extension_implements_protocol(event_log: FakeEventLog) -> None:
    assert isinstance(CameraTrackingExtension(event_log), SceneExtension)


def test_camera_tracking_prepare_is_noop(plotter: FakePlotter, event_log: FakeEventLog) -> None:
    extension = CameraTrackingExtension(event_log)
    before = extension.__dict__.copy()

    extension.prepare(build_context(plotter))

    assert extension.__dict__ == before
    assert event_log.events == []


def test_camera_tracking_bind_view_registers_observer(plotter: FakePlotter, event_log: FakeEventLog) -> None:
    extension = CameraTrackingExtension(event_log)

    extension.bind_view(runtime_context(plotter))

    assert "ModifiedEvent" in plotter.camera.observers
    assert callable(plotter.camera.observers["ModifiedEvent"])
    assert extension._observer_id == 1


def test_camera_tracking_bind_view_warns_no_camera(event_log: FakeEventLog) -> None:
    plotter_without_camera = object()
    ctx = RuntimeContext(
        plotter=plotter_without_camera,
        render_window=object(),
        session_id="session-1",
        config=object(),
        view=object(),
        server=object(),
    )

    with pytest.warns(UserWarning, match="plotter has no camera attribute"):
        CameraTrackingExtension(event_log).bind_view(ctx)

    assert event_log.events == []


def test_camera_tracking_throttle(
    plotter: FakePlotter,
    event_log: FakeEventLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([1.0, 1.1])
    monkeypatch.setattr(
        "jupyter_workbench.adapters.visualization.extensions.time.monotonic",
        lambda: next(times),
    )
    extension = CameraTrackingExtension(event_log, throttle_ms=500)
    extension.bind_view(runtime_context(plotter))

    fire_modified(plotter.camera)
    plotter.camera._position = (4.0, 5.0, 6.0)
    fire_modified(plotter.camera)

    assert len(event_log.events) == 1


def test_camera_tracking_duplicate_suppression(
    plotter: FakePlotter,
    event_log: FakeEventLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([1.0, 2.0])
    monkeypatch.setattr(
        "jupyter_workbench.adapters.visualization.extensions.time.monotonic",
        lambda: next(times),
    )
    extension = CameraTrackingExtension(event_log, throttle_ms=500)
    extension.bind_view(runtime_context(plotter))

    fire_modified(plotter.camera)
    fire_modified(plotter.camera)

    assert len(event_log.events) == 1


def test_camera_tracking_logs_event(
    plotter: FakePlotter,
    event_log: FakeEventLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([1.0, 2.0])
    monkeypatch.setattr(
        "jupyter_workbench.adapters.visualization.extensions.time.monotonic",
        lambda: next(times),
    )
    extension = CameraTrackingExtension(event_log, throttle_ms=500)
    extension.bind_view(runtime_context(plotter))

    fire_modified(plotter.camera)
    plotter.camera._position = (7.0, 8.0, 9.0)
    fire_modified(plotter.camera)

    assert event_log.events[-1] == (
        "camera.modified",
        {
            "position": [7.0, 8.0, 9.0],
            "focal_point": [0.0, 0.0, 0.0],
            "view_up": [0.0, 1.0, 0.0],
        },
    )


def test_camera_tracking_event_payload_shape(plotter: FakePlotter, event_log: FakeEventLog) -> None:
    extension = CameraTrackingExtension(event_log, throttle_ms=0)
    extension.bind_view(runtime_context(plotter))

    fire_modified(plotter.camera)

    event_type, payload = event_log.events[0]
    assert event_type == "camera.modified"
    assert set(payload) == {"position", "focal_point", "view_up"}
    for value in payload.values():
        assert isinstance(value, list)
        assert all(isinstance(item, float) for item in value)


def test_camera_tracking_handler_error_warns(plotter: FakePlotter, event_log: FakeEventLog) -> None:
    extension = CameraTrackingExtension(event_log, throttle_ms=0)
    extension.bind_view(runtime_context(plotter))
    plotter.camera.GetPosition = lambda: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]

    with pytest.warns(UserWarning, match="event handler error: boom"):
        fire_modified(plotter.camera)

    assert event_log.events == []


def test_build_context_fields() -> None:
    assert [field.name for field in fields(BuildContext)] == [
        "plotter",
        "render_window",
        "session_id",
        "config",
    ]


def test_runtime_context_inherits_build() -> None:
    assert issubclass(RuntimeContext, BuildContext)
    assert [field.name for field in fields(RuntimeContext)] == [
        "plotter",
        "render_window",
        "session_id",
        "config",
        "view",
        "server",
    ]


def test_noncritical_extension_attribute(event_log: FakeEventLog) -> None:
    assert CameraTrackingExtension.critical is False
    assert CameraTrackingExtension(event_log).critical is False
