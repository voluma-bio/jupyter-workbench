"""nbformat notebook store adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import nbformat
from nbformat import NotebookNode


class NbformatStore:
    """NotebookPort implementation backed by nbformat."""

    def create(self, path: Path) -> None:
        """Create an empty notebook at path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        notebook = nbformat.v4.new_notebook()
        nbformat.write(notebook, path)

    def append_code_cell(self, path: Path, source: str, outputs: list[dict[str, Any]]) -> int:
        """Append a code cell and return its cell index."""
        notebook = self._read(path)
        cell_outputs = [NotebookNode(output) for output in outputs]
        cell = nbformat.v4.new_code_cell(source=source, outputs=cell_outputs)
        notebook.cells.append(cell)
        self._write(path, notebook)
        return len(notebook.cells) - 1

    def append_markdown_cell(self, path: Path, source: str) -> int:
        """Append a markdown cell and return its cell index."""
        notebook = self._read(path)
        notebook.cells.append(nbformat.v4.new_markdown_cell(source=source))
        self._write(path, notebook)
        return len(notebook.cells) - 1

    def read_cells(self, path: Path) -> list[dict[str, Any]]:
        """Read notebook cells as serializable dictionaries."""
        notebook = self._read(path)
        return [dict(cell) for cell in notebook.cells]

    def cell_count(self, path: Path) -> int:
        """Return the number of cells in a notebook."""
        return len(self._read(path).cells)

    def _read(self, path: Path) -> NotebookNode:
        return cast(NotebookNode, nbformat.read(path, as_version=4))

    def _write(self, path: Path, notebook: NotebookNode) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        nbformat.write(notebook, path)
