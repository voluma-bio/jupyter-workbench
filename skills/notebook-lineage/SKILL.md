---
name: notebook-lineage
description: Inspect and recover notebook-backed workbench lineage.
---

# Notebook Lineage

Notebook history is the authority for recovery and reuse. Use lineage commands when a kernel is degraded, when checking replay history, or when handing durable notebook state to another agent.

## Inspect lineage

```bash
jupyter-workbench lineage --session-id review-1
```

`lineage` is read-only. It reports the active notebook, derived notebooks, and replay revision count from `sessions/<id>/lineage.json` plus durable notebook files.
The output also includes full `revisions`, `active_notebook`, and `is_derived` so agents can see the exact replay, derive, and compact chain before mutating notebook state.

Interpret revision history as an audit trail: `revisions` are replay backups of earlier active notebooks, derived notebooks are source-preserving working copies, and compacted notebooks are cleanup artifacts with kept/removed cell metadata. Before mutating lineage, identify which notebook is active, whether it is already derived, and which source notebook must remain preserved for recovery.

## When to derive vs compact

Use `derive` when you want a safe working copy before manual edits, exploratory cleanup, or additional notes. Use `compact` when the goal is to remove failed or explicitly selected dead-end cells while preserving the accepted notebook story in a new artifact. If unsure whether a cell is load-bearing, derive first and compact only after the lineage and snapshot make the source relationship clear.

## Derive a clean notebook

Use `derive` before exploratory edits that should not alter the current notebook artifact:

```bash
jupyter-workbench derive --session-id review-1
```

Derive copies every cell from the current active notebook into `sessions/<id>/notebooks/derived_N.ipynb`, records the derivation in `lineage.json`, and updates the manifest so future `exec` and `markdown` writes go to the derived notebook. If a derived notebook is already active, derive chains from that active notebook.

## Compact dead-end cells

Use `compact` to make a cleanup notebook:

```bash
jupyter-workbench compact --session-id review-1
```

Without explicit cell indexes, compact removes failed code cells that have a later successful code cell, treating them as dead-end attempts superseded by corrections. To remove specific cells, repeat `--cell`:

```bash
jupyter-workbench compact --session-id review-1 --cell 3 --cell 4
```

Compact writes a new `sessions/<id>/notebooks/compacted_N.ipynb`, records removed/kept cells in lineage metadata, and makes the compacted notebook active for future writes.

## Source preservation guarantee

Lineage mutations never edit the notebook they derive or compact from. The source notebook remains on disk unchanged, and cleanup work always lands in a new derived notebook artifact.

## Recover a degraded kernel

`open` reports `kernel_degraded` when durable session state exists but the kernel is unavailable. Do not assume `open` silently repairs it. Run explicit replay:

```bash
jupyter-workbench replay --session-id review-1
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
