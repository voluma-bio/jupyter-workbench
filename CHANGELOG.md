# Changelog

Caveman style. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/). Versions before X.Y.Z in git history only.

## [Unreleased]

### Added
- Explicit `replay` and `lineage` CLI/service paths with replay revision metadata.
- Per-session mutation lock for notebook-affecting session, execution, and replay operations.
- PyVista/trame visualization manifest tracking and screenshot helper flow.
- `pyvista-interactive` skill and bootstrap guidance for live scene URL and screenshots.
- Notebook-backed `exec`, `exec --file`, `markdown`, and `snapshot` CLI paths.
- Bounded execution summaries with output and traceback artifact handles.
- Public DTO, port, service constructor, CLI signature, and MCP skeleton contracts.
- Bootstrap `jupyter-workbench` package scaffold.

### Changed
- Replay failure now shuts down contaminated kernels, preserves `replay_failed` status, and removes orphan revision backups.
- Session close now reports failed shutdowns instead of hiding live kernels.
- Session open now reopens closed/create-failed sessions with crash-safe manifests.
