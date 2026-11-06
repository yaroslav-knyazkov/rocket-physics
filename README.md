# rocket-physics

A Python-based 2D rocket-trajectory simulator with a physics model derived from first principles and documented in a compiled LaTeX report. Includes tools for motor selection, aerodynamic optimization, and trade-space exploration—no server, no UI, pure Python.

**Core features:**
- **Deterministic 2D flight dynamics**: gravity, realistic motor thrust curves, aerodynamic drag, wind and atmospheric effects, integration via adaptive step-size methods
- **Physics derived and verified**: all equations documented in [`dev/docs/latex/main.pdf`](dev/docs/latex/main.pdf) (41 pages); code is validated against the report, not the other way around
- **Tools for mission planning**: compare motors against a target apogee, size airbrakes, sweep parametric studies, analyze weight–aerodynamic trade-offs
- **Extensible 6DOF groundwork**: quaternion rotation, angular dynamics, and damping for future 3D modes already in the codebase
- **For practitioners**: run your own vehicle (specific motor, airframe, launch site, weather conditions) and get trajectory plots and CSV export in minutes

Built for rocketry engineers and enthusiasts who want to reason about rocket behavior through simulation, not spreadsheets or online calculators.

## Quick Links

- **[Complete physics derivation and model documentation](dev/docs/latex/main.pdf)** (LaTeX report, 41 pages)
- **[Build your own rocket](#build-your-own-rocket)** — no templates, no registry, just copy and edit
- **[Installation](#installation)** — Python 3.12 + pip
- **[Examples](#quick-start)** — minimal end-to-end scenario and utility commands

## Stack

- **Python 3.12**
- **Dependencies**: numpy, scipy, matplotlib (see `requirements.txt`)
- **Testing**: pytest
- **Documentation**: LaTeX (`dev/docs/latex/`)
- **No UI, no server**: command-line tools and importable modules

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

## Quick Start

There are no pre-built entry scripts in the repository. `apps/` is a library and toolkit that you either:
1. Run as a module: `python -m apps.<type>.<name>.<module>`
2. Import into your own Python script

### Minimal example: simulate one flight

Run the demo scenario (Cesaroni K570 motor, 54 mm airframe) with a short script (same pattern as `tests/test_worked_scenario_example.py`):

```python
from apps.input.demo_scenario import DEMO_SCENARIO
from apps.sim.schema import assemble
from apps.sim.engine.integrate import run_sim
from apps.sim.engine import report

cfg = assemble(DEMO_SCENARIO)
result = run_sim(cfg.params, cfg.s0)
report.print_run_summary(result, cfg.params, cfg.s0)
```

This prints a summary of the flight (apogee, motor burn time, landing location, etc.) to the console.

### Utility commands

Other `apps/` modules are run the same way—individually, without wrapper scripts:

- **`python -m apps.optimization.motor_selection.compare_motors`**  
  Compare a set of motors from `apps/optimization/motor_selection/motors.py`. Outputs PNG and CSV to `output/`.

- **`python -m apps.optimization.motor_selection.scenario_sweep --motors a,b,c [--target M]`**  
  Sweep the demo scenario across a comma-separated list of RASP motor names, optionally targeting a specific apogee. Outputs plots.

- **`python -m apps.optimization.airbrake_sizing.solve_cda [--spec NAME]`**  
  Compute the optimal airbrake area (drag coefficient × area) for a named spec from `apps/optimization/airbrake_sizing/targets.py`, given a target apogee.

- **`python -m apps.analysis.cfd_conditions.select_conditions`**  
  Extract key points from the demo scenario trajectory (velocity, altitude, Mach number) for CFD setup.

- **`python -m apps.analysis.weight_aero_tradeoff.trade_surface`** /  **`...compare_configs`**  
  Visualize mass–drag trade-offs with isoapogee contours, or compare multiple named scenario configurations side by side.

All utilities write PNG and CSV outputs to `output/` in your current working directory (created on first run, ignored by git).

## Build Your Own Rocket

There is no configuration registry and no special file naming. The only reference is a single template:

1. Copy `apps/input/demo_scenario.py`.
2. Rename `DEMO_SCENARIO` to something meaningful for your vehicle.
3. Edit the values. **Every field is annotated inline** with:
   ```python
   # REQ|OPT, <unit or options> -- <explanation>
   ```
   - **`REQ`** = you must supply a real value for your vehicle
   - **`OPT`** = safe to leave as-is (a sensible library default from `apps/sim/schema.py`)

The dataclasses (`Rocket`, `LaunchSite`, `Weather`, `Motor`, `Scenario`) and the assembly function (`assemble()`) are all in `apps/sim/schema.py`. Once you've created your variant, use it exactly as in the quick-start example above.

## Tests

**Targeted run** (fast, during development):

```bash
python -m pytest tests/test_<name>.py -q
```

**Full suite**:

```bash
python -m pytest -q
```

⚠️ The full suite is slow (several minutes on a typical machine). Don't run it as a habit for every small change during local development—this project has no CI to offload it. Run targeted tests while coding; run the full suite before committing.

## Directory Structure

```
apps/                          — core library and tools
  sim/
    engine/                    — physics model, ODE integrator, plots, report generation
    schema.py                  — Rocket, LaunchSite, Weather, Motor, Scenario dataclasses + assemble()
  input/                       — demo scenario, vehicle reference, atmospheric sounding fetcher
  analysis/                    — CFD condition extraction, mass–drag trade-offs, ensemble analysis
  optimization/                — motor selection, airbrake sizing, apogee targeting solvers
  control/                     — flight software and control laws
  _shared/                     — shared utilities (trajectory artifacts, flight statistics)
projects/                      — your workspace
  examples/data/               — bundled fixtures (motors, aerodynamic tables, soundings; read-only)
  data/                        — (git-ignored) your personal data; created empty on first use
tests/                         — pytest test suite
dev/                           — project tracker and team documentation (not needed for users)
```

## Deployment and Network

- **No server, no deployment**. This is a pure local library and script toolkit.
- **Only one network call in the entire codebase**: the manual fetch `apps/input/sounding_fetch/fetch_sounding.py` (University of Wyoming atmospheric soundings). You run it by hand when needed.
- **The physics engine** (`apps/sim/engine/`) is always offline and fully deterministic.

## Learn More

- **Complete physics derivation**: See [`dev/docs/latex/main.pdf`](dev/docs/latex/main.pdf). Every equation is typeset and cross-checked with the code.
- **Development and architecture**: See `CLAUDE.md` and `dev/PROJECT-STATUS.md` (internal team documentation).
- **Contribute**: Reports, forks, and pull requests are welcome. If you find a modeling error or have a feature request, open an issue.

---

Built by a team of agents for practitioners who want to simulate rocket flight with transparency and rigor.
