# Research: Dryden turbulence model (gusts/turbulence power spectrum)

Date: 2026-10-01. Requested by the user: "add wind gusts and turbulence power models." Scope
decided by the user (AskUserQuestion): **Dryden spectrum, altitude-dependent scale length and
intensity** (not a single constant-sigma knob).

## 1. Why this is a real gap, not greenfield

`docs/architecture.md` §16 already specified (written at Step 21): gust amplitudes should come
"from a von Karman/Dryden-like spectrum." The actual Step-21 implementation in `sim/wind.py`'s
`_gust_realization` never did this -- it draws `_GUST_N=8` log-spaced frequencies (periods 3s to
600s) with **half-normal random weights** normalized to unit sum-of-squares, and adds the result
as a single scalar perturbation to the wind *speed* `W(h)` before direction decomposition. No real
PSD shape, no altitude dependence, no separate along/cross components. This research replaces that
placeholder with the real MIL-F-8785C/MIL-HDBK-1797 Dryden model.

## 2. Primary sources actually read (not reconstructed from training data)

1. **Madden, M.M., "Verifying Implementation of the Dryden Turbulence Model and MIL-F-8785 Gust
   Gradient," NASA Langley Research Center** (https://ntrs.nasa.gov/api/citations/20190000875).
   Fetched and read as rendered PDF pages. Equations (1)-(3) give the Dryden PSD in both spatial
   (`Omega`) and temporal (`omega`) form, directly transcribed below.
2. **Cole, K. & Wickenheiser, A., "Spatio-Temporal Wind Modeling for UAV Simulations"**
   (arXiv:1905.09954, dissertation chapter). Fetched and read as rendered PDF pages. Table 3.1
   (p.11) gives the low-altitude **Von Karman** scale-length/intensity formulas with an
   unambiguous fraction bar -- used here to cross-check the Dryden scale-length/intensity formulas,
   which both documents state are shared between the two models (only the PSD shape functions
   differ). This caught a real transcription risk: an initial WebFetch summarization of the
   MathWorks Dryden documentation page misread the scale-length formula as a **product**
   (`Lu = h*(0.177+0.000823h)^1.2`) rather than a **quotient**; both primary sources read here
   confirm it is a quotient. Flagging this explicitly per this project's established practice of
   verifying subagent/tool-summarized formulas against a source actually read, not trusted at face
   value (see the B9 `c_mq` research note for the precedent).

## 3. The verified formulas

All altitude values are AGL (`h`), in **feet** in the original spec; `W20` is the mean wind speed
at 20 ft (6 m) AGL. Low-altitude regime: `h < 1000 ft`.

### 3.1 Scale lengths (ft)

```
L_w = h
L_u = L_v = h / (0.177 + 0.000823*h)^1.2
```

### 3.2 Intensities (ft/s)

```
sigma_w = 0.1 * W20
sigma_u = sigma_v = sigma_w / (0.177 + 0.000823*h)^0.4
```

### 3.3 Dryden PSD, temporal form (rad/s), `V` = vehicle true airspeed

```
Phi_u(omega) = sigma_u^2 * (2*L_u)/(pi*V) * 1 / (1 + (L_u*omega/V)^2)

Phi_v(omega) = sigma_v^2 * (L_v/(pi*V)) * (1 + 3*(L_v*omega/V)^2) / (1 + (L_v*omega/V)^2)^2

Phi_w(omega) = sigma_w^2 * (L_w/(pi*V)) * (1 + 3*(L_w*omega/V)^2) / (1 + (L_w*omega/V)^2)^2
```

(Madden eqs. 1-3; the vertical form is structurally identical to the lateral form with `L_w`,
`sigma_w` in place of `L_v`, `sigma_v`.)

### 3.4 Medium/high altitude (`h >= 2000 ft`)

Isotropic: `L_u = L_v = L_w = 1750 ft` (533.4 m), `sigma_u = sigma_v = sigma_w`, read off a
probability-of-exceedance chart (light/moderate/severe) in the original spec -- there is no closed
formula here, it's a lookup table keyed on altitude and exceedance probability. **Not pinned
numerically by this research pass** -- left as a `Params`-settable intensity rather than a
hardcoded chart value (see open question 4.2).

### 3.5 Transition, `1000 ft <= h < 2000 ft`

Both sources describe this as a gap in MIL-F-8785C/MIL-HDBK-1797 that implementors fill with
**linear interpolation** between the low-altitude model evaluated at 1000 ft and the
medium/high-altitude model evaluated at 2000 ft. (MIL-F-8785B instead has a continuous closed-form
covering the whole boundary layer with no gap -- `L_u = L_v = L_FA^(2/3) * h^(1/3)` for
`h < L_FA = 1750 ft`, `L_w = h` -- noted here as an alternative worth considering during specing
since it avoids a manually-stitched interpolation, but not the version the user asked to verify.)

## 4. Open questions for the architecture spec (not resolved by this research pass)

### 4.1 Reference airspeed for the Taylor frozen-turbulence conversion

The PSDs above are functions of temporal frequency `omega = V*Omega`, where `V` is the *vehicle's*
airspeed (Taylor's frozen-turbulence hypothesis: the vehicle flies through a spatially frozen
turbulence field at speed `V`, so spatial wavenumbers appear as temporal frequencies scaled by
`V`). Aircraft simulations hold `V` roughly constant per scenario; **this rocket's speed changes by
orders of magnitude over one flight** (0 at the pad to supersonic at burnout). The existing
architecture (`sim/wind.py` docstring, established at Step 21) has a **hard constraint**: the gust
perturbation must be a deterministic pure function of `t` alone, because `solve_ivp` evaluates the
RHS at arbitrary/repeated/rejected times -- a realization that depends on the (still being solved
for) instantaneous vehicle speed would make the RHS a non-function of `t` and break the adaptive
solver's step-size control, exactly the failure mode Step 21 already designed around for the
simpler ad-hoc gust. A true state-coupled Dryden filter (the "gold standard," driving a
speed-varying linear filter with white noise) is therefore not compatible with this project's
existing determinism requirement. The practical options, to put to the user/architect:

  (a) Freeze `V` at one reference value (e.g. a new `Params` field) for the whole realization --
      simplest, keeps the existing frozen-sum-of-sinusoids machinery, but the "airspeed" driving
      the spectral shape is then a fiction for most of the flight.
  (b) Don't convert to temporal frequency via `V` at all -- choose temporal frequencies directly
      (as today's `_gust_realization` already does, log-spaced periods) and evaluate `Phi(omega)`
      treating `omega` as already-temporal, skipping the `V` substitution. This drops the
      spatial-to-temporal conversion's physical meaning but keeps determinism trivially and still
      gets the *shape* (rolloff, relative energy across u/v/w) of the real spectrum.
  (c) Something else the architect proposes.

  This needs an explicit decision and a documented limitation (this project's established pattern
  for the 2D crosswind projection and the deferred B7 vertical wind) -- not a silent pick.

### 4.2 Medium/high-altitude intensity numbers

No formula, only a chart, for `sigma` above 2000 ft by exceedance probability. Needs either: a
`Params` field the user sets directly (`turbulence_severity` or a direct `sigma` value), or
specific light/moderate/severe numbers pulled from a further research pass if the user wants named
presets. Not resolved here.

### 4.3 Vertical (w) component

The user previously deferred B7 (vertical wind) explicitly ("leave it"). The Dryden model's `w`
component is vertical-gust turbulence, which is the same deferred territory. Recommend the
architect scope this step to the horizontal `u`/`v` components only (feeding the existing
`w_along`/`w_cross` decomposition in `wind_horizontal_enu`), explicitly leaving `w_z` at the
`wind_inertial` level untouched (still `0.0`), consistent with the standing B7 deferral -- flag
this rather than silently deciding it.

## 5. Decision (2026-10-01, by the user)

- **4.1 Reference airspeed:** fixed reference speed. Add a new `Params` field (e.g.
  `turbulence_ref_speed_ms`) holding one constant `V` used for the whole frozen realization's
  `omega = V*Omega` conversion. Document as a known fiction for the parts of the flight where true
  airspeed differs from this reference -- same documentation standard as the 2D-crosswind and B7
  vertical-wind limitations already recorded in `architecture.md`.
- **4.2 High-altitude intensity:** user-set `Params` field (e.g. `turbulence_sigma_high_ms`) for
  the isotropic `sigma` above 2000 ft, rather than hardcoding a light/moderate/severe chart. No
  further research pass needed.
- **4.3 Vertical component:** confirmed out of scope, per the standing B7 deferral -- horizontal
  (`u`/`v`) only.

These decisions, plus open question 4.3's recommendation, go into the architecture spec next.
