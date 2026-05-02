# jupyter-workbench bootstrap

## Install

Use one of these installation paths:

```bash
uv add jupyter-workbench
uv tool install jupyter-workbench
uvx jupyter-workbench --help
```

For local development in this repo, use:

```bash
uv sync --extra dev
uv run jupyter-workbench --help
```

## Session management

The default durable root is `.jupyter-workbench/` in the current directory.

Create a new session:

```bash
jupyter-workbench open
```

Create or reattach to a named session:

```bash
jupyter-workbench open --session-id review-1
jupyter-workbench open --session-id review-1
```

The second command reattaches to the existing durable session when its kernel is healthy. It does not create a second notebook lineage root for the same session id.

Inspect one session and list all sessions:

```bash
jupyter-workbench status review-1
jupyter-workbench list
```

Use a non-default root when needed:

```bash
jupyter-workbench open --root-dir /path/to/.jupyter-workbench --session-id review-1
jupyter-workbench status --root-dir /path/to/.jupyter-workbench review-1
jupyter-workbench list --root-dir /path/to/.jupyter-workbench
```

Close live runtime resources while preserving artifacts:

```bash
jupyter-workbench close review-1
```

Close does not delete the manifest, active notebook, outputs, visualization event logs, or screenshots. A session whose durable state remains but whose kernel is unavailable reports `kernel_degraded`; explicit replay is the recovery path in a later phase.

A new session creates:

```text
.jupyter-workbench/
  sessions/
    <session_id>/
      manifest.json
      kernel.json
      notebooks/
        active.ipynb
      outputs/
      visualizations/
        manifests/
        screenshots/
```

## Execution

Execute inline Python in the persistent kernel and append it to `notebooks/active.ipynb` before execution:

```bash
jupyter-workbench exec --session-id review-1 "print('hello')"
```

Execute a Python file as one notebook-backed code cell. The cell source is the file contents and metadata records the source path:

```bash
jupyter-workbench exec --session-id review-1 --file analysis_step.py
```

Append markdown notes without rewriting prior cells:

```bash
jupyter-workbench markdown --session-id review-1 "## Review note\nUser asked for closer view."
```

If `--session-id` is omitted, execution commands target the most recent non-closed session under the root. Prefer explicit ids for multi-session work.

Execution responses are bounded. Large outputs and tracebacks are written under `sessions/<session_id>/outputs/` and returned as artifact paths.

Read the machine-readable session snapshot:

```bash
jupyter-workbench snapshot --session-id review-1
```

Snapshot reports kernel state, notebook path, cell count, recent execution summaries, artifact references, lineage pointer, and placeholder visualization fields.

## Visualization

Placeholder: start PyVista + trame scenes inside the persistent Jupyter kernel, expose browser URLs, poll events, and capture screenshots.

## Cleanup and lineage

Placeholder: inspect lineage, replay sessions, derive notebooks, and compact history for cheaper cleanup agents.
