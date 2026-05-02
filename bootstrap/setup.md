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

Close does not delete the manifest, active notebook, outputs, visualization event logs, or screenshots. A session whose durable state remains but whose kernel is unavailable reports `kernel_degraded`; explicit replay is the recovery path.

A new session creates:

```text
.jupyter-workbench/
  sessions/
    <session_id>/
      manifest.json
      kernel.json
      lineage.json
      notebooks/
        active.ipynb
      outputs/
      events.jsonl
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

Snapshot reports kernel state, notebook path, cell count, recent execution summaries, artifact references, lineage pointer, and persisted visualization summaries including active scene URL, scene revision, screenshots, degraded scenes, and recovery guidance.

## MCP server

Install or run with the optional MCP extra, then expose the same service-backed tools through FastMCP:

```bash
uv run --extra mcp jupyter-workbench-mcp
# or
uv run --extra mcp fastmcp run jupyter_workbench.mcp:mcp
```

MCP tools are thin wrappers around the same core services as the CLI. They return the same DTO field semantics as JSON dictionaries. Errors propagate as MCP tool errors rather than returned `{"error": ...}` dictionaries.

The MCP surface includes:

- `open_session(session_id?, root_dir?)`
- `exec_code(code?, session_id?, file?, root_dir?)`
- `markdown(text, session_id?, root_dir?)`
- `snapshot(session_id?, root_dir?)`
- `status(session_id, root_dir?)`
- `list_sessions(root_dir?)`
- `close(session_id, root_dir?)`
- `replay(session_id, root_dir?)`
- `lineage(session_id, root_dir?)`
- `derive(session_id, root_dir?)`
- `compact(session_id, cells_to_remove?, root_dir?)`

## Cheap-agent cleanup workflow

After an expensive analysis agent finishes notebook-backed work, hand the durable session to a cheap cleanup agent before final review. The expensive agent should preserve artifacts, optionally close live visualization resources, and provide the session id. The cleanup agent only needs the `jupyter-workbench` CLI and the `.jupyter-workbench/` durable root. It does not need PyVista, trame, a browser, or a live visualization kernel.

Step-by-step cleanup:

```bash
jupyter-workbench lineage review-1
jupyter-workbench derive review-1
jupyter-workbench compact review-1
jupyter-workbench snapshot --session-id review-1
```

Use lineage to understand the active notebook, revisions, derived notebooks, compacted notebooks, and source relationships. Use snapshot output to read recent execution summaries, screenshots, event summaries, visualization status, and artifact paths without running visualization code. If automatic compaction is too broad or too narrow, inspect the cells and compact specific dead-end cells instead:

```bash
jupyter-workbench compact review-1 -c 3 -c 5 -c 7
```

Cleanup must preserve the accepted analysis story: final parameters, artifact manifests, screenshot references, event evidence, correction explanations, and report cells. `derive` and `compact` write new notebook artifacts and leave source notebooks unchanged, so another agent can recover or compare the pre-cleanup notebook later.

## Visualization

Visualization runs inside the persistent Jupyter kernel through `exec`; there is no separate visualization daemon or CLI command. The runtime environment must import the v0 visualization dependencies: `pyvista`, `trame`, `trame-vtk`, `trame-vuetify`, `ipywidgets`, and `nest_asyncio2`.

Verify imports when bootstrapping a new environment:

```bash
uv run python -c "import pyvista, trame, trame_vtk, trame_vuetify, ipywidgets, nest_asyncio2; print('viz ok')"
```

Create and show a live browser-viewable scene from notebook-executed Python:

```bash
jupyter-workbench exec --session-id review-1 "
import pyvista as pv
plotter = pv.Plotter()
plotter.add_mesh(pv.Sphere(), color='tomato')
plotter.add_axes()
plotter.show(jupyter_backend='trame')
"
```

When trame display data includes a URL, `exec` persists scene metadata under:

```text
.jupyter-workbench/sessions/review-1/visualizations/manifests/active.json
```

The `exec` result includes `visualization_delta`, and `snapshot` includes the same scene in `visualization_summary`. Ask the user to open the browser URL for live review; do not reduce user-facing visualization to text-only summaries.

If display data indicates PyVista/trame output but no browser URL is available, the scene is recorded as degraded. Snapshots then report `visualization_status: "visualization_degraded"`, list degraded scenes in `visualization_summary.degraded_scenes`, and include recovery guidance. The kernel remains usable: continue `exec`, `snapshot`, `lineage`, `replay`, and future derive/compact workflows. Recover by re-executing the scene setup code through `jupyter-workbench exec`; do not start a second runtime tool just to rebuild visualization state.

Capture a screenshot by executing code in the same kernel that still owns `plotter`:

```bash
jupyter-workbench exec --session-id review-1 "
from jupyter_workbench.adapters.visualization.screenshots import capture_screenshot
shot = capture_screenshot('review-1', '.jupyter-workbench', 'scene1.png', plotter=plotter)
print(shot)
"
```

Screenshots are written under `sessions/<session_id>/visualizations/screenshots/` and appear in later snapshots. If the helper cannot find a plotter, pass the live plotter explicitly as `plotter=plotter`.

Register durable interaction callbacks from the same persistent kernel when agents need to observe user scene manipulations:

```bash
jupyter-workbench exec --session-id review-1 "
from jupyter_workbench.adapters.visualization.event_log import DurableEventLog
from jupyter_workbench.adapters.visualization.pyvista_trame import PyVistaTrameHelper

events = DurableEventLog('.jupyter-workbench', 'review-1')
viz = PyVistaTrameHelper('.jupyter-workbench')
viz.register_pick_callback('review-1', plotter, events)
viz.register_slider_callback('review-1', plotter, events, (0.0, 10.0), 'threshold')
viz.register_key_callback('review-1', plotter, events)
viz.register_camera_callback('review-1', plotter, events)
"
```

Read or wait on events with caller-managed byte cursors:

```bash
jupyter-workbench exec --session-id review-1 "
records, cursor = events.read(cursor=0)
print({'events': records, 'cursor': cursor})
records, cursor, timed_out = events.wait(cursor, timeout=10.0)
print({'events': records, 'cursor': cursor, 'timed_out': timed_out})
"
```

Event records append to `sessions/<session_id>/events.jsonl` as typed JSONL entries. Later snapshots include an `event_summary` with recent events, total count, and current cursor.

## Recovery and lineage

Inspect lineage without touching the live kernel:

```bash
jupyter-workbench lineage review-1
```

Replay a degraded or intentionally reconstructed session through a fresh kernel:

```bash
jupyter-workbench replay review-1
```

Replay backs up the current active notebook to `notebooks/revision_N.ipynb`, clears active code-cell outputs, re-executes code cells in order, updates `lineage.json`, and records `notebook_revision` in the manifest. Visualization setup cells are just notebook code, so replay reconstructs the notebook-backed visualization path; a new browser URL may be surfaced by the re-executed trame display.

If replay fails, the command returns `status: replay_failed`, `failed_cell`, and an `error_artifact` path under `outputs/`. Prior notebook artifacts remain available, and the manifest is marked `replay_failed` for explicit follow-up.

Per-session mutation locking serializes `open` when creating, `exec`, `markdown`, `replay`, and `close`. Read-only commands (`snapshot`, `status`, `list`, `lineage`) do not take the mutation lock and report the latest committed durable state.
