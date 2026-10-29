# Индекс dev/docs/

> Навигация по `dev/docs/`: одна строка на файл. Хронология — `log.md`, глоссарий терминов — `tag.md`.
> Ведёт `documentation`-агент; обновляется при каждом новом файле в `dev/docs/`.
> Правило порога ~150 KB (CLAUDE.md «Индекс dev/docs») уже близко для этого файла — при превышении
> заводится парный `index-archive.md`.

## Сквозные справочники (не читать целиком — см. CLAUDE.md)

- `architecture.md` (295 KB) — сквозной архитектурный журнал проекта, секции `§NN`, живой, пополняется каждой фазой; читать срезом (`Grep -n` по `## N.`).
- `roadmap.md` (215 KB) — пошаговый план по фазам (`## Phase X.Y`), статус и тикеты каждого шага; читать срезом.
- `PROJECT-STATUS-legacy.md` (121 KB) — архив старого трекера до перехода на `dev/status.json`/`dev/PROJECT-STATUS.md` (2026-10-15); только чтение, не живой документ.

## Архитектурные тикеты фаз (`architecture-NN-*.md`)

- `architecture-28-rewrite.md` — Phase 2.11: разбор `Params` на составные группы, `sim/aero.py` на три модели, sampled-data режим, `run.py`→`sim/report.py`.
- `architecture-29-motor-selection.md` — Phase 2.12 (Steps 61-62): App 3, подбор мотора по апогею, отдельное от `sim/` приложение.
- `architecture-30-apps-4-5-and-configs.md` — Phase 2.13 (Steps 63-69): App 4 (аэротормоз C_dA), App 5 (компромисс масса/аэро), пакет `configs/`, `apps/common/`.
- `architecture-31-config-separation.md` — Phase 2.15 (Steps 71-74): разделение `Rocket`/`LaunchSite`/`Weather`/`Scenario`, `assemble()`; реестр описанный здесь впоследствии архивирован Phase 2.18.
- `architecture-32-motor-separation.md` — Phase 2.16 (Steps 75-84): пакет `Motor`, composed-масса, реальные `.eng`/`.rasp` кривые, `configs/motors/`; реестр архивирован Phase 2.18.
- `architecture-33-configs-one-demo.md` — Phase 2.16 (Steps 85-91): чистка `configs/` до одного шаблона + одного demo на пакет, `study_vehicle.py`, D-76/D-79.
- `architecture-34-axial-drag-sign.md` — Phase 2.16 (Step 93 + 94-96): фикс знака осевой аэросилы (D-91..D-94a), демо-парашют, защита от раскрытия на старте.
- `architecture-35-paper-alignment.md` — Phase 2.17 (текущая, IN PROGRESS): план приведения кода к утверждённому отчёту по трём целям пользователя; решения D-109..D-118.
- `architecture-apps-sim-restructure.md` — Phase 2.19 (Steps 126-134, COMPLETE): `apps/` становится корнем продукта, `sim/`→`apps/sim/engine/`, `configs/` как пакет упраздняется, `data/`→`examples/data`+`data/`.

## Тикеты отдельных шагов (`task-NN-*.md`)

- `task-30-3d-rotational-dynamics.md` — Phase 3, Step 30: полная вращательная динамика 3D, полный симметричный тензор инерции (6 чисел), уравнения Эйлера в общей форме.
- `task-104-segmented-rk45.md` — Phase 2.17, Step 104 (D-116/D-128): сегментированный RK45 вместо `rk4` для sampled-data/ZOH режима.
- `task-107-sampled-laws-registry.md` — Phase 2.17, Step 107: реестр sampled-законов, пакет `controllers/`, законы `proportional_drag`/`pi_apogee`, заглушка эстиматора.
- `task-108-sensors-estimator.md` — Phase 2.17, Step 108: баро-канал (`sim/sensors.py`), настоящий альфа-бета фильтр в `controllers/estimator.py`.
- `task-109-roll-reaction-wheel.md` — Phase 2.17, Step 109: развязанная 2D крутильная степень свободы с реактивным маховиком, переменная ширина вектора состояния.
- `task-116-lp-relabel.md` — Phase 2.17, Step 116 (D-125): релейбл `l_p` как станции приведения момента, ЦД/статзапас как производные величины.
- `task-117-cm-rename.md` — Phase 2.17, Step 117 (D-126): переименование внутренних `C_m`/`C_mq` в `C_m_code`/`C_mq_code`.
- `task-118-axial-cos2-hybrid.md` — Phase 2.17, Step 118 (D-127): форма осевой силы вне плато 85° — cos²-гибрид вместо линейного пандуса.
- `task-119-b36-fix.md` — Phase 2.17, Step 119 (D-128, B36): фикс скалярного fallback `c_mq` под table-моделью относительно `cm_convention`.
- `task-136-137-point-mass-flight-path-angle.md` — Phase 2.17, Steps 136-137 (D-162): точечно-массовая скорость угла наклона траектории (gravity turn), заметка в LaTeX + диагностика `flight_stats.py`.

## QA-отчёты (`qa-report-*.md`)

- `qa-report-2.17-m1.md` — Milestone M1 (Steps 97-100, 112): PASS с замечаниями, 1 major (QA-1, битый `cm_convention`), 9 minor.
- `qa-report-2.17-step30.md` — Step 30 (3D вращательная динамика): PASS, 2 minor.
- `qa-report-2.17-step103.md` — Step 103 (модель привода аэротормоза): PASS с замечаниями, 3 minor.
- `qa-report-2.17-step104.md` — Step 104 (сегментированный RK45 + ZOH): PASS.
- `qa-report-2.17-step105.md` — Step 105 (разброс параметров + ensemble runner): PASS, важная находка про стоимость ансамбля для D-116.
- `qa-report-2.17-step107.md` — Step 107 (реестр sampled-законов): PASS, off-by-one в самоотчёте разработчика задокументирован, не дефект.
- `qa-report-2.17-step108.md` — Step 108 (баро-канал + альфа-бета эстиматор): PASS, 3 minor.
- `qa-report-2.17-step109.md` — Step 109 (2D крен + маховик): PASS, байт-в-байт CSV подтверждён отдельным worktree.
- `qa-report-2.17-step113-114.md` — Steps 113-114 (прямые коммиты пользователя: фикс QA-1..QA-10 + code-review раунд): PASS, 2 паденья теста отнесены к окружению (numpy/scipy).
- `qa-report-2.17-step115.md` — Step 115 (безопасное подмножество аудита конвенций): PASS без замечаний.
- `qa-report-2.17-step116.md` — Step 116 (D-125, релейбл `l_p`): PASS.
- `qa-report-2.17-step117.md` — Step 117 (D-126, переименование `C_m`/`C_mq`): PASS.
- `qa-report-2.17-step118.md` — Step 118 (D-127, cos²-гибрид осевой силы): PASS.
- `qa-report-2.17-step119.md` — Step 119 (D-128, фикс `c_mq` fallback): PASS.
- `qa-report-2.18-step120-121.md` — Steps 120-121 (configs-пивот: `datafiles.py` + packaging): PASS.
- `qa-report-2.18-step122.md` — Step 122 (`examples/worked_scenario.py` как единая crib-sheet): PASS.
- `qa-report-2.18-step123.md` — Step 123 (репойнт 12 файлов на `DEMO_SCENARIO`): PASS.
- `qa-report-2.18-step124.md` — Step 124 (CLI-1, развязка `apps/` от реестра): PASS.
- `qa-report-2.18-step125.md` — Step 125 (финальный шаг пивота: архивация реестра `configs/`): PASS, фаза 2.18 готова к мержу.

## Диагностика, верификация, аудиты (read-only записки)

- `diagnosis-rk45-v2-table.md` — диагностика зависания RK45 на демо-airframe с `example_v2.csv`: разрыв табличной аэро на α≈±180°, не жёсткость/нестабильность.
- `jorgensen-verification-notes.md` — факт-чек трёх значений Jorgensen-расширения (`eta`, `C_dn`, `C_x180`, D-128) против первоисточников NASA TR R-474/TN D-6996.
- `conventions-industry-standard-analysis.md` — аудит `sim/` на соответствие отраслевым конвенциям (повод: знак `C_m`/B31/D-111); 6 самодельных конвенций против стандарта.
- `configs-layout-analysis.md` — анализ развилок визуального разделения `_TEMPLATE_*`/demo от пользовательских файлов в `configs/<kind>/`; рекомендация — подпапка `_library/`.

## Пивоты (анализ развилок, не решения)

- `pivot-configs-and-packaging-analysis.md` — Phase 2.18: анализ (F1-F16) отказа от реестра `configs/*` в пользу обычных классов + упаковки `pip install -e .`.
- `pivot-apps-restructure-analysis.md` — Phase 2.19 (Pivot 2): анализ (F1-F17) возврата `apps/` в пакет, таксономии по типам, переноса `data/`→`examples/`.

## Прочие заметки и записи сессий

- `vision.md` — первый vision-документ проекта (2026-10-27), переосмысление rocket-physics как инструмента, без физики/архитектуры/стека.
- `journal-archive.md` — архив записей `dev/journal.md` до порога ~150 KB; индекс — `status_query.py md-journal --archive`.
- `session-2026-10-15-phase-2.16-handoff.txt` — лог терминальной сессии, постановка задачи Phase 2.16 (шаблоны REQ/OPT, demo/template в `configs/`, один пример в `data/`).
- `step-99-notes.md` — Step 99: аэро-таблица v2, `l_p_m` от носа, заголовок `cm_convention`.
- `step-102-notes.md` — Step 102: аэротормоз как ось `f_b` таблицы аэродинамики.
- `step-112-notes.md` — Step 112: измерения Jorgensen-расширения (ballistic/chute/clamp), ссылка на параметры из research-заметки.

## LaTeX (`latex/`) — отдельное read-only дерево, не редактируется

- `latex/main.tex` + `latex/sections-ai/*.tex` — исходник статьи (physics source of truth), секции `rocket-2d.tex`/`models.tex`/`other-dynamics.tex`/`rocket-3d.tex`/`appendix.tex`/`assumptions.tex`/`backlog.tex`/`analysis.tex`/`introduction.tex`; скомпилированный `main.pdf` лежит рядом. Тулчейна LaTeX в окружении нет, агенты не компилируют.
- `latex/code-vs-paper.md` — свод 2026-10-17: сопоставление кода (`feature/motor-config-separation`) и статьи раздел-за-разделом, что `\todo` закрыто/открыто.
- `latex/model-proposals.md` — обзор недостающих элементов по каждой физической модели (гравитация/тяга/масса/атмосфера/аэро/др.), с оценкой эффекта и трудоёмкости.
- `latex/review-round3-notes.md` — протокол 3-го раунда ревью статьи (кадры/рамки, знак `A_m`, обозначения тяги).
- `latex/review-round7-notes.md` — протокол 7-го раунда ревью (шум тяги, крен, Dryden, вращение Земли, `other-dynamics.tex`, аэротормоз).
- `latex/research/` — заметки-первоисточники: `3d-readiness-proposal.md`, `3d_equations_of_motion.md`, `c_mq_pitch_damping.md`, `dryden_turbulence_model.md`, `jorgensen-params-findings.md`, `model-development-candidates.md`, `restodo-findings.md`, `round6-findings.md`, `round7-findings.md`.
