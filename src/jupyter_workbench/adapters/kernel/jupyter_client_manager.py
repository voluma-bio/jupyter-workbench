"""jupyter_client kernel manager adapter."""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path
from typing import Any, cast

from jupyter_client.blocking.client import BlockingKernelClient
from jupyter_client.manager import KernelManager

from jupyter_workbench.core.interfaces import ExecutionOutput


class JupyterClientManager:
    """KernelPort implementation backed by jupyter_client."""

    def __init__(self, root_dir: Path | None = None, timeout_seconds: float = 60.0) -> None:
        self.root_dir = root_dir or Path(".jupyter-workbench")
        self.timeout_seconds = timeout_seconds
        self._managers: dict[str, KernelManager] = {}
        self._clients: dict[str, BlockingKernelClient] = {}

    def start(self, session_id: str) -> None:
        """Start a kernel for a session."""
        connection_file = self._connection_file(session_id)
        connection_file.parent.mkdir(parents=True, exist_ok=True)
        manager = KernelManager(connection_file=str(connection_file))
        env = os.environ.copy()
        env["JPY_PARENT_PID"] = "0"
        manager.start_kernel(
            env=env,
            extra_arguments=["--IPKernelApp.parent_handle=0", "--no-stdout", "--no-stderr"],
            independent=True,
        )
        self._managers[session_id] = manager
        manager.write_connection_file()
        # The session connection file is durable workbench state, not a temp file.
        setattr(manager, "_connection_file_written", False)
        client = cast(BlockingKernelClient, manager.blocking_client())
        client.start_channels()
        try:
            client.wait_for_ready(timeout=self.timeout_seconds)
        except Exception:
            self.shutdown(session_id)
            raise
        self._clients[session_id] = client
        self._write_kernel_pid(session_id, manager)

    def connect(self, session_id: str, connection_file: str) -> None:
        """Connect to an existing kernel for a session."""
        client = BlockingKernelClient(connection_file=connection_file)
        client.load_connection_file(connection_file)
        client.start_channels()
        self._clients[session_id] = client

    def execute(self, session_id: str, code: str) -> ExecutionOutput:
        """Execute code in a connected session kernel."""
        client = self._clients.get(session_id)
        if client is None:
            connection_file = self._connection_file(session_id)
            if not connection_file.exists():
                return ExecutionOutput(stdout="", stderr="", display_data=[], error="kernel not connected")
            self.connect(session_id, str(connection_file))
            client = self._clients[session_id]

        message_id = client.execute(code)
        deadline = time.monotonic() + self.timeout_seconds
        stdout: list[str] = []
        stderr: list[str] = []
        display_data: list[dict[str, Any]] = []
        error: str | None = None

        while time.monotonic() < deadline:
            try:
                message = client.get_iopub_msg(timeout=1)
            except Exception:
                continue
            parent = message.get("parent_header", {})
            if parent.get("msg_id") != message_id:
                continue
            msg_type = message.get("msg_type")
            content = message.get("content", {})
            if msg_type == "stream":
                if content.get("name") == "stderr":
                    stderr.append(str(content.get("text", "")))
                else:
                    stdout.append(str(content.get("text", "")))
            elif msg_type in {"display_data", "execute_result"}:
                display_data.append(dict(content.get("data", {})))
            elif msg_type == "error":
                traceback = content.get("traceback") or []
                error = "\n".join(str(line) for line in traceback) or str(content.get("evalue", ""))
            elif msg_type == "status" and content.get("execution_state") == "idle":
                break
        else:
            error = error or f"execution timed out after {self.timeout_seconds:g}s"

        return ExecutionOutput(
            stdout="".join(stdout),
            stderr="".join(stderr),
            display_data=display_data,
            error=error,
        )

    def is_alive(self, session_id: str) -> bool:
        """Return whether a session kernel is reachable."""
        manager = self._managers.get(session_id)
        if manager is not None:
            try:
                if bool(manager.is_alive()):
                    return True
            except Exception:
                pass
        return self.probe_alive(session_id)

    def probe_alive(self, session_id: str) -> bool:
        """Probe kernel reachability without retaining persistent client state."""
        connection_file = self._connection_file(session_id)
        if not connection_file.exists():
            return False
        client = BlockingKernelClient(connection_file=str(connection_file))
        try:
            client.load_connection_file(str(connection_file))
            client.start_channels(iopub=False, stdin=False, control=False)
            client.wait_for_ready(timeout=min(self.timeout_seconds, 2.0))
            return bool(client.is_alive())
        except Exception:
            return False
        finally:
            try:
                client.stop_channels()
            except Exception:
                pass

    def shutdown(self, session_id: str) -> bool:
        """Stop a session kernel if it is running."""
        client = self._clients.pop(session_id, None)
        manager = self._managers.pop(session_id, None)

        if manager is None:
            connection_file = self._connection_file(session_id)
            if connection_file.exists():
                try:
                    manager = KernelManager(connection_file=str(connection_file))
                    manager.load_connection_file()
                except Exception:
                    manager = None

        if manager is not None:
            try:
                manager.shutdown_kernel(now=True)
            except Exception:
                self._kill_manager_process(manager)
            if self.probe_alive(session_id):
                self._kill_manager_process(manager)
                self._kill_pid_file(session_id)
        else:
            self._kill_pid_file(session_id)
        if client is not None:
            try:
                client.stop_channels()
            except Exception:
                pass
        time.sleep(0.5)
        return not self.probe_alive(session_id)

    def _connection_file(self, session_id: str) -> Path:
        return self.root_dir / "sessions" / session_id / "kernel.json"

    def _pid_file(self, session_id: str) -> Path:
        return self.root_dir / "sessions" / session_id / "kernel.pid"

    def _write_kernel_pid(self, session_id: str, manager: KernelManager) -> None:
        provisioner = getattr(manager, "provisioner", None)
        pid = getattr(provisioner, "pid", None)
        if not isinstance(pid, int):
            return
        pid_file = self._pid_file(session_id)
        tmp_file = pid_file.with_suffix(".pid.tmp")
        tmp_file.write_text(f"{pid}\n")
        tmp_file.replace(pid_file)

    def _kill_manager_process(self, manager: KernelManager) -> None:
        try:
            kernel = getattr(manager, "kernel", None)
            if kernel is not None:
                kernel.kill()
                kernel.wait(timeout=5)
        except Exception:
            pass

    def _kill_pid_file(self, session_id: str) -> None:
        try:
            pid = int(self._pid_file(session_id).read_text().strip())
        except (OSError, ValueError):
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            return
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not self.probe_alive(session_id):
                return
            time.sleep(0.1)
        try:
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        except Exception:
            pass
