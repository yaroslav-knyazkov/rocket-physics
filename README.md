# rocket-physics

Симулятор траектории ракеты: 2D-модель полёта (гравитация, тяга по реальной
кривой, аэродинамика, ветер/атмосфера) с интегратором и построением графиков,
плюс задел под 3D/6DOF-динамику (кватернионы, вращение, демпфирование по
тангажу) — частично уже в коде (`apps/sim/engine/dynamics3d.py`,
`quaternion.py`, `rotation.py`, `forces3d.py`, `state3d.py`), но ещё не
основной путь симуляции. Физика выведена и задокументирована в LaTeX-отчёте
(`dev/docs/latex/`) — код сверяется с ним, а не наоборот.

Проект для тех, кто хочет прогнать траекторию конкретной ракеты (мотор +
аэродинамика + стартовые условия) и получить график/CSV, подобрать мотор или
аэротормоз под целевую апогею, или оценить компромисс масса-аэродинамика —
без сервера, без UI, напрямую из Python-скриптов.

## Стек

- Python 3.12
- numpy, scipy, matplotlib (`requirements.txt`)
- pytest (тесты)

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

## Быстрый старт

Пред-собранных входных скриптов в репозитории нет: `apps/` — библиотека/
тулкит, которую вы либо запускаете как модуль
(`python -m apps.<тип>.<имя>.<модуль>`), либо импортируете из своего
скрипта. Минимальный пример — прогнать демо-сценарий (реальный мотор
Cesaroni K570 на 54-мм корпусе) из короткого скрипта в своей `projects/`
(тот же паттерн, что в `tests/test_worked_scenario_example.py`):

```python
from apps.input.demo_scenario import DEMO_SCENARIO
from apps.sim.schema import assemble
from apps.sim.engine.integrate import run_sim
from apps.sim.engine import report

cfg = assemble(DEMO_SCENARIO)
result = run_sim(cfg.params, cfg.s0)
report.print_run_summary(result, cfg.params, cfg.s0)
```

Печатает сводку полёта (апогея, время работы мотора и т.п.) в консоль.

Остальные утилиты из `apps/` запускаются так же — отдельными модулями, без
готовых обёрток:

- **`python -m apps.optimization.motor_selection.compare_motors`** —
  сравнение набора моторов из `apps/optimization/motor_selection/motors.py`;
  **`...scenario_sweep --motors a,b,c [--target M]`** — sweep демо-сценария
  по списку RASP-моторов относительно целевой апогеи.
- **`python -m apps.optimization.airbrake_sizing.solve_cda [--spec NAME]`**
  — подбор площади аэротормоза (`C_dA`) под целевую апогею именованного
  спека из `apps/optimization/airbrake_sizing/targets.py`.
- **`python -m apps.analysis.cfd_conditions.select_conditions`** — выбор
  условий (скорость/число Маха, высота) для постановки CFD-расчёта по
  траектории демо-сценария.
- **`python -m apps.analysis.weight_aero_tradeoff.trade_surface`** /
  **`...compare_configs`** — компромисс масса-аэродинамика: поверхность
  обмена массы на аэродинамику с изо-апогейными линиями / сравнение
  именованных сценариев друг с другом.

Каждая из этих команд пишет PNG/CSV в `output/` текущей рабочей директории
(создаётся на лету при первом запуске, гитигнор).

## Построить свою ракету

Нет реестра и нет файла-на-конфигурацию — только один файл-образец:

1. Скопируйте `apps/input/demo_scenario.py`.
2. Переименуйте `DEMO_SCENARIO` во что-то своё.
3. Отредактируйте значения — каждое поле в файле помечено прямо в
   комментарии `# REQ|OPT, <единица или варианты> -- <пояснение>`: `REQ` —
   обязательно задать своё значение, `OPT` — можно оставить как есть,
   это осмысленный умолчальный вариант из `apps/sim/schema.py`.

Датаклассы (`Rocket`/`Site`/`Weather`/`Motor`/`Scenario`) и сборка сценария
(`assemble()`) — всё в `apps/sim/schema.py`.

## Тесты

Точечный прогон (быстро, в разработке):

```bash
python -m pytest tests/test_<имя>.py -q
```

Полный прогон:

```bash
python -m pytest -q
```

Полный прогон медленный (несколько минут на обычной машине) — не запускайте
его «по привычке» на каждую мелкую правку в локальной разработке без фоновой
обвязки, здесь нет CI, который возьмёт это на себя.

## Структура каталогов

```
apps/                      — корень продукта
  sim/engine/               — физическая модель, интегратор, отчёты, графики
  sim/schema.py             — Rocket/Site/Weather/Motor/Scenario датаклассы + assemble()
  input/                    — демо-сценарий, study_vehicle, сетевой фетчер зондирований
  analysis/                 — CFD-условия, компромисс масса-аэродинамика, ensemble
  optimization/             — подбор мотора, подбор аэротормоза
  control/                  — законы управления (flight_software)
  _shared/                  — общие утилиты (artifacts, flight_stats)
projects/                  — ваша рабочая область: входные скрипты, свои ракеты
  examples/data/            — бандловые read-only фикстуры (демо-моторы, аэро, зондирования)
  data/                     — (гитигнор) ваши личные данные, создаётся пустой
tests/                      — pytest-сьют
dev/                        — трекер проекта и документация команды агентов (не нужен конечному пользователю)
```

## Деплой и сеть

Нет сервера и нет деплоя — локальная библиотека + скрипты. Единственный
сетевой вызов во всём проекте — ручной запуск
`apps/input/sounding_fetch/fetch_sounding.py` (данные зондирований
University of Wyoming); сама физическая модель (`apps/sim/engine/`) всегда
работает офлайн и детерминирована.

## Подробнее

- Физика и вывод уравнений — `dev/docs/latex/`.
- Процесс разработки, команда агентов, статус проекта — `CLAUDE.md` и
  `dev/PROJECT-STATUS.md`.
