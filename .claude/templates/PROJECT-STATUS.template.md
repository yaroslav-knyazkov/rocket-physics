# PROJECT STATUS — {{PROJECT_NAME}}

> **Один дом на факт.** Стадии, решения, реестр артефактов — в `dev/status.json` (срез: `python .claude/scripts/status_query.py current`). Журнал — `dev/journal.md`. Здесь — только открытые пункты, риски и отложенные решения; секции-стабы не заполнять.

## 1. Видение продукта

→ `dev/docs/vision.md`

## 2. Продуктовая карта

→ `dev/docs/product-map.md`

## 3. Roadmap по стадиям

→ `status_query.py roadmap`

## 4. Scope текущей стадии

→ `status_query.py current`

## 5. Доска задач

→ `status_query.py stage <id>`

## 6. ⏳ Ожидает решения / аппрува

_(пока пусто)_

## 7. Лог решений

→ `status_query.py decisions --since <дата>`

## 8. Риски

| Риск | Влияние | Статус |
|---|---|---|

## 9. Индекс deliverables

→ `status_query.py key artifacts`, навигация по документам — `dev/docs/index.md`

## 10. Отложенные решения (Deferred Decisions)

_(пока пусто)_

## 11. Журнал проекта

→ `dev/journal.md` (`status_query.py md-journal --last 3`)
