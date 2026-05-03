---
name: pyvista-interactive
description: Show interactive 3D PyVista scenes to users from a jupyter-workbench session. Use when analysis output needs visual verification in a browser.
---

# PyVista Interactive

Visualization runs inside the persistent Jupyter kernel via trame-vtklocal (VTK.wasm). One CLI tool, one kernel, one session.

## Show a scene

```bash
jupyter-workbench open --session-id review-1

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

Ask the user to open the browser URL. The `scene` handle stays in kernel memory for updates and cleanup.

Builder options:
- `.port(9000)` — fixed port; omit for OS-assigned (supports multiple scenes)
- `.public_host('my-server.local')` — when the server is accessed via a different hostname
- `.title('Pressure field')` — scene title in the browser
- `.track_camera()` — log camera events to the session event log (pass `event_log` to `for_session`)
- `.use(extension)` — register a custom `SceneExtension`

## Observation loop

The core human-in-the-loop workflow:

1. `exec` creates or updates the scene via `PyVistaDisplay`.
2. User views and manipulates the scene in the browser.
3. Agent captures a screenshot or polls events.
4. Agent explains what changed before applying the next update.

Update a running scene:

```bash
jupyter-workbench exec --session-id review-1 "
plotter.add_mesh(pv.Cube(), color='green', opacity=0.5)
scene.refresh()
"
```

Close when done:

```bash
jupyter-workbench exec --session-id review-1 "
scene.close()
"
```

## Screenshots

Use the helper — it creates the artifact directory and returns the path:

```bash
jupyter-workbench exec --session-id review-1 "
from jupyter_workbench.adapters.visualization.screenshots import capture_screenshot
shot = capture_screenshot('review-1', '.jupyter-workbench', 'scene1.png', plotter=plotter)
print(shot)
"
```

Direct fallback:

```bash
jupyter-workbench exec --session-id review-1 "
from pathlib import Path
path = Path('.jupyter-workbench/sessions/review-1/visualizations/screenshots/scene1.png')
path.parent.mkdir(parents=True, exist_ok=True)
plotter.screenshot(str(path))
print(path)
"
```

Snapshot includes screenshot paths in `visualization_summary.screenshots`.

## Durable interaction events

Camera tracking via the builder:

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

Additional callbacks (picks, sliders, keys) via `PyVistaTrameHelper`:

```bash
jupyter-workbench exec --session-id review-1 "
from jupyter_workbench.adapters.visualization.pyvista_trame import PyVistaTrameHelper

viz = PyVistaTrameHelper('.jupyter-workbench')
viz.register_pick_callback('review-1', plotter, events)
viz.register_slider_callback('review-1', plotter, events, (0.0, 10.0), 'threshold')
viz.register_key_callback('review-1', plotter, events)
"
```

Poll events:

```bash
jupyter-workbench exec --session-id review-1 "
records, cursor = events.read(cursor=0)
print({'events': records, 'cursor': cursor})
"
```

Wait with timeout:

```bash
jupyter-workbench exec --session-id review-1 "
records, cursor, timed_out = events.wait(cursor, timeout=10.0)
print({'events': records, 'cursor': cursor, 'timed_out': timed_out})
"
```

Event records have `seq`, `ts`, `type`, and `payload`. Snapshot surfaces `event_summary`.

## Inspect visualization state

```bash
jupyter-workbench snapshot --session-id review-1
```

Key fields: `visualization_status`, `visualization_summary.active_scene.browser_url`, `visualization_summary.scene_revision`, `visualization_summary.screenshots`.

Persisted under:

```text
.jupyter-workbench/sessions/review-1/visualizations/
  manifests/active.json
  screenshots/
```

## Recover degraded visualization

`visualization_status: "visualization_degraded"` means the scene failed but the kernel may still be healthy. Re-execute the scene setup through `exec` and check that `visualization_delta.scene.status == "healthy"` or `visualization_status` returns to `"visualization_healthy"`.

Rebuild through the existing kernel/session so notebook lineage stays authoritative.
