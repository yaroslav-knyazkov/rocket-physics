# wt.py — force-push and ref-deletion safety (2026-08-30)

Working notes for the two data-loss holes closed in `wt.py`, plus the audit of the
rest of the file. Everything here was measured on git 2.55.0.windows.5 in throwaway
sandboxes, not reasoned from the docs alone.

## The threat model

A *second writer* pushes to the same task branch `wt/<slug>`: the user's own terminal,
or a parallel agent session that resolved to the same slug. Their commit exists **only**
on `origin/wt/<slug>` — no local ref anywhere in our worktree points at it. Every check
in the old code compared local refs against `origin/<base>`, so their commit was
invisible to all of them.

## Hole 1 — `sync` force-pushed over them

```python
git(["fetch", "origin", branch], path)                       # advances refs/remotes/origin/<branch>
git(["push", "--force-with-lease", "origin", branch], path)  # lease compares against that same ref
```

A **bare** `--force-with-lease` compares against `refs/remotes/origin/<branch>`. The
fetch one line above had just set that ref to the second writer's commit, so the lease
agreed with the remote by construction and the force-push wiped them. Measured: the
push reports `+ 445197d...a96be7f feat -> feat (forced update)` and origin now holds
our tip. The `die()` below it ("Someone else moved …") could only fire for a push
landing in the seconds between the fetch and the push.

The rebase does not save it: `rebase origin/<base>` replays *local* commits onto the
base. A commit that exists only on `origin/<branch>` is never replayed.

## Hole 2 — `land` never looked at `origin/<branch>`

The preflight computed `unpushed = origin/<branch>..HEAD` and blocked when non-zero,
but never the mirror `HEAD..origin/<branch>`. A branch **behind its own remote** passed
the gate; `merge --no-ff` took the local HEAD (without their commits), the base was
pushed, then the worktree, the local branch *and* the remote branch were deleted. Their
commits became unreachable on origin and the SHA printed "for recovery" was our tip,
not theirs.

## Why the fix is not literally "explicit lease" (measured)

The obvious fix — pin the lease to the sha captured *before* the fetch,
`--force-with-lease=<branch>:<sha>` — is necessary but not sufficient, and it
**disables** `--force-if-includes`. Four measurements, same scenario (they pushed,
we then fetched, then committed locally):

| push flags | result |
|---|---|
| `--force-with-lease` (bare) | **ACCEPTED** — their commit destroyed (the old bug) |
| `--force-with-lease=<branch>:<actual>` `--force-if-includes` | **ACCEPTED** — includes is a no-op once `<expect>` is explicit |
| `--force-with-lease` `--force-if-includes` | **REJECTED** — origin's tip is not in our reflog |
| `--force-with-lease=<branch>:<stale sha>` | **REJECTED** — "stale info" |

So an explicit `<expect>` only protects while our *belief* is stale. The moment
anything fetches — and `wt.py status` fetches on every run, which CLAUDE.md tells the
orchestrator to do before committing — the belief is current, the explicit lease agrees,
and only the reflog rule can still tell "our own pre-rebase tip" from "someone else's
commit".

## What `push_leased()` does instead — three layers

1. **Belief vs reality.** `expected` is `refs/remotes/origin/<branch>` captured *before*
   this command fetched anything. If it moved, refuse. (Covers: nobody fetched in between.)
2. **Is that tip ours?** If origin is ahead of us, its tip must appear in the local
   branch's reflog (`rev-list --walk-reflogs`), i.e. it must be a commit this worktree
   published earlier and is now rewriting. Measured: legit rebase → tip present (1 hit);
   second writer → absent (0 hits). (Covers: `status` already fetched their work.)
3. **The push itself.** git ≥ 2.30 → bare `--force-with-lease --force-if-includes`,
   the combination that makes git enforce the reflog rule natively (layer 1 has already
   verified the tracking ref, so a bare lease is exact here). Older git → explicit
   `--force-with-lease=<branch>:<actual>`, with layers 1-2 carrying the weight. The
   old-git branch was exercised by monkeypatching `git_version` → legit rewrite pushes,
   second writer refused, their commit still on origin.

Reflog windows are finite (200 entries here, git expires at 90 days). A tip that falls
out of the window causes a *refusal*, never an overwrite — the safe direction, and the
refusal text spells out the manual command.

## Audit of the rest of the file

Fixed — same hole, unambiguous:

- **`cmd_commit` push fallback.** A rejected plain push fell back to a bare
  `--force-with-lease`. Reachable exactly as documented in CLAUDE.md: `wt.py status`
  (fetch) → `wt.py commit` → plain push rejected → bare lease satisfied → their commit
  gone, with the script printing a cheerful `committed …, pushed to origin/wt/demo`.
  Now: fetch, then `push_leased()`, then exit 3 with the refusal text.
- **`cmd_drop` guard.** `unmerged = base..branch` only ever looked at the *local*
  branch, yet drop deletes the **remote** branch too. A branch with no local commits
  but a second writer's commit on origin was deleted silently, exit 0. Now drop fetches
  and counts `branch..origin/branch`; non-zero blocks without `--force`.
- **`cmd_land` remote delete.** Plain `push origin --delete` used a preflight that ran
  minutes earlier. Now leased to the tip the preflight saw; on rejection the branch
  survives on origin and the WARN says how to look at it. (Verified a leased delete does
  reject a moved remote: `! [rejected] (delete) -> feat (stale info)`.)
- **Recovery SHAs.** land and drop print the `origin/<branch>` tip as well whenever it
  differs from the local tip (`print_remote_tip_recovery`).

Listed, deliberately **not** changed:

- **`cmd_drop --force` still deletes the remote branch.** That is the documented meaning
  of the flag, and it is now an informed decision: the block above it names the
  origin-only commits, and the recovery SHA is printed. Leasing it would make "abandon"
  fail in exactly the case where the operator asked to abandon.
- **`cmd_new` only warns when `push -u` fails.** If `origin/wt/<slug>` survives from an
  earlier life of the same slug, the push is rejected (nothing is overwritten) and the
  worktree is left with a branch that is not tracking. No data loss, but a latent trap:
  `new` never asks `remote_branch_exists(repo, branch)` even though it does check the
  local branch. Worth a separate ticket; changing `new` was outside this task.
- **`cmd_status` fetches.** It is documented as read-only and it is, for the repo
  content — but it does hit the network and it does move remote-tracking refs, which is
  what armed both lease holes. Harmless now; noted because "read-only" is doing some
  work in that docstring.
- **`land` deletes the remote branch even if `git branch -d` failed.** After the new
  preflight the merge guarantees `-d` succeeds, so this is unreachable in practice.
- **`git reset` in `cmd_commit`** (index-only, after a refused commit) and
  **`worktree remove --force` in `drop`** — both keep or are gated on the dirty-file
  guard; not this class of bug.
- **`push origin <base>` in `land`** is a plain push: if the base moved it is rejected
  and retried by hand. No force anywhere near the base branch.

## Tests

`.claude/scripts/tests/test_wt.py`: 15 → 20. The five new ones all fail against the
pre-fix script (verified by running them against `git show HEAD:.claude/scripts/wt.py`)
and pass after:

- `test_sync_refuses_to_overwrite_a_second_writers_push` — no fetch in between (layer 1).
- `test_sync_refuses_after_status_already_fetched_their_commit` — `status` fetched first
  (layer 2; the one a pinned lease alone would not catch).
- `test_land_blocked_when_branch_is_behind_its_own_remote` — the missing preflight.
- `test_commit_does_not_force_over_a_second_writers_push` — the fallback push.
- `test_drop_refuses_to_delete_a_branch_whose_commits_live_only_on_origin` — the guard
  that never looked at origin.

Every one of them asserts, after the refusal, that `git ls-remote origin wt/demo` still
points at the second writer's commit: the point is not the exit code, it is that their
work is still there.

Run: `PYTHONUTF8=1 python -m pytest .claude/scripts/tests/test_wt.py -v` from the
worktree root (~75 s; each test builds real repos).
