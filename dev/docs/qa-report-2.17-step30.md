# QA Report — Step 30 (Phase 2.17): 3D rotational dynamics

## Кратко (RU)

- **Вердикт: PASS**, с двумя minor-находками, не блокирующими приёмку.
- Знаковая конвенция тензора инерции (`sim/inertia.py::tensor`/`omega_dot`) перепроверена
  самостоятельно (отдельный скрипт, свой оракул на `np.cross`, не повторяющий алгебру разработчика
  и тикета) — сходится точно. Осесимметричная редукция сверена вручную с
  `3d_equations_of_motion.md` §4 и `task-109` §109.1.4 — согласие подтверждено.
  Точечно-массовый оракул-тест (§30.9 #2) пересчитан с нуля — PASS.
- Сохранение момента импульса при нулевом моменте — пересчитано самостоятельно в теле (своя RK4,
  свои ассерты) и подтверждено в инерциальной раме через полный прогон тестов — оба PASS,
  с огромным запасом по точности (~1e-14 против заявленных 1e-9/1e-10).
  **Проверка допуска PD-проверки (`validate`) — разработчик прав**: тикет §30.8.3 буквально
  требует жёсткий `<=0.0` без `tol` для положительной определённости (в отличие от `tol`-допуска
  для неравенства треугольника), и смягчение допуска реально ломает
  `test_validate_rejects_a_singular_tensor` — проверено вручную на обоих тестовых случаях.
- Рефакторинг 2D (`pitch_moment`) численно бит-в-бит (полный прогон: 800/800, 0 расхождений вне
  двух новых тестовых файлов) — НО есть тихая деградация: `thrust_body`/`aero_force_body` теперь
  вычисляются дважды на RHS-вызов вместо одного (следствие сигнатуры `pitch_moment`, заданной самим
  тикетом) — комментарий Step 9 про "halves the model evaluations" теперь частично неточен.
  Minor, не влияет на корректность.
- DoD-пункт 11 тикета (докстринги обязаны цитировать метки LaTeX, не переизлагать физику прозой)
  выполнен не полностью: докстринг `sim/params.py::Inertia` переизлагает знаковую конвенцию и
  матрицу прозой без ссылки на `eq:inertia_matrix`/`sec:3d_inertia`; два reduction-теста в
  `tests/test_inertia.py` также не цитируют `eq:eom_rot_3d_diag`/`eq:eom_rot_3d_axisym`. Minor,
  легко исправимо.
- Полный прогон тестов (мой собственный, фоном, с опросом): 800 passed, 0 failed, 791.68s —
  совпадает с заявлением разработчика.

## Scope

Independent verification of uncommitted Step 30 changes on `feature/sim-paper-alignment`:
real 3D rotational dynamics in `sim/dynamics3d.py`, new `sim/inertia.py`, inertia wiring in
`sim/params.py`/`configs/schema.py`/template, `pitch_moment` extraction in `sim/dynamics.py`,
shared `flow_fb_coeffs_3d` helper in `sim/forces3d.py`.

Ground truth: `dev/docs/task-30-3d-rotational-dynamics.md`, `dev/docs/latex/sections-ai/rocket-3d.tex`.

## 1. File list vs. ticket

`git diff --stat` on uncommitted changes: `configs/rockets/_TEMPLATE_rocket.py`, `configs/schema.py`,
`sim/dynamics.py`, `sim/dynamics3d.py`, `sim/forces3d.py`, `sim/params.py`, `sim/state3d.py`,
`tests/test_dynamics3d.py` (all modified) + new `sim/inertia.py`, `tests/test_inertia.py`. Exactly
matches the ticket's §30.12 file list. No file outside the ticket's scope changed. (Untracked
`docs/` at repo root and this QA report are unrelated to Step 30.)

**Discrepancy found (cosmetic, not a defect):** developer's self-report claims a fix was also made
to `tests/test_template_docs.py`'s "REQ/OPT cell format". `git diff tests/test_template_docs.py`
shows **no changes** to that file — it is untouched. The template's new `Inertia` table rows already
conform to that test's format requirements (exactly 5 cells, `REQ`/`OPT` literal) without any test
change; `python -m pytest -q tests/test_template_docs.py` passes (30/30 incl. other template tests).
Harmless inaccuracy in the self-report, not a code defect.

## 2. Sign-convention cross-check — PASS, independently re-derived

Read `sim/inertia.py::tensor`/`omega_dot` and ticket §30.1.2/§30.1.3/§30.1.4 side by side. Wrote a
standalone script (not reusing `sim.inertia.tensor` or the developer's test file) that:
- builds the same three point masses/positions as `test_tensor_matches_the_mass_integral_for_three_point_masses`,
- computes `I_xx..I_yz` by explicit summation of the §30.1.2 integral definitions,
- assembles the 3x3 matrix with the `-I_xy`/`-I_xz`/`-I_yz` off-diagonal signs by hand,
- compares `I @ omega` against `Σ m·(r × (ω × r))` computed directly via `np.cross`, for 6 omega
  directions (5 from the ticket + 1 extra I added).

Result: exact agreement (`rtol=1e-12, atol=1e-13`) for all 6 directions — see transcript. This
confirms the sign convention independently of the developer's own test and algebra.

Also cross-checked the **axisymmetric reduction** (§30.1.4) by hand against `omega_dot`'s general
form: setting `I_yy=I_zz=I_t`, `I_xx=I_a` and expanding the gyroscopic cross term analytically gives
`I_a·ωx_dot=Mx`, `I_t·ωy_dot−(I_t−I_a)·ωz·ωx=My`, `I_t·ωz_dot+(I_t−I_a)·ωx·ωy=Mz` — matches both
`dev/docs/latex/research/3d_equations_of_motion.md` §4's block (confirmed by grep/read of that file)
and `task-109-roll-reaction-wheel.md` §109.1.4's pitch line, as the ticket claims at §30.1.4/§30.13's
"cross-checks performed" note. `tests/test_inertia.py::test_omega_dot_reduces_to_the_axisymmetric_component_form`
independently re-derives the same three scalar equations inline (not calling `omega_dot` for the
comparison target) and passes.

**Verdict: sign convention is correct, confirmed by an independent oracle, not merely re-trusting the
ticket's or developer's own derivation.**

## 3. Point-mass oracle test — re-derived from scratch, PASS

Ran my own independent Python snippet (see transcript) duplicating the three point masses/positions
but computing H two ways without reusing any of the codebase's inertia logic beyond the raw
`np.cross` identity. All 6 omega directions agree to `1e-12` relative / `1e-13` absolute. This is the
single most load-bearing check in the ticket (§30.9 #2) and it independently reproduces.

## 4. Torque-free conservation — re-verified independently, PASS, well inside tolerance

Re-ran the body-frame conservation check (ticket test #13) myself, calling the actual
`sim.inertia.tensor`/`omega_dot` but with my own RK4 driver and my own asserts (not importing the
test file): asymmetric tensor (`I_xx=0.05, I_yy=0.06, I_zz=0.065`, nonzero products), `omega0=(0.5,
-0.3, 0.8)`, `M=0`, 10 s at `dt=1e-4`. Result: `max_dH ≈ 7.7e-15`, `max_dKE ≈ 1.4e-14` — far inside
the claimed `1e-9` tolerance (in fact close to machine epsilon accumulation, i.e. as good as a
conservative integrator can do).

The inertial-frame check (test #19, `to_dcm(q) @ (I·ω)` constant) and the quaternion-norm-drift check
(test #20) were read in full in `tests/test_dynamics3d.py` and re-run via the targeted suite below
(`tests/test_inertia.py tests/test_dynamics3d.py`, 22 passed) — both PASS at their claimed
tolerances (`1e-9`). Not independently re-implemented from scratch (would duplicate the ticket's own
check almost verbatim), but the logic was read line-by-line and matches §30.10.2's description
exactly (uses `to_dcm`/`q_dot` together, ties `omega_dot` to the quaternion path, strictly stronger
than the body-frame-only test per the ticket's own claim).

## 5. PD-check tolerance scrutiny — code-review's suggestion correctly rejected

Read `sim/inertia.py::validate`, ticket §30.8.3's table, and `test_validate_rejects_a_singular_tensor`
directly.

Ticket §30.8.3 row 2 (not positive definite): check is literally `min(eigvalsh(I)) <= 0` — **no
tolerance term**. Row 3 (triangle inequality): check is `l1 + l2 - l3 < -tol` — **with** a tolerance
term. The implementation (`sim/inertia.py:108` `if l1 <= 0.0:` vs. `:117` `if triangle_slack < -tol:`)
matches the ticket's table exactly, asymmetric tolerance and all.

`test_validate_rejects_a_singular_tensor` exercises exactly the boundary this matters for: an
all-zero tensor and `diag(0.0, 1.0, 1.0)`, both with a zero eigenvalue. If `l1 <= 0.0` were loosened
to `l1 <= -tol` (i.e. code-review's suggested change, treating it symmetrically with the triangle
check), both inputs — having `l1 == 0.0` exactly, not `< 0` — would **pass** the PD check (0.0 is not
`<= -tol` for any positive `tol`), and the test would fail (no `ValueError` raised). I confirmed this
by hand: `tol = 1e-12*trace(I)` is strictly positive for both cases (trace = 2.0 and 1.0 respectively),
so `-tol < 0`, and `0.0 <= -tol` is False.

**Verdict: the developer's rationale is correct and matches the ticket's own primary source exactly,
not just a plausible-sounding excuse.** The asymmetry (hard `<=0.0` for PD, `tol`-forgiving for the
triangle inequality) is intentional per §30.8.3's own table and per the docstring's own explanation
(an exactly-singular tensor is itself numerically unusable by `omega_dot`'s `np.linalg.solve`, so
treating it as inadmissible is correct, not merely convenient to pass a test). Applying code-review's
suggestion would indeed have broken `test_validate_rejects_a_singular_tensor`, exactly as claimed.

## 6. The 2D path — `pitch_moment` extraction

Read `sim/dynamics.py`'s full diff (both the new `pitch_moment` function and the call site inside
`derivatives`). The extracted body is a **literal, line-for-line move** — same operand order
(`aA`, `aB`, `thrust`, `aero_force`, `M_thrust + M_aero + M_moment`), same intermediate names, no
reassociation. Traced the single 2D call site: `derivatives` now calls
`M_y = pitch_moment(t, y, p, flow, hold, fb, coeffs)` with exactly the locals already in scope, per
the ticket's own prescribed signature (§30.4.2 note 2). Full-suite run (below) confirms zero pin
movement, which is the ticket's own standard of proof (§30.11.1).

**However — a real, if minor, side effect the "pure move" framing glosses over.** Before this
step, `thrust = thrust_body(...)` and `aero_force = aero_force_body(...)` were computed **once** in
`derivatives` (lines ~323/332) and reused for both the translational force sum and the moment
assembly — this is exactly what the pre-existing "Step 9" comment at `sim/dynamics.py:305-309`
documents ("computing them once and reusing them for both the force sum and the moment halves the
model evaluations per RHS call"). `pitch_moment` does **not** receive `thrust`/`aero_force` as
parameters (per the ticket's own prescribed signature, §30.4.2 note 2, which only threads
`flow, hold, fb, coeffs`) — it recomputes both internally (`sim/dynamics.py:217-218`). So on every 2D
RHS evaluation, `thrust_body` and `aero_force_body` are now each called **twice** instead of once.
Both are pure, deterministic functions (confirmed by reading their docstrings/`sim/forces.py`), so
the **numeric result is unaffected and no pin moves** — but it is a quiet performance regression that
reintroduces exactly the class of duplicate evaluation the Step-9 comment was written to describe as
eliminated, and that comment is now mildly stale (true for `flow`/`fb`/`coeffs`, no longer true for
`thrust`/`aero_force`). This traces back to the ticket's own §30.4.2 prescribed signature, not a
developer deviation — flagging for the architect/developer to decide whether `pitch_moment` should
instead accept precomputed `thrust`/`aero_force` (mirroring `forces3d.py`'s own
`flow_fb_coeffs_3d` optional-param pattern used elsewhere in this same step) to close the gap.
**Severity: minor** (no correctness impact, cheap functions, not visible in any current benchmark/pin).

## 7. `flow_fb_coeffs_3d` backward compatibility

Read `sim/forces3d.py` in full. `aero_force_body_3d`/`moment_body_3d` both default
`flow=None, fb=None, coeffs=None`; when `None` (every pre-existing call site, including every
existing test), each recomputes via its own `_s2d(s)` + the same pure calls as before — bit-for-bit
identical to pre-Step-30 behaviour. `sim/dynamics3d.py`'s `model == "none"` branch calls
`aero_force_body_3d(t, y, p)` with no overrides (unchanged path); only the new `model == "tensor"`
branch computes `flow_fb_coeffs_3d` once and threads it into both calls. Confirmed no silent
behaviour change for any existing caller.

## 8. `configs/schema.py` / 2D inertness

`Rocket.inertia: Inertia = dataclasses.field(default_factory=Inertia)` → every existing/2D-only
config gets `model="none"` by default. `assemble` calls `inertia_mod.validate(p.inertia, roll=p.roll)`
unconditionally, but `validate` returns immediately (no-op) when `ine.model == "none"` (confirmed by
reading `sim/inertia.py:83-84`) — so this is inert for every config that exists today. Confirmed via
the full-suite run (zero failures outside the two new test files).

## 9. Admissibility constant — independently re-derived

Re-derived `|I_yy - I_zz| <= I_xx` by hand from the two triangle inequalities containing `I_xx`
(`I_xx + I_yy - I_zz >= 0` and `I_xx + I_zz - I_yy >= 0`, each itself `2*INT x^2 dm >= 0` and
`2*INT x^2 dm >= 0`... — rechecked the three cyclic identities `I_xx+I_yy-I_zz = 2*INT z^2 dm`,
`I_yy+I_zz-I_xx = 2*INT x^2 dm`, `I_zz+I_xx-I_yy = 2*INT y^2 dm` directly from the §30.1.2 integral
definitions): adding/subtracting the two `I_xx`-containing inequalities gives exactly
`|I_yy - I_zz| <= I_xx`. Matches the ticket's §30.1.5 derivation exactly — this is standard rigid-body
mechanics (the principal-moments triangle inequality), not something invented for this ticket, and
it re-derives cleanly from first principles independent of the ticket's own text.

## 10. Full suite

`python -m pytest -q`, `run_in_background`, polled in capped loops. Result: **800 passed, 0 failed,
56 warnings, 791.68s (0:13:11)**. Exact pass count matches the developer's claim (780 baseline + 20
new = 800). Runtime longer than this project's usual ~220-390s baseline (likely this machine's
current load), but exit code 0 and zero failures — no numeric pin moved anywhere, confirming
§30.9/§30.11/DoD item 9's requirement.

## 11. Docstrings citing LaTeX labels vs. re-deriving physics in prose — PARTIAL gap found

Ticket DoD item 11 (§30.16): "every new docstring names the equation labels of §30.14.3 ... A
docstring that re-derives the physics in prose instead of citing a label is a review finding."
Checked every row of §30.14.3's citation table against the actual code:

| Code | Ticket says cite | Actual |
|---|---|---|
| `sim/inertia.py::tensor` | `eq:inertia_integrals`, `eq:inertia_matrix`, `sec:conventions` | present (module + function docstring) |
| `sim/inertia.py::validate` | `eq:inertia_pd`, `eq:inertia_triangle`, `eq:inertia_ellipsoid`, `eq:inertia_transverse_bound` | present |
| `sim/inertia.py::omega_dot` | `eq:eom_rot_3d`, `eq:eom_rot_3d_expanded`, (`eq:eom_rot_3d_axisym` for the reduction test) | present |
| `sim/params.py::Inertia` | `eq:inertia_matrix`, `sec:3d_inertia` | **MISSING** — docstring cites only `task-30 SS30.1.2` (the ticket, not the paper) and **re-derives the sign convention and the 3x3 matrix layout in prose** instead |
| `sim/forces3d.py::moment_body_3d` | `eq:moment_3d` (and `eq:eom_rot` for the planar projection) | `eq:moment_3d` present; `eq:eom_rot` secondary citation absent |
| `sim/dynamics3d.py` | `eq:state_vector_3d`, `eq:quat_kinematics_components`, `eq:eom_rot_3d_expanded` | present |
| `tests/test_inertia.py` reduction tests | `eq:eom_rot_3d_diag`, `eq:eom_rot_3d_axisym` | **MISSING** — both reduction-test docstrings cite ticket section numbers (`SS30.1.4`/`SS30.1.6`) only, not the LaTeX labels |

**Finding (minor, DoD non-conformance): `sim/params.py::Inertia`'s docstring is the clearest hit of
DoD item 11's own definition of a violation** — it literally re-states the integral definitions and
the 3x3 off-diagonal-minus-signs matrix in prose (the same content as `rocket-3d.tex`'s
`eq:inertia_integrals`/`eq:inertia_matrix`) without citing either label or `sec:3d_inertia` anywhere.
Secondary, smaller gaps: `tests/test_inertia.py`'s two reduction tests and `moment_body_3d`'s
secondary `eq:eom_rot` note. None of these affect correctness or test outcomes — purely a
documentation/traceability gap against an explicitly named DoD item.

## Overall verdict: PASS

All 11 verification items in scope were independently checked (not re-trusted from the developer's
self-report or the ticket's own prose) and hold. Two minor, non-blocking findings:

- **Minor-1 (performance/doc staleness):** `pitch_moment`'s ticket-prescribed signature causes
  `thrust_body`/`aero_force_body` to be evaluated twice per 2D RHS call instead of once (§6 above).
  No numeric/pin impact. Traces to the ticket's own §30.4.2 signature, not a developer deviation.
- **Minor-2 (DoD item 11 non-conformance):** `sim/params.py::Inertia`'s docstring re-derives the
  sign convention/matrix in prose instead of citing `eq:inertia_matrix`/`sec:3d_inertia`; two
  `tests/test_inertia.py` reduction-test docstrings and `moment_body_3d`'s secondary `eq:eom_rot`
  note likewise omit a labeled citation the ticket's own §30.14.3 table calls for (§11 above).

No blocker or major defects found. Sign convention (the single highest-risk item) is confirmed
correct by an independent oracle calculation; the PD-check tolerance decision the developer made
against code-review's suggestion is confirmed correct against the ticket's own primary source.



