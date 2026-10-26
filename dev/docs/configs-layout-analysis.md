# `configs/` layout — separating library-owned files from user files

## Кратко (RU)

- Документ разбирает жалобу пользователя: в каждом из 5 подпакетов `configs/{rockets,sites,weather,motors,scenarios}/`
  шаблон (`_TEMPLATE_*.py`) и единственный библиотечный demo/placeholder лежат в той же папке, куда пользователь
  добавляет свои реальные конфиги — визуально не разделено "это framework" от "это моё".
- `__pycache__`/`__init__.py` "захламление" — косметика: `__pycache__` уже в `.gitignore`, не проблема репозитория;
  упомянуто и закрыто одной строкой, не разбирается таблицей вариантов.
- Рассмотрено 4 варианта: (A) только соглашение об именовании/README без переноса файлов; (B) подпапка
  `configs/<kind>/_library/` в каждом из 5 подпакетов; (C) единое дерево `configs/_library/<kind>/` на верхнем
  уровне; (D) манифест/TOML вместо Python-кортежа `_MODULES` (отклонён — не решает жалобу, дорогой, другая ось).
- **Рекомендация: (B)** — подпапка `_library/` внутри каждого подпакета. Регистрационный ключ не меняется
  (`mod.__name__.split(".")[-1]` работает на любой глубине), стоимость миграции умеренная и локальная
  (~10 файлов переместить, ~5 `__init__.py` плюс одна новая пустая `__init__.py` на подпапку, ~11 строк-путей
  в тестах, десяток строк в докстрингах), импорт-DAG (SS31.5) не нарушается — подпапка остаётся внутри своего
  вида, а не уходит в соседнее дерево.
- (C) даёт чуть более чистую картину "одна полка на всё", но *увеличивает* число `__init__.py`/pycache (жалоба
  #2), а не уменьшает, и добавляет лишний прыжок импорта через `configs._library.<kind>` — не рекомендуется.
- Нулевая правка (фоллбэк): расширить существующий докстринг/добавить `README.md` в каждом подпакете, явно
  называющий framework-owned файлы — без переноса файлов, без правки тестов.

## Contents

- [1. Current state](#1-current-state)
- [2. The pain points, precisely](#2-the-pain-points-precisely)
- [3. Alternatives](#3-alternatives)
  - [A. Convention only, no file moves](#a-convention-only-no-file-moves)
  - [B. Per-subpackage `_library/` subfolder](#b-per-subpackage-_library-subfolder)
  - [C. Single top-level `configs/_library/` tree](#c-single-top-level-configs_library-tree)
  - [D. Manifest/TOML-based registry (rejected)](#d-manifesttoml-based-registry-rejected)
- [4. Recommendation](#4-recommendation)
- [5. Zero-churn fallback](#5-zero-churn-fallback)

---

## 1. Current state

Read: `configs/__init__.py` (top-level "how do I add my own" docstring), `configs/motors/__init__.py` +
`configs/motors/_TEMPLATE_motor.py` + `configs/motors/cti_k570.py` as the concrete worked example,
`configs/sites/__init__.py` (confirms the identical shape), `dev/docs/architecture-31-config-separation.md`
§31.5/§31.8, `dev/docs/architecture-33-configs-one-demo.md` §33.2, `tests/test_config_registries.py`,
`tests/test_configs.py`.

All 5 subpackages (`rockets/`, `sites/`, `weather/`, `motors/`, `scenarios/`) follow one shape, set at
§31.5 and reconfirmed at §33.2 ("end state: every subpackage holds `__init__.py`, its `_TEMPLATE_*.py`, and
**exactly one** registered piece"):

```
configs/<kind>/
  __init__.py            # explicit _MODULES tuple, NAMES dict keyed off each module's .name, names(), get()
  _TEMPLATE_<kind>.py     # blank, every field commented REQ/OPT, NOT in _MODULES, imports cleanly anyway
  <one real file>.py      # the one library-shipped worked example: cti_k570.py / origin_msl.py /
                          #   isa_dry_calm.py / demo.py (rockets) / demo.py (scenarios)
  <user's own files>.py   # whatever the user adds, same directory, same registration dance
```

Registration mechanics that matter for any restructuring:

- **`_MODULES` is an explicit tuple, never directory auto-discovery** (§31.5 rule 1, repeated in every
  subpackage's own docstring) — "a half-finished draft must not appear by existing, and 'who uses this
  piece' stays one grep." This is explicitly *not* up for relitigation here; the question is directory
  layout, not registry mechanism.
- **The registry key is `mod.__name__.split(".")[-1]`** (the module's *basename*, not its full dotted
  path) checked against `piece.name` (`tests/test_config_registries.py::test_registry_keys_equal_module_basenames`,
  and the sibling pin in `tests/test_configs.py:91-96` for the scenario registry). This is the load-bearing
  fact for every alternative below: nesting a module one directory deeper changes its `__name__` (e.g.
  `configs.motors.cti_k570` → `configs.motors._library.cti_k570`) but **not its basename**, so this pin
  survives a subfolder move untouched.
- **Templates import cleanly but are never registered** (§31.5 rule, SS31.8 #6): pinned by
  `test_import_template_first_has_no_circular_import` and
  `test_template_imports_cleanly_and_is_absent_from_its_registry` in `tests/test_config_registries.py`,
  parametrised over 5 literal module-path strings (10 occurrences total, since each appears once as an
  import target and once as an attribute-access expression).
- **Import DAG is one-directional** (§31.5 rule 2): piece modules import `from configs.schema import X`,
  never reach up into their own subpackage's `__init__` or into `configs`/`configs.scenarios`. Any layout
  change must preserve this — it is what keeps the 5 "fresh interpreter, import this module first" tests
  (SS31.8 #3) passing.
- Registered names (`cti_k570`, `origin_msl`, `isa_dry_calm`, `demo` ×2) are referenced **185 times across
  27 files** (tests, apps, docs) — grepped directly for this analysis. Renaming the registered *name* of a
  piece (as opposed to moving the *file* that defines it) is expensive; this matters below because one
  naive reading of "separate library files by naming" would be to prefix the demo filenames, which would
  force a name change too (the basename-equals-name pin), rippling through all 27 files. The subfolder
  alternatives below keep every registered name exactly as-is; only the module's dotted path grows one
  segment.

## 2. The pain points, precisely

**Real cost (#1 — directory mixing):** when a user is filling in their own motor/rocket by hand in the
same directory as `_TEMPLATE_*.py` and the one shipped demo, there is no filesystem signal for "these two
files are framework reference material, read-only, never yours to edit" versus "this is where your files
go, make as many as you like." The `_TEMPLATE_` prefix only disambiguates the template, not the demo
(`cti_k570.py`, `origin_msl.py`, etc. look exactly like a user's own real file, because structurally they
are the same shape). This is a genuine navigation/cognition cost, worth solving.

**Cosmetic, not a real cost (#2 — `__init__.py` + `__pycache__` per directory):** `__pycache__/` is already
`.gitignore`d (root pattern + `.claude/**/__pycache__/`), so it is not a repo/commit/review problem — it is
a purely local, purely visual side-effect of Python's ordinary bytecode caching on import, unavoidable
without `PYTHONDONTWRITEBYTECODE=1` (which only makes every import slower, with no compensating benefit).
Noted, not solved — no alternative below is scored against this axis beyond "does it make the per-directory
file count better or worse," since that is the only way it interacts with #1's fix.

## 3. Alternatives

### A. Convention only, no file moves

Keep every file exactly where it is. Make the "framework-owned vs. yours" distinction *textual* instead of
*structural*: extend each subpackage's `__init__.py` docstring (already does this, but briefly) and/or add
one `README.md` per subpackage stating plainly "`_TEMPLATE_<kind>.py` and `<demo>.py` are the only two
library-owned files in this directory, read-only reference; everything else here is yours." Optionally also
rename nothing, but add a one-line comment at the top of the demo file itself making the same point (the
`_TEMPLATE_*` docstring already does, the demo files' docstrings currently do not call this out explicitly).

- **What changes:** 5 new `README.md` files (or 5 docstring additions), zero code, zero registry changes.
- **What breaks:** nothing. Zero test edits, zero import edits, zero path strings anywhere.
- **Migration cost:** trivial — under an hour, no test run needed beyond sanity.
- **What it buys:** a reader who opens the directory and reads top-to-bottom gets the distinction; a reader
  who just sees a flat `ls`/file-explorer listing still sees everything mixed together with no visual cue
  beyond the `_TEMPLATE_` prefix already in place. Does not address the literal complaint ("visually/
  cognitively mixed together") as directly as a structural split would — the files are still interleaved
  alphabetically in any directory listing (`_TEMPLATE_motor.py`, `cti_k570.py`, `my_motor.py` all sort
  together once the user adds their own).

### B. Per-subpackage `_library/` subfolder

Each subpackage grows one nested package holding exactly its template and its one demo/placeholder;
everything the user adds stays directly under the subpackage root, now otherwise containing only the
registry `__init__.py`:

```
configs/motors/
  __init__.py             # registry; import line becomes `from configs.motors._library import cti_k570`
  _library/
    __init__.py            # trivial, 1-line docstring, no registry logic of its own
    _TEMPLATE_motor.py
    cti_k570.py
  <user's own motor files>.py   # nothing else lives here but the user's own content
```

Same shape repeated for `rockets/`, `sites/`, `weather/`, `scenarios/` (10 files moved total: 5 templates +
5 demos).

- **What changes:**
  - 10 files moved one directory deeper (`git mv`).
  - 5 new trivial `_library/__init__.py` files (one line each).
  - 5 edits to each kind's own `__init__.py`: the `_MODULES` import line gains `._library` (e.g.
    `from configs.motors import cti_k570` → `from configs.motors._library import cti_k570`); the registry
    logic itself (`MOTORS = {...}`, `names()`, `get()`) is untouched, since it only ever reads
    `mod.MOTOR.name` and `mod.__name__`, neither of which cares about nesting depth.
  - `tests/test_config_registries.py`: 10 literal module-path-string occurrences become
    `configs.<kind>._library._TEMPLATE_<kind>` (5 in the `test_import_template_first_has_no_circular_import`
    parametrisation, 5 in `test_template_imports_cleanly_and_is_absent_from_its_registry`'s).
  - `tests/test_configs.py:220`: the one demo-path fresh-interpreter string becomes
    `configs.scenarios._library.demo`.
  - Docstring touch-ups (not test-breaking, just stale-prose risk if skipped): each `_TEMPLATE_<kind>.py`'s
    "to use this template" 3-step instructions currently say "rename this file ... register in
    `configs/<kind>/__init__.py`'s `_MODULES` tuple" — still correct verbatim, since the instructions never
    named the *old* path explicitly as something to move *out of*. The one docstring that does need an
    edit is `configs/__init__.py`'s top-level "how do I add my own" guide, which currently reads as if demo
    files sit directly in each subpackage; and each subpackage's own `__init__.py` docstring, which
    currently spells out the full file list as architecture doc §31.5 did — both are a few lines each, not
    structural.
  - `dev/docs/architecture-31-config-separation.md` and `-33-configs-one-demo.md` are historical per-phase
    design records (not living specs); they are not required to track a later refactor exactly, but a
    one-line "superseded by configs-layout-analysis.md, D-NN" pointer at the top of §31.5's directory tree
    is good practice.
- **What breaks:** the two test files above (11 literal path strings) and the "find it" habit of grepping
  `configs/motors/cti_k570.py` directly — one more path segment to type/autocomplete, nothing more; `rg`
  and IDE "go to definition" are unaffected.
- **Migration cost:** moderate — mechanical, low-risk, same class of change as the SS31.6 amendment this
  project already did once (`configs.demo_75mm` → `configs.scenarios.demo_75mm`, "a mechanical consequence
  of a `git mv`"). Every test that would catch a mistake here already exists and is parametrised, so a
  missed path shows up immediately as a specific, readable failure, not a silent gap.
  Rough size: ~10 files moved, ~10 one-line edits (5 new nested `__init__.py` + 5 import-line edits in the
  existing kind `__init__.py`), ~11 test-string edits, ~6-10 docstring lines touched.
- **What it buys:** the structural separation the complaint actually asks for. `ls configs/motors/` now
  shows `__init__.py`, `_library/`, and nothing else until the user adds their own file — the one remaining
  entry in that listing *is* the user's own content, unambiguously. The import DAG (§31.5 rule 2) is
  preserved exactly: `_library/` sits inside its own kind's subpackage, so the existing
  "pieces never import up" invariant needs no new case to reason about — it is still "one subpackage, one
  registry, one place pieces live," just one level deeper.

### C. Single top-level `configs/_library/` tree

Instead of nesting a `_library/` inside each of the 5 kind subpackages, pull every template and demo into
one top-level tree mirroring the 5 kinds:

```
configs/
  _library/
    __init__.py
    rockets/{__init__.py, _TEMPLATE_rocket.py, demo.py}
    sites/{__init__.py, _TEMPLATE_site.py, origin_msl.py}
    weather/{...}
    motors/{...}
    scenarios/{...}
  rockets/__init__.py        # `from configs._library.rockets import demo`
  sites/__init__.py
  ...
```

- **What changes:** the same 10 file moves as (B), but landing two directories away from their kind's
  registry instead of one; **6** new `__init__.py` files instead of (B)'s 5 (one package-level
  `configs/_library/__init__.py` plus one per kind under it); same 11 test-string edits, now with an extra
  path segment (`configs._library.motors._TEMPLATE_motor` instead of `configs.motors._library._TEMPLATE_motor`).
- **What breaks:** same tests as (B), same count, slightly longer path strings. Additionally raises one
  design question (B) does not: does `configs/rockets/__init__.py` re-export
  `configs._library.rockets._TEMPLATE_rocket` under its old public name for anyone who imported the template
  by its pre-refactor path, or is the path change accepted outright as a named exception (the SS31.6
  precedent)? Not a blocker, just one more decision to write down than (B) needs.
- **Migration cost:** moderate, marginally higher than (B) — one extra `__init__.py`, one extra import hop
  to reason about per kind, otherwise the same shape of change.
- **What it buys:** a single, very visible shelf — "everything under `configs/_library/` is framework
  reference, full stop, never touch it" — arguably a cleaner one-sentence mental model than (B)'s "each
  kind has its own `_library/` subfolder." But it **does not help pain point #2** the way its visual framing
  suggests it might: it adds one more `__init__.py` (and one more `__pycache__/`) than (B), not fewer, since
  it needs both a package-level `__init__.py` for `configs/_library/` itself and one per kind underneath.
  It also moves the demo/template two hops away from the registry that uses it (`configs/motors/__init__.py`
  now reaches across into a sibling top-level tree rather than one level down into its own subpackage),
  which is a small but real regression against §31.5's "who uses this piece stays one grep" goal — the
  piece file is no longer adjacent to the registry that names it.

### D. Manifest/TOML-based registry (rejected)

Replace each subpackage's `_MODULES = (cti_k570,)` Python tuple with a declarative manifest
(`configs/motors/_registry.toml` listing module names to import) parsed at package-import time, instead of
a hardcoded tuple of already-imported module objects.

- **What changes:** the registry *mechanism* in all 5 subpackages, plus a TOML parser dependency (or
  hand-rolled parsing) and import-by-string machinery (`importlib.import_module`) replacing direct `import`
  statements.
- **What breaks:** this is a different axis entirely from the complaint. It does not touch directory layout
  at all — a manifest-driven registry still has to point at *some* file, and that file can live in the
  exact same mixed directory as today, so by itself it does nothing for pain point #1 unless paired with
  (B) or (C) anyway. It also directly conflicts with the project's explicit, repeatedly-stated design
  choice (§31.5, restated verbatim in all 5 `__init__.py` docstrings, §30.4 before that): "explicit tuple,
  never auto-discovery... a half-finished draft must not appear by existing." A TOML manifest listing
  string module names loses the one property an explicit Python tuple of already-imported objects gives
  for free — a typo'd or half-written entry fails loudly at import time with a Python traceback pointing at
  the exact line, rather than at whatever error the manifest parser's string-to-import resolution produces.
  It would also touch every registry test that currently inspects `pkg._MODULES` as a tuple of module
  objects (`mod.__name__`, `mod.CONFIG.name`, etc. — a dozen+ assertions across two test files).
- **Migration cost:** expensive, and for a capability nobody asked for. Reject.
- **Why it's listed anyway:** the brief named it as a possibility to rule out explicitly, since it is the
  one alternative that changes the registry's *shape* rather than the *directory layout* — worth stating
  plainly why it is off the table rather than silently omitting it.

## 4. Recommendation

**(B) — a `_library/` subfolder nested inside each of the 5 existing subpackages.**

Reasoning, in order of weight:

1. It is the only alternative that solves pain point #1 (structural separation, visible in a plain
   directory listing) **without** making pain point #2 worse. (C) adds a 6th new `__init__.py`/`__pycache__`
   pair where (B) adds only 5; (A) adds zero of either but also does not structurally separate anything.
2. It keeps every piece adjacent to the registry that uses it — `configs/motors/_library/cti_k570.py` is
   still one hop from `configs/motors/__init__.py`, preserving §31.5's "who uses this piece stays one grep"
   property exactly. (C) trades that property away for a marginally cleaner top-level story.
3. The registered name never changes (only the module's dotted path gains one segment), so the expensive
   path — renaming `cti_k570`/`origin_msl`/`isa_dry_calm`/`demo` themselves, which ripple through 185
   occurrences across 27 files — is never on the table for any of B/C. This is worth stating because the
   "naming prefix" half of the brief's menu (if read as "rename the demo files to carry a marker prefix")
   is the one path that *would* hit that 185-occurrence blast radius; nesting avoids it entirely.
4. Migration cost is bounded and precedented: this project already executed the identical class of move
   once (SS31.6's `configs.demo_75mm` → `configs.scenarios.demo_75mm`, explicitly characterised there as "a
   mechanical consequence of a `git mv`... not a relaxation of the compatibility goal"), and the existing
   parametrised tests (`tests/test_config_registries.py`) catch every missed path immediately and by name.

## 5. Zero-churn fallback

If the user wants the smallest possible change: **(A)**, convention-only. Add one short paragraph to each
subpackage's existing `__init__.py` docstring (they already describe the registry; extend them to name the
two library-owned files explicitly and say "everything else you add here is yours"), optionally backed by
a one-line `README.md` per subpackage for anyone browsing in a plain file explorer rather than reading
source. Zero file moves, zero test edits, zero import edits — purely additive prose. It does not give the
structural separation (B) gives, but it is the cheapest way to materially reduce the "which of these is
framework vs. mine" friction the user hit while hand-editing a config.
