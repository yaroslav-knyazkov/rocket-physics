# Хронология dev/docs/

> Один файл — одна запись, дата = дата создания файла (первый коммит), не дата последней правки.
> Тип: `design` (архитектурный/пивот-документ), `task` (тикет шага), `qa` (QA-отчёт), `diagnosis`
> (диагностика/верификация), `analysis` (аудит/разбор развилок), `notes` (рабочая заметка/сессия),
> `vision` (видение проекта). Порог ~150 KB — см. `dev/docs/index.md`, раздел «Сквозные справочники».

## [2026-09-19] design | architecture.md заведён (сквозной архитектурный журнал)
## [2026-09-19] design | roadmap.md заведён (пошаговый план по фазам)
## [2026-09-19] design | PROJECT-STATUS-legacy.md — старый трекер (архивирован 2026-10-15)
## [2026-10-10] design | §28: Phase 2.11 — разбор `Params`, три модели `sim/aero.py`, sampled-data режим
## [2026-10-13] design | §29: Phase 2.12 — App 3, подбор мотора по апогею (Steps 61-62)
## [2026-10-13] design | §30: Phase 2.13 — Apps 4-5, `apps/common/`, пакет `configs/` (Steps 63-69)
## [2026-10-14] design | §31: Phase 2.15 — разделение `Rocket`/`LaunchSite`/`Weather`/`Scenario` (Steps 71-74)
## [2026-10-15] design | §32: Phase 2.16 — пакет `Motor`, composed-масса, реальные `.eng`/`.rasp` кривые
## [2026-10-15] notes | session-2026-10-15-phase-2.16-handoff.txt — постановка задачи Phase 2.16 (REQ/OPT-шаблоны, один demo)
## [2026-10-15] design | §33: Phase 2.16 — чистка `configs/` до одного demo на пакет (D-76/D-79)
## [2026-10-15] design | §34: Phase 2.16 — фикс знака осевой аэросилы (D-91..D-94a), демо-парашют
## [2026-10-18] design | §35: Phase 2.17 — план paper-alignment, три цели пользователя (D-109..D-118)
## [2026-10-18] diagnosis | diagnosis-rk45-v2-table.md — зависание RK45 на разрыве табличной аэро при α≈±180°
## [2026-10-18] notes | step-99-notes.md — аэро-таблица v2, `l_p_m` от носа, `cm_convention`
## [2026-10-19] qa | qa-report-2.17-m1.md — Milestone M1 (Steps 97-100, 112): PASS с замечаниями
## [2026-10-19] notes | step-102-notes.md — аэротормоз как ось `f_b` таблицы аэродинамики
## [2026-10-19] notes | step-112-notes.md — измерения Jorgensen-расширения (ballistic/chute/clamp)
## [2026-10-21] qa | qa-report-2.17-step113-114.md — прямые коммиты пользователя (QA-1..QA-10 фикс + code-review): PASS
## [2026-10-22] analysis | conventions-industry-standard-analysis.md — аудит `sim/` против отраслевых конвенций (повод: C_m/B31/D-111)
## [2026-10-22] qa | qa-report-2.17-step103.md — Step 103 (модель привода аэротормоза): PASS с замечаниями
## [2026-10-22] qa | qa-report-2.17-step105.md — Step 105 (разброс параметров + ensemble runner): PASS
## [2026-10-22] qa | qa-report-2.17-step115.md — Step 115 (безопасное подмножество аудита конвенций): PASS
## [2026-10-23] task | task-116-lp-relabel.md — Step 116 (D-125): релейбл `l_p` как станции приведения момента
## [2026-10-23] qa | qa-report-2.17-step116.md — Step 116 (D-125, релейбл l_p): PASS
## [2026-10-24] diagnosis | jorgensen-verification-notes.md — факт-чек eta/C_dn/C_x180 против NASA TR R-474/TN D-6996
## [2026-10-24] task | task-104-segmented-rk45.md — Step 104 (D-116/D-128): сегментированный RK45 для ZOH
## [2026-10-24] task | task-107-sampled-laws-registry.md — Step 107: реестр sampled-законов, пакет `controllers/`
## [2026-10-24] task | task-117-cm-rename.md — Step 117 (D-126): переименование `C_m`/`C_mq` → `C_m_code`/`C_mq_code`
## [2026-10-24] task | task-118-axial-cos2-hybrid.md — Step 118 (D-127): cos²-гибрид осевой силы вне плато 85°
## [2026-10-24] task | task-119-b36-fix.md — Step 119 (D-128, B36): фикс fallback `c_mq` под table-моделью
## [2026-10-24] qa | qa-report-2.17-step104.md — Step 104 (сегментированный RK45 + ZOH): PASS
## [2026-10-24] qa | qa-report-2.17-step107.md — Step 107 (реестр sampled-законов): PASS
## [2026-10-24] qa | qa-report-2.17-step117.md — Step 117 (D-126, переименование C_m/C_mq): PASS
## [2026-10-24] qa | qa-report-2.17-step118.md — Step 118 (D-127, cos²-гибрид): PASS
## [2026-10-24] qa | qa-report-2.17-step119.md — Step 119 (D-128, фикс c_mq fallback): PASS
## [2026-10-25] task | task-30-3d-rotational-dynamics.md — Phase 3, Step 30: полная вращательная динамика 3D
## [2026-10-25] task | task-108-sensors-estimator.md — Step 108: баро-канал + настоящий альфа-бета фильтр
## [2026-10-25] task | task-109-roll-reaction-wheel.md — Step 109: 2D крен с реактивным маховиком
## [2026-10-25] qa | qa-report-2.17-step30.md — Step 30 (3D вращательная динамика): PASS
## [2026-10-25] qa | qa-report-2.17-step108.md — Step 108 (баро-канал + альфа-бета эстиматор): PASS
## [2026-10-25] qa | qa-report-2.17-step109.md — Step 109 (2D крен + маховик): PASS
## [2026-10-26] analysis | configs-layout-analysis.md — развилки разделения `_TEMPLATE_*`/demo от файлов пользователя в `configs/<kind>/`
## [2026-10-26] analysis | pivot-configs-and-packaging-analysis.md — Phase 2.18: отказ от реестра `configs/*`, упаковка (F1-F16)
## [2026-10-26] qa | qa-report-2.18-step120-121.md — Steps 120-121 (datafiles.py + packaging): PASS
## [2026-10-27] design | architecture-apps-sim-restructure.md — Phase 2.19: `apps/` корень продукта, `sim/`→`apps/sim/engine/`
## [2026-10-27] analysis | pivot-apps-restructure-analysis.md — Phase 2.19 (Pivot 2): таксономия apps/, `data/`→`examples/` (F1-F17)
## [2026-10-27] qa | qa-report-2.18-step122.md — Step 122 (examples/worked_scenario.py единая crib-sheet): PASS
## [2026-10-27] qa | qa-report-2.18-step123.md — Step 123 (репойнт 12 файлов на DEMO_SCENARIO): PASS
## [2026-10-27] qa | qa-report-2.18-step124.md — Step 124 (CLI-1, развязка apps/ от реестра): PASS
## [2026-10-27] qa | qa-report-2.18-step125.md — Step 125 (архивация реестра configs/, финал пивота 2.18): PASS
## [2026-10-27] vision | vision.md — первый vision-документ проекта, переосмысление rocket-physics как инструмента
## [2026-10-28] notes | journal-archive.md — архив dev/journal.md до порога ~150 KB
## [2026-10-28] task | task-136-137-point-mass-flight-path-angle.md — Steps 136-137 (D-162): gravity-turn, flight_stats диагностика

## LaTeX (`latex/`) — отдельная подшкала, датируется по сопутствующим ревью-раундам

## [2026-10-16] notes | latex/review-round3-notes.md — ревью-раунд 3: рамки/кадры, знак A_m, обозначения тяги
## [2026-10-17] notes | latex/code-vs-paper.md — свод сопоставления кода и статьи раздел-за-разделом
## [2026-10-17] notes | latex/model-proposals.md — обзор недостающих элементов по моделям физики
## [2026-10-17] notes | latex/review-round7-notes.md — ревью-раунд 7: шум тяги, крен, Dryden, вращение Земли, аэротормоз
