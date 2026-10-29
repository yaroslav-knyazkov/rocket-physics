# Глоссарий dev/docs/

> Термин → где раскрыт. Не определение термина самого по себе — только адрес.
> Вести по мере появления новых терминов в новых документах `dev/docs/`.

## Физика / модель

- **θ_v (flight-path angle, угол наклона траектории)** — `task-136-137-point-mass-flight-path-angle.md` (определение, различие от θ/тангажа и γ/крена); диагностика — там же (`flight_stats.py`).
- **Λ (Lambda ratio)** — `task-136-137-point-mass-flight-path-angle.md` (диагностика `flight_stats.py`).
- **gravity turn (точечно-массовая динамика `dθ_v/dt = −g·cos(γ)/V`)** — `task-136-137-point-mass-flight-path-angle.md`.
- **C_m / C_mq (пользовательские, convention-aware поля)** — `step-99-notes.md` (`cm_convention` на загрузке таблицы); `conventions-industry-standard-analysis.md` §1.1 (переопределённость момента); `task-117-cm-rename.md` (почему граница ввода-вывода не переименовывается).
- **C_m_code / C_mq_code (внутренние, всегда-code-convention поля)** — `task-117-cm-rename.md` (D-126); QA — `qa-report-2.17-step117.md`.
- **cm_convention: code|standard** — `step-99-notes.md` (ввод); `task-119-b36-fix.md` (B36, скалярный fallback под table-моделью); `qa-report-2.17-step119.md`.
- **l_p / l_p_m (станция приведения момента, не ЦД-как-вход)** — `task-116-lp-relabel.md` (D-125, релейбл + производные ЦД/статзапас); `conventions-industry-standard-analysis.md` §12.1 (находка).
- **статический запас (static margin)** — `task-116-lp-relabel.md`; `conventions-industry-standard-analysis.md`.
- **axial_flow_factor / знак осевой аэросилы** — `architecture-34-axial-drag-sign.md` (D-91..D-94a, баг + линейный фикс); `task-118-axial-cos2-hybrid.md` (D-127, cos²-гибрид вне плато 85°).
- **Jorgensen large-α extension (eta, C_dn, C_x180)** — `step-112-notes.md` (параметры, измерения); `jorgensen-verification-notes.md` (факт-чек против NASA TR R-474/TN D-6996); `conventions-industry-standard-analysis.md`.
- **B36 (баг: c_mq fallback не уважает cm_convention)** — `task-119-b36-fix.md`; `qa-report-2.17-step119.md`.
- **аэротормоз как ось f_b (table-модель)** — `step-102-notes.md`.
- **actuator model (rate/range/command-delay)** — `qa-report-2.17-step103.md`; тикет упомянут в `roadmap.md` Phase 2.17 Step 103.
- **альфа-бета (constant-velocity) эстиматор** — `task-108-sensors-estimator.md`.
- **sampled laws registry / controllers/** — `task-107-sampled-laws-registry.md`.
- **reaction wheel / 2D крен (roll)** — `task-109-roll-reaction-wheel.md`; QA — `qa-report-2.17-step109.md`.
- **3D вращательная динамика / полный симметричный тензор инерции** — `task-30-3d-rotational-dynamics.md`; `latex/research/3d_equations_of_motion.md`; QA — `qa-report-2.17-step30.md`.
- **Dryden turbulence model** — `latex/research/dryden_turbulence_model.md`; обзор в `latex/model-proposals.md`; ревью — `latex/review-round7-notes.md`.
- **C_m,q (pitch damping)** — `latex/research/c_mq_pitch_damping.md`.

## Численные методы

- **RK45 "зависание" / разрыв табличной аэро на α≈±180°** — `diagnosis-rk45-v2-table.md`.
- **сегментированный RK45 + ZOH (sampled-data режим)** — `task-104-segmented-rk45.md` (D-116/D-128); QA — `qa-report-2.17-step104.md`.
- **чувствительность RK45-пинов к numpy/scipy** — `qa-report-2.17-step113-114.md` (D-77/D-122, перепин пинов под конкретную машину); см. также CLAUDE.md «ловушки».

## Архитектурные пивоты и реструктуризация

- **configs/ pivot (отказ от реестра файл-на-экземпляр)** — `pivot-configs-and-packaging-analysis.md` (F1-F16, анализ); `architecture-31-config-separation.md`/`architecture-32-motor-separation.md`/`architecture-33-configs-one-demo.md` (реестр, который этот пивот впоследствии упраздняет); QA серии `qa-report-2.18-step120-121.md` … `qa-report-2.18-step125.md`.
- **apps/ restructure (Pivot 2, apps/ как корень продукта)** — `pivot-apps-restructure-analysis.md` (F1-F17, анализ); `architecture-apps-sim-restructure.md` (решение/реализация, Phase 2.19).
- **sim/datafiles.py (3-правила резолва пути к данным)** — `pivot-configs-and-packaging-analysis.md`; QA — `qa-report-2.18-step120-121.md`.
- **examples/worked_scenario.py (единая crib-sheet, заменяет 5 _TEMPLATE_*.py)** — `pivot-configs-and-packaging-analysis.md`; QA — `qa-report-2.18-step122.md`.
- **Motor registry / .eng / .rasp кривые** — `architecture-32-motor-separation.md`.
- **study_vehicle.py (вынесенный assumed-constant-mass вектор для Apps 3/5)** — `architecture-33-configs-one-demo.md` (D-79).
- **_library/ подпапка (развилка визуального разделения framework/пользователь в configs/)** — `configs-layout-analysis.md`.

## Аудиты / конвенции

- **аудит индустриальных конвенций (повод: знак C_m, B31/D-111)** — `conventions-industry-standard-analysis.md`; безопасный фикс-набор — `qa-report-2.17-step115.md`.
- **первоисточники Jorgensen (NASA TR R-474, TN D-6996)** — `jorgensen-verification-notes.md`.

## Процесс / трекер

- **Milestone M1 (Phase 2.17)** — `qa-report-2.17-m1.md`.
- **Phase 2.16 — motor-config-separation** — `architecture-32-motor-separation.md`, `architecture-33-configs-one-demo.md`, `architecture-34-axial-drag-sign.md`; постановка задачи — `session-2026-10-15-phase-2.16-handoff.txt`.
- **Phase 2.17 — sim-paper-alignment (в работе)** — `architecture-35-paper-alignment.md`; тикеты `task-104-*` … `task-136-137-*`.
- **Phase 2.18 — configs/ pivot** — `pivot-configs-and-packaging-analysis.md`; QA `qa-report-2.18-step120-121.md` … `qa-report-2.18-step125.md`.
- **Phase 2.19 — apps/ restructure** — `architecture-apps-sim-restructure.md`, `pivot-apps-restructure-analysis.md`.
- **vision (первый документ видения проекта)** — `vision.md`.
