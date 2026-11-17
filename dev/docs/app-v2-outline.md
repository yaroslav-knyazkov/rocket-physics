# App v2 outline — subapp-based composition (draft, not an architecture decision)

## Кратко (RU)

- Черновой набросок пользователя: будущая реструктуризация `apps/` в композицию "под-приложений"
  (subapps) — по той же логике, по которой пишется report v2 (`dev/docs/latex-v2/`): frame → forces →
  mass/MOI/CM → weight → thrust → aero → (будущее: magnetic, radiation pressure).
- Слои: **models** (визуализация + интерактивная игра с данными + поставка моделей солверам) →
  **solvers** (normal flight, rail, parachute — пока не решено, отдельные солверы или фазы одного) →
  **optimization** (CFD, ideal mass/drag, ideal thrust — ideal thrust ещё не реализован) →
  **controllers** (airbrake + задел на будущее).
- Результат полёта — большая таблица, хранится как массивы внутри класса (атрибут/property, не
  дефолтный возвращаемый объект).
- Открытые вопросы: нужен ли отдельный subapp `forces`, или его функции распределяются по
  mass/weight/thrust/aero; где по месту будет `orbit` app (явно не решено, задел на будущее).
- **Ничего не реализовывать** — это чистая фиксация идеи по прямой просьбе пользователя
  (2026-11-17), не архитектурное решение и не ревью `architect`. Неформально, без стадии в
  `status.json`, без ветки — как и `dev/docs/latex-v2/`.

## Status

Draft outline only, captured verbatim-structured from the user's own brain-dump while they write the
report v2 LaTeX in parallel (`dev/docs/latex-v2/`). **Not implemented. Not reviewed by `architect`. Not a
committed decision in `dev/status.json`.** Treat as raw material for a future architecture pass, not a
spec.

## The idea

Restructure `apps/` into composable subapps, deliberately mirroring the same modular breakdown the user
is drafting for the report v2 (one LaTeX section per physical concept → one subapp per the same concept).
The models layer exists to (1) visualize the underlying data, (2) let the user interactively explore/tune
it, and (3) feed the resulting models to the solvers.

## Layer 1 — models (subapps, one per physical concept)

1. **frame** — definition of the inertial frame(s).
2. **forces** — position and direction of applied forces. *Open question (user's own): might not be
   needed as its own subapp; could be split and absorbed into the subapps below instead.*
3. **mass, moment of inertia, center of mass, etc.**
4. **weight** — definition of the gravity model. For gravity-gradient effects, needs: center of gravity,
   total force.
5. **thrust** — magnitudes, support for multiple points of application.
6. **aerodynamics**
7. *(later)* magnetic
8. *(later)* radiation pressure

## Layer 2 — solvers

Consume the models above. Planned: **normal flight**, **rail**, **parachute**.

*Open question (user's own):* should rail and parachute be additional phases folded into the main
"normal flight" solver, or separate solver subapps in their own right? Undecided.

**Output:** a big results table per flight, kept as arrays inside the class — exposed as an
attribute/property, not as the function's default return value/output.

## Layer 3 — optimization

Uses the simulated flight data to optimize/derive something. Planned:

- **CFD** — input variables + optimization.
- **ideal** — mass, drag.
- **ideal thrust** — not implemented yet.

(Solver layer is designed to expand further over time; optimization apps sit downstream of whatever
solvers exist.)

## Layer 4 — controllers

Predefined control methods, shape still TBD based on what actually gets implemented along the way.
Planned: **airbrake**, with more methods to follow.

## Unplaced / open questions

- **`forces` subapp vs. splitting it** into mass/weight/thrust/aero instead — undecided (see Layer 1,
  item 2).
- **`normal flight` vs. `rail`/`parachute`** as one solver with phases vs. separate solvers — undecided.
- **Where does an `orbit` app fit?** Flagged explicitly by the user as future development with no
  placement decided yet — not layer 1-4 above, not positioned relative to them either.

## Non-goals right now

Nothing in this document is implemented, scheduled, or architecturally committed. It is a capture of the
user's own working outline, written in parallel with the report v2 draft, for a future architecture pass
to pick up deliberately (stack/structure decisions would still go through `architect` + the usual
approval gate when that time comes).
