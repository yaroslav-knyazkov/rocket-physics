"""projects/fx27/runs -- the 7 entry points (dev/docs/architecture-38-fx27-
port.md SS38.6/SS38.11, ticket FX27-4). Run as
`python -m projects.fx27.runs.<name>` from the repo root. Every script
writes its artifacts to `output/` via `apps._shared.artifacts.output_dir()`
(gitignored) -- never into `projects/`.
"""
