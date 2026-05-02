"""Durable JSONL event log for visualization callbacks."""

from __future__ import annotations

import json
import os
import time
import warnings
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any

from filelock import FileLock

POLL_INTERVAL_SECONDS = 0.5


class DurableEventLog:
    """Append-only per-session event log with caller-managed byte cursors."""

    def __init__(self, root_dir: Path | None = None, session_id: str | None = None) -> None:
        self.root_dir = root_dir or Path(".jupyter-workbench")
        self.session_id = session_id
        self.path = self._event_path(session_id) if session_id is not None else None
        self._seq = count(self._highest_existing_seq() + 1)

    def for_session(self, session_id: str) -> DurableEventLog:
        """Return an event log bound to a session under the same root."""
        return DurableEventLog(self.root_dir, session_id)

    def append(self, event_type: str, payload: dict[str, Any]) -> int:
        """Append an event and return its sequence number.

        Returns -1 when the event was not durably persisted.
        """
        try:
            path = self._require_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(str(self._lock_path())):
                disk_seq = self._highest_existing_seq()
                seq = max(next(self._seq), disk_seq + 1)
                self._seq = count(seq + 1)
                self._append_record(path, seq, event_type, payload)
        except Exception as exc:
            warnings.warn(f"failed to append durable event log record: {exc}", stacklevel=2)
            return -1
        return seq

    def _append_record(self, path: Path, seq: int, event_type: str, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            record = {"seq": seq, "ts": self._now(), "type": event_type, "payload": payload}
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def read(self, cursor: int = 0) -> tuple[list[dict[str, Any]], int]:
        try:
            path = self._require_path()
            if not path.exists():
                return [], 0
            start = max(cursor, 0)
            events: list[dict[str, Any]] = []
            last_good_offset = start
            with path.open("rb") as handle:
                handle.seek(start)
                for line in handle:
                    try:
                        data = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if isinstance(data, dict):
                        events.append(data)
                        last_good_offset = handle.tell()
                return events, last_good_offset
        except Exception:
            return [], max(cursor, 0)

    def wait(self, cursor: int, timeout: float = 30.0) -> tuple[list[dict[str, Any]], int, bool]:
        deadline = time.monotonic() + max(timeout, 0.0)
        current_cursor = max(cursor, 0)
        while True:
            events, new_cursor = self.read(current_cursor)
            if events:
                return events, new_cursor, False
            current_cursor = new_cursor
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return [], current_cursor, True
            time.sleep(min(POLL_INTERVAL_SECONDS, remaining))

    def _event_path(self, session_id: str | None) -> Path:
        if session_id is None:
            raise ValueError("session_id is required")
        return self.root_dir / "sessions" / session_id / "events.jsonl"

    def _lock_path(self) -> Path:
        path = self._require_path()
        return path.parent / "events.lock"

    def _require_path(self) -> Path:
        if self.path is None:
            self.path = self._event_path(self.session_id)
        return self.path

    def _highest_existing_seq(self) -> int:
        try:
            path = self._require_path()
            if not path.exists():
                return -1
            highest = -1
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, dict):
                        try:
                            seq = int(data.get("seq", -1))
                        except (TypeError, ValueError):
                            continue
                        highest = max(highest, seq)
            return highest
        except Exception:
            return -1

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
