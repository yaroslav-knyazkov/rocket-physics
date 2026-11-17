"""projects/fx27/runs -- the entry points (dev/docs/architecture-38-fx27-
port.md SS38.6/SS38.11, ticket FX27-4; reorganised Phase 2.27,
architecture-43-fx27-restructure.md SS43.3/SS43.9 FX27D-4). One file per
analysis type under `runs/point/` (not one folder per competition as
before) -- `comparison.py` picks its competition/case via `--case`
(SS43.5). Run as `python -m projects.fx27.runs.point.<name>` from the
repo root. Every script writes its artifacts to `output/` via
`apps._shared.artifacts.output_dir()` (gitignored) -- never into
`projects/`.
"""
