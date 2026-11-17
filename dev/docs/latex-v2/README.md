# Report v2 -- draft workspace

Scratch space for the next revision of the Rocket Physics report. **v1 (`../latex/`) stays frozen and
untouched** -- it keeps building/reading as-is, as the baseline/reference while v2 is being written.

## Status

Started 2026-11-17 as an informal personal-editing space (not a tracked `dev/status.json` stage, no
dedicated git branch). Progress gets a note in `dev/journal.md` when something changes, not a full
stage lifecycle. Promote this to a formal stage later if it grows into a tracked multi-session effort.

## Layout

```
latex-v2/
  main.tex             preamble copied from v1 (packages, page setup, \todo/\simtodo/\restodo/
                        \figtodo/\comptodo/\ai/\aitext macros) + \input scaffold, no content yet
  sections/*.tex        empty stubs, one per \input target, named after v1's section breakdown
  README.md            this file
```

The section list in `sections/` (`introduction`, `rocket-2d`, `models`, `other-dynamics`, `rocket-3d`,
`analysis`, `assumptions`, `backlog`, `appendix`) is **only a starting point carried over from v1's
structure** -- rename, split, merge, add or delete freely; `main.tex`'s `\input` list is the only place
that needs to stay in sync with whatever files actually exist here.

Each empty stub points back at its v1 counterpart in a comment, purely as a "here's what v1 said on this
topic" pointer -- copy/adapt from it by hand as you see fit, nothing here is wired to v1 automatically.

## Shared reference material

Research notes and literature findings are **not duplicated** into this folder -- they stay the single
shared pool at `../latex/research/` (model proposals, Jorgensen verification notes, round6/7 findings,
3D readiness proposal, etc.). Read from there; if v2 produces new research notes of its own, decide at
that point whether they belong in the shared pool or here.

## Build

No LaTeX toolchain (pdflatex/latexmk) is set up in the dev environment for this project (same as v1) --
compile on your own machine. `main.tex` is the entry point; it uses `\input{sections/<name>}` for each
piece, same mechanism as v1's `\input{sections-ai/<name>}`.

## Policy reminder

Per `CLAUDE.md`, LaTeX sources are not edited by agents by default -- only by explicit request, and only
the scaffolding above was set up on that basis (structure, not content). Writing the actual v2 content is
on you; ask the orchestrator to delegate specific sections to an agent only if/when you want that instead
of writing them yourself.
