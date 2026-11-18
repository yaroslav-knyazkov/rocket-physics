"""projects/fx27/data/utils -- campaign-agnostic logic shared across
cspace/euroc (as opposed to `data/cspace/`/`data/euroc/`, which hold
per-competition content). First tenant: `aero/drag_theory.py` (Step 157,
moved out of `data/cspace/aero/` -- it is generic physics, not
cspace-specific; the campaign-specific CSVs/generators it feeds stay
under `data/cspace/aero/`).
"""
