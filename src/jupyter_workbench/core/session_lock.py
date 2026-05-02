"""Per-session file lock utilities."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from filelock import FileLock


class SessionLock:
    """Cross-platform per-session mutation lock."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or Path(".jupyter-workbench")

    @contextmanager
    def acquire(self, session_id: str) -> Iterator[None]:
        """Acquire the mutation lock for one session."""
        lock_path = self.root_dir / "sessions" / session_id / "session.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(lock_path)):
            yield
