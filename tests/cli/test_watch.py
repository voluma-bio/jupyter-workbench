"""CLI and service tests for the watch command."""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import nbformat
import pytest
from typer.testing import CliRunner

from jupyter_workbench.adapters.notebook.nbformat_store import NbformatStore
from jupyter_workbench.cli import app
from jupyter_workbench.core import watch_service
from jupyter_workbench.core.lineage_service import LineageService
from jupyter_workbench.core.session_lock import SessionLock
from jupyter_workbench.core.session_service import SessionNotFoundError, SessionService
from jupyter_workbench.core.watch_service import LiveNotebookViewer, watch_session


class _NoopKernel:
    def start(self, session_id: str) -> None:
        raise AssertionError("kernel should not be used in compact tests")

    def connect(self, session_id: str, connection_file: str) -> None:
        raise AssertionError("kernel should not be used in compact tests")

    def execute(self, session_id: str, code: str) -> object:
        raise AssertionError("kernel should not be used in compact tests")

    def is_alive(self, session_id: str) -> bool:
        raise AssertionError("kernel should not be used in compact tests")

    def probe_alive(self, session_id: str) -> bool:
        raise AssertionError("kernel should not be used in compact tests")

    def shutdown(self, session_id: str) -> bool:
        raise AssertionError("kernel should not be used in compact tests")


def test_watch_cli_forwards_options(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_watch_session(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("jupyter_workbench.cli.watch_session", fake_watch_session)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "watch",
            "--session-id",
            "abc123",
            "--port",
            "9010",
            "--host",
            "0.0.0.0",
            "--poll-interval",
            "0.25",
            "--no-open-browser",
            "--root-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert captured == {
        "session_id": "abc123",
        "root_dir": tmp_path,
        "host": "0.0.0.0",
        "port": 9010,
        "poll_interval": 0.25,
        "open_browser": False,
    }


def test_live_viewer_follows_compacted_notebook(tmp_path: Path) -> None:
    root_dir = tmp_path / "wb"
    session_id = "sess1234"
    _bootstrap_session(
        root_dir=root_dir,
        session_id=session_id,
        notebook_name="active.ipynb",
        cells=[
            nbformat.v4.new_markdown_cell("obsolete cell"),
            nbformat.v4.new_markdown_cell("kept cell"),
        ],
    )

    viewer = LiveNotebookViewer(
        session_id=session_id,
        root_dir=root_dir,
        host="127.0.0.1",
        port=0,
        poll_interval=0.05,
        open_browser=False,
    )
    url = viewer.start()
    try:
        assert "obsolete cell" in _get_text(url)
        etag_before = _get_text(f"{url}etag")

        service = LineageService(kernel=_NoopKernel(), notebook=NbformatStore(), root_dir=root_dir)
        service.compact(session_id, cells_to_remove=[0])

        _wait_until(lambda: _get_text(f"{url}etag") != etag_before)
        html = _get_text(url)
        assert "obsolete cell" not in html
        assert "kept cell" in html
    finally:
        viewer.stop()


def test_live_viewer_refreshes_when_active_notebook_is_updated_in_place(tmp_path: Path) -> None:
    root_dir = tmp_path / "wb"
    session_id = "sesslive1"
    notebook_path = _bootstrap_session(
        root_dir=root_dir,
        session_id=session_id,
        notebook_name="active.ipynb",
        cells=[nbformat.v4.new_markdown_cell("existing cell")],
    )

    viewer = LiveNotebookViewer(
        session_id=session_id,
        root_dir=root_dir,
        host="127.0.0.1",
        port=0,
        poll_interval=0.05,
        open_browser=False,
    )
    url = viewer.start()
    try:
        assert "new live cell" not in _get_text(url)
        etag_before = _get_text(f"{url}etag")

        NbformatStore().append_markdown_cell(notebook_path, "new live cell")

        _wait_until(lambda: _get_text(f"{url}etag") != etag_before)
        assert "new live cell" in _get_text(url)
    finally:
        viewer.stop()


def test_live_viewer_refresh_waits_for_session_lock_to_release(tmp_path: Path) -> None:
    root_dir = tmp_path / "wb"
    session_id = "sesslock1"
    notebook_path = _bootstrap_session(
        root_dir=root_dir,
        session_id=session_id,
        notebook_name="active.ipynb",
        cells=[nbformat.v4.new_markdown_cell("initial cell")],
    )

    viewer = LiveNotebookViewer(
        session_id=session_id,
        root_dir=root_dir,
        host="127.0.0.1",
        port=0,
        poll_interval=0.05,
        open_browser=False,
    )
    url = viewer.start()
    try:
        etag_before = _get_text(f"{url}etag")
        lock = SessionLock(root_dir)
        with lock.acquire(session_id):
            notebook_path.write_text('{"cells": [')
            viewer.schedule_refresh()
            _assert_etag_unchanged(f"{url}etag", etag_before, duration=0.35)

            notebook = nbformat.v4.new_notebook(
                cells=[
                    nbformat.v4.new_markdown_cell("initial cell"),
                    nbformat.v4.new_markdown_cell("cell after lock release"),
                ]
            )
            nbformat.write(notebook, notebook_path)

        _wait_until(lambda: _get_text(f"{url}etag") != etag_before)
        html = _get_text(url)
        assert "cell after lock release" in html
    finally:
        viewer.stop()


def test_live_viewer_bumps_port_on_collision(tmp_path: Path) -> None:
    root_dir = tmp_path / "wb"
    session_id = "sess5678"
    _bootstrap_session(
        root_dir=root_dir,
        session_id=session_id,
        notebook_name="active.ipynb",
        cells=[nbformat.v4.new_markdown_cell("port check")],
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    occupied_port = sock.getsockname()[1]

    viewer = LiveNotebookViewer(
        session_id=session_id,
        root_dir=root_dir,
        host="127.0.0.1",
        port=occupied_port,
        poll_interval=0.05,
        open_browser=False,
    )
    try:
        url = viewer.start()
        assert f":{occupied_port}/" not in url
    finally:
        viewer.stop()
        sock.close()


def test_live_viewer_recovers_after_scheduled_refresh_failure(tmp_path: Path, monkeypatch) -> None:
    root_dir = tmp_path / "wb"
    session_id = "sessrecover1"
    notebook_path = _bootstrap_session(
        root_dir=root_dir,
        session_id=session_id,
        notebook_name="active.ipynb",
        cells=[nbformat.v4.new_markdown_cell("existing cell")],
    )

    viewer = LiveNotebookViewer(
        session_id=session_id,
        root_dir=root_dir,
        host="127.0.0.1",
        port=0,
        poll_interval=0.05,
        open_browser=False,
    )
    url = viewer.start()
    try:
        original_render = watch_service._render_html
        calls = {"count": 0, "failed": 0}

        def flaky_render(notebook_bytes: bytes) -> tuple[str, dict[str, object]]:
            calls["count"] += 1
            if calls["count"] == 1:
                calls["failed"] += 1
                raise RuntimeError("forced render failure")
            html, resources = original_render(notebook_bytes)
            return html, resources

        monkeypatch.setattr(watch_service, "_render_html", flaky_render)

        viewer.schedule_refresh()
        _wait_until(lambda: calls["failed"] == 1)
        etag_after_failure = _get_text(f"{url}etag")

        NbformatStore().append_markdown_cell(notebook_path, "cell after failed refresh")
        viewer.schedule_refresh()
        _wait_until(lambda: _get_text(f"{url}etag") != etag_after_failure)
        assert calls["count"] >= 2
        html = _get_text(url)
        assert "existing cell" in html
        assert "cell after failed refresh" in html
    finally:
        viewer.stop()


def test_watch_session_stops_viewer_when_start_raises(monkeypatch, tmp_path: Path) -> None:
    class _FakeViewer:
        stop_calls = 0

        def __init__(self, **_: object) -> None:
            pass

        def start(self) -> str:
            raise RuntimeError("startup failed")

        def wait_forever(self) -> None:
            raise AssertionError("wait_forever should not run after start failure")

        def stop(self) -> None:
            _FakeViewer.stop_calls += 1

    monkeypatch.setattr(watch_service, "LiveNotebookViewer", _FakeViewer)

    with pytest.raises(RuntimeError, match="startup failed"):
        watch_session(
            session_id="sess-start-fail",
            root_dir=tmp_path / "wb",
            host="127.0.0.1",
            port=9010,
            poll_interval=0.1,
            open_browser=False,
        )
    assert _FakeViewer.stop_calls == 1


def test_live_viewer_html_contains_seeded_etag(tmp_path: Path) -> None:
    root_dir = tmp_path / "wb"
    session_id = "sessetag1"
    _bootstrap_session(
        root_dir=root_dir,
        session_id=session_id,
        notebook_name="active.ipynb",
        cells=[nbformat.v4.new_markdown_cell("etag seed cell")],
    )

    viewer = LiveNotebookViewer(
        session_id=session_id,
        root_dir=root_dir,
        host="127.0.0.1",
        port=0,
        poll_interval=0.05,
        open_browser=False,
    )
    url = viewer.start()
    try:
        html = _get_text(url)
        etag = _get_text(f"{url}etag")
        # The served HTML must contain the etag as the seeded initial value
        assert json.dumps(etag) in html
        # Etag is content-based: same content yields same etag
        assert etag == _get_text(f"{url}etag")
        # Etag looks like a hex hash prefix, not a timestamp
        assert len(etag) == 16
        assert all(c in "0123456789abcdef" for c in etag)
    finally:
        viewer.stop()


def test_live_viewer_rejects_path_traversal(tmp_path: Path) -> None:
    root_dir = tmp_path / "wb"
    session_id = "sesstraversal"
    _bootstrap_session(
        root_dir=root_dir,
        session_id=session_id,
        notebook_name="active.ipynb",
        cells=[nbformat.v4.new_markdown_cell("traversal test cell")],
    )

    viewer = LiveNotebookViewer(
        session_id=session_id,
        root_dir=root_dir,
        host="127.0.0.1",
        port=0,
        poll_interval=0.05,
        open_browser=False,
    )
    url = viewer.start()
    try:
        # Verify normal content serves fine
        assert "traversal test cell" in _get_text(url)

        # Path traversal attempts must return 404
        for malicious_path in ["/../etc/passwd", "/../../../etc/hosts", "/..%2f..%2fetc/passwd"]:
            with pytest.raises(HTTPError) as exc_info:
                _get_text(f"{url.rstrip('/')}{malicious_path}")
            assert exc_info.value.code == 404
    finally:
        viewer.stop()


def test_live_viewer_stop_is_idempotent(tmp_path: Path) -> None:
    root_dir = tmp_path / "wb"
    session_id = "sessidem"
    _bootstrap_session(
        root_dir=root_dir,
        session_id=session_id,
        notebook_name="active.ipynb",
        cells=[nbformat.v4.new_markdown_cell("idempotent stop cell")],
    )

    viewer = LiveNotebookViewer(
        session_id=session_id,
        root_dir=root_dir,
        host="127.0.0.1",
        port=0,
        poll_interval=0.05,
        open_browser=False,
    )
    viewer.start()
    viewer.stop()
    # Second stop must not raise
    viewer.stop()


def test_watch_session_raises_for_nonexistent_session(tmp_path: Path) -> None:
    root_dir = tmp_path / "wb"
    root_dir.mkdir(parents=True)
    (root_dir / "sessions").mkdir()

    with pytest.raises(SessionNotFoundError, match="no active sessions found"):
        watch_session(
            session_id=None,
            root_dir=root_dir,
            host="127.0.0.1",
            port=0,
            poll_interval=0.1,
            open_browser=False,
        )


def test_resolve_session_id_prefers_newest_non_closed_manifest(tmp_path: Path) -> None:
    root_dir = tmp_path / "wb"
    _bootstrap_session(
        root_dir=root_dir,
        session_id="activeold",
        notebook_name="active.ipynb",
        cells=[nbformat.v4.new_markdown_cell("old active")],
        status="active",
    )
    _bootstrap_session(
        root_dir=root_dir,
        session_id="closednew",
        notebook_name="active.ipynb",
        cells=[nbformat.v4.new_markdown_cell("closed")],
        status="closed",
    )
    _bootstrap_session(
        root_dir=root_dir,
        session_id="activenew",
        notebook_name="active.ipynb",
        cells=[nbformat.v4.new_markdown_cell("new active")],
        status="active",
    )

    active_old_manifest = root_dir / "sessions" / "activeold" / "manifest.json"
    closed_new_manifest = root_dir / "sessions" / "closednew" / "manifest.json"
    active_new_manifest = root_dir / "sessions" / "activenew" / "manifest.json"

    now = time.time()
    os.utime(active_old_manifest, (now - 15, now - 15))
    os.utime(active_new_manifest, (now - 5, now - 5))
    os.utime(closed_new_manifest, (now, now))

    assert SessionService.resolve_session_id(root_dir) == "activenew"


def _bootstrap_session(
    *,
    root_dir: Path,
    session_id: str,
    notebook_name: str,
    cells: list[object],
    status: str = "active",
) -> Path:
    notebook_path = root_dir / "sessions" / session_id / "notebooks" / notebook_name
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook(cells=cells)
    nbformat.write(notebook, notebook_path)

    manifest_path = root_dir / "sessions" / session_id / "manifest.json"
    manifest = {
        "session_id": session_id,
        "root_dir": str(root_dir),
        "notebook_path": str(notebook_path.relative_to(root_dir)),
        "created_at": "2026-01-01T00:00:00Z",
        "status": status,
        "visualization_status": "visualization_absent",
        "notebook_revision": 0,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return notebook_path


def _get_text(url: str) -> str:
    with urlopen(url, timeout=2.0) as response:  # noqa: S310
        return response.read().decode("utf-8")


def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


def _assert_etag_unchanged(etag_url: str, expected: str, duration: float) -> None:
    deadline = time.time() + duration
    while time.time() < deadline:
        assert _get_text(etag_url) == expected
        time.sleep(0.02)
