"""Read-only live notebook watch service."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import threading
import webbrowser
from dataclasses import dataclass
from errno import EADDRINUSE
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import nbformat
from nbconvert import HTMLExporter
from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileSystemMovedEvent
from watchdog.observers import Observer

from jupyter_workbench.core.session_lock import SessionLock
from jupyter_workbench.core.session_service import SessionNotFoundError, SessionService


@dataclass(frozen=True)
class _NotebookSnapshot:
    notebook_path: Path
    notebook_bytes: bytes


class _WatchRequestHandler(BaseHTTPRequestHandler):
    """Serve rendered notebook HTML and etag updates."""

    def do_GET(self) -> None:  # noqa: N802
        server = cast(_WatchHTTPServer, self.server)
        parsed = urlparse(self.path)
        if parsed.path == "/etag":
            self._serve_bytes(
                server.viewer.current_etag().encode("utf-8"),
                content_type="text/plain; charset=utf-8",
            )
            return

        response = server.viewer.read_rendered_file(parsed.path)
        if response is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content, content_type = response
        self._serve_bytes(content, content_type=content_type)

    def log_message(self, format: str, *args: object) -> None:
        """Disable request logging."""
        return

    def _serve_bytes(self, content: bytes, *, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


class _WatchHTTPServer(ThreadingHTTPServer):
    """HTTP server with access to live viewer state."""

    def __init__(self, server_address: tuple[str, int], viewer: "LiveNotebookViewer") -> None:
        super().__init__(server_address, _WatchRequestHandler)
        self.viewer = viewer


class _SessionEventHandler(FileSystemEventHandler):
    """Watchdog event handler that triggers notebook refreshes."""

    def __init__(self, viewer: "LiveNotebookViewer") -> None:
        self.viewer = viewer

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self.viewer.handle_path_change(Path(os.fsdecode(event.src_path)))
        if isinstance(event, FileSystemMovedEvent):
            self.viewer.handle_path_change(Path(os.fsdecode(event.dest_path)))


class LiveNotebookViewer:
    """Manage live notebook rendering and HTTP serving for one session."""

    def __init__(
        self,
        *,
        session_id: str,
        root_dir: Path,
        host: str,
        port: int,
        poll_interval: float,
        open_browser: bool,
    ) -> None:
        self.session_id = session_id
        self.root_dir = root_dir
        self.host = host
        self.port = port
        self.poll_interval = poll_interval
        self.open_browser = open_browser
        self._render_tmp = tempfile.TemporaryDirectory(prefix="jupyter-workbench-watch-")
        self._render_root = Path(self._render_tmp.name)
        self._active_render_dir: Path | None = None
        self._current_etag = "0"
        self.current_notebook_path: Path | None = None
        self._manifest_path = self.root_dir / "sessions" / self.session_id / "manifest.json"
        self._observer = Observer()
        self._server: _WatchHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._refresh_timer: threading.Timer | None = None
        self._refresh_lock = threading.Lock()
        self._render_state_lock = threading.Lock()
        self._schedule_lock = threading.Lock()
        self._stop_lock = threading.Lock()
        self._session_lock = SessionLock(self.root_dir)
        self._stopped = threading.Event()
        self._cleaned_up = False

    def start(self) -> str:
        """Start refresh loop and HTTP server, returning the served URL."""
        self.refresh()
        self._server = self._bind_server(self.host, self.port)
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()
        self._observer.schedule(_SessionEventHandler(self), str(self._manifest_path.parent), recursive=True)
        self._observer.start()

        host = self.host
        bound_port = self._server.server_address[1]
        url = f"http://{host}:{bound_port}/"
        print(f"Watching session {self.session_id} at {url}", flush=True)
        if self.open_browser:
            webbrowser.open(url)
        return url

    def wait_forever(self) -> None:
        """Block until stopped."""
        while not self._stopped.wait(0.25):
            continue

    def stop(self) -> None:
        """Stop all background resources."""
        with self._stop_lock:
            if self._cleaned_up:
                return
            self._stopped.set()
            with self._schedule_lock:
                if self._refresh_timer is not None:
                    self._refresh_timer.cancel()
                    self._refresh_timer = None
            if self._observer.is_alive():
                self._observer.stop()
                self._observer.join(timeout=2.0)
            if self._server is not None:
                self._server.shutdown()
                self._server.server_close()
            if self._server_thread is not None:
                self._server_thread.join(timeout=2.0)
            with self._refresh_lock:
                pass
            self._render_tmp.cleanup()
            self._cleaned_up = True

    def handle_path_change(self, changed_path: Path) -> None:
        """Debounce refreshes for manifest and active notebook changes."""
        try:
            changed = changed_path.resolve()
        except OSError:
            return
        tracked = {self._manifest_path.resolve()}
        if self.current_notebook_path is not None:
            tracked.add(self.current_notebook_path.resolve())
        if changed not in tracked:
            return
        self.schedule_refresh()

    def schedule_refresh(self) -> None:
        """Schedule a debounced refresh."""
        if self._stopped.is_set():
            return
        with self._schedule_lock:
            if self._refresh_timer is not None:
                self._refresh_timer.cancel()
            self._refresh_timer = threading.Timer(self.poll_interval, self._run_scheduled_refresh)
            self._refresh_timer.daemon = True
            self._refresh_timer.start()

    def refresh(self) -> None:
        """Read notebook safely, render HTML, and publish an updated etag."""
        with self._refresh_lock:
            if self._stopped.is_set():
                return
            snapshot = self._snapshot_notebook()
            self.current_notebook_path = snapshot.notebook_path
            html, resources = _render_html(snapshot.notebook_bytes)
            self._publish_render_bundle(html, resources)

    def current_etag(self) -> str:
        with self._render_state_lock:
            return self._current_etag

    def read_rendered_file(self, path: str) -> tuple[bytes, str] | None:
        relative_path = Path("index.html") if path == "/" else Path(path.lstrip("/"))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            return None
        with self._render_state_lock:
            render_dir = self._active_render_dir
            if render_dir is None:
                return None
            full_path = (render_dir / relative_path).resolve()
            try:
                full_path.relative_to(render_dir.resolve())
            except ValueError:
                return None
            if not full_path.is_file():
                return None
            content = full_path.read_bytes()
        content_type = mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"
        return content, content_type

    def _run_scheduled_refresh(self) -> None:
        try:
            self.refresh()
        except Exception as error:
            print(f"watch refresh failed: {error}")

    def _publish_render_bundle(self, html: str, resources: dict[str, Any]) -> None:
        etag = _content_hash(html, resources)
        final_html = _inject_reloader(html, etag)
        staged_dir = Path(tempfile.mkdtemp(prefix="render-", dir=self._render_root))
        _write_render_bundle(staged_dir, final_html, resources)
        with self._render_state_lock:
            previous_dir = self._active_render_dir
            self._active_render_dir = staged_dir
            self._current_etag = etag
        if previous_dir is not None:
            shutil.rmtree(previous_dir, ignore_errors=True)

    def _snapshot_notebook(self) -> _NotebookSnapshot:
        with self._session_lock.acquire(self.session_id):
            manifest = _read_manifest(self._manifest_path, self.session_id)
            notebook_path = _notebook_path(self.root_dir, manifest)
            if not notebook_path.exists():
                raise SessionNotFoundError(f"notebook not found for session: {self.session_id}")
            notebook_bytes = notebook_path.read_bytes()
        return _NotebookSnapshot(notebook_path=notebook_path, notebook_bytes=notebook_bytes)

    def _bind_server(self, host: str, port: int) -> _WatchHTTPServer:
        candidate = port
        for _ in range(100):
            try:
                return _WatchHTTPServer((host, candidate), self)
            except OSError as error:
                if error.errno != EADDRINUSE:
                    raise
                candidate += 1
        raise OSError(f"unable to bind host={host!r} starting at port={port}")


def watch_session(
    *,
    session_id: str | None,
    root_dir: Path,
    host: str,
    port: int,
    poll_interval: float,
    open_browser: bool,
) -> None:
    """Serve a read-only live notebook view for one session."""
    resolved_session_id = SessionService.resolve_session_id(root_dir, session_id)
    viewer = LiveNotebookViewer(
        session_id=resolved_session_id,
        root_dir=root_dir,
        host=host,
        port=port,
        poll_interval=poll_interval,
        open_browser=open_browser,
    )
    try:
        viewer.start()
        viewer.wait_forever()
    except KeyboardInterrupt:
        pass
    finally:
        viewer.stop()


def _read_manifest(manifest_path: Path, session_id: str) -> dict[str, Any]:
    if not manifest_path.exists():
        raise SessionNotFoundError(f"session not found: {session_id}")
    return json.loads(manifest_path.read_text())


def _notebook_path(root_dir: Path, manifest: dict[str, Any]) -> Path:
    notebook_path = Path(str(manifest["notebook_path"]))
    if notebook_path.is_absolute():
        return notebook_path
    return root_dir / notebook_path


def _render_html(notebook_bytes: bytes) -> tuple[str, dict[str, Any]]:
    notebook = nbformat.reads(notebook_bytes.decode("utf-8"), as_version=4)
    for template_name in ("lab", "classic"):
        try:
            body, resources = HTMLExporter(template_name=template_name).from_notebook_node(notebook)
            return body, resources
        except Exception:
            continue
    raise RuntimeError("failed to render notebook with nbconvert templates: lab, classic")


def _content_hash(html: str, resources: dict[str, Any]) -> str:
    """Compute a content-based etag from rendered HTML and resources."""
    hasher = hashlib.sha256()
    hasher.update(html.encode("utf-8"))
    for name in sorted(resources.get("outputs", {}).keys()):
        payload = resources["outputs"][name]
        data = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
        hasher.update(name.encode("utf-8"))
        hasher.update(data)
    return hasher.hexdigest()[:16]


def _inject_reloader(html: str, etag: str) -> str:
    etag_json = json.dumps(etag)
    script = f"""
<script>
(() => {{
  let current = {etag_json};
  const poll = async () => {{
    try {{
      const value = (await fetch('/etag', {{ cache: 'no-store' }})).text();
      const etag = await value;
      if (etag !== current) {{
        window.location.reload();
      }}
    }} catch (_err) {{
      // ignore transient polling errors
    }}
  }};
  setInterval(poll, 500);
  poll();
}})();
</script>
"""
    marker = "</body>"
    if marker in html:
        return html.replace(marker, f"{script}\n{marker}")
    return f"{html}\n{script}"


def _write_render_bundle(render_dir: Path, html: str, resources: dict[str, Any]) -> None:
    render_dir.mkdir(parents=True, exist_ok=True)
    index_path = render_dir / "index.html"
    tmp_path = index_path.with_suffix(".html.tmp")
    tmp_path.write_text(html)
    tmp_path.replace(index_path)

    output_files_dir = str(resources.get("output_files_dir", "files"))
    outputs_dir = render_dir / output_files_dir
    for name, payload in dict(resources.get("outputs", {})).items():
        target = outputs_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
        temp_target = target.with_suffix(target.suffix + ".tmp")
        temp_target.write_bytes(data)
        temp_target.replace(target)
