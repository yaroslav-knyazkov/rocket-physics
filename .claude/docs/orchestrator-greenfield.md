# Orchestrator: greenfield scaffold (new project / new major direction)

Read this before step one on a new project or a new major direction. Not needed for routine stage work — approval gates and the comparison-table template stay in `orchestrator.md`. Trackers: if `dev/status.json`, `dev/PROJECT-STATUS.md`, `dev/journal.md` do not exist yet, create them from `.claude/templates/` first.

## Complexity estimation (Estimation Gate)

After the initial discovery, `product-manager` is obliged to return an estimate of the project's complexity. **Do not start implementation before that estimate.**

product-manager estimates by these criteria: the number of entities/integrations, the presence of complex business logic, scalability requirements, uncertainty in the requirements. Returns one of:

- `complexity: simple` — the project is small, the boundaries are clear, there are few risks.
- `complexity: complex` — the project is large, many dependencies, high uncertainty, or iterative delivery is required.

### Branch: simple

Implement the project **as fully as possible** without a breakdown into stages:
- The full pipeline in one pass: `product → architect → developer (+frontend-developer if there is UI) → qa + security → documentation`.
- The approval gates remain (brief, stack, architecture, deploy).
- The finish: a working product + documentation.

### Branch: complex — MVP + stages

1. `product-manager` forms the **MVP scope** (the minimal valuable set of features) and the **stage plan** (Stage 1, Stage 2, …). Every stage is an independently launchable slice of the product with concrete deliverables.
2. Show the user the MVP scope and the stage plan through **AskUserQuestion**. Wait for an explicit "yes" on the scope and the order of stages — this is an approval gate.
3. Run the stages **sequentially**. Inside every stage:
   a. `product` — the stage requirements + acceptance criteria.
   b. `architect` — architecture/changes for this stage.
   c. **Checkpoint:** show the user the technical decision points and the tool choice in the comparison table format (see `orchestrator.md` § "How to present technical decision points"). Wait for confirmation.
   d. If there is UI: `frontend-developer` agrees the patterns → **user approval** → implementation.
   e. `developer` (then `frontend-developer`, as separate steps) — implementation. Several tickets from `task.md` — one at a time, sequentially.
   f. `qa`, then `security` — checking, one after the other.
   g. `documentation` — updating the documentation.
   h. **Closing the stage:** record the status in the tracker → **tracker archiving** (`archive_status.py --stages <id>` → `--apply`, see `orchestrator.md` § «Tracker archiving») → if the stage added a release step, a DB operation, or a data procedure, call `documentation` to update `dev/docs/release-runbook.md` → commit → **stage report** to the user: what was done, what is left, risks. Ask: continue to the next stage or adjust the plan?
4. Never move to the next stage without an explicit "yes" from the user.

## Kickoff: determining the scope (the FIRST step on a new project)

Before launching any agent, run a quick scope kickoff with the user. One exchange — and all subsequent steps go only through the needed modules.

**Step 1.** Ask for a short description of the task/project (1–3 sentences), if it has not been stated yet.

**Step 2.** Show the module checklist through `AskUserQuestion` with `multiSelect: true`:

```
Вопрос: «Какие модули нужны для этого проекта?
         Снимите галочки с тех, что не нужны или уже готовы.»

Варианты (все отмечены по умолчанию):
  ✅ vision             — разворот сырой идеи в полную картину (один раз, только новый проект)
  ✅ product-manager    — discovery, продуктовая карта, оценка сложности
  ✅ product            — требования, user stories, acceptance criteria
  ✅ architect          — архитектура, стек, структура проекта
  ✅ developer          — реализация backend-кода
  ✅ frontend-developer — реализация UI, design-sync, согласование паттернов
  ✅ qa                 — тест-кейсы, тестирование, дефекты
  ✅ security           — секреты, XSS, инъекции, права доступа
  ✅ documentation      — README, API docs, инструкции запуска
```

**Step 3.** Record the chosen scope in the tracker (`status.json`, the `"active_modules"` field). Skip the excluded agents in the working cycle — do not call them and do not wait for their outputs.

> **Rule:** if the user excluded a module another one depends on (for example, removed `architect` but kept `developer`) — warn them and ask for a deliberate confirmation.

## Working cycle

1. **Kickoff** (see above) — determine the scope, record the active modules.
2. New project → `vision` (once, if it is in the active modules) — unfolds the idea into the vision brief (you pass the path to the agent; by default `dev/docs/vision.md`), then `product-manager` (discovery + **estimation**, reads the vision brief as its main input), if it is in the active modules.
3. **Gate #1 — Brief approval:** get the short project description from product-manager → show it to the user through AskUserQuestion → wait for an explicit "yes". Only after that do you move on.
4. Check/create the tracker (`dev/status.json`, `dev/PROJECT-STATUS.md`, `dev/journal.md` from `.claude/templates/`).
5. **Estimation Gate:** get `complexity` from product-manager → choose the simple / complex branch.
   - Simple → the full pipeline (active modules only).
   - Complex → show the MVP + the stage plan → get approval → go stage by stage.
6. Delegate the next step per the scope **from the active modules**, passing the context.
7. **Gate #2 — Stack and architecture approval:** after architect → a comparison table → AskUserQuestion → wait for a "yes".
8. Get the JSON, process the decisions/approvals through the user.
9. Update the tracker.
10. Repeat. On completion of a stage (complex) or of the whole project (simple) — a report + a proposal for the next step (with approval) + recording in the tracker + a proposal to run `/compact` (see `orchestrator.md` § "Compact after a block").

Use TodoWrite for a visible plan: mark the current stage and branch (simple/complex).
