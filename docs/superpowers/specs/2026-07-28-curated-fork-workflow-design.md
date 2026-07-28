---
title: Curated Fork Workflow Design
date: 2026-07-28
status: approved
---

# Curated Fork Workflow Design

## Objective

Maintain `untko/superpowers` as an independently installable, customized version
of Superpowers while selectively adopting useful changes from
`obra/superpowers`. The fork must not automatically import every upstream
change, and no contribution back to upstream is expected.

## Repository Ownership

- `origin` is the writable custom fork: `https://github.com/untko/superpowers.git`.
- `upstream` is the read-only source project:
  `https://github.com/obra/superpowers.git`.
- `main` is the stable, installable custom product.
- `upstream/main` is the remote-tracking reference used to inspect the original
  project's current state.

The fork's `main` branch is not required to match `upstream/main`.

## Branch Model

- Develop custom changes on short-lived `skill/<topic>` branches created from
  `main`.
- Evaluate selected upstream changes on short-lived `pick/<topic>` branches
  created from `main`.
- Merge reviewed topic branches into `main`.
- Do not retain `self-updating` as a permanent integration branch after its
  current contents have been promoted to `main`.
- Maintain an `upstream-reviewed` bookkeeping branch that points to the newest
  upstream commit already considered. This branch contains no custom work and
  is never installed.

## Initial Migration

The current `self-updating` branch is a descendant of local and remote `main`;
therefore, it can be promoted to `main` with a fast-forward rather than a
history rewrite.

The migration will:

1. Inventory and preserve the four pre-existing untracked files without adding,
   deleting, or overwriting them.
2. Fast-forward local `main` to `self-updating`.
3. Verify the resulting tree and run relevant repository checks.
4. Push the fast-forwarded `main` to `origin`.
5. Create `upstream-reviewed` at the current `upstream/main` commit and push it
   to `origin`.
6. Keep `self-updating` temporarily as a recovery pointer. Remove it only in a
   separate, explicitly approved cleanup after the migrated `main` is verified.

## Selective Upstream Update Cycle

For each review cycle:

1. Fetch upstream history with pruning.
2. Review non-merge commits and skill diffs between `upstream-reviewed` and
   `upstream/main`.
3. Classify each upstream change as adopt, adapt, or skip.
4. For an isolated compatible change, cherry-pick it with `-x` onto a
   `pick/<topic>` branch.
5. For a coupled or conflicting change, manually port the useful behavior and
   document what was intentionally omitted.
6. Run the tests and behavioral evaluations relevant to the affected skills and
   harness adapters.
7. Merge accepted work into `main` and push it to `origin`.
8. Advance `upstream-reviewed` after the whole upstream range has been reviewed,
   including skipped commits.

Upstream release merges, version bumps, and broad infrastructure changes are
not cherry-picked by default. They are adopted only when their complete effects
are understood and desired.

## Conflict and Failure Handling

- If an upstream commit depends on earlier upstream work, cherry-pick the
  dependency series oldest-first or manually adapt the behavior.
- If a cherry-pick conflicts with a locally customized skill, preserve the local
  product behavior and port the upstream intent deliberately. Do not resolve
  conflicts mechanically.
- If verification fails, abort or revert the topic branch; `main` remains the
  last verified custom release.
- Existing untracked files are outside the migration and must remain untouched.

## Verification

The initial migration is complete when:

- local `main` and `origin/main` point to the promoted custom commit;
- `main` contains all current `self-updating` changes;
- `upstream-reviewed` points to the upstream commit reviewed during migration;
- the four pre-existing untracked files are unchanged;
- relevant repository checks pass; and
- no force-push or upstream write occurred.

Future update cycles are complete when every newly reviewed upstream commit has
an explicit adopt, adapt, or skip outcome and accepted changes pass their
relevant tests before reaching `main`.
