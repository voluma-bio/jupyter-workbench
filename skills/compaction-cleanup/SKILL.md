---
name: compaction-cleanup
description: Clean and compact workbench notebooks without requiring live visualization.
---

# Compaction Cleanup

Use this skill for the canonical cheap-agent cleanup workflow after expensive notebook-backed analysis is done and before handing the notebook to another agent or reviewer. Cleanup uses durable `jupyter-workbench` notebook lineage only; it does not need a live browser, PyVista, trame, or visualization kernel.

## Prerequisites

- `jupyter-workbench` CLI is installed and available.
- An existing session has notebook history under the configured workbench root.
- The expensive analysis agent has finished the analysis story and, when visualization was used, has preserved durable artifacts such as snapshots, screenshots, outputs, event logs, and notebook cells.
- Know the session id. Use explicit positional `<session_id>` arguments for handoff work on lineage commands.

## When to use

Use compaction cleanup:

- after expensive analysis or review has reached accepted parameters/results,
- before handing the workbench session to a cheaper cleanup agent,
- before sharing a notebook with a reviewer who should not read every failed attempt,
- when a notebook has failed cells, superseded experiments, duplicate displays, or noisy debug output.

Do not use cleanup to reinterpret the analysis, delete accepted decisions, or rebuild visualizations. If the cleanup agent cannot tell whether a cell is load-bearing, keep it or derive first and explain the uncertainty.

## Workflow

### 1. Inspect lineage

Start from the durable lineage record:

```bash
jupyter-workbench lineage <session-id>
```

Read the reported `active_notebook`, `revisions`, derived notebooks, compacted notebooks, replay history, and `is_derived` state. The lineage tells you which notebook is current and which source notebooks must remain preserved.

Optionally inspect the snapshot for cell counts, recent execution summaries, output artifacts, screenshots, event summaries, and visualization status:

```bash
jupyter-workbench snapshot --session-id <session-id>
```

### 2. Identify dead-end cells

Remove only cells that are not part of the accepted analysis story:

- code cells with errors that are superseded by later successful cells,
- abandoned threshold/parameter attempts replaced by accepted values,
- duplicate display or setup cells with no unique screenshot, event, output artifact, or decision,
- temporary debug prints that do not explain the final result,
- exploratory branches explicitly marked abandoned or dead-end.

Keep cells that carry durable meaning:

- final setup, imports, and accepted parameters,
- artifact loads/writes and manifest references,
- screenshot paths and event-log reads used in review,
- markdown explanations, user correction notes, and rationale,
- final reports, measurements, and handoff summaries.

### 3. Derive before manual edits

Before any manual notebook edits or exploratory cleanup, derive a fresh notebook:

```bash
jupyter-workbench derive <session-id>
```

`derive` copies every cell from the current active notebook into a new `sessions/<id>/notebooks/derived_N.ipynb`, records the source relationship in `lineage.json`, and makes the derived notebook active. Future writes go to the derived notebook while the source notebook remains unchanged.

### 4. Compact automatically

For the common case, let `compact` remove failed code cells that have later successful code cells:

```bash
jupyter-workbench compact <session-id>
```

This creates a new compacted notebook, records kept/removed cells in lineage metadata, and makes the compacted notebook active.

### 5. Compact specific cells

When you have inspected cells and know exact dead ends, pass explicit cell indexes:

```bash
jupyter-workbench compact <session-id> -c 3 -c 5 -c 7
```

Use explicit cells for duplicate displays, abandoned experiments, and noisy debug cells that automatic compaction cannot infer. Explain why each removed cell is safe to omit from the accepted story.

### 6. Verify source preservation and handoff state

After compaction, inspect lineage and snapshot again:

```bash
jupyter-workbench lineage <session-id>
jupyter-workbench snapshot --session-id <session-id>
```

Verify:

- `active_notebook` points at the derived or compacted notebook,
- the previous source notebook still exists on disk and remains referenced by lineage,
- removed cells are recorded in compact metadata,
- screenshots, output artifacts, event summaries, final parameters, and report cells remain referenced,
- the cleanup result is understandable without replaying visualization.

## Source preservation guarantee

Lineage mutations never edit the notebook they derive or compact from. `derive` and `compact` always write a new notebook artifact and update the active pointer. Source notebooks remain on disk unchanged for recovery, audit, and comparison.

## No visualization runtime needed

Cheap cleanup agents need only the `jupyter-workbench` CLI and durable files. They do not need:

- an active browser session,
- a live trame server,
- PyVista imports,
- a healthy visualization kernel.

Use lineage, snapshots, notebooks, outputs, screenshots, and event logs to understand what happened. If visualization state is degraded, do not start a second runtime just for cleanup; preserve the degradation note and compact only cells whose role is clear from durable artifacts.
