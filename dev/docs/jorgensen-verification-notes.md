## Кратко (RU)

Факт-чек трёх значений в `sim/aero.py` (строки 136-145, Jorgensen large-AoA extension, D-128) против первичных источников NASA TR R-474 (1977) и NASA TN D-6996 (1973), прочитанных целиком через Firecrawl PDF-парсинг.

- **`eta`-таблица (fineness ratio → finite-length factor):** оба отчёта дают `eta` **только как график** (Fig. 4 в обоих, со ссылкой на один и тот же первичный источник — учебник Goldstein 1938 + McKinney NASA TN D-540 1960). Текст PDF не содержит табличных значений `eta` вообще — ни одного числа. Вердикт: **UNVERIFIABLE FROM TEXT**. Нужен человек, читающий график глазами (или сканирующий сам Goldstein/McKinney).
- **`C_dn = 1.2`:** найдена прямая цитата в TN D-6996: `C_dn ≈ 1.2` для докритического числа Рейнольдса по кроссфлоу (`Re_n < ~2×10^5`), ламинарный слой с отрывом перед критическим Re. Значение и диапазон применимости **совпадают** с комментарием в коде. Вердикт: **VERIFIED**.
- **`C_x180` (осевая сила на 180°):** формула **найдена явно** — TN D-6996 eq. (9): `C_A = C_AW + C_ASF + C_AB`, с явной формулировкой «at α=0° or 180°» и прямым указанием, что `C_AW` считается по тому концу тела, который обращён к потоку («the nose or forward-facing base»). Волновой/донный член нужен для формы носа (конус/оживало/плоский торец), трения — омываемая площадь, базового давления — только M∞/γ (сверхзвук) или fig. 8 (эмпирика). Реализуемо с геометрией, которая обычно уже есть в конфиге ракеты (длина/диаметр, площадь омываемой поверхности, форма носа), но **не является тривиальным fallback на `C_x(0)`** — это отдельная, более сложная подмодель. Вердикт: **CORRECTION NEEDED** (формула существует и applicable, просто не реализована; `C_x180 = C_x(0)` fallback — не то же самое, что реальный расчёт).

---

# Jorgensen primary-source verification (D-128)

Sources read in full (PDF text extracted via Firecrawl, `parsers: ["pdf"]`), not abstracts:

1. Jorgensen, L.H., *Prediction of Static Aerodynamic Characteristics for Slender Bodies Alone and With Lifting Surfaces to Very High Angles of Attack*, NASA TR R-474, Sept. 1977. https://ntrs.nasa.gov/api/citations/19770026166/downloads/19770026166.pdf
2. Jorgensen, L.H., *Prediction of Static Aerodynamic Characteristics for Space-Shuttle-Like and Other Bodies at Angles of Attack From 0° to 180°*, NASA TN D-6996, Jan. 1973. https://ntrs.nasa.gov/api/citations/19730006261/downloads/19730006261.pdf

Both documents turn out to cover overlapping ground; TN D-6996 is the earlier, more detailed exposition and is the actual primary source for all three items (TR R-474 largely repeats/cross-references the same figures and the same underlying reference numbers, renumbered).

## 1. `eta` finite-length/fineness-ratio factor table

Code (`sim/aero.py` lines 136-141):
```python
_ETA_LAM = np.array([2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 30.0, 40.0])
_ETA_VAL = np.array([0.577, 0.607, 0.643, 0.668, 0.685, 0.701, 0.724, 0.753, 0.795, 0.815])
```
Comment claims source = "Jorgensen NASA TR R-474 Fig. 4 (digitized, ±0.005)".

**What the text actually says (TN D-6996):**

> "In figure 4, values of η from reference 22 are plotted as a function of length-to-diameter ratio. For reference, η's for flat plates are also presented (plotted as a function of plate length-to-width ratio). In spite of a dearth of η data throughout the subsonic Mach number regime, the results given in figure 4 have been used to successfully..." [page in "Estimation of Normal-Force and Pitching-Moment..." section]

> "Values of η for circular cylinders at very low crossflow Mach numbers (from ref. 56) [TN D-6996 numbering: ref. 22] are plotted as a function of length/diameter ratio in figure 4. Values of η for flat plates are also plotted, but as a function of plate length/width ratio."

> Figure caption (identical in both reports, modulo wording): "Figure 4. – Ratio of crossflow drag coefficient for a finite length cylinder (or flat plate) to that for an infinite length cylinder (or flat plate), from ref. 22 [TN D-6996] / ref. 56 [TR R-474]."

**Underlying reference chain** — both reports cite the *same* two sources for this figure, confirmed by reading the reference list of each PDF directly:
- Ref. 22 (TN D-6996) = Ref. 56 (TR R-474): Goldstein, Sydney, *Modern Developments in Fluid Dynamics*, Oxford, The Clarendon Press, vol. 2, sec. 195, 1938, pp. 439-440.
- Ref. 23 (TN D-6996) = Ref. 57 (TR R-474): McKinney, Linwood W., *Effects of Fineness Ratio and Reynolds Number on the Low-Speed Crosswind Drag Characteristics of Circular and Modified-Square Cylinders*, NASA TN D-540, 1960.

**Finding:** Neither PDF's extracted text contains a single tabulated numeric value of η at any length/diameter ratio. Fig. 4 is a plot (image), and the markdown/text extraction of the PDF — grepped exhaustively for "eta", "finite-length", "fig. 4", "length/diameter", "length-to-diameter" — returns only the surrounding prose (as quoted above) and LaTeX-rendered axis labels, never a data table or sampled coordinate list. No appendix data table for this figure exists in either report. The only route to real numbers is reading the actual plotted curve (a human eyeballing the PNG/scan of Fig. 4) or sourcing McKinney's TN D-540 / Goldstein 1938 directly (not fetched here — out of the two-source scope given, and Goldstein 1938 is a pre-digital textbook, unlikely to have an OCR-friendly PDF at all).

One indirectly useful data point: elsewhere in TN D-6996 the report derives η values *backward* from high-α C_N wind-tunnel data via `η·C_dn = (C_N - sin2α·cos(α/2)·(...)) / (...)` (an independent empirical check, not the Fig. 4 digitization) — this is a different computation path and does not give the Fig. 4 curve values either.

Qualitative sanity check only: physically η must → 1 as l/d → ∞ (finite cylinder behaving like an infinite one) and η < 1 for any finite length (end-relief effect reduces crossflow drag), which the code's monotonically-increasing-toward-~0.8-1.0 table shape is consistent with — but this is a shape check, not a value check, and cannot confirm or refute the ±0.005 precision claimed in the code comment.

**Verdict: UNVERIFIABLE FROM TEXT.** The code comment's claim of "digitized, ±0.005" precision from Fig. 4 cannot be confirmed or refuted by reading the PDF text — the figure is a graph with no accompanying data table in either primary source. Closing this gap needs either (a) a human visually reading the actual Fig. 4 plot in a rendered/scanned copy of either PDF, or (b) tracking down McKinney NASA TN D-540 (1960) or Goldstein (1938) directly for an original data table, neither of which was in scope for this pass.

## 2. `C_dn = 1.2` (crossflow drag coefficient of circular cylinder)

Code (`sim/aero.py` lines 143-144):
```
# UNVERIFIED: C_dn = 1.2 (constant, subsonic subcritical cylinder crossflow). Mach/Re dependence
# (transonic peak 1.6-2.0, supercritical drop) is out of scope (backlog B35). Field default: Aero.C_dn.
```

**Direct quote found in TN D-6996** (section "Crossflow drag coefficient", discussing Fig. 1 — "Variation of crossflow drag coefficient with crossflow Mach number for circular cylinders" — and Fig. 2 — "Variation of crossflow drag coefficient with crossflow Reynolds number for circular cylinders at subcritical crossflow Mach numbers (M_n ≤ 0.4)"):

> "Figure 2 gives the variation of C_dn with Re_n for M_n less than about 0.4. It has been well documented over the last 58 years (e.g., refs. 11, 16-18) that C_dn ≈ 1.2 for laminar boundary-layer flow and separation just before the critical Reynolds number of about Re_n = 2×10^5. At about Re = 5×10^5 there is evidence (e.g., refs. 19-21) of laminar boundary-layer flow around the front of the cylinder to an angular position of about 80° or 90° where the flow separates, undergoes transition, and reattaches at an angular position of about 110° to form..." [describes the post-critical drag drop, consistent with the code comment's "supercritical drop"]

Second, independent confirmation later in the same report, applied to a worked example:

> "It should be noted that the C_N curve for M∞ = 0.3 was computed for a free-stream Reynolds number of Re = 10^5, so that, throughout the α range, all of the values of crossflow Reynolds number (Re_n = Re sin α) are subcritical and C_dn ≈ 1.2 (see fig. 2)."

Figure 2's data table (extracted from the PDF text — this one *does* have a readable table, unlike Fig. 4) gives C_dn as a function of Re_n for M_n = 0.25 to 0.50 (subcritical branch, rising from ~0.27 at the *lowest* tabulated Re_n row shown in the extract — note: this low value of 0.27 corresponds to a very low Re_n row (~1.1×10^? units unclear from table formatting) and is NOT representative of the "C_dn ≈ 1.2 subcritical plateau" being discussed in the prose; the 1.2 plateau is the flat region of the curve just below the critical Re, not the lowest-Re end of the tabulated range). The prose statement ("C_dn ≈ 1.2... just before the critical Reynolds number of about Re_n = 2×10^5") is the authoritative, directly quotable number and matches the code's constant.

Figure 1 (Mach-number variation) text also explicitly flags the code's "out of scope" note as a real, named gap in Jorgensen's own model: the transonic rise and supercritical drop in C_dn with Mach number is discussed qualitatively in the surrounding prose (not fully tabulated in text-extractable form) — consistent with the code comment citing it as deferred to backlog B35.

**Verdict: VERIFIED.** `C_dn = 1.2` matches Jorgensen's stated value for subcritical crossflow Reynolds number (`Re_n` below ~2×10^5) at low crossflow Mach number (`M_n ≲ 0.4`), cited directly in TN D-6996's "Crossflow drag coefficient" section and reused in a worked M∞=0.3 example in the same report. The code's framing ("subsonic subcritical cylinder crossflow", Mach/Re dependence out of scope) matches the primary source's own scope limitation.

## 3. `C_x180` (tail-first axial-force coefficient)

Code (`sim/aero.py` lines 144-145):
```
# UNVERIFIED: tail-first axial magnitude. Jorgensen uses a separate C_A(180 deg); its value is not
# verified here, so Aero.C_x180 == 0.0 falls back to C_x(0) of the table. The user should set it.
```

**The formula exists and is explicit** — TN D-6996, section "Axial-Force Coefficients for Bodies of Revolution at Angles of Attack of 0° and 180°":

> "To predict the variation of C_A with angle of attack by [...] the axial-force coefficient at α=0° or 180° can be expressed by
>
> C_A = C_AW + C_ASF + C_AB  (9)
>
> where C_AW represents the wave or pressure contribution from the nose or forward-facing base; C_ASF is the skin-friction contribution; and C_AB is the base-pressure contribution."

This is an explicit, single formula covering *both* α=0° (nose-first) and α=180° (tail/base-first) — the "nose **or** forward-facing base" wording is the key: at 180°, the body's base becomes the forward-facing surface and the term `C_AW` is evaluated with a geometry model appropriate to *whatever shape is now facing the flow* (confirmed later in the same section, see below), not a separate independent "C_A(180°)" constant as the code comment implies.

**Sub-model for `C_AW` (wave/pressure term) — depends on the facing shape's geometry:**
- Conical nose (facing flow, e.g. normal nose-first flight), supersonic/hypersonic, Linnell-Bailey correlation:
  `C_AW = (4 sin²θ)(2.5 + 8β sinθ) / (1 + 16β sinθ)`  (eq. 10), where `β = sqrt(M∞² − 1)` and `θ` is the cone half-angle. Quoted RMS accuracy ~1.4% vs. exact Taylor-Maccoll cone theory over `0.05 ≤ β sinθ ≤ 10`.
- Circular-arc tangent-ogive nose: read off a correlation curve (not a closed-form equation in the extracted text) at high supersonic/hypersonic M∞.
- **Flat-faced nose or flat base forward** (the case directly relevant for a tail-first rocket with a flat/near-flat motor-end base facing the flow at α=180°): "it can be assumed that the stagnation pressure coefficient C_pstag is nearly constant over the flat face, so that `C_AW ≈ C_pstag`." C_pstag vs. M∞ is given by a correlation curve (refs. 31, 32 in TN D-6996), not a closed-form equation in the extracted text.

**Sub-model for `C_ASF` (skin-friction term):** "can be readily computed by any number of classical flat-plate methods... assume a turbulent boundary layer and compute the skin friction by either the T′ method, the Spalding and Chi method, or the second method of Van Driest." Formally (eq. 13-19 context): `C_aSF = f(M_a, Re_a, A_s/A)` — needs axial Mach `M_a = M∞ cos α`, axial Reynolds number `Re_a = Re·(ρ/μ)·d·cos α` (eq. 18-19 form, as extracted — note the extracted equation (19) render had a formatting artifact, `Re_a = Re·(ρ/d)·cosα`, which is almost certainly an OCR/markdown mangling of `Re_a = Re·cos α`, i.e. the reference Reynolds number scaled by `cos α`; the clean prose statement "determined from axial components (M_a and Re_a) of free-stream Mach number and Reynolds number" is the reliable part), and the body's **wetted surface area ratio `A_s/A`** (wetted area over reference area).

**Sub-model for `C_AB` (base-pressure term):** `C_AB = -C_pB`. For supersonic flow, Gabeaud's correlation (eq. 11):
`C_pB = (2/(γM∞²)) · {(2/(γ+1))^1.4 · (1/M∞)^2.8 · [2γM∞² - (γ-1)] / (γ+1) - 1}` (as extracted; the exact bracketing may have minor OCR artifacts in nested exponents — recommend a human re-check of eq. 11 against the actual PDF page before implementing it verbatim). Alternatively, "either equation (11) or the results in figure 8 can be used to predict C_AB" (fig. 8 is empirical data, M∞ from subsonic to ~∞, with `C_AB = -C_pB` holding as `M∞ → ∞`). This term is a function of `M∞` (and `γ`) only in the extracted formula — no explicit base-area-ratio scaling term appears in the quoted eq. (11) itself (consistent with `C_AB` already being nondimensionalized by reference area `A` per eq. 13's `C_a = F_a/(q_a·A)`, under the implicit assumption base area ≈ reference area; a boat-tailed or necked-down base would need an explicit area-ratio correction not found in the extracted text for this specific equation).

**What geometry inputs this would need, relative to what the project's configs likely already carry:**
- Nose/base shape type (cone half-angle `θ`, or "flat", or ogive) and the relevant shape parameter — likely **not yet a structured field** in `Rocket`/`Aero` configs (would need to check `configs/` schemas directly; not done in this pass, out of scope for a text-fact-check).
- Reference diameter `d` / reference area `A` — very likely already present (needed for all aero coefficients).
- Wetted surface area `A_s` (or wetted-area ratio `A_s/A`) for the skin-friction term — may or may not already be a config field; this is a a genuinely new geometric input if absent.
- `γ` (ratio of specific heats, 1.4 for air) — a constant, not a config field, trivial to supply.
- Free-stream `M∞`, `Re` (already available from flight-condition state, not body geometry).

**Verdict: CORRECTION NEEDED.** A real formula exists in the primary source (TN D-6996 eq. 9, with sub-terms eq. 10/11 and flat-face/skin-friction correlations) and is explicitly stated to apply at both α=0° and α=180° by swapping which end's geometry feeds the `C_AW` term — it is *not* a separate independent empirical constant the way the code comment frames "Jorgensen uses a separate C_A(180°)". The current `Aero.C_x180 == 0.0 → fallback to C_x(0)` is therefore not a faithful stand-in for the real physics (nose-forward and base-forward wave/pressure contributions are generally quite different — e.g. a pointed nose vs. a blunt/flat base at the same Mach number give very different `C_AW`). Implementing the real formula needs at minimum a nose/base shape-type + shape-parameter field and (for the skin-friction term) a wetted-area field, neither of which was confirmed present in the current config schema during this fact-finding pass (would need a separate, short look at `configs/rocket*.py` / `sim/params.py` to confirm — flagged as a follow-up, not done here since this task was source-verification-only).

## Open items / what would need a human or further research

1. **Item 1 (eta table):** cannot be closed by text extraction. Needs a human to read the actual Fig. 4 plot image (either PDF rendered to image, or via `McKinney NASA TN D-540 (1960)` / `Goldstein 1938` original data, neither fetched in this pass).
2. **Item 3 (C_x180) eq. 11 (base pressure, Gabeaud):** the extracted LaTeX for eq. 11 has nested-exponent formatting that looks plausible but was not cross-checked character-by-character against the rendered PDF page — recommend a quick visual confirmation of eq. 11's exact exponents before anyone implements it from this document alone.
3. Whether `configs/` already carries nose/base shape-parameter and wetted-area fields was not checked (out of scope: this was a primary-source fact-check, not a codebase audit) — flagged for whoever picks up the `CORRECTION NEEDED` item.
