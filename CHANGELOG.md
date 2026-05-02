# Changelog

Caveman style. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/). Versions before X.Y.Z in git history only.

## [Unreleased]

### Added
- Public DTO, port, service constructor, CLI signature, and MCP skeleton contracts.
- Bootstrap `jupyter-workbench` package scaffold.

### Changed
- Session close now reports failed shutdowns instead of hiding live kernels.
- Session open now reopens closed/create-failed sessions with crash-safe manifests.
