---
name: pyvista-interactive
description: Build PyVista + trame-vtklocal interactive scenes inside a jupyter-workbench kernel session.
---

# PyVista Interactive

Use this skill when an agent needs a user-visible PyVista scene from a durable `jupyter-workbench` session. Visualization runs inside the persistent Jupyter kernel via `trame-vtklocal` (VTK.wasm). There is no separate visualization CLI.

## Start a live scene

1. Open or attach to a session.

```bash
jupyter-workbench open --session-id review-1
```

2. Execute scene setup code in the kernel. The `PyVistaDisplay` builder handles interactor normalization, trame server lifecycle, and display automatically.

```bash
jupyter-workbench exec --session-id review-1 "
import pyvista as pv
from jupyter_workbench.visualization import PyVistaDisplay

plotter = pv.Plotter(off_screen=True)
plotter.add_mesh(pv.Sphere(), color='tomato')
plotter.add_axes()
scene = PyVistaDisplay.for_session('review-1', plotter).port(9000).show(display=False)
print(scene.url)
"
```

The `scene` handle stays in kernel memory for later updates, screenshots, and cleanup.

Options on the builder (all optional):
- `.title('My Scene')` — set scene title
- `.port(9000)` — explicit port (default: OS-assigned)
- `.public_host('my-server.local')` — public URL host
- `.track_camera()` — log camera movement to the session event log (requires `event_log`)
- `.use(extension)` — register a custom `SceneExtension`
- `.show(display=False)` — return handle without displaying iframe

The execution result should surface `visualization_delta` when trame display output includes a browser URL. If the URL is present, ask the user to open it; do not replace the review with text-only descriptions.

## Inspect durable visualization state

```bash
jupyter-workbench snapshot --session-id review-1
```

Read `visualization_status`, `visualization_summary.active_scene.browser_url`, `visualization_summary.scene_revision`, `visualization_summary.degraded_scenes`, `visualization_summary.recovery_guidance`, and `visualization_summary.screenshots`. These are persisted under:

```text
.jupyter-workbench/sessions/review-1/visualizations/
  manifests/active.json
  screenshots/
```

## Scene lifecycle

Close a scene when done to free the port and update status:

```bash
jupyter-workbench exec --session-id review-1 "
scene.close()
"
```

Or use a context manager for automatic cleanup:

```bash
jupyter-workbench exec --session-id review-1 "
import pyvista as pv
from jupyter_workbench.visualization import PyVistaDisplay

plotter = pv.Plotter(off_screen=True)
plotter.add_mesh(pv.Sphere(), color='tomato')
with PyVistaDisplay.for_session('review-1', plotter).port(9000).show(display=False) as scene:
    print(scene.url)
    # scene closes automatically on exit
"
```

Update a running scene after modifying the plotter:

```bash
jupyter-workbench exec --session-id review-1 "
plotter.add_mesh(pv.Cube(), color='green', opacity=0.5)
scene.refresh()
"
```

## Recover degraded visualization

A snapshot with `visualization_status: "visualization_degraded"` means the visualization layer failed or trame display data did not surface a usable browser URL. The kernel can still be healthy and remains the source of truth for recovery. Continue using `jupyter-workbench exec`, `snapshot`, `lineage`, `replay`, and future derive/compact flows against the same session.

Recovery path:

1. Read `visualization_summary.degraded_scenes` and `visualization_summary.recovery_guidance`.
2. Re-execute the scene setup cell/code through `jupyter-workbench exec --session-id <id> ...`.
3. Confirm the next `exec` result has `visualization_delta.scene.status == "healthy"` or the next snapshot returns `visualization_status: "visualization_healthy"`.

Do not launch a second runtime tool to reconstruct the scene; rebuild it through the existing workbench kernel/session so notebook lineage remains authoritative.

## Capture a screenshot

Screenshots are captured by executing Python in the same kernel that owns the live plotter. Prefer the helper because it creates the durable artifact directory and returns the artifact path.

```bash
jupyter-workbench exec --session-id review-1 "
from jupyter_workbench.adapters.visualization.screenshots import capture_screenshot
shot = capture_screenshot('review-1', '.jupyter-workbench', 'scene1.png', plotter=plotter)
print(shot)
"
```

Direct pattern when a helper import is not appropriate:

```bash
jupyter-workbench exec --session-id review-1 "
from pathlib import Path
path = Path('.jupyter-workbench/sessions/review-1/visualizations/screenshots/scene1.png')
path.parent.mkdir(parents=True, exist_ok=True)
plotter.screenshot(str(path))
print(path)
"
```

A later `snapshot` should include the screenshot path in `visualization_summary.screenshots`.

## Observation loop

Repeat this loop for human-in-the-loop work:

1. `exec` creates or updates the PyVista scene via `PyVistaDisplay`.
2. The scene serves a live browser view via trame-vtklocal (VTK.wasm).
3. User observes and manipulates the scene in the browser (rotate, pan, zoom).
4. Agent captures screenshots or polls event helpers when available.
5. Agent explains what changed and why in plain language before applying another `exec` update.

## Durable interaction events

Enable camera tracking via the builder for automatic event logging:

```bash
jupyter-workbench exec --session-id review-1 "
from jupyter_workbench.adapters.visualization.event_log import DurableEventLog
from jupyter_workbench.visualization import PyVistaDisplay

events = DurableEventLog('.jupyter-workbench', 'review-1')
scene = (
    PyVistaDisplay.for_session('review-1', plotter, event_log=events)
    .track_camera()
    .port(9000)
    .show(display=False)
)
print(scene.url)
"
```

For additional interaction callbacks (picks, sliders, keys), use `PyVistaTrameHelper` directly:

```bash
jupyter-workbench exec --session-id review-1 "
from jupyter_workbench.adapters.visualization.pyvista_trame import PyVistaTrameHelper

viz = PyVistaTrameHelper('.jupyter-workbench')
viz.register_pick_callback('review-1', plotter, events)
viz.register_slider_callback('review-1', plotter, events, (0.0, 10.0), 'threshold')
viz.register_key_callback('review-1', plotter, events)
"
```

Poll from a caller-managed cursor:

```bash
jupyter-workbench exec --session-id review-1 "
records, cursor = events.read(cursor=0)
print({'events': records, 'cursor': cursor})
"
```

Wait for a new interaction with an explicit timeout:

```bash
jupyter-workbench exec --session-id review-1 "
records, cursor, timed_out = events.wait(cursor, timeout=10.0)
print({'events': records, 'cursor': cursor, 'timed_out': timed_out})
"
```

Event records have `seq`, `ts`, `type`, and `payload`. Snapshot includes `event_summary.recent_events`, `event_summary.total_event_count`, and `event_summary.cursor`.
