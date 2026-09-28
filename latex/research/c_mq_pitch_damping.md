# Research: pitch-damping (`C_mq`) methods more defensible than the Step 44 test fixture

**Scope note on tooling (read first).** This session's toolset for this research pass did not
include Context7, Firecrawl, or Exa — only local filesystem access and read-only Notion. None of
the sources below could be live-fetched or full-text-searched; nothing here is a verified quote
against a primary text opened this session. What follows is reconstructed from trained knowledge
of these specific, well-known publications (all of them widely cited in the amateur/experimental
rocketry and missile-aerodynamics literature), with confidence flagged per claim. Formula
**structure** (what a method depends on, in general terms) is reported with higher confidence than
exact numeric coefficients or equation numbers, which should be treated as indicative and checked
against the primary source before being encoded in a test. Where I give a URL it is a commonly-cited
location for the document, not one I retrieved this session — verify before citing further.

## 0. What the simulator has today (for grounding)

From `sim/params.py` and `sim/dynamics.py` (read directly this session):

- One monolithic normal-force-slope, `C_N_alpha` (`Params.C_N_alpha`, or `aero.C_N` from an
  `aero_table`) — not decomposed by nose/body/fin.
- `l1` = CoP-to-CoG distance (`aA = -l1_aero * x_hat_r`, with `aero.cop_l1` allowing table-driven
  CoP travel), `l2` = CoP-to-thrust-point distance, `d_ref` = reference diameter, `S` = reference
  area. Step 43 adds lateral offsets `u_B`, `u_C` (CoG/thrust off-axis), not relevant to `C_mq`
  itself.
- No fin geometry (span, root/tip chord, sweep) and no per-component (nose/frustum/fin) normal-force
  distribution `c_N'(x)` anywhere in the codebase.
- `architecture.md` §24.4's test fixture, `c_mq = 2·C_Nα·(l1/d_ref)²`, is explicitly a "single
  lifting surface" strip estimate — all of `C_Nα` concentrated at one point, `l1` aft of the CoG —
  and is documented as a sanity check, not a value to ship (`roadmap.md` B9).

## 1. Nielsen, *Missile Aerodynamics*

**Citation.** Nielsen, Jack N. *Missile Aerodynamics*. McGraw-Hill, 1960 (reprinted by Nielsen
Engineering & Research / AIAA, ISBN 0-9668508-0-5, ~1988 reprint). Standard reference, university
libraries and some AIAA reprint sellers; I did not verify a free URL this session — likely paywalled
or library-only for the full text.

**What it covers (general knowledge, structure-level confidence).** Nielsen treats dynamic
stability derivatives (`C_mq`, `C_mα̇`, usually combined as `C_mq + C_mα̇` under the standard
"missile in planar pitching motion" quasi-steady assumption, the same short-period lumping this
project's `analysis.tex` already uses via `α̇ ≈ θ̇`) in two separate regimes:

- **Body of revolution alone**, via slender-body potential-flow theory (in the tradition of Munk's
  1924 airship work and Bryson's 1953 extension — see §4 below, which Nielsen's text draws on and
  cites). This body-alone contribution depends on the **body's volume/radius distribution and CG
  location relative to the body's length**, not on a fin breakdown — but it is *not* reducible to
  this project's single scalar `C_N_alpha`, because in pure potential flow a body of revolution's
  own static `C_Nα` is small/near-zero (slender-body theory gives zero net normal force for a
  constant-radius cylinder) while its damping contribution is not. So Nielsen's body-alone term is
  a genuinely separate input (an integral of the radius-squared profile `r(x)²`, i.e. essentially
  the body's volume and its distribution), which the simulator does not currently have (`d_ref` is
  a single constant diameter, not a profile `r(x)`).
- **Finned vehicle damping**, via the same strip/local-angle-of-attack logic OpenRocket later
  operationalized in open-source form (§3): each lifting surface's local normal force is evaluated
  at its own local velocity, including the rotation-induced component `ω·x`, and the moment is
  integrated. This branch does need a per-component (in practice, per-fin) normal-force-curve slope
  and moment arm — the fin breakdown this project has explicitly deferred.

**Bottom line for this project.** Nielsen's body-alone slender-body result is the closest thing to
a "no fin geometry needed" formula, but it needs a radius/volume distribution the simulator doesn't
model (only a single `d_ref`), so it is *not* a drop-in replacement usable purely from
`C_N_alpha`/`l1`/`d_ref` without an added assumption about body shape (e.g., approximating the body
as a uniform cylinder of length `l1+l2` and diameter `d_ref`, which is itself an interpretation this
research is not endorsing, only flagging as the kind of simplification someone would have to make).
The finned branch needs the deferred Barrowman-style component build-up.

## 2. Barrowman's 1966 thesis and damping extensions

**Citation.** Barrowman, James S. *The Practical Calculation of the Aerodynamic Characteristics of
Slender Finned Vehicles*. B.S. Thesis, The Catholic University of America, 1966 (also circulated as
NASA/NARAM technical reports; a commonly-cited scan is hosted on `apogeerockets.com`'s technical
publications page and in various NAR/TRA archives — URL not verified this session).

**Scope (moderate-high confidence — this is a widely repeated fact in the rocketry literature,
including in the background sections of works that discuss Barrowman, such as the OpenRocket thesis
itself).** Barrowman's original method computes only **static** coefficients: `C_Nα` per component
(nose, conical/ogive transitions, fins with interference correction) and the overall center-of-
pressure (CP) location — i.e., exactly the `C_N_alpha`/CoP-location pair this project's
`aero.cop_l1` and `C_N_alpha` already represent, generalized to a per-component sum. **Barrowman's
1966 work does not address pitch damping (`C_mq`) at all** — no rate-derivative term appears in the
original method. I am not aware of a single universally-adopted "Barrowman-style" damping extension
carrying Barrowman's own name; the extension that became the de facto standard in the hobby/
experimental community is OpenRocket's own strip-theory addition (§3), which explicitly builds on
top of a Barrowman-style static component breakdown but is Niskanen's contribution, not Barrowman's.
Flagging as an open question rather than a confirmed negative: I cannot rule out a lesser-known
academic damping extension bearing Barrowman's name that simply didn't surface in training data or
that would require a literature search (e.g. via a citation index) this session's tools couldn't do.

## 3. OpenRocket (Niskanen thesis) — strip-theory pitch/yaw damping

**Citation.** Niskanen, Sampo. *Development of an Open Source model rocket simulation software*.
Master's thesis, Helsinki University of Technology / Aalto University, 2009. Implementation:
`openrocket/openrocket`, `unstable` branch,
`core/src/main/java/info/openrocket/core/aerodynamics/BarrowmanStabilityCalculator.java`.

**Verified 2026-09-28 directly against the GitHub source (this supersedes the memory-reconstructed
version originally written in this section — the actual method is geometric, not a `c_N'(x)`
integral as first guessed).** Quoted from `calculateDampingMoments` and `getDampingMultiplier`:

```java
// body contribution — cacheDiameter = (sum of body-component planform areas) / (sum of lengths);
// cgx = CG position from nose tip; cacheLength = total body length
double mul = 0.275 * cacheDiameter / (refArea * refLength);
mul *= (pow4(cgx) + pow4(cacheLength - cgx));

// + per fin set:
mul += 0.6 * min(finCount, 4) * finPlanformArea
       * pow3(|finMidchordX - cgx|) / (refArea * refLength);

mul *= 3;                                        // "Higher damping yields much more realistic apogee turn"
pitchDampingMoment = min(mul * (pitchRate/velocity)^2, total.getCm());   // hard-capped at the static moment
```

**Two things this corrects from the earlier guess:**
1. **Inputs are pure planform geometry, not an aerodynamic coefficient.** It needs body planform
   area/length (nose + tubes, to build an "average diameter" proxy `cacheDiameter`) and, per fin
   set, fin count/planform area/midchord axial position — it does **not** use `C_Nα` anywhere. That
   makes it a lighter dependency than assumed: it does not actually require the deferred Barrowman
   *aerodynamic* component build-up, only basic fin/body *shape* data, which this simulator also does
   not currently track (no fin span/chord/sweep at all).
2. **It is explicitly a calibrated engineering approximation, not a first-principles derivation.**
   The `×3` multiplier and its comment, and the hard cap at the static moment (`total.getCm()`, so
   damping can never exceed or flip the sign of the restoring moment), are tuned for "realistic"
   simulated apogee turnover — not derived from strip theory in a way that would survive a from-first-
   principles check. Adopting this method means adopting that tuning, not just its formula shape.

**Inputs required.** Body planform area/length and per-fin-set count/planform-area/midchord-position
— new geometry `Params` fields the simulator does not have. **Not usable from the simulator's
current single `C_N_alpha` scalar as-is**, though it is a smaller gap than the full Barrowman
aero-coefficient build-up would be.

## 4. Classical slender-body-of-revolution closed form (Munk/Bryson-type, NACA/aeroballistics tradition)

**Citation (moderate confidence).** The foundational result traces to Munk, Max M., *The Aerodynamic
Forces on Airship Hulls*, NACA Report No. 184, 1924 (potential-flow "apparent mass" moment for a
body of revolution) — freely available via the NASA Technical Reports Server (`ntrs.nasa.gov`), URL
not verified this session. It was extended to missile/slender-body dynamic derivatives by Bryson,
Arthur E., "Stability Derivatives for a Slender Missile with Applications to a Wing-Body-Tail
Configuration," *Journal of the Aeronautical Sciences*, Vol. 20, No. 5, 1953, pp. 297–308 — the
paper most often cited (including, per §1, inside Nielsen) as the source of the closed-form
potential-flow pitch-damping term for slender bodies.

**Form (structure-level confidence only — do not encode the coefficient without checking the
primary source).** The classical result expresses the *potential-flow* part of `(C_mq + C_mα̇)` for
a slender body of revolution as an integral of the body's cross-sectional area (equivalently, its
local radius-squared profile) along its length, weighted by the squared distance from the CG,
normalized by `Sref` and a reference length — conceptually an "added moment of inertia of the
displaced fluid" about the CG, purely a function of the body's shape (fineness ratio, volume
distribution) and CG location, with **no fin geometry** and **no wind-tunnel/CFD data** required.
This is the genuine "body alone, no fins" family the task asked about. Two caveats worth stating
plainly: (a) it is a purely inviscid/potential-flow term — it captures the "apparent mass" damping
mechanism but omits viscous cross-flow drag contributions that are known (Nielsen and others) to
also matter, especially at higher angles of attack; and (b) like Nielsen's body term in §1, it needs
the body's **shape/volume distribution**, not the simulator's single `C_N_alpha` scalar — `d_ref`
alone under an assumed-cylinder simplification is the closest current-model proxy, and that
simplification is this researcher's own suggestion for how one *might* adapt it, not something
found stated that way in a source.

## 5. Other open amateur-rocketry tools: RASAero II, RockSim

**Brief, as requested — not rabbit-holed.** RASAero II (Charles E. Rogers/John Beans, aerodynamics
prediction based partly on Missile DATCOM-derived methods and supersonic panel/empirical data) and
RockSim (Apogee Components) are both **proprietary, closed-source** tools; I am not aware of either
publishing its dynamic-stability/pitch-damping formula in an open technical document comparable to
Niskanen's thesis. This is a well-known state of affairs in the hobby community (repeatedly stated
on rocketry forums such as `rocketryforum.com` when the question of "how does X compute damping"
comes up) but I could not confirm or find a citable primary technical document this session — flag
as **not found / likely not publicly documented**, rather than asserting a specific method exists.

## Comparison table

| Method | Required inputs | Usable at CURRENT model fidelity (single `C_Nα`, no fin breakdown)? | Usable only after deferred Barrowman component build-up? |
|---|---|---|---|
| Step 44 test fixture, `2·C_Nα·(l1/d_ref)²` | `C_Nα`, `l1`, `d_ref` | Yes — already implemented, but explicitly a non-authoritative sanity check | — |
| Nielsen — body-of-revolution potential flow | body radius/volume profile `r(x)`, CG location | No — needs a shape profile the sim doesn't store (only assumable via a cylinder simplification, not sourced) | No — this is a body-shape need, not a fin need; still a gap either way |
| Nielsen — finned-vehicle strip term | per-fin `C_Nα`, moment arms | No | Yes |
| Barrowman 1966 (static only) | per-component `C_Nα`, CP | N/A — no damping term at all | N/A |
| OpenRocket / Niskanen strip theory (verified against source) | body/fin planform geometry (areas, lengths, midchord positions) — no `C_Nα` needed, but includes a `×3` calibration factor and a hard cap at the static moment | No — needs fin/body shape data the sim doesn't track | Not gated on Barrowman aero build-up specifically — needs fin/body *geometry*, a smaller/separate gap |
| Munk/Bryson slender-body closed form | body radius/volume profile, CG location | No (same shape-profile gap as Nielsen body term; a cylinder-simplification proxy is possible but is this researcher's own extrapolation, not a sourced statement) | Partially — still needs a shape input the fin build-up alone won't supply |
| RASAero II / RockSim | undocumented (proprietary) | Unknown — not publicly documented | Unknown |

No recommendation is made here on which method the project should adopt; that decision belongs to
the architect and the user.

## Decision (2026-09-28)

Presented to the user with the verified OpenRocket findings above (source-code-confirmed, not the
original memory-reconstructed version). Options offered: (a) add fin/body planform geometry and port
OpenRocket's formula including its `×3` tuning and cap; (b) same geometry, but keep only the
geometric/strip-theory shape and drop the `×3`/cap tuning; (c) leave `c_mq` at the Step 44 test
fixture for now; (d) keep researching Nielsen/the classical slender-body forms against primary
sources the same way. **User chose (c): leave the Step 44 test fixture
(`c_mq = 2·C_Nα·(l1/d_ref)²`) in place.** No `Params`/code changes made as a result of this research
pass. Revisit if/when fin geometry is modeled for other reasons (e.g. a future Barrowman aero
build-up), since OpenRocket's method turns out not to be strictly gated on that build-up itself, only
on shape data.
