"""Root wrapper 4 of 5 (roadmap.md Step 69, D-29): the CFD condition
selector app, `apps/analysis/cfd_conditions/select_conditions.py`'s
`main()` -- a front door so `python run_cfd_conditions.py` works the same
way `python run.py` does, without replacing the app's own
`python -m apps.analysis.cfd_conditions.select_conditions` invocation
(architecture-30-apps-4-5-and-configs.md SS30.3)."""

from apps.analysis.cfd_conditions.select_conditions import main

if __name__ == "__main__":
    main()
