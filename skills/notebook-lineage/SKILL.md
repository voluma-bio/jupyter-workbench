---
name: notebook-lineage
description: Inspect and recover notebook-backed workbench lineage.
---

# Notebook Lineage

Notebook history is the authority for recovery and reuse. Use lineage commands when a kernel is degraded, when checking replay history, or when handing durable notebook state to another agent.

## Inspect lineage

```bash
jupyter-workbench lineage review-1
```

`lineage` is read-only. It reports the active notebook, derived notebooks, and replay revision count from `sessions/<id>/lineage.json` plus durable notebook files.

## Recover a degraded kernel

`open` reports `kernel_degraded` when durable session state exists but the kernel is unavailable. Do not assume `open` silently repairs it. Run explicit replay:

```bash
jupyter-workbench replay review-1
```

Replay starts a fresh kernel, backs up the prior active notebook as `notebooks/revision_N.ipynb`, clears active outputs, and re-executes code cells in order. Visualization setup cells are ordinary notebook code, so replay re-runs them and can surface a new browser URL for the reconstructed scene path.

## Replay failure contract

If replay fails, previous notebook artifacts remain available, the session manifest is marked `replay_failed`, and the result includes:

- `failed_cell`
- `error_artifact`
- `status: replay_failed`

Inspect the artifact before deciding whether to edit or derive a cleanup notebook.

## Concurrency rule

Mutating lineage operations share the per-session mutation lock with `exec`, `markdown`, `open` create, and `close`. Read-only `lineage`, `snapshot`, `status`, and `list` do not acquire that lock and observe committed durable state only.
