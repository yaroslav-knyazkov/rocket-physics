"""apps/analysis/weight_aero_tradeoff/trade_surface.py -- App 5 mode (b):
the 2-D weight-vs-aero trade surface and its exchange rate (Step 67,
roadmap.md; dev/docs/architecture-30-apps-4-5-and-configs.md SS30.7.1;
moved here from apps/weight_aero_tradeoff/trade_surface.py at Phase 2.19
Step 131, dev/docs/architecture-apps-sim-restructure.md).

**What this answers.** "If a fairing change costs me N grams and saves me
M cm^2 of C_dA, is it worth it?" -- the trade surface turns that into a
number (the local iso-apogee exchange rate, SS30.2 F10) that is reusable
for *every* component decision on this vehicle without re-running
anything, once the surface itself has been built.

**Axes (D-39): 2-D, C_dA x mass.** The drag axis is `C_dA = aero.S *
aero.C_x`, swept via **`aero.C_x` at fixed `aero.S`**, never via `S`
(F9). The reason is physical, not a style choice: this project's own
solver measures apogee as a function of the product `S*C_x` alone (to
within floating-point/adaptive-step noise -- see
`tests/test_weight_aero_tradeoff.py`'s invariance test), so the 1-D drag
axis *can* legitimately be a single scalar C_dA. But `aero.S` does not
*only* enter through that product: it also multiplies the normal force
(`q*S*C_z`) and the pitching moment (`q*S*d_ref*C_m`) independently of
`C_x`. Sweeping `S` to move `C_dA` would therefore move three physical
quantities at once (axial drag, normal force, pitching moment) for the
sake of varying one (axial drag) -- fine for this repo's attitude-frozen
demo scenario (`C_z = C_m = 0`, so the other two terms are inert anyway),
but silently wrong for any vehicle where they are not. Sweeping `C_x`
instead moves only the axial term, under every aero model that defines a
`C_x` at all. The mass axis is swept via `weight.m`.

**B22 (roadmap.md's existing backlog entry, "Mass changes that also
change inertia and geometry" -- recorded here too, not just there):
`weight.I` is held fixed across the whole mass axis, and so, implicitly,
is every `lengths.*` field (`l1`, the CoP->CoG arm, in particular).**
Added mass is modelled as adding no pitch inertia and moving no geometry.
This is *exact* for the attitude-frozen demo scenario this app ships
against (`C_z = C_m = 0`, so there is no rotational dynamics for `I`/`l1`
to act on in the first place), but becomes an approximation the moment a
vehicle's attitude actually evolves (a nonzero `C_z`/`C_m`, a wind model,
a recovery event before apogee): real added mass almost always moves the
pitch MOI and the CoP-CoG arm too, and this surface would not reflect
that -- a physically complete mass axis needs a component model (*where*
the mass is added), which is a design decision not made yet (B22, same
gap as B15 from App 3's side). Printed alongside the surface
(`print_surface_table`) so a user of a non-attitude-frozen config sees
the caveat, not just the numbers.

**`nan` policy.** A grid point whose flight produced no `apogee` event
(`events["apogee"] is None`, e.g. the flight was cut off by `solver.t_max`
before it crested) is `nan` in `TradeSurface.apogee`. `np.gradient`
propagates a `nan` to every finite-difference stencil that touches it,
and `print_surface_table`/`print_exchange_rates` report *how many* grid
points were lost (`count_unflyable`) rather than silently reporting a
hole in the printed grid.

**Gradients: `np.gradient` on the already-computed grid, no extra
simulator runs.** This is a specific, falsifiable justification, not a
generic "finite differences are fine" wave: SS30.2 F10 *measured* an
11x11 version of this exact surface and found it smooth and strictly
monotone decreasing along both axes over the whole box. A central
difference on a grid that is already known (not merely assumed) to be
smooth in this region is a sound way to get a local slope; it would not
be sound on a surface with discontinuities (e.g. one spanning a
`C_z = 0 <-> C_z != 0` boundary, or an airbrake deployment threshold) --
this module does not claim to generalise past the regime F10 measured.

**Interpolation: bilinear via `scipy.interpolate.RegularGridInterpolator`
(`method="linear"`), exact at grid nodes.** `scipy` is already a project
dependency used elsewhere for gridded interpolation
(`sim/soundings.py`); this is not a new one. Linear interpolation on a
regular grid reduces to an exact point lookup when queried exactly on a
grid node (the interpolation weight on every other corner is exactly
0.0), which is what `tests/test_weight_aero_tradeoff.py`'s node-exact
check exercises directly -- the classic failure mode here is swapping the
two axes (see `TradeSurface.apogee`'s shape convention below), which a
single-point check on the diagonal would not catch; the test checks
several non-diagonal points.

**Artifacts (D-40: not persisted as committed data).** `output/` is
gitignored; the surface is recomputed on demand each run, not cached.
`data/` in this project means measured or synthetic *physical input*, not
a computed result, and at ~5-6 s a cache would be a correctness liability
(a stale surface silently answering for a changed vehicle) bought for
approximately nothing -- the "reusable for every component" requirement
is met by `apogee_at`/`exchange_rate` on the in-memory `TradeSurface`
plus the CSV, not by a committed artifact.

**The contour plot is new, app-local matplotlib code (SS30.2 F13),
deliberately not routed through `sim/plotting.py`.** That module's entire
contract is `Result -> Figure` (`plot_trajectory`, `plot_time_histories`,
`plot_trajectory_overlay` all take one or more `Result`s). A trade
surface is a 2-D grid of apogee values, not a `Result` -- there is no
`Result` to hand it, and forcing one into existence just to reuse a
`savefig` call would be contortion, not reuse. This is a deliberate
non-reuse, not an oversight.
"""

from __future__ import annotations

import csv
import dataclasses
import time
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import RegularGridInterpolator

from apps.input import study_vehicle
from apps._shared.artifacts import ensure_dir, output_dir
from apps._shared.flight_stats import _assert_derivatives_reconstructible, flight_stats
from configs.schema import Config
from sim.integrate import run_sim
from sim.params import replace as params_replace


@dataclasses.dataclass(frozen=True)
class TradeAxes:
    """The two swept axes. `cda_values` are axial `C_dA = aero.S *
    aero.C_x` values [m^2] (see module docstring, F9, for why this is
    swept via `aero.C_x` at fixed `aero.S`); `mass_values` are
    `weight.m` values [kg]. Both must be strictly increasing (required by
    `RegularGridInterpolator` and assumed by `np.gradient`'s spacing
    argument) -- not re-checked here, same "house rule, no validator"
    convention as `sim.params.replace` (architecture.md SS7)."""

    cda_values: tuple[float, ...]
    mass_values: tuple[float, ...]


@dataclasses.dataclass(frozen=True)
class TradeSurface:
    """The computed grid plus the config it was built against.

    `apogee.shape == (len(axes.mass_values), len(axes.cda_values))` --
    rows are mass, columns are C_dA. `nan` at a grid point means that
    flight produced no apogee event (see module docstring's `nan`
    policy)."""

    cfg: Config
    axes: TradeAxes
    apogee: np.ndarray

    def _interp(self, grid: np.ndarray, cda: float, m: float) -> float:
        """Bilinear interpolation of `grid` (same shape/axes as
        `self.apogee`) at the point `(m, cda)` -- note the axis order
        matches `self.apogee`'s own (mass first, C_dA second), the one
        thing a transposed-axis bug would get backwards. `nan` outside
        the grid's bounding box, same as a `nan` grid node propagating
        through the interpolation weights."""
        interpolator = RegularGridInterpolator(
            (self.axes.mass_values, self.axes.cda_values),
            grid,
            method="linear",
            bounds_error=False,
            fill_value=np.nan,
        )
        return float(interpolator([[m, cda]])[0])

    def apogee_at(self, cda: float, m: float) -> float:
        """Bilinear interpolation inside the box; exact at a grid node
        (`cda`, `m`) == one of `self.axes`' own values; `nan` outside the
        box."""
        return self._interp(self.apogee, cda, m)

    def gradients(self) -> "tuple[np.ndarray, np.ndarray]":
        """`(d(apogee)/d(C_dA), d(apogee)/dm)`, both shaped like
        `self.apogee`, via `np.gradient` (central differences) on the
        already-computed grid -- no extra simulator runs (see module
        docstring for why that is sound here)."""
        d_dm, d_dcda = np.gradient(self.apogee, self.axes.mass_values, self.axes.cda_values)
        return d_dcda, d_dm

    def partials_at(self, cda: float, m: float) -> "tuple[float, float]":
        """`(d(apogee)/d(C_dA), d(apogee)/dm)` at `(cda, m)` -- the two
        raw sensitivities `gradients()` computes on the grid, bilinearly
        interpolated to an arbitrary point (exact at a grid node, same
        `RegularGridInterpolator` property `apogee_at` relies on). Public
        (not underscore-prefixed) because `print_exchange_rates` prints
        both raw sensitivities alongside the derived exchange rate, and
        re-deriving them from `exchange_rate`'s one return value would be
        circular."""
        d_dcda_grid, d_dm_grid = self.gradients()
        d_dcda = self._interp(d_dcda_grid, cda, m)
        d_dm = self._interp(d_dm_grid, cda, m)
        return d_dcda, d_dm

    def exchange_rate(self, cda: float, m: float) -> float:
        """The implicit-function-theorem slope of the iso-apogee contour
        through `(cda, m)`:

            along apogee(C_dA, m) = const:
                (dA/dC_dA) dC_dA + (dA/dm) dm = 0
                => dm/dC_dA = -(dA/dC_dA) / (dA/dm)      [kg/m^2]

        Negative under the measured regime (apogee strictly decreasing in
        both C_dA and m, F10): increasing one requires decreasing the
        other to hold apogee fixed."""
        d_dcda, d_dm = self.partials_at(cda, m)
        return -d_dcda / d_dm


def build_surface(cfg: Config, axes: TradeAxes) -> TradeSurface:
    """Run the simulator at every `(mass, C_dA)` grid point and reduce
    each flight to its apogee altitude (`nan` if the flight produced no
    apogee event -- the `nan` policy in the module docstring). `C_dA` is
    realised as `aero.C_x = cda / cfg.params.aero.S` (`aero.S` itself is
    never swept, per F9); every other field of `cfg.params` is held fixed
    at `cfg`'s own value for every grid point, including `weight.I` and
    every `lengths.*` field -- added mass moves no inertia and no
    geometry here (B22, module docstring).

    Raises `ValueError` if `cfg.params.aero.S == 0.0` (no `C_x` can
    realise a nonzero `C_dA` at zero reference area) and propagates
    `apps._shared.flight_stats`'s `sample_rate_hz` guard (F8) once,
    pre-flight, rather than on the first grid point -- the same
    fail-fast reasoning `compare_motors.compare_motors`'s own pre-flight
    pass applies.

    Raises `ValueError` (D-82) if `cfg.params.weight.m_d is not None`: with
    the mass model on the integrator reads mass from `y[M]`, so the swept
    `weight.m` is inert and the mass axis would come out flat (F3).
    """
    if cfg.params.weight.m_d is not None:
        raise ValueError(
            f"config {cfg.name!r}: mass model is on (weight.m_d="
            f"{cfg.params.weight.m_d!r}); the integrator reads mass from "
            "y[M], so the swept weight.m is inert and the mass axis would "
            "be flat (F3). App 5 is a constant-mass study."
        )
    if cfg.params.aero.S == 0.0:
        raise ValueError(
            f"config {cfg.name!r}: aero.S == 0.0 -- the C_dA axis is swept "
            "via aero.C_x = cda / aero.S (F9), which is undefined at "
            "S == 0.0."
        )
    _assert_derivatives_reconstructible(cfg.params)

    n_m = len(axes.mass_values)
    n_c = len(axes.cda_values)
    apogee = np.full((n_m, n_c), np.nan)

    for i, m in enumerate(axes.mass_values):
        for j, cda in enumerate(axes.cda_values):
            c_x = cda / cfg.params.aero.S
            p = params_replace(cfg.params, {"weight.m": m, "aero.C_x": c_x})
            result = run_sim(p, cfg.s0)
            stats = flight_stats(result, p)
            if stats.apogee_altitude is not None:
                apogee[i, j] = stats.apogee_altitude

    return TradeSurface(cfg=cfg, axes=axes, apogee=apogee)


def count_unflyable(apogee: np.ndarray) -> "tuple[int, int]":
    """`(n_nan, n_total)` over the whole grid: how many `(mass, C_dA)`
    combinations never produced an apogee event. A standalone function
    so the counting logic is directly testable on a hand-built array,
    independent of the print formatting that uses it."""
    n_total = int(apogee.size)
    n_nan = int(np.sum(np.isnan(apogee)))
    return n_nan, n_total


def print_surface_table(s: TradeSurface) -> None:
    """Plain fixed-width grid: rows = mass [kg], columns = C_dA [cm^2]
    (design units -- more readable than m^2 at this scale), cell =
    apogee [m] or `nan` if that grid point never produced an apogee
    event. Reports the B22 caveat (weight.I and every lengths.* field
    held fixed on the mass axis) and the `nan` count (not silently
    dropped, module docstring)."""
    n_nan, n_total = count_unflyable(s.apogee)

    header = "".join(f"{cda * 1e4:>10.3f}" for cda in s.axes.cda_values)
    print(
        f"\nWeight-vs-aero trade surface for {s.cfg.name!r} "
        f"(apogee [m]; rows = mass [kg], columns = C_dA [cm^2]):"
    )
    print(f"{'m\\C_dA':>8}{header}")
    print("-" * (8 + 10 * len(s.axes.cda_values)))
    for i, m in enumerate(s.axes.mass_values):
        row = "".join(
            f"{s.apogee[i, j]:>10.1f}" if not np.isnan(s.apogee[i, j]) else f"{'nan':>10}"
            for j in range(len(s.axes.cda_values))
        )
        print(f"{m:>8.3f}{row}")
    print(f"({n_nan} of {n_total} grid points did not fly -- shown as nan)")
    print(
        "(weight.I and every lengths.* field held fixed across the mass "
        "axis -- exact for this attitude-frozen scenario [C_z=C_m=0], an "
        "approximation otherwise; B22)"
    )


def print_exchange_rates(s: TradeSurface) -> None:
    """The exchange rate at **several** grid points (a 3x3 sub-sample of
    the grid: low/mid/high on each axis), not just the baseline -- the
    rate is the local slope of an iso-apogee contour and F10 measured
    this surface as visibly nonlinear, so a single number would
    misrepresent how much it moves across the box. Printed as both raw
    partial-derivative sensitivities and design units (mm^2 of C_dA per
    gram, and its reciprocal g per cm^2); `nan` rates (inherited from a
    `nan` neighbourhood in the apogee grid, via `np.gradient`) are printed
    as `nan`, not dropped, and counted in the trailing summary line."""
    n_m = len(s.axes.mass_values)
    n_c = len(s.axes.cda_values)
    m_idx = sorted({0, n_m // 2, n_m - 1})
    c_idx = sorted({0, n_c // 2, n_c - 1})

    print(
        "\nIso-apogee exchange rate at several grid points (LOCAL -- "
        "position-dependent, not a single global number, SS30.2 F10):"
    )
    header = (
        f"{'m[kg]':>8}{'CdA[cm^2]':>11}{'dA/dCdA[m/m^2]':>16}{'dA/dm[m/kg]':>13}"
        f"{'rate[mm2/g]':>13}{'rate[g/cm2]':>13}"
    )
    print(header)
    print("-" * len(header))

    n_nan = 0
    n_total = 0
    for i in m_idx:
        for j in c_idx:
            m = s.axes.mass_values[i]
            cda = s.axes.cda_values[j]
            n_total += 1

            d_dcda, d_dm = s.partials_at(cda, m)
            rate_kg_per_m2 = -d_dcda / d_dm

            if np.isnan(rate_kg_per_m2):
                n_nan += 1
                print(
                    f"{m:>8.3f}{cda * 1e4:>11.3f}{'nan':>16}{'nan':>13}"
                    f"{'nan':>13}{'nan':>13}"
                )
                continue

            # Design units (module docstring):
            #   mm^2 of C_dA per gram = (1 / rate[kg/m^2]) * 1000
            #     (m^2/kg -> mm^2/g: x1e6 mm^2/m^2, /1000 g/kg == x1000)
            #   g per cm^2            = rate[kg/m^2] * 0.1
            #     (kg/m^2 -> g/cm^2: x1000 g/kg, /1e4 cm^2/m^2 == x0.1)
            mm2_per_g = (1.0 / rate_kg_per_m2) * 1000.0
            g_per_cm2 = rate_kg_per_m2 * 0.1

            print(
                f"{m:>8.3f}{cda * 1e4:>11.3f}{d_dcda:>16.1f}{d_dm:>13.2f}"
                f"{mm2_per_g:>13.3f}{g_per_cm2:>13.3f}"
            )

    print(f"({n_nan} of {n_total} printed rates lost to a nan neighbourhood)")
    print(
        "(negative: to hold apogee fixed, increasing one of {C_dA, mass} "
        "requires decreasing the other)"
    )


def save_surface_csv(s: TradeSurface, path: Path) -> None:
    """Long format -- one row per grid point, columns `m_kg, cda_m2,
    apogee_m` -- joinable/plottable in anything, unlike a wide pivot
    table that bakes in the grid's shape."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["m_kg", "cda_m2", "apogee_m"])
        for i, m in enumerate(s.axes.mass_values):
            for j, cda in enumerate(s.axes.cda_values):
                writer.writerow([m, cda, s.apogee[i, j]])


def save_contour_plot(s: TradeSurface, path: Path) -> None:
    """Filled iso-apogee contours in the (C_dA, m) plane -- C_dA [cm^2] on
    x, mass [kg] on y, the baseline point marked. New, app-local
    matplotlib code (module docstring, F13): `sim/plotting.py`'s contract
    is `Result -> Figure`, and this is a 2-D grid, not a `Result`."""
    cda_grid, m_grid = np.meshgrid(s.axes.cda_values, s.axes.mass_values)
    fig, ax = plt.subplots(figsize=(8, 6))
    cs = ax.contourf(cda_grid * 1e4, m_grid, s.apogee, levels=20)
    fig.colorbar(cs, ax=ax, label="Apogee [m]")

    baseline_cda = s.cfg.params.aero.S * s.cfg.params.aero.C_x
    baseline_m = s.cfg.params.weight.m
    ax.plot(
        baseline_cda * 1e4, baseline_m, marker="*", color="red", markersize=16,
        linestyle="none", label=f"baseline ({s.cfg.name})",
    )

    ax.set_xlabel("C_dA [cm^2]")
    ax.set_ylabel("Mass [kg]")
    ax.set_title(f"Weight-vs-aero trade surface: {s.cfg.name}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main(argv: "Optional[list[str]]" = None) -> None:
    """Self-sufficient entry point: `python -m
    apps.analysis.weight_aero_tradeoff.trade_surface` (the apps keep their
    own invocation, architecture.md SS30.3) or `run_trade.py --mode surface`
    (the default mode, the only one this step builds)."""
    import argparse

    from apps.analysis.weight_aero_tradeoff.scenarios import default_axes

    parser = argparse.ArgumentParser(
        description="App 5 mode (b): the weight-vs-aero trade surface and "
        "its iso-apogee exchange rate"
    )
    parser.add_argument("--out-dir", default=None, help="default: output/")
    args = parser.parse_args(argv)
    cfg = study_vehicle.CONFIG

    axes = default_axes(cfg)
    n_runs = len(axes.mass_values) * len(axes.cda_values)

    t0 = time.perf_counter()
    surface = build_surface(cfg, axes)
    elapsed = time.perf_counter() - t0

    print_surface_table(surface)
    print_exchange_rates(surface)
    print(f"\n({n_runs} runs in {elapsed:.2f} s)")

    out_dir = ensure_dir(Path(args.out_dir) if args.out_dir else output_dir())
    csv_path = out_dir / "trade_surface.csv"
    png_path = out_dir / "trade_surface_contour.png"
    save_surface_csv(surface, csv_path)
    save_contour_plot(surface, png_path)
    print(f"Saved {csv_path}")
    print(f"Saved {png_path}")


if __name__ == "__main__":
    main()
