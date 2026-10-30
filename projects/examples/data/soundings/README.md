# projects/examples/data/soundings/

Radiosonde cases, selected through `soundings.case` (one directory per case,
one CSV per station). This is the bundled fixture corpus (Phase 2.19, Step
129) -- your own personal sounding data goes in the gitignored root
`projects/data/` instead, see `projects/data/README.md`. Three categories,
one directory each:

| directory | category | who reads it |
|---|---|---|
| `example/` (`LKPR_202605011200.csv`) | Single-station example (LKPR); the tier-2 sounding case. | `tests/test_atmosphere.py`, `tests/test_soundings.py`, `tests/test_integrate.py`, `tests/test_plotting.py`, `run.py`; also used as the base case in the field tests. |
| `field_example/` (`FLDA_...csv`, `FLDB_...csv`) | Multi-station synthetic field: two stations ~37 km apart, which exercises tier-3 horizontal interpolation (IDW/RBF). `example/` cannot. | `tests/test_atmosphere.py` (case `"field_example"`); `tests/test_wind.py` refers to it only in comments. |
| `example_live/` (`72672_202401151200.csv`) | Real fetched artifact, NOT an example: station 72672, 2024-01-15 12 Z, genuine output of `apps/input/sounding_fetch/fetch_sounding.py`. Kept as the only real-world sounding in the tree. | No test loads it by name; `apps/input/sounding_fetch/fetch_sounding.py` documents it as its sample output (`--case example_live`), and `tests/test_fetch_sounding.py` checks the same format with a temporary file. |
