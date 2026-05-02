---
name: session-management
description: Manage jupyter-workbench sessions through the public CLI contract.
---

# Session Management

Use the single `jupyter-workbench` tool for lifecycle work. Do not invent parallel session roots, direct kernel commands, or separate visualization runtimes.

## Open or reattach

Default root is `.jupyter-workbench/`:

```bash
jupyter-workbench open
```

Prefer a stable session id when returning to work:

```bash
jupyter-workbench open --session-id review-1
```

Running `open` again with the same id reattaches when the existing kernel is healthy. It must not create another notebook lineage root for that session id.

## Inspect

```bash
jupyter-workbench status review-1
jupyter-workbench list
```

If durable state exists but the kernel is gone, treat `kernel_degraded` as an observable state. Do not silently recreate or replay the session. Replay is an explicit recovery action taught by the lineage skill in a later phase.

## Close

```bash
jupyter-workbench close review-1
```

Close stops live runtime resources only. Notebook, manifest, output, event, and screenshot artifacts remain under `.jupyter-workbench/sessions/<session_id>/`.

## Custom roots

When a workflow passes a custom root, keep using that root for all lifecycle commands:

```bash
jupyter-workbench open --root-dir /work/.jupyter-workbench --session-id review-1
jupyter-workbench status --root-dir /work/.jupyter-workbench review-1
jupyter-workbench list --root-dir /work/.jupyter-workbench
jupyter-workbench close --root-dir /work/.jupyter-workbench review-1
```


## Execute notebook-backed work

Use `exec` for compute-only and visualization setup work. Inline code and `--file` both append a code cell to the active notebook before execution and return the same structured result shape.

```bash
jupyter-workbench exec --session-id review-1 "print('ready')"
jupyter-workbench exec --session-id review-1 --file step.py
```

Use `markdown` for durable notes:

```bash
jupyter-workbench markdown --session-id review-1 "## What changed"
```

Use `snapshot` as the canonical machine-readable read surface after mutations:

```bash
jupyter-workbench snapshot --session-id review-1
```

Large outputs stay bounded in command responses. Follow artifact paths under `sessions/<session_id>/outputs/` when full stdout, rich output, or tracebacks are needed.
