# Rocket Trajectory Simulation — Project Status

## Summary
Personal-use rocket trajectory simulator, built from scratch in Python (no RocketPy).
Physics spec lives in `main.tex` (source of truth, updated by the user as derivations evolve).
Approach: incremental, step-by-step, one small piece at a time, committed individually.

- Phase 1: 2D planar rigid-body sim (translation + pitch rotation), all force/model parameters
  as constants (no real thrust curve, no wind, no varying atmosphere yet).
- Phase 2: replace constants with real models (thrust curve + mass depletion, atmosphere,
  wind, aerodynamic coefficients as functions).
- Phase 3: extend to 3D (full 6-DOF).

## Scope notes (per user)
- Single user, personal tool — no need for input validation/normalization, multi-user config, etc.
- Everything currently in `main.tex` should be reflected in code; models start as constants.
- Commit after every completed step (small, reviewable increments).

## Current stage
**Phase 2 COMPLETE** (all 19 mandatory steps, see below). **Phase 2.5 (Steps 33-37) COMPLETE**,
inserted after the Phase 2 milestone closeout — still 2D, not Phase 3. Next: Phase 3 (3D, full
6-DOF) — not started, awaiting the user's go-ahead. Steps 33-35:
- Step 33 — doc restructuring: `main.tex` split into `latex/main.tex` +
  `latex/sections/{rocket-2d,models}.tex`; added the `§Current assumptions` section; filled
  previously-empty stubs; AI-authored text marked with `\ai{}`. No code changes. Commit `3aaec51`.
- Step 34 — removed the `linear` gravity model (dominated by `radial`, no advantage; went negative
  above `h=R_e/2`). `gravity_model="linear"` now raises `KeyError`. Commit `6d48576`.
- Step 35 — aero force now resolved in **body axis**, not wind axis (was double-applying the
  relative-wind rotation; the two conventions only agreed at α=0). Also fixed, in the same commit,
  an unbounded-α hang in `sim/aero.py`'s constant-fallback `C_N`/`C_m` (linear `C_N_alpha*alpha`
  → `C_N_alpha*sin(alpha)`, since an unperturbed vertical flight can coast tail-first through
  `V=0` at apogee and land exactly on `atan2`'s branch cut). Commit `6fa46f2`.

Step 36 — variable mass: CoG/moment-of-inertia travel. `m` is now the 7th integrated state
component (`dm/dt = -T_ref(t)/(I_sp·g0)`). `l_B(t)`/`I(t)` (parallel-axis, two-lumped-mass model)
recomputed every RHS call from `m(t)` and new `Params` constants `m_d,l_d,l_p,I_d,I_sp`. Gated by
`p.m_d` (`None` = off, default) — every existing scenario reproduces prior behavior exactly.
116/116 tests passing. Commit `2610cd8`. **Two open modeling questions flagged for review**
(developer made the conservative, spec-literal choice for both rather than guess, per this
project's history with Step 15/25):
1. Should `p.l1`/`p.l2` (CoP-to-CoG / CoP-to-thrust moment arms) also travel with `l_B(t)`?
   `main.tex` only gives formulas for `l_B(t)`/`I(t)`, nothing for the attachment points, and its
   own §Current assumptions still lists `l1,l2` as fixed — left fixed for now.
2. `I_p(t)` (propellant's own moment of inertia) needs a proportionality constant not given by
   Step 36's 4 new constants — implemented as `(I_d/m_d)*m_p(t)` (same specific MOI as the dry
   structure), documented as a placeholder matching `main.tex`'s own "uniform density, fixed
   shape" `\todo`.

Step 37 — non-inertial (Coriolis/centrifugal) correction. `sim/rotation.py` (new):
`omega_components(lat0_deg, azimuth_deg)` — Earth's Ω decomposed in the launch tangent-plane frame
per the architect's derivation (`latex/sections/models.tex`, commit `a98f283`, verified to 4.4e-16
against an independent 3D calculation). Key finding: in-plane Coriolis is driven entirely by Ω's
out-of-plane component, so a due-North/South launch (or the poles) gets exactly zero in-plane
Coriolis even though the true effect is maximal there (just lateral, which a 2D model can't
represent) — documented as an explicit closure, same precedent as the existing crosswind closure
in §Wind. Implemented per user-approved **scope Option B**: in-plane Coriolis added to
`sim/dynamics.py`'s translational derivatives, gated by new `Params.earth_rotation` (bool, default
`False`, bit-for-bit inert) — *plus* the discarded lateral component computed and exposed as a
labeled diagnostic (not fed into the physics), so the blind spot is visible instead of silent. The
residual centrifugal term (Option D) was deliberately **not** implemented, per the user's explicit
choice — documented as a closed decision, not a gap. 123/123 tests passing (7 new). Commit
`9af29c7`.

Verified: `earth_rotation=False` is bit-for-bit inert regardless of `lat0_deg`/`azimuth_deg`;
in-plane Coriolis matches the closed form independently re-derived in the test (~2.81×10⁻² m/s² at
`lat0=50°, azimuth=90°, V=300 m/s`, matching the architect's ~2.8×10⁻² report); the existing
~4.6 km-apogee scenario deflects ~8.4 m downrange at apogee with Coriolis on at that geometry,
matching `models.tex`'s own order-of-magnitude estimate ("order 10 m over a 30 s powered ascent");
the in-plane term is exactly zero at `azimuth=0°/180°` for every latitude tested, with the lateral
diagnostic nonzero there instead — the documented blind spot, and the exact property the
diagnostic exists to demonstrate.

**Process note:** the developer caught and correctly resolved a contradiction in the orchestrator's
own dispatch instructions for this step (the detailed scope description said the lateral
diagnostic must be nonzero at `azimuth=0°/180°`; a later "Checks" bullet, copied loosely from
`roadmap.md`'s older wording, said the opposite). Resolved by re-deriving from `models.tex` itself
— the authoritative source — rather than taking either instruction on faith, and verified
numerically. No harm done, but a reminder to double-check dispatch prompts for internal
consistency, not just against the spec.

## Report finalization pass (2026-09-27, not a numbered roadmap step)

Documentation-only pass over `latex/main.tex` + `sections/{rocket-2d,models}.tex` after Phase 2.5
closed, at the user's request. No code changes; nothing under `sim/` or `tests/` touched. Done by
the architect in two runs (a rate-limit interruption in between; no partial edits were lost — the
tree was clean before the retry).

**Two real bugs found and fixed in `rocket-2d.tex` §Analytical analysis** (both pre-existing user
text, both independently re-derived and cross-checked against the running code before being
touched — same discipline as Steps 15/25/37):
1. **θ sign convention.** The force equations assumed θ measured from the vertical
   (`-mg cosθ`/`mg sinθ`), contradicting §Frames' stated — and code-matching — convention of θ
   measured from the horizontal. Corrected to `-mg sinθ`/`mg cosθ`, verified against
   `sim/frames.py`'s `R_body_to_inertial`. No code change needed; `sim/dynamics.py` already
   implements the correct form.
2. **C/D point-label swap in the moment equation.** Had the thrust point `C` and the aerodynamic
   reference point `D` interchanged between the two terms (`(u_B-u_D)T ... + (l_B-l_C)A_z` instead
   of `(u_B-u_C)T ... + (l_B-l_D)A_z`). Verified against `sim/dynamics.py`'s actual cross-product
   terms numerically. Independent of bug 1 (moments are taken about the CoG, weight doesn't
   appear). The user's own pre-existing todo — "write that `l_C` is irrelevant" — only holds under
   the corrected form, which is corroborating evidence this was a transcription slip. Propagates
   mechanically into the static-stability derivative and the SM formula (`l_B-l_C` → `l_B-l_D`),
   same structure otherwise.

**Structural changes:**
- `models.tex` subsections reordered so every model's inputs precede its use (Atmosphere → Wind →
  Relative wind/AoA → Gravity → Non-inertial corrections → Thrust → Mass/MOI → Aerodynamics),
  fixing 4 forward-references.
- New **§Backlog and future work** (end of `main.tex`): thrust-axis misalignment/control,
  wing-body aero/analytic CoP/airframe/air brake, dimensionless stability margin, dynamic
  stability analysis — each as "what it is / waiting on what" — plus an index pointing at
  deferrals already stated elsewhere (grain geometry, moist air, vertical wind, aero-coefficient
  CFD expansion — all left untouched, verified byte-identical to `HEAD`).
- §Current assumptions rewritten — it was stale after Steps 36/37 (still claimed constant
  mass/CoG/I and zero Earth-rotation term).
- Three follow-up decisions the user chose from a comparison table:
  1. **Symbol collision** (reference area/length written `A,l` in one place, `S,d_ref` in
     another): renamed to `S`/`d_ref` throughout §Analytical analysis to match `models.tex`/the
     simulator. Exposed and fixed two related gaps along the way — `A_m`'s magnitude equation was
     missing from `models.tex` despite the code computing it (added), and the Reynolds number's
     `l_ref` was a redundant second reference length (renamed to `d_ref`).
  2. **Point-label mismatch** (report's A/B/C/D vs. code's `l1`/`l2`): documented the bridge only
     (`l_1 = l_D - l_B`, `SM = -l_1`); no code rename. Left as a future roadmap step if ever wanted.
  3. **Cross-references**: every section/subsection across all three files is now labelled, and
     all ~90 textual "§ Name > Subname" references converted to `\autoref`.

**Not verified:** no LaTeX toolchain is available in this environment, so nothing was compiled —
only checked statically (brace/environment balance, every `\autoref` target defined, zero leftover
textual `\S Capital` references). **Compile locally (two passes) and do a visual read-through
before treating this as final.**

Also surfaced by the architect, not fixed (genuinely out of scope for Step 37): `rocket-2d.tex`
§Analytical analysis's force equations assume θ measured from the vertical, conflicting with
§Frames and the actual code (θ measured from horizontal, nose-up) — a pre-existing inconsistency
in the user's own older text. Flagged for a small dedicated fix step later, not urgent.

**Phase 2.5 milestone: COMPLETE.** All 5 steps (33-37) done and committed individually. Phase 3
(3D, full 6-DOF) has not been started.

## Phase 2.6 doc/derivation pass (2026-09-27) — Steps 38-40 spec'd, code not yet implemented

At the user's request: implement gravity direction varying with downrange distance (Backlog B4),
thrust-axis misalignment, and humid-air density (Backlog B5) — plus two restructuring requests
folded in: reorder `models.tex` to **Gravity → Thrust → Mass → Aerodynamics → Atmosphere → other**
(Wind/Relative wind/Non-inertial), and promote "Analytical analysis" out of `rocket-2d.tex` into
its own `latex/sections/analysis.tex`. Done by the architect, documentation/derivation only — no
code changes yet (that's Steps 38-40, next).

**Restructuring:**
- `models.tex` subsections reordered per the user's explicit force-grouped order (a deliberate
  reversal of the report-finalization pass's dependency-first order) — this reintroduces forward
  references (§Thrust cites §Atmosphere's `p_amb`, §Aerodynamics cites §Atmosphere's ρ and §Other's
  `alpha`, further down in the document). Flagged transparently in the doc rather than silently
  "corrected" back, since `\autoref` resolves regardless of definition order.
- New `latex/sections/analysis.tex`: "Analytical analysis" promoted to its own top-level section
  (kept `\label{sec:analysis}` so every existing cross-reference survives). Fills the long-standing
  `\todo{actual section with thrust and no-thrust stability}` with an organized derivation across
  three configurations — **no thrust**, **aligned thrust**, **misaligned thrust** — plus the static
  stability analysis, in the user's requested order, with a small comparison table at the end of
  §Moment tying the three configurations together (user confirmed keeping this layout over an
  alternative that groups the three moment cases contiguously).

**New physics, derived (not yet coded):**
1. **Step 38 — gravity direction vs. downrange.** The local vertical rotates by `φ = x/R_e` from
   the launch vertical; `weight_inertial`'s direction becomes `(-sinφ, cosφ)` instead of the fixed
   `(0,1)`. Gated by a new `gravity_direction: str = "parallel" | "radial"` field (orthogonal to
   `gravity_model`'s magnitude selection, dispatch-dict pattern matching every other named-model
   field). Direction-only — no change to altitude bookkeeping, stays independent of the existing
   Coriolis correction (their own "independent and comparable, don't multiply" framing already in
   the doc). Verified numerically against the real `sim/dynamics.py`/`sim/frames.py` before being
   written up (e.g. the rotated-weight contribution to `dvx/dt`/`dvz/dt` reproduced exactly, zero
   contribution to `domega/dt`).
2. **Step 39 — thrust-axis misalignment.** A fixed nozzle cant angle `δ`
   (`thrust_misalign_deg: float = 0.0`), giving `T = T·(cosδ x̂_r + sinδ ẑ_r)`. Verified that
   `sim/dynamics.py`'s existing generic cross-product machinery needs **no code change at all** —
   it already produces exactly `(l1+l2)·T·sinδ` once `thrust_body` returns a vector with a nonzero
   `ẑ_r` component (the "future gimbal drops in with no structural change" comment in `dynamics.py`
   was literally true). Scoped to misalignment only, not a commanded/control-law gimbal (that stays
   backlog).
3. **Step 40 — humid-air density**, approved by the user: an optional `Td_K` (dewpoint, kelvin)
   sounding CSV column, gated by `humid_air: bool = False`, applying the standard Magnus/virtual-
   temperature correction (`ρ = p/(R_d·T_v)`) in the sounding/field tiers only — ISA stays dry-air
   by definition. Absent column → all-NaN → dry-air fallback, zero cost to every existing data
   file. Verified against a real sounding row (~0.5-1.25% density reduction, temperate to hot-humid
   conditions) and Magnus-formula reference values.

**Not verified:** no LaTeX toolchain in this environment — not compiled, only structurally checked
(51 labels, 191 cross-references, 0 dangling, 0 duplicates across all 4 files). **Compile locally
before treating this as final**, same caveat as the report-finalization pass.

**Next:** developer implements Steps 38, 39, 40 in that order, one commit each, full regression
suite after each. Steps 38 and 39 both touch `sim/forces.py` and must be done sequentially, not in
parallel, despite being physically independent corrections. Exact function signatures/`Params`
fields/formulas for all three are pinned in `architecture.md` §23.1/§23.2/§23.3 and in the
architect's dispatch — no developer should need to re-derive anything, only implement and test.

## Phase 2.6 milestone: COMPLETE (2026-09-27) — Steps 38, 39, 40 implemented and committed

All three steps done sequentially (38→39 both touch `sim/forces.py`, done one at a time as
planned), each independently verified by the orchestrator (diff review + a from-scratch `pytest`
run) before committing — not taken on the developer's self-report alone.

- **Step 38 — non-parallel gravity** (commit `da77aa6`). `sim/gravity.py` gains
  `z_hat_g(t,y,p)`, dispatching on new `Params.gravity_direction` ("parallel" default = the fixed
  `(0,1)` every prior step used; "radial" = `(-sin(x/R_e), cos(x/R_e))`), orthogonal to the
  existing `gravity_model` magnitude dispatch. `weight_inertial` now multiplies by it instead of
  the hard-coded `(0,1)`. 128/128 tests (5 new): `"parallel"` bit-for-bit regardless of `R_e`/`x`;
  `z_hat_g` stays unit-norm; `"radial"`'s translational shift matches the closed form
  `[-g·sinφ, g·(cosφ-1)]` exactly; `domega/dt` is **exactly** (not approximately) unchanged, since
  weight passes through the CoG and contributes no moment regardless of direction.
- **Step 39 — thrust-axis misalignment** (commit `f3089aa`). `thrust_body` gains
  `Params.thrust_misalign_deg` (default `0.0`), returning `T·(cosδ, sinδ)` instead of the on-axis
  `(T, 0)`. `sim/dynamics.py` needed **zero functional change** — its existing generic
  cross-product moment machinery already produces `(l1+l2)·T·sinδ`, independently re-verified
  numerically before trusting the architect's claim. Fixed manufacturing-grade misalignment only,
  not a commanded/control-law gimbal (that stays backlog). 134/134 tests (6 new): bit-for-bit at
  `δ=0`; moment shift matches the closed form exactly; shift is exactly zero post-burnout; the
  shift is identical at two different angles of attack (confirming a constant `δ` shifts the trim
  point without touching the static-stability slope `∂θ̈/∂α`); a statically stable airframe trims
  toward the sign of `δ` instead of diverging, and reversing `δ`'s sign mirrors it.
- **Step 40 — humid-air density** (commit `069abce`), the sounding-CSV-format extension approved
  by the user beforehand. New optional `Td_K` (dewpoint, kelvin) column, absent = all-NaN = dry
  fallback. `sim/soundings.py` carries `Td` through `Sounding`/`SoundingState`/`ResampledCase` and
  tier-3 IDW/RBF combination — the RBF stacking arithmetic was rewritten explicitly (4→5 blocks)
  specifically to make an off-by-one slicing mistake visible at the diff level, and a dedicated
  test exercises exactly that. `sim/atmosphere.py` gains `sat_vapor_pressure`/
  `virtual_temperature`/`moist_density` (Magnus formula; `R_d/R_v` computed, never hard-coded);
  applied in the sounding/field tiers only when `Params.humid_air` is set and dewpoint is finite —
  ISA stays dry-air by definition, untouched. 150/150 tests (16 new). One correction the developer
  found and flagged rather than silently accepting: the dispatch prompt's reference value
  `sat_vapor_pressure(20°C) = 2333.4 Pa` was a typo against the stated formula — independently
  re-derived to `2333.4406 Pa` (50-digit precision) and pinned to the verified value instead.

**Also landed in the same block, doc/derivation-only** (commit `17da67b`, before the three code
steps): `models.tex` reordered to **Gravity → Thrust → Mass → Aerodynamics → Atmosphere → other**
(a deliberate, user-requested reversal of the report-finalization pass's dependency-first order —
reintroduces some forward-references, flagged transparently rather than "corrected" back); and
"Analytical analysis" promoted out of `rocket-2d.tex` into its own `latex/sections/analysis.tex`
(label `sec:analysis` preserved), filling the long-standing `\todo{actual section with thrust and
no-thrust stability}` with an organized derivation across no-thrust / aligned / misaligned-thrust
configurations.

**Not verified:** still no LaTeX toolchain in this environment — the doc pass was structurally
checked only (51 labels, 191 cross-references, 0 dangling/duplicate). **Compile locally before
treating the report as final**, same standing caveat as every prior doc pass this project has had.

**Test suite: 150/150 passing**, up from 123 at the start of this block (5 + 6 + 16 new, one step
at a time, each independently re-run by the orchestrator before its commit).

## Gravity models complete (all 4 main.tex variants)
Step 10-11 finished all four gravity variants (constant/linear/radial/wgs84). Next steps move to
atmosphere.

## Phase 2 progress
- Step 9 — `sim/flow.py` (Flow: V, alpha, u_hat, n_hat; wind stubbed at zero until Step 21).
  `aero_force_body` now uses actual relative wind instead of fixed body axes. 13/13 tests passing
  (6 new). Ascent leg unchanged (apogee 1650.7038 m / 18.5071 s, exact match to Step 8). Impact
  time changed 35.9856s -> 37.8688s and max speed 188.88 -> 178.30 m/s — this is the intended
  physics fix: previously drag always added to the fall during descent (nose up, moving down);
  now it correctly opposes the actual relative wind and slows the fall, as roadmap Step 9 intended
  ("makes the descent leg physical for the first time"). Commit `79af229`.
- Step 10 — `sim/gravity.py`: constant/linear/radial models via `Params.gravity_model` string +
  dispatch dict (approved pattern). `Params` gains `gravity_model` (default "constant", preserves
  all behavior) and `R_e` (Earth radius, 6.371e6 m). 20/20 tests passing (7 new). Default-model
  regression exact match to Step 9. At current scenario altitude (~1650m) linear/radial differ
  from constant by ~0.39 m; at h=100km they diverge by ~7.5e-4 relative, as physically expected.
  Commit `1f8c641`.
- Step 11 — `sim/gravity.py`: 4th variant "wgs84" (Somigliana normal gravity + second-order
  free-air correction, standard published NIMA TR8350.2 constants). `Params` gains
  `lat0_deg`, `lon0_deg`, `h0_m`, `azimuth_deg` (site block, per architecture.md §18, safe
  defaults, no behavior change for other models). 26/26 tests passing. Spot-checks: equator
  9.7803253 m/s^2, pole 9.8321849 m/s^2 (both match published constants to 7 sig figs — the pole
  value is a derived cross-check, not an input, giving high confidence the formula is correct),
  45° mid-latitude 9.8061978 m/s^2, decreasing with altitude as expected. Commit `f53a0f8`.
- Step 12 — `sim/atmosphere.py`: full 7-layer ISA (troposphere through mesosphere), `AirState`
  (rho, p, T, a, mu). Fixed g_isa=9.80665 kept separate from the user's selected gravity model
  (correct per the standard's own definition). NOT yet wired into flow/forces/dynamics (that's
  Step 13). 36/36 tests passing. Sea-level values match standard reference exactly (rho=1.225,
  p=101325, T=288.15K, a=340.29 m/s, mu=1.789e-5 Pa*s); tropopause and 5000m checks correct.
  Commit `09950ce`.
- Step 13 — `sim/flow.py`, `sim/forces.py`, `sim/params.py`: Flow gains air, q=½ρV², M=V/a,
  Re=ρVl_ref/μ; added aero_model with "constant" and "coefficients" (A_x = qS·C_A0,
  A_z = qS·C_Nα·α, A_m = qS·d_ref·C_mα·α); added S, d_ref, l_ref, C_A0, C_N_alpha, C_m_alpha to
  Params. Verified that aero_model="constant" reproduces Step 12 exactly; with "coefficients"
  drag vanishes at V=0, reverses on descent and falls with altitude. Commit `9b558c1`.
- Step 14 — `sim/thrust_curve.py` (new): time/thrust table via `lru_cache`d loader + `np.interp`,
  zero after the last point. Removed the `T_BURN` constant-thrust hack from `sim/forces.py`
  entirely — `thrust_body` now calls `thrust_curve.thrust(t, s, p)`. Added `motor_curve: str = ""`
  to `Params` (default reproduces the "no thrust" case, matching every other Phase 2 field's
  Phase-1-preserving-default pattern; `run.py`'s scenario now sets `motor_curve="placeholder.csv"`
  explicitly, since the old `T=50.0` field is no longer read by `thrust_body` at all). Added a
  `burnout` event to both integrators in `sim/integrate.py` (`Result.events["burnout"]`), including
  a real scipy `solve_ivp` gotcha found and fixed along the way: an event function that stays
  *exactly* zero over an extended interval (post-burnout, or the whole flight with no curve) gets
  classified as both a rising and falling edge by scipy's `<=`/`>=` event logic, causing spurious
  detections at t=0; fixed with a tiny epsilon shift (`_BURNOUT_EPS = 1e-9` N) on the RK45 path
  only (the hand-written RK4 path does a direct numeric comparison and doesn't need it).
  `data/motors/placeholder.csv` is a small illustrative solid-motor-shaped curve (ignition spike to
  150N, settle to 90N, flat sustain, linear tail-off to 0 by t=2.0s; stated total impulse
  162.75 N·s, verified by `np.trapezoid` in `tests/test_thrust_curve.py`). 47/47 tests passing (4
  new thrust-curve tests + 3 new burnout-event tests in `tests/test_integrate.py`; `T_BURN`'s old
  regression test in `tests/test_dynamics.py` updated to use the new curve, since the field it used
  to set, `T`, is now inert). This step intentionally changes the trajectory versus Step 13 (a real
  motor curve replacing a fake constant-thrust rectangle is the point of the step) — there is no
  bit-for-bit regression claim here, unlike the gravity/atmosphere/aero model-selection steps.
  Commit `0d184bf`.
- Step 16 — `sim/thrust_curve.py`, `sim/params.py`: altitude pressure correction on top of the
  curve lookup, `T(t,h) = T_ref(t) + A_e*(p_ref - p_amb)` with `p_amb` from
  `atmosphere.air_state(t, s, p).p`. `Params` gains `A_e` (default 0.0, nozzle exit area) and
  `p_ref` (default 101325.0 Pa). The correction is guarded to only apply while `T_ref(t) > 0`
  (motor actually flowing) — otherwise `A_e*(p_ref - p_amb)` would manufacture nonzero thrust from
  ambient pressure alone during coast/pre-ignition, breaking the clean zero-after-burnout cutoff
  Step 14's burnout event depends on. `A_e = 0.0` (the default, used by `run.py`'s scenario)
  short-circuits before touching the atmosphere model at all, reproducing Step 14 bit-for-bit
  regardless of `p_ref` or `atmosphere_model` — confirmed via `run.py` (identical printed summary:
  burnout 2.0000s, apogee 4609.2267m/30.1209s, max speed 304.0110 m/s, impact 62.4745s). 50/50
  tests passing (3 new: inert-at-default, sign/magnitude-correct pressure boost mid-burn verified
  against the exact ISA sea-level pressure, still-zero after burnout with `A_e != 0`).
  Commit `0882da3`.
- Step 17 — `sim/soundings.py` (new): shared data layer for atmosphere tiers 2/3 AND wind tiers
  2/3 (no physics wired in yet — pure infrastructure). `Sounding` NamedTuple per architecture.md
  §17 (station/lat/lon/elev/time_utc + h/p/T arrays + u/v ENU wind components derived at load time
  from wdir/wspd via the standard meteorological convention). `load_case(case)` (`lru_cache`d,
  globs `data/soundings/<case>/*.csv`). `interp_altitude(sounding, h) -> SoundingState(p,T,rho,a,mu,u,v)`
  — the tier-2 (single-station) altitude-interpolation seam Steps 18/22 will call: T linear in h,
  p linear in ln(p), u/v linear in h, rho/a/mu derived (reusing `atmosphere.py`'s own physical
  constants, not duplicated). Below the lowest data point: continues with the sounding's own local
  lapse rate from its first two points (isothermal fallback for a degenerate single-row file).
  Above the highest data point: an ISA-*shaped* profile re-anchored at the sounding's own top point
  so T/p stay continuous at the seam (reuses `atmosphere.py`'s layer-crossing algorithm, walking
  forward from the new anchor rather than sea level). Worked example committed at
  `data/soundings/example/LKPR_202605011200.csv` (extends architecture.md §17's own literal LKPR
  example up through the tropopause, hand-crafted, ISA-like-but-not-identical — no live weather
  API, offline only). 62/62 tests passing (12 new): the roadmap's stated check (an ISA-derived
  synthetic sounding round-trips through the loader/interpolator to within 0.5% of
  `atmosphere.air_state` between its nodes), wind ENU conversion at the four cardinal directions,
  continuity at both extrapolation seams, physical sanity (finite, positive, monotone p/rho) well
  above the data range, the local-lapse-rate below-range behavior, the single-row degenerate case,
  and `load_case` caching/missing-case-error behavior. Commit `cc77846`.
- Step 18 — `sim/atmosphere.py`, `sim/params.py`: tier 2, `"sounding"` — `_sounding_air_state`
  loads `p.sounding_case` via `soundings.load_case` (first station only; multi-station combination
  is Step 20), computes `h_msl` the same way tier 1 does, and repackages
  `soundings.interp_altitude`'s `p/T/rho/a/mu` into `AirState` (drops `u`/`v` — wind.py's concern,
  Step 22). `Params` gains `sounding_case: str = ""`. Default `atmosphere_model="isa"` unchanged.
  66/66 tests passing (4 new): the ISA-derived synthetic case matches `"isa"` to ~0.05% between
  nodes (well inside the 0.5% bound); a full trajectory run with that synthetic case matches the
  `"isa"` run's apogee/impact to ~0.01-0.02%; with the real worked example (LKPR, elevation 380m),
  the station's actual numbers are warmer and lower-density than ISA predicts at that altitude
  (measured ~0.71% lower density), and a full trajectory run confirms the physically expected
  consequence — less drag, apogee ~0.47% higher, impact time ~0.98% shorter — checked as a strict
  directional assertion, not just `!=`. Commit `26f1f8f`.
- Step 19 — `sim/soundings.py`, `sim/params.py`: tier-3 horizontal combination across stations,
  pure infrastructure (not wired into `atmosphere.py`/`wind.py` yet — Steps 20/23). `_resample_case`
  resamples every station of a case onto a common altitude grid at load time (cached on
  `(case, grid_top_m, grid_step_m)`), reusing `interp_altitude` level-by-level rather than
  duplicating its interpolation/extrapolation rules. `project_latlon` does the equirectangular
  tangent-plane projection centred on the launch site. `interp_field_at(case, E, N, h, p)` weights
  the resampled stations at a tangent-plane point (`"idw"` default — `wᵢ ∝ 1/(dᵢ²+ε²)` — or
  `"rbf"` via `scipy.interpolate.RBFInterpolator`), combines with a dot product, then feeds the
  combined profile back through `interp_altitude` for the final altitude lookup.
  `interp_field(case, y, h, p)` is the convenience wrapper from the rocket's own state vector
  (ground position `(x·sin A, x·cos A)`) — this is the exact seam Steps 20/23 call. `Params` gains
  `horizontal_interp` (default `"idw"`), `grid_top_m` (30000.0), `grid_step_m` (100.0),
  `idw_epsilon_m` (500.0). 72/72 tests passing (6 new): one station reproduces tier 2 exactly;
  querying at one station's own coordinates among several is dominated by (but, correctly per the
  IDW+epsilon math, not identical to) that station, checked against an exact analytic bound, not a
  loose tolerance; two identical-profile stations combine to that same profile everywhere,
  including far outside both; the rocket-ground-position wrapper agrees with the explicit-point
  seam; an `"rbf"` smoke test inside a 3-station triangle; and projected-vs-haversine distance
  <0.1% — with an explicitly documented, verified caveat that this bound holds for cardinal-direction
  offsets at any distance up to 100 km and moderate diagonals (~35 km), but a diagonal pushed all
  the way to 100 km can exceed 0.1% (an expected property of the equirectangular/plate-carree
  approximation architecture.md §17 itself specifies, not a bug — flagged rather than silently
  narrowed). Commit `9d6e791`.
- Step 20 — `sim/atmosphere.py`: tier 3, `"field"` — `_field_air_state` delegates to
  `soundings.interp_field(p.sounding_case, y, h_msl, p)` (Step 19's horizontal-combination
  machinery) and repackages the result into `AirState`, same as tier 2 minus wind. First
  atmosphere model whose output depends on `y[X]`, not just `y[Z]`. No new `Params` fields (all of
  `sounding_case`/`horizontal_interp`/`grid_top_m`/`grid_step_m`/`idw_epsilon_m` already existed
  from Steps 18/19). New multi-station example: `data/soundings/field_example/` — FLDA (lat 48.0,
  lon 16.0, T0=293.15K/p0=102000Pa, warm/high-pressure) and FLDB (lat 48.0, lon 16.5, ~37km due
  east, T0=288.15K/p0=99000Pa, cooler/low-pressure), both sharing the standard troposphere lapse
  rate, kept purely cardinal (east-west only) per Step 19's own note about diagonal placements
  degrading the tangent-plane projection's accuracy. 74/74 tests passing (2 new): a single-station
  case reproduces the `"sounding"` tier exactly through the full `air_state` seam; with the
  two-station case, density along a ground-track sweep from FLDA to FLDB decreases monotonically —
  the correct direction given FLDA is actually denser than FLDB at every shared altitude (pressure
  offset dominates despite FLDA also being warmer), confirmed from the stations' real numbers, not
  asserted blindly. Commit `f818573`.
- Step 21 — `sim/wind.py` (new), `sim/flow.py`, `sim/params.py`: tier 1, `"analytic"` —
  `wind_inertial` dispatches on `p.wind_model` (`"none"` default, zeros; `"analytic"` power-law
  shear `W(h) = wind_ref_ms*(max(h,h_ref)/h_ref)^shear_exp`, AGL not MSL, clamped below `h_ref`).
  Meteorological `wdir - azimuth` projection onto the flight plane per architecture.md §16;
  cross-plane component computed and discarded via `wind_horizontal_enu` (exposed for Phase 3 to
  reuse unchanged). Optional deterministic gusts: a frozen sum of 8 sinusoids with phases/weights
  drawn once from `np.random.default_rng(gust_seed)`, cached per seed; `gust_sigma=0.0` skips the
  RNG entirely. `flow._wind_inertial` now delegates here instead of the inline zeros stub. `Params`
  gains `wind_model`, `wind_ref_ms`, `wind_dir_deg`, `wind_ref_h_m`, `wind_shear_exp`, `gust_sigma`,
  `gust_seed`. 81/81 tests passing (7 new): `"none"` reproduces the pre-Step-21 stub bit-for-bit
  (verified by monkeypatching the old stub back in and diffing a full trajectory, not a pinned
  baseline); a pure headwind raises `V` by exactly the wind speed; the four cardinal directions
  give the derived-not-guessed sign (headwind/tailwind/crosswind/crosswind); headwind and tailwind
  of equal speed bracket the still-air apogee in the correct order (needed an inclined launch —
  purely vertical flight makes headwind/tailwind indistinguishable, since `|v_rel|` depends on
  `w_x²` when the rocket's own downrange velocity is negligible); gust determinism (bit-for-bit
  identical across repeated calls) and `gust_sigma=0.0` exactness. Flagged in passing (not a Step
  21 bug): the `C_N_alpha`/`C_m_alpha`/`l1` combination shared by earlier test modules is
  pitch-unstable the moment `alpha != 0` is ever engaged — invisible before this step since every
  prior one kept `theta` pinned with zero wind; worth remembering for Step 25. Commit `7e15296`.
- Step 22 — `sim/wind.py`: tier 2, `"sounding"` — `_sounding_wind` loads `p.sounding_case` via
  `soundings.load_case` (first station only, same convention as the atmosphere tiers) and
  `soundings.interp_altitude` for `(u, v)` ENU wind at `h_msl = -y[Z] + p.h0_m` (MSL, not AGL —
  a measured station profile is tied to real altitude, unlike tier 1's ground-referenced shear).
  Projects ENU `(u, v)` onto the flight plane via `w_along = u·sin(A) + v·cos(A)`,
  `w_cross = u·cos(A) - v·sin(A)` — derived from first principles and verified algebraically
  consistent with tier 1's `w_x = -W·cos(wdir-azimuth)`/`w_y = -W·sin(wdir-azimuth)` by
  substituting tier 1's own ENU conversion and reducing via the cos/sin angle-difference
  identities. No new file format, loader, or `Params` field — reuses Step 17/18's machinery
  entirely. 86/86 tests passing (6 new, `tests/test_wind.py` now 12): a synthetic constant-wind
  sounding matches the analytic model at `shear_exp=0` (including strictly-between-node
  interpolation); a synthetic pure-veering profile (wdir sweeping 0→45→90°) shifts the downrange
  component exactly as `-W·cos(wdir)` predicts; the real `example` (LKPR) case's wind genuinely
  veers 210°→265° from 380m to 10000m, confirmed against hand-computed expected values at each
  data row; MSL (not AGL) altitude convention confirmed via `h0_m`. Commit `1c10109`.
- Step 23 — `sim/wind.py`: tier 3, `"field"` — `_field_wind` delegates to
  `soundings.interp_field(p.sounding_case, y, h_msl, p)` (Step 19's horizontal-combination
  machinery, same call `atmosphere._field_air_state` makes at Step 20) and reuses tier 2's exact
  ENU→flight-plane projection unchanged. 6 executable lines, as the roadmap itself predicted
  ("reusing the Step 19 weighting machinery unchanged... a handful of lines"). No new `Params`
  fields. This closes out all three wind tiers (analytic/sounding/field), mirroring the atmosphere
  tiers exactly. 88/88 tests passing (2 new): a single-station case reproduces the `"sounding"`
  tier exactly through the full `wind_inertial` seam; a new synthetic two-station case with
  genuinely opposing wind directions (0°/180°, cardinal N-S placement) shows the along-plane wind
  component increasing strictly monotonically across an 11-point ground-track sweep, negative near
  one station and positive near the other, crossing zero exactly once. Commit `b1fb9fb`.

## Step 24 — skipped for now (optional, deferred as non-trivial)
Step 24 (time interpolation between sounding snapshots) is marked optional in the roadmap. Skipped
rather than attempted this pass: it needs a "group multiple time-snapshots per physical station"
concept that doesn't exist yet in `sim/soundings.py` — right now every CSV file in a case is
treated as an independent *spatial* station, so feeding it two snapshots of the *same* station
would currently be silently double-counted by the tier-3 IDW average as two different stations at
the same location. That's a real design decision, not "a handful of lines" — deferred until there's
an actual multi-snapshot dataset to design against.

## Sign-convention correction (pre-Step-25, 2026-09-20/21)
The architect flagged (`architecture.md` §19/§22 item 5) that `main.tex`'s original geometry
(`Aa = -l1·x̂_r`) makes a linear normal aero force **divergent**, not restoring, for any positive
`l1` — static stability needs the CoP aft of the CoG. Per the user: `l1`/`l2` are meant to stay
**positive** throughout (both measured from the nose tip), so the fix is not "make `l1` negative"
but a corrected geometry: `main.tex`'s `Geometry` subsection now has `Aa = +l1·x̂_r`
(`aA = -l1·x̂_r`, `aB = -(l1+l2)·x̂_r`) — commit `ac2cff2`. The corresponding code fix landed as its
own dedicated commit before Step 25:
- `sim/dynamics.py`: `aA`/`aB` now built as `(-p.l1, 0)` / `(-(p.l1+p.l2), 0)`, matching the
  corrected `main.tex`.
- `tests/test_forces.py`: the Step 6 regression test's closed form re-derived and flipped to
  `M_y = -l1·A_z - A_m` (from `+l1·A_z - A_m`), independently re-derived via `_cross_y`, not just
  asserted.
- Scanned every test using the flagged unstable fixture (`l1=0.3, C_N_alpha=2.0, C_m_alpha=-0.5`,
  first noticed by Step 21's developer) — none needed changes: each either never calls
  `dynamics.derivatives`/`run_sim` directly, keeps `theta` pinned with zero/symmetric wind so
  `alpha` stays 0 throughout, or is a differential comparison (old-stub-vs-new, isa-vs-sounding,
  RK4-vs-RK45) where the sign cancels out on both sides.
- New test demonstrates the actual physical fix directly (not just algebra): an off-axis launch
  (`alpha0 = -0.15 rad`) with `aero_model="coefficients"`, `C_N_alpha=2.0`, `l1=0.3` stays
  **bounded** (`|alpha|` never exceeds its initial magnitude by more than ~1%, oscillatory) under
  the corrected sign, versus reaching `alpha(1.0s) ≈ -2.19 rad` (~14.6× the initial magnitude, past
  ±π/2) with the old sign reconstructed for contrast. Honest caveat, confirmed not assumed: this
  model has no pitch-rate damping yet (arrives with Step 25's real coefficients), so a bounded
  undamped oscillator — not literal decay to zero — is the correct, verified characterization of
  "restoring" here.
- `run.py` provably unaffected (its scenario has `A_z=0, A_m=0`, `aero_model="constant"`) —
  confirmed byte-for-byte identical stdout before/after.
- 89/89 tests passing (1 new). Commit `c2e7537`.

## Phase 2 progress (continued)
- Step 25 — `sim/aero.py` (new): `C_A(α,M)`, `C_N(α,M)`, `C_m(α,M)`, `cop_l1(α,M)` — table-driven
  via `p.aero_table` (own design, since architecture.md §19 leaves the exact column format
  unspecified: `alpha_deg,M,C_A,C_N,C_m,l1_m` rows, rectangular `(M,α)` grid, `np.interp` in α
  within each bracketing M row then linearly blended across the M bracket, clamped — not
  extrapolated — outside the M range), with the existing `Params` constants (`C_A0`, `C_N_alpha`,
  `C_m_alpha`, `l1`) as the exact fallback when `p.aero_table==""` (default). New
  `data/aero/example.csv`: synthetic, illustrative fin-rocket-shaped table (transonic drag hump,
  peak normal-force slope near M=1, restoring `C_m`, CoP moving aft with Mach), every row keeping
  `l1_m > 0` (stable per the just-corrected sign convention). `sim/forces.py`'s `"coefficients"`
  regime now calls `aero.C_A`/`C_N`/`C_m` instead of inline formulas (bit-for-bit unchanged when no
  table). `sim/dynamics.py`'s `derivatives()` now computes `l1_aero = aero.cop_l1(flow.alpha,
  flow.M, p)` for `aA` (the CoP position) only — `aB` (the thrust exit point, a fixed mechanical
  point on the body) deliberately stays on the constant `p.l1`, since coupling it to the moving CoP
  would invent an unspecified thrust-misalignment effect outside this step's scope. This needed one
  extra `flow_state` call in `dynamics.py` beyond a pure constant-to-function swap — flagged as a
  small, deliberate exception to the roadmap's general "dynamics.py doesn't change in Phase 2"
  note, not a structural change. 96/96 tests passing (7 new): table lookup verified against an
  independent hand computation of the same bilinear formula; exact-grid-point lookup with zero
  interpolation error; edge-clamping (no extrapolation); malformed non-rectangular table rejected
  with `ValueError`; no-table path reproduces every pre-Step-25 formula bit-for-bit including
  through the full `dynamics.derivatives()` seam; a decisive check that `dynamics.py` actually uses
  the table's `l1` and not a deliberately-absurd stale `p.l1=999.0`; and a full-trajectory
  weathercocking check extending the sign-fix commit's off-axis scenario through the real
  table-driven path. Same honesty finding as the sign-fix commit, re-verified with the real table
  (not assumed): `alpha(t)` stays bounded and oscillatory (`[-0.150, -0.0998, 0.0548, 0.0433,
  -0.0930, -0.0636]` rad over `t=0..5s`), not decaying to zero — this model still has no
  pitch-rate-damping term anywhere, so genuine decay isn't physically achievable at this step
  regardless of the table's nonlinearity. Commit `c4fe830`.
- Step 26 — `tools/fetch_sounding.py` (new, approved by the user — the only part of the project
  that touches the network): a hand-run CLI, never imported by `sim/`, fetching from the
  University of Wyoming radiosonde archive's current live endpoint
  (`https://weather.arcc.uwyo.edu/wsgi/sounding` — the older `weather.uwyo.edu` host has moved;
  discovered by fetching it directly since a research subagent's session lacked Firecrawl this
  time). `robots.txt` there disallows `/wsgi`, the actual data endpoint — used anyway with the
  user's explicit, informed approval (a hand-run, occasional, single-request tool, not the
  bulk/automated crawling robots.txt is aimed at), documented transparently in the script's
  docstring and in every file's `# source:` line. Splits network I/O (`fetch_raw`) from pure logic
  (`parse_response`/`resample_rows`/`format_canonical`) so the parsing path is unit-testable
  offline. Resamples the archive's ~1-second-resolution response (thousands of rows) down to a
  configurable altitude step (default 250 m, nearest-sample) before writing the canonical CSV
  format. Handles the archive's "no data" case (confirmed live: HTTP 404 with a plain-text body,
  not the 200 originally assumed) as a clear `SoundingFetchError`. 109/109 tests passing (13 new,
  all offline against a captured response fixture — no live network call in the automated suite).
  Live end-to-end verification (station 72672, 2024-01-15 12:00Z): 5040 raw rows → 122 resampled,
  written to `data/soundings/example_live/72672_202401151200.csv` (kept, committed, as a genuine
  real-data worked example alongside the earlier hand-crafted ones), loads with zero edits via
  `sim.soundings.load_case`, physically sane values throughout (elevation 1699m closely matches
  station 72672/KRIW's real ~1697m elevation — a good independent sanity check the unit
  conversions and metadata convention are correct). Commit `00a576a`.
- Step 27 — `run.py`, `sim/plotting.py`: the payoff for the whole model-selection pattern
  (architecture.md §12). `run.py` gains `sweep(base_params, field, values, s0)` — the exact
  `dataclasses.replace(p, <field>=<value>)` idiom §12 itself specifies, one `run_sim` per variant
  — plus a plain-text summary table (apogee altitude/time, max dynamic pressure "max-Q" sampled via
  `flow_state` on the same dense grid the single-run summary already uses, impact time) and
  `sim/plotting.py` gains `plot_trajectory_overlay` (flight-path + altitude-vs-time panels, one
  line per variant, same dense-output convention as the existing plot functions). Two sweeps run by
  default: the four gravity models (at this scenario's own ~4.6 km apogee) and `"isa"` vs the real
  LKPR sounding (`data/soundings/example`, `aero_model="coefficients"` so the atmosphere is
  actually load-bearing). The original single-run scenario and its printed summary are completely
  unaffected (confirmed byte-identical). 114/114 tests passing (5 new): sweep produces one `Result`
  per variant with sane summaries; gravity apogee ordering is physically predictable
  (`constant < linear ≈ radial < wgs84` at this scale, `wgs84` highest partly because the default
  `lat0_deg=0.0` equator start has `γ₀(0)=9.7803 < g=9.80665`); atmosphere sweep confirms the real
  sounding gives higher apogee and lower max-Q than ISA (less dense air, less drag — consistent
  with Step 18's own finding); a direct check that gravity-model divergence is small (`<1%`) at
  ~4.6 km but clearly visible (`~8×` larger) at 100 km, exactly the roadmap's stated check; overlay
  plot returns a valid figure. Actual printed sweep tables:
  ```
  Gravity model comparison (gravity_model sweep):
  gravity_model    apogee_alt[m]   apogee_t[s]     max_q[Pa]   impact_t[s]
  ------------------------------------------------------------------------
  constant             4609.2267       30.1209    54853.4687       62.4745
  linear               4612.2749       30.1465    54852.6283       62.5327
  radial               4612.2651       30.1465    54852.6241       62.5326
  wgs84                4624.2535       30.2202    54864.7281       62.6972

  Atmosphere model comparison (station LKPR) (atmosphere_model sweep):
  atmosphere_model   apogee_alt[m]   apogee_t[s]     max_q[Pa]   impact_t[s]
  --------------------------------------------------------------------------
  isa                   682.3775        9.5833    23066.9337       25.9148
  sounding              685.1434        9.6047    23002.8091       25.9532
  ```
  Commit `9291b32`.

## Phase 2 milestone: COMPLETE
Every model family in `main.tex` §Models is implemented and selectable via a `Params` string field:
4 gravity variants, 3 atmosphere tiers, 3 wind tiers, a real thrust curve with pressure correction,
and Mach/α-dependent aero coefficients with CoP travel — plus the shared real-data infrastructure
(sounding format/loader/altitude-interpolation/horizontal-interpolation) backing the tier-2/3
variants of both atmosphere and wind, an offline fetch helper for real sounding data, and a
comparison-sweep tool that makes the point of having multiple models actually visible. 19 mandatory
steps, all committed individually as the working rules require. 2 steps (15, 24) remain optional
and deferred, not blocking. Phase 3 (3D, 6-DOF) has not been started.

## Phase 2 milestone reached
Steps 9-23 and 25-26 all complete (Step 15 optional/blocked, Step 24 optional/deferred). Every
model family in `main.tex` §Models is now implemented and selectable: gravity (4 variants),
atmosphere (3 tiers), wind (3 tiers), thrust curve + pressure correction, and Mach/α-dependent aero
coefficients with CoP travel. Only Step 27 (the comparison-sweep payoff step) remains to close out
Phase 2.

## Step 15 — skipped for now (optional, still blocked)
Step 15 (propellant depletion / variable mass) is marked optional in the roadmap's dependency
graph and remains blocked: `main.tex` §Current assumptions still states "CoG doesn't change",
which directly contradicts a time-varying `I(t)`/`l1(t)`/`l2(t)`. Re-checked 2026-09-20 before
starting Step 16 — still unchanged. Proceeding straight to Step 16 (pressure correction), which
does not depend on Step 15. Revisit Step 15 if/when the user updates `main.tex` with the CoG/
inertia-shift derivation.

## Phase 2 scope (expanded per user request 2026-09-19)
- Gravity: constant, linear, radial (inverse-square), WGS84 real-data — selectable via
  `Params.gravity_model` string.
- Atmosphere: ISA / real single-station sounding / real multi-station spatially-interpolated —
  goal is rho, Reynolds number, Mach number.
- Wind: same three-tier structure (analytic / single-station / multi-station interpolated),
  sharing data infrastructure (`sim/soundings.py`) with atmosphere.
- Launch rail and recovery moved to a Backlog section (deferred, not deleted).
- `main.tex` updated (commit `9895505`) with relative-wind/AoA derivation and Gravity/Atmosphere/
  Wind model specs. `architecture.md`/`roadmap.md` revised for Phase 2 (commit `84b70f2`):
  Steps 9-27 + Backlog (B1-B6).

## Phase 2 decisions log (2026-09-19)
- Model selection: `Params` string field + dispatch dict per family (not pure §4 single-body
  seam, not strategy objects) — keeps one public function per family, makes model comparison
  trivial, self-documents in printed/CSV output.
- Real-data format: one unified sounding CSV per station/time (T, p, wind together), folder =
  "case" under `data/soundings/`. Shared loader/interpolator for atmosphere AND wind tiers 2-3.
- No pandas — `numpy.genfromtxt` + a small header parser. `requirements.txt` unchanged.
- No live weather API — manual CSV drop into `data/soundings/` for now. An optional offline
  fetch script (`tools/fetch_sounding.py`, stdlib urllib, no dependency) may be added later as
  its own approved step; `sim/` never touches the network.

## Known issue flagged by architect (not blocking yet)
Sign convention check needed before Step 25 (aero coefficients): per `main.tex`'s geometry
(`Aa = -l1*x_hat_r`), a normal aero force produces a **divergent** moment when `l1 > 0` — static
stability requires `l1 < 0` (CoP aft of CoG). The old roadmap had this backwards. Revisit before
Step 25.

## Milestone
All of `main.tex` (as of Step 6) is implemented in code: translation + rotation, all
forces/moments, everything as constants. Confirmed by 7 passing tests (frames, forces, and an
independent RK4-vs-RK45 cross-check) plus multiple regression checks across steps. Full 2D
trajectory + pitch plots and flight summary in place (Step 7). Two independent integrators
(scipy RK45 and a hand-written RK4) agree on the same physics (Step 8), proving `dynamics.py`
itself — not just the solver — is correct.

## Completed steps
- Step 1 — scaffolding: `Params`/`State` containers, `run.py` prints them. Commit `4c3f836`.
- Step 2 — vertical point-mass flight under constant thrust + gravity (theta frozen at pi/2,
  no aero). Sign convention validated: apogee altitude/time match the analytic closed form
  (`a = T/m - g`) to ~1e-7 relative error. Introduced a temporary `T_BURN = 2.0s` constant in
  `sim/dynamics.py` (Step-2-only device, to be replaced by the real thrust curve in Step 11).
  Commit `2024207`.
- Step 3 — altitude and vertical-velocity plots vs. time (`sim/plotting.py`), sampled from the
  dense `solve_ivp` interpolant. `run.py` saves `output.png` (gitignored) and calls `plt.show()`.
  Trajectory shape confirmed numerically (monotonic climb, peak at apogee, monotonic descent to
  impact). Added `.gitignore` (pycache, generated PNGs). Commit `3c5f261`.
- Step 4 — `sim/forces.py` (weight_inertial, thrust_body, aero_force_body, aero_moment_y, per
  architecture.md's model-swap seam); `dynamics.py` refactored to build forces from it (rotation
  matrix at theta=pi/2 written inline, not yet in frames.py — that's Step 5). Constant axial drag
  `A_x` now lowers apogee (1650.70 m vs Step 3's 1839.43 m); regression-checked A_x=0 reproduces
  Step 3 exactly. Commit `68eb716`.
- Step 5 — `sim/frames.py` (R_body_to_inertial, to_inertial, to_body — the only trig in the
  codebase); `dynamics.py` refactored to use it instead of inline cos/sin. First tests added
  (`tests/test_frames.py`, 4 passing: identity at theta=0, nose-to-up at theta=pi/2, orthogonality,
  round-trip). `theta` still fixed (not yet integrated). Step 4 regression reproduced exactly;
  tilted trajectory (theta0=60°) demonstrated non-zero downrange motion (throwaway check, not
  committed to run.py). Commit `f794ec8`.
- Step 6 — rotational dynamics: `theta`/`omega` are now real integrated states, moment
  `M_y = cross_y(aB,T) + cross_y(aA,A_f) + A_m` about the CoG (cross products written explicitly,
  not pre-simplified, so a future gimbal/misalignment drops in cleanly). 2 new tests
  (`tests/test_forces.py`: thrust moment is exactly zero on-axis; moment matches closed form
  `l1*A_z - A_m` to 1e-12). Regression: theta stays exactly constant when A_z=A_m=0 (current
  placeholder), apogee/impact unchanged from Step 5. Demonstrated correct-direction pitch-over
  (positive A_m -> nose down) via throwaway check. Commit `d5226ac`.
- Step 7 — `plot_trajectory` (downrange vs altitude, equal aspect) and extended
  `plot_time_histories` (2x2: altitude, speed, pitch deg, pitch-rate deg/s) added to
  `sim/plotting.py`. `run.py` prints a full flight summary (apogee altitude/time, max speed,
  impact time, downrange at impact) and saves `trajectory.png`, `time_histories.png`,
  `trajectory.csv` (all gitignored). With current placeholder (vertical launch, A_z=0):
  downrange at impact = 0 m, as expected. Commit `81615c6`.
- Step 8 — hand-written fixed-step RK4 integrator (`method="rk4"` in `run_sim`), independent of
  `scipy.integrate.solve_ivp`. Cross-check test confirms RK4 and RK45 agree on apogee
  altitude/time and impact time to well within grid-resolution tolerance (apogee time diff
  ~2e-4 s, impact time diff ~4e-4 s, apogee altitude diff ~0.036 m at dt=1e-4s) — proves
  `dynamics.py` itself is correct, independent of which integrator drives it. RK45 remains the
  default; `run.py`'s output is byte-for-byte unchanged. Commit `53a3894`.

## Phase 1 — closed out
8/8 steps done. Everything currently in `main.tex` is implemented, tested, plotted. Next: Phase 2
(Steps 9-17), replacing constants with real models one at a time.

## Active modules
architect (done for now), developer (implementation, one roadmap step at a time). Everything
else (product, qa, security, documentation) — on hold, not needed for this scope unless it grows.

## Links
- `main.tex` — physics derivation (source of truth, user-maintained, re-check before every step)
- `architecture.md` — project structure + tech stack (approved)
- `roadmap.md` — step-by-step build plan, 22 steps across 3 phases (approved) — **this is the
  ticket list**, no separate task.md

## Decisions log
- 2026-09-19 — Architecture approved as recommended: z-down (NED-like) inertial frame,
  `scipy.integrate.solve_ivp` as integrator, fixed-signature `f(t, state, params)` seam for
  Phase 2 model swaps, quaternions for Phase 3 attitude, minimal pytest physics-sanity tests.
- 2026-09-19 — Physics confirmed by user: `ẑ_g` points down (`W = m·g·ẑ_g` correct as-is);
  positive `A_m` pitches the nose down (restoring/stabilizing moment).
- 2026-09-19 — CoG kept fixed for now (matches current `main.tex`); user will update `main.tex`
  with the CoG/inertia-shift derivation before Phase 2 Step 12 (propellant depletion).

## Known future main.tex updates needed (not blocking now)
- Aero force direction (`A_f`) is currently hard-coded against body axes — valid only nose-first;
  Step 9 (relative wind / angle of attack) needs a `main.tex` update to generalize this.
- CoG/inertia shift from propellant depletion — needed before Step 12.
- Thrust model (`§Models > Thrust`) is still a stub — needed before Steps 11/13.
