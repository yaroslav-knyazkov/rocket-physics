"""Root wrapper 3 of 5 (roadmap.md Step 66, D-29): the airbrake C_dA
sizing app, `apps/optimization/airbrake_sizing/solve_cda.py`'s `main()` --
a front door so `python run_airbrake.py` works the same way `python
run.py` does, without replacing the app's own `python -m
apps.optimization.airbrake_sizing.solve_cda`
invocation (architecture-30-apps-4-5-and-configs.md SS30.3)."""

from apps.optimization.airbrake_sizing.solve_cda import main

if __name__ == "__main__":
    main()
