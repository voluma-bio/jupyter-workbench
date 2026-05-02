"""Notebook-backed execution service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jupyter_workbench.core.interfaces import ExecutionOutput, KernelPort, NotebookPort
from jupyter_workbench.core.models import ExecResult, NotebookMutationResult
from jupyter_workbench.core.session_service import SessionNotFoundError

INLINE_LIMIT_BYTES = 64 * 1024
OUTPUT_WARNING_BYTES = 1024 * 1024


class ExecutionService:
    """Transport-agnostic notebook execution and markdown operations."""

    def __init__(
        self,
        kernel: KernelPort,
        notebook: NotebookPort,
        root_dir: Path | None = None,
    ) -> None:
        self.kernel = kernel
        self.notebook = notebook
        self.root_dir = root_dir or Path(".jupyter-workbench")

    def exec_code(
        self,
        code: str | None = None,
        *,
        session_id: str | None = None,
        file: Path | None = None,
    ) -> ExecResult:
        """Execute inline or file-backed code in a session notebook."""
        if file is not None:
            return self.exec_file(file, session_id=session_id)
        if code is None:
            raise ValueError("inline code or --file is required")
        return self._execute_source(code, session_id=session_id, metadata={})

    def exec_file(self, file_path: Path, *, session_id: str | None = None) -> ExecResult:
        """Execute a Python file as one notebook-backed code cell."""
        source = file_path.read_text()
        metadata = {"jupyter_workbench": {"source_file": str(file_path)}}
        return self._execute_source(source, session_id=session_id, metadata=metadata)

    def markdown(self, text: str, *, session_id: str | None = None) -> NotebookMutationResult:
        """Append markdown text to a session notebook."""
        resolved_session_id = self._resolve_session_id(session_id)
        manifest = self._read_manifest(resolved_session_id)
        notebook_path = self._notebook_path(manifest)
        cell_index = self.notebook.append_markdown_cell(notebook_path, text)
        return NotebookMutationResult(
            session_id=resolved_session_id,
            cell_index=cell_index,
            cell_type="markdown",
        )

    def _execute_source(
        self,
        source: str,
        *,
        session_id: str | None,
        metadata: dict[str, Any],
    ) -> ExecResult:
        resolved_session_id = self._resolve_session_id(session_id)
        manifest = self._read_manifest(resolved_session_id)
        notebook_path = self._notebook_path(manifest)

        cell_index = self.notebook.append_code_cell(notebook_path, source, [], metadata=metadata)
        execution = self.kernel.execute(resolved_session_id, source)
        outputs = self._notebook_outputs(execution)
        self.notebook.update_code_cell_outputs(
            notebook_path,
            cell_index,
            outputs,
            execution_count=cell_index,
        )

        full_output = self._full_output_text(execution)
        output_artifacts: list[str] = []
        inline_summary = full_output
        if self._byte_len(full_output) > INLINE_LIMIT_BYTES:
            artifact = self._write_output_artifact(resolved_session_id, cell_index, "output.txt", full_output)
            output_artifacts.append(artifact)
            inline_summary = self._truncate_text(full_output, INLINE_LIMIT_BYTES)
            inline_summary += f"\n\n[truncated; full output: {artifact}]"

        error_traceback = execution.error
        if execution.error:
            artifact = self._write_output_artifact(
                resolved_session_id,
                cell_index,
                "traceback.txt",
                execution.error,
            )
            output_artifacts.append(artifact)

        status = "error" if execution.error else "ok"
        return ExecResult(
            session_id=resolved_session_id,
            cell_index=cell_index,
            status=status,
            inline_summary=inline_summary,
            output_artifacts=output_artifacts,
            error_traceback=error_traceback,
            visualization_delta=None,
            output_size_warning=self._byte_len(full_output) > OUTPUT_WARNING_BYTES,
        )

    def _notebook_outputs(self, execution: ExecutionOutput) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        if execution.stdout:
            outputs.append({"output_type": "stream", "name": "stdout", "text": execution.stdout})
        if execution.stderr:
            outputs.append({"output_type": "stream", "name": "stderr", "text": execution.stderr})
        for data in execution.display_data:
            outputs.append({"output_type": "display_data", "data": data, "metadata": {}})
        if execution.error:
            outputs.append(
                {
                    "output_type": "error",
                    "ename": "ExecutionError",
                    "evalue": execution.error.splitlines()[-1] if execution.error.splitlines() else execution.error,
                    "traceback": execution.error.splitlines(),
                }
            )
        return outputs

    def _full_output_text(self, execution: ExecutionOutput) -> str:
        parts: list[str] = []
        if execution.stdout:
            parts.append(execution.stdout)
        if execution.stderr:
            parts.append(execution.stderr)
        for data in execution.display_data:
            parts.append(json.dumps(data, indent=2, sort_keys=True))
        if execution.error:
            parts.append(execution.error)
        return "\n".join(part for part in parts if part)

    def _write_output_artifact(self, session_id: str, cell_index: int, suffix: str, content: str) -> str:
        output_dir = self.root_dir / "sessions" / session_id / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"cell_{cell_index}_{suffix}"
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(content)
        tmp_path.replace(path)
        return str(path)

    def _resolve_session_id(self, session_id: str | None) -> str:
        if session_id is not None:
            return session_id
        sessions_dir = self.root_dir / "sessions"
        candidates: list[tuple[float, str]] = []
        for manifest_path in sessions_dir.glob("*/manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if str(manifest.get("status")) == "closed":
                continue
            candidates.append((manifest_path.stat().st_mtime, manifest_path.parent.name))
        if not candidates:
            raise SessionNotFoundError("no active sessions found; pass --session-id or run 'jupyter-workbench open'")
        return max(candidates)[1]

    def _read_manifest(self, session_id: str) -> dict[str, Any]:
        manifest_path = self.root_dir / "sessions" / session_id / "manifest.json"
        if not manifest_path.exists():
            raise SessionNotFoundError(f"session not found: {session_id}")
        return json.loads(manifest_path.read_text())

    def _notebook_path(self, manifest: dict[str, Any]) -> Path:
        notebook_path = Path(str(manifest["notebook_path"]))
        if notebook_path.is_absolute():
            return notebook_path
        return self.root_dir / notebook_path

    def _truncate_text(self, value: str, limit_bytes: int) -> str:
        encoded = value.encode("utf-8")
        if len(encoded) <= limit_bytes:
            return value
        return encoded[:limit_bytes].decode("utf-8", errors="ignore")

    def _byte_len(self, value: str) -> int:
        return len(value.encode("utf-8"))
