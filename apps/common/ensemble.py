"""apps/common/ensemble.py -- dispersion hooks + Monte-Carlo ensemble runner
(Step 105, Phase 2.17, dev/docs/architecture-35-paper-alignment.md SS35.4.5).

`sim/` itself stays single-run (no Monte Carlo inside the physics engine);
this module lives in the apps layer and drives many single `run_sim`-shaped
`evaluate(config)` calls, one per perturbed sample.

Two kinds of perturbed input, told apart by `Dispersion.stage`:

- `"scenario"` -- a field that lives on the `configs.schema.Scenario` tree
  itself (airframe mass/CG/inertia, motor, rail, ...). `Weight` is DERIVED
  inside `configs.schema.assemble` (SS32.3, `_weight_from_pieces`), so a
  perturbed airframe mass only takes effect through a fresh `assemble` call,
  not a post-hoc `Params` patch.
- `"params"` -- a dotted `Params` path (`aero.cx_scale`, `atmosphere.dT_K`,
  `thrust.k_J`, `wind.*`, `site.rail_angle_deg`, ...). These are routed
  through `Scenario.overrides` -- the SAME dotted-path mechanism
  `configs/schema.py`'s own module docstring documents (`{"site.rail_angle_deg":
  85.0}`) and `assemble` already applies via `sim.params.replace`, in the
  order `assemble` itself picks ("s0 AFTER overrides", SS31.4) -- so a
  dispersed rail angle correctly moves the derived pad attitude too, with no
  second code path needed.

Either way, every `Dispersion.apply(obj, value) -> obj` in a sample's list is
threaded through the SAME `Scenario` object, in order, and `assemble()` is
called exactly once per sample at the end -- there is no separate "scenario
stage" vs "params stage" execution pass; `stage` only selects which of the
two mechanisms above one particular dispersion's `apply` uses.

Reproducibility (the module's own acceptance tests): per-sample RNG streams
come from `numpy.random.SeedSequence(seed).spawn(n)`, drawn and APPLIED in
the main process before any work is handed to a worker -- so which sample
index gets which random stream, and which `Config` that sample becomes, is
fixed by `(seed, n)` alone, independent of `workers`. Only the expensive part
(`evaluate(config)`, typically a full `run_sim`) runs in a worker process;
`Dispersion.apply`/`draw` are often closures (not spawn-picklable) and are
NEVER sent across the process boundary -- only picklable `Config` objects
and the caller's own top-level `evaluate` function are.
"""

from __future__ import annotations

import csv
import dataclasses
import functools
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, NamedTuple, Sequence

import numpy as np

from configs.schema import Config, Scenario, assemble

__all__ = [
    "Dispersion",
    "EnsembleResult",
    "run_ensemble",
    "normal_path",
    "uniform_path",
    "lognormal_path",
    "airframe_mass",
    "airframe_cg",
    "wind_speed_dir",
    "save_csv",
]

# np.nanpercentile points reported by every `run_ensemble` call (SS35.4.5's
# "structured numpy table + percentile summaries").
_DEFAULT_PERCENTILES: "tuple[float, ...]" = (5.0, 25.0, 50.0, 75.0, 95.0)

# Column names `run_ensemble` always reserves for itself -- a user-chosen
# `Dispersion.name`/`evaluate()` metric key colliding with one of these would
# silently overwrite it in the structured table.
_RESERVED_COLUMNS = frozenset({"sample", "error"})


class Dispersion(NamedTuple):
    """One perturbed input. `apply(scenario, value) -> scenario` folds one
    drawn `value` into a (new, the tree is all frozen dataclasses) `Scenario`;
    `draw(rng) -> value` samples it from a `numpy.random.Generator`. `stage`
    is `"scenario"` (direct dotted replace on the `Scenario` tree) or
    `"params"` (routed through `Scenario.overrides`, see the module
    docstring) -- it exists so a caller building a `Dispersion` by hand knows
    which of the two `_apply_*` helpers below to reach for; the generic
    `normal_path`/`uniform_path`/`lognormal_path` constructors pick the right
    one from the `stage` argument alone."""

    name: str
    apply: Callable[[Any, float], Any]
    draw: Callable[[np.random.Generator], float]
    stage: str  # "scenario" | "params"


@dataclasses.dataclass(frozen=True)
class EnsembleResult:
    """One row per sample (SS35.4.5's "structured numpy table"): `sample`
    (0-based index), one float column per `Dispersion.name` (the drawn
    value), one float column per `evaluate()` metric key (NaN for a sample
    whose `evaluate` call raised), and `error` (the exception's
    `f"{type}: {msg}"`, empty string for a successful sample).

    `percentiles[metric][pct]` is `np.nanpercentile` of that metric's column
    at `pct` -- NaN rows (failed samples) are excluded from each metric's own
    percentiles, so a handful of failures don't poison the whole summary.
    """

    table: np.ndarray
    dispersion_names: "tuple[str, ...]"
    metric_names: "tuple[str, ...]"
    percentiles: "dict[str, dict[float, float]]"

    @property
    def n_failed(self) -> int:
        return int(np.count_nonzero(self.table["error"] != ""))


# ----------------------------------------------------------------------
# Generic dotted-path replace (Scenario side) -- `sim.params.replace` only
# ever rebuilds one level of `Params` group nesting (its own docstring); a
# `Scenario` dotted path can go three levels deep (`rocket.airframe.m`), so
# this is its own small recursive helper, not a reuse of that one.
# ----------------------------------------------------------------------


def _dotted_replace(obj: Any, path: str, value: Any) -> Any:
    head, sep, rest = path.partition(".")
    if not sep:
        return dataclasses.replace(obj, **{head: value})
    return dataclasses.replace(obj, **{head: _dotted_replace(getattr(obj, head), rest, value)})


def _apply_scenario_path(path: str) -> Callable[[Scenario, float], Scenario]:
    def apply(sc: Scenario, value: float) -> Scenario:
        return _dotted_replace(sc, path, value)

    return apply


def _apply_params_path(path: str) -> Callable[[Scenario, float], Scenario]:
    def apply(sc: Scenario, value: float) -> Scenario:
        # Staged into Scenario.overrides -- configs.schema.assemble applies
        # it via sim.params.replace itself, in assemble's own order (notably
        # "s0 AFTER overrides", SS31.4), not a second, independent code path.
        return dataclasses.replace(sc, overrides={**sc.overrides, path: value})

    return apply


def _clip(draw: Callable[[np.random.Generator], float], lo: "float | None", hi: "float | None"):
    if lo is None and hi is None:
        return draw

    def clipped(rng: np.random.Generator) -> float:
        v = draw(rng)
        if lo is not None:
            v = max(v, lo)
        if hi is not None:
            v = min(v, hi)
        return v

    return clipped


# ----------------------------------------------------------------------
# Generic path-based constructors (SS35.4.5): one dotted path, any
# Params/Scenario field, "scenario" or "params" stage.
# ----------------------------------------------------------------------


def normal_path(
    path: str,
    mean: float,
    sigma: float,
    stage: str = "params",
    name: "str | None" = None,
    clip_min: "float | None" = None,
    clip_max: "float | None" = None,
) -> Dispersion:
    """`value ~ N(mean, sigma)`, optionally clipped to `[clip_min, clip_max]`
    (e.g. a mass or a wind speed must stay >= 0)."""
    if stage not in ("scenario", "params"):
        raise ValueError(f"normal_path: stage must be 'scenario' or 'params', got {stage!r}")
    draw = _clip(lambda rng: float(rng.normal(mean, sigma)), clip_min, clip_max)
    apply = _apply_scenario_path(path) if stage == "scenario" else _apply_params_path(path)
    return Dispersion(name=name or f"normal:{path}", apply=apply, draw=draw, stage=stage)


def uniform_path(
    path: str,
    low: float,
    high: float,
    stage: str = "params",
    name: "str | None" = None,
) -> Dispersion:
    """`value ~ U(low, high)`."""
    if stage not in ("scenario", "params"):
        raise ValueError(f"uniform_path: stage must be 'scenario' or 'params', got {stage!r}")
    draw = lambda rng: float(rng.uniform(low, high))  # noqa: E731
    apply = _apply_scenario_path(path) if stage == "scenario" else _apply_params_path(path)
    return Dispersion(name=name or f"uniform:{path}", apply=apply, draw=draw, stage=stage)


def lognormal_path(
    path: str,
    mean: float,
    sigma: float,
    stage: str = "params",
    name: "str | None" = None,
    clip_min: "float | None" = None,
    clip_max: "float | None" = None,
) -> Dispersion:
    """`value ~ lognormal(mean, sigma)` (`numpy.random.Generator.lognormal`'s
    own convention: `mean`/`sigma` are of the underlying normal in log-space,
    not of the lognormal distribution itself) -- the natural choice for a
    strictly-positive quantity (a mass, a drag-area multiplier) where a
    `normal_path` would risk drawing a negative value in the tail."""
    if stage not in ("scenario", "params"):
        raise ValueError(f"lognormal_path: stage must be 'scenario' or 'params', got {stage!r}")
    draw = _clip(lambda rng: float(rng.lognormal(mean, sigma)), clip_min, clip_max)
    apply = _apply_scenario_path(path) if stage == "scenario" else _apply_params_path(path)
    return Dispersion(name=name or f"lognormal:{path}", apply=apply, draw=draw, stage=stage)


# ----------------------------------------------------------------------
# Convenience wrappers for the common scenario-stage cases (SS35.4.5).
# ----------------------------------------------------------------------


def airframe_mass(mean_kg: float, sigma_kg: float) -> Dispersion:
    """`Rocket.airframe.m ~ N(mean_kg, sigma_kg)`, clipped at a small
    positive floor (a non-positive mass is unphysical and `_weight_from_
    pieces` divides by it)."""
    return normal_path("rocket.airframe.m", mean_kg, sigma_kg, stage="scenario", clip_min=1e-6)


def airframe_cg(mean_m: float, sigma_m: float) -> Dispersion:
    """`Rocket.airframe.l ~ N(mean_m, sigma_m)` (CoG station from the nose,
    clipped at 0 -- a station aft of the nose tip, same convention as every
    other `Sections`/`Airframe` field, SS32.5)."""
    return normal_path("rocket.airframe.l", mean_m, sigma_m, stage="scenario", clip_min=0.0)


def wind_speed_dir(
    speed_mean_ms: float,
    speed_sigma_ms: float,
    dir_mean_deg: float,
    dir_sigma_deg: float,
) -> "tuple[Dispersion, Dispersion]":
    """`(Wind.ref_ms, Wind.dir_deg)`, each independently normal: speed
    clipped at 0 (a negative reference speed is unphysical,
    `sim/wind.py`'s shear law takes its sign from `ref_ms` directly);
    direction unclipped (a meteorological bearing wrapping past 0/360 deg is
    harmless -- `sim/wind.py` only ever consumes it through `sin`/`cos`)."""
    speed = normal_path(
        "wind.ref_ms", speed_mean_ms, speed_sigma_ms, stage="params", clip_min=0.0,
        name="wind_speed_ms",
    )
    direction = normal_path(
        "wind.dir_deg", dir_mean_deg, dir_sigma_deg, stage="params", name="wind_dir_deg",
    )
    return speed, direction


# ----------------------------------------------------------------------
# The ensemble runner.
# ----------------------------------------------------------------------


def _safe_evaluate(evaluate: Callable[[Config], "dict[str, float]"], cfg: Config) -> "tuple[dict, str | None]":
    """Run one sample's `evaluate(cfg)`; any exception is caught and
    reported as `(metric)->NaN, error=str(exc)` rather than aborting the
    whole ensemble (SS35.4.5's own acceptance test) -- a single pathological
    sample (e.g. an aero table whose alpha range the dispersion pushed the
    flight out of) must not cost every other sample its result. Top-level
    (not a closure) so `functools.partial(_safe_evaluate, evaluate)` is
    picklable for `ProcessPoolExecutor`'s Windows `spawn` start method."""
    try:
        metrics = evaluate(cfg)
    except Exception as e:  # noqa: BLE001 -- deliberately broad, see docstring
        return {}, f"{type(e).__name__}: {e}"
    return dict(metrics), None


def run_ensemble(
    base: Scenario,
    dispersions: Sequence[Dispersion],
    n: int,
    seed: int,
    evaluate: Callable[[Config], "dict[str, float]"],
    workers: "int | None" = None,
) -> EnsembleResult:
    """`n` samples of `base` perturbed by `dispersions`, each reduced to a
    metrics dict by `evaluate`. `seed` plus `n` fixes every sample's draws
    (`numpy.random.SeedSequence(seed).spawn(n)`, one child per sample,
    independent of `workers` -- see the module docstring).

    `evaluate` must be a top-level (module-level), picklable callable --
    `workers != 1` runs it inside a `ProcessPoolExecutor`, which on Windows
    always `spawn`s (no fork), and `spawn` can only hand a worker a function
    it can re-import by name, never a closure or a lambda. `workers=1` is
    the one exception: it runs every sample in this process, so no
    pickling/spawning happens at all (useful for a quick/debugging run, and
    for the reproducibility test this function's own ticket requires:
    `workers=1` must equal `workers=4`).

    Raises `ValueError` up front for a duplicate `Dispersion.name`, a name
    colliding with the reserved `"sample"`/`"error"` columns, or (once every
    sample has been evaluated) a name shared between a dispersion and an
    `evaluate()` metric -- any of the three would silently overwrite a
    column in the result table (scenario_sweep.py's QA-6 duplicate-name
    guard is the precedent this follows).
    """
    disp_names = tuple(d.name for d in dispersions)
    dup = sorted({name for name in disp_names if disp_names.count(name) > 1})
    if dup:
        raise ValueError(f"run_ensemble: duplicate dispersion name(s) {dup}")
    reserved_hit = sorted(set(disp_names) & _RESERVED_COLUMNS)
    if reserved_hit:
        raise ValueError(f"run_ensemble: dispersion name(s) {reserved_hit} collide with reserved column(s)")

    # (1) Sample + apply in THIS process -- draws[i] depends only on
    #     (seed, n, i), never on `workers` (the ticket's own reproducibility
    #     test). Dispersion.apply/draw may be closures; they never leave
    #     this process.
    seed_seqs = np.random.SeedSequence(seed).spawn(n)
    draws = np.empty((n, len(dispersions)), dtype=float)
    configs_list: "list[Config]" = []
    for i in range(n):
        rng = np.random.default_rng(seed_seqs[i])
        sc = base
        for j, d in enumerate(dispersions):
            value = float(d.draw(rng))
            draws[i, j] = value
            sc = d.apply(sc, value)
        configs_list.append(assemble(sc))

    # (2) Evaluate -- the only part that may run in worker processes, and
    #     the only part (Config, evaluate) that must be picklable.
    if workers == 1:
        raw = [_safe_evaluate(evaluate, cfg) for cfg in configs_list]
    else:
        fn = functools.partial(_safe_evaluate, evaluate)
        with ProcessPoolExecutor(max_workers=workers) as ex:
            raw = list(ex.map(fn, configs_list))

    metrics_list = [m for m, _ in raw]
    errors = [e for _, e in raw]
    metric_names = tuple(sorted({k for m in metrics_list for k in m}))
    overlap = sorted(set(disp_names) & set(metric_names))
    if overlap:
        raise ValueError(f"run_ensemble: dispersion name(s) {overlap} collide with evaluate() metric name(s)")

    # (3) The structured table (SS35.4.5).
    dtype = (
        [("sample", "i8")]
        + [(name, "f8") for name in disp_names]
        + [(name, "f8") for name in metric_names]
        + [("error", "U500")]
    )
    table = np.zeros(n, dtype=dtype)
    table["sample"] = np.arange(n)
    for j, name in enumerate(disp_names):
        table[name] = draws[:, j]
    nan = float("nan")
    for name in metric_names:
        table[name] = [m.get(name, nan) for m in metrics_list]
    table["error"] = [e or "" for e in errors]

    percentiles: "dict[str, dict[float, float]]" = {}
    for name in metric_names:
        col = table[name]
        finite = col[~np.isnan(col)]
        percentiles[name] = {
            pct: float(np.percentile(finite, pct)) if finite.size else nan for pct in _DEFAULT_PERCENTILES
        }

    return EnsembleResult(
        table=table, dispersion_names=disp_names, metric_names=metric_names, percentiles=percentiles
    )


def save_csv(result: EnsembleResult, path) -> None:
    """Structured table -> CSV, one row per sample -- same "structured
    output table + CSV export" convention as
    `apps/motor_selection/scenario_sweep.py`'s `SweepRow`/`save_csv`.
    Plain stdlib `csv`, not `np.savetxt`: the table mixes float columns with
    the string `error` column, which `np.savetxt` cannot format in one call.
    """
    fieldnames = result.table.dtype.names
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fieldnames)
        for row in result.table:
            w.writerow(list(row))
