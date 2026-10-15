# UI patterns template

Skeleton for `dev/docs/ui-patterns-<stage>.md`, filled by **frontend-developer** at step 0 (design sync),
once per project or UI stage. Kept out of the persona on purpose: it is cold text, needed rarely, and
would otherwise be paid for on every spawn.

Language: English body + Russian `## Кратко (RU)` block first in the file (project language policy).
Rows below are examples — replace with the real decisions, do not ship the placeholders.

---

# Project UI patterns

## Component library
[what we use: shadcn/ui, MUI, Ant Design, custom components — with a rationale]

## Patterns for typical tasks

| Task | Pattern | Component | Rationale |
|------|---------|-----------|-----------|
| Input form | Controlled form | React Hook Form + Zod | validation + typing |
| Paginated list | Virtualisation | TanStack Virtual | performance |
| Async data | Server state | TanStack Query | cache + invalidation |
| Navigation | File-based routing | React Router / App Router | project convention |
| Global state | Zustand store | ... | simplicity |
| ... | ... | ... | ... |

## State management
[the approach: server state vs client state, what is stored where]

## Component structure
[folders: pages/, components/, hooks/, utils/ — the convention]

## Naming
[components PascalCase, hooks use*, files kebab-case etc.]

## Styles
[Tailwind / CSS modules / styled-components — the usage rules]

## Accessibility (a11y)
[minimum requirements: aria-label, keyboard nav etc.]
