---
title: Curated Fork Migration Implementation Plan
date: 2026-07-28
status: approved
design: docs/superpowers/specs/2026-07-28-curated-fork-workflow-design.md
---

# Curated Fork Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the current customized `self-updating` branch to the fork's stable `main` branch and establish a safe cursor for selective upstream reviews.

**Architecture:** Treat `origin/main` as the customized product and `upstream/main` as a read-only source of candidate changes. Disable pushes to the `upstream` remote locally, preserve `self-updating` as a recovery pointer, and track the last reviewed original-project commit with `upstream-reviewed`.

**Tech Stack:** Git, POSIX shell, Python `unittest`, existing repository shell tests

## Global Constraints

- Never push any ref to the `upstream` remote or otherwise write to `obra/superpowers`.
- Never create, update, or submit a pull request against `obra/superpowers`.
- Push only to the `origin` remote at `https://github.com/untko/superpowers.git`.
- Do not force-push any branch.
- Do not delete `self-updating`; keep it as a recovery pointer after migration.
- Do not add, delete, overwrite, or clean the four pre-existing untracked files.
- Commit only the approved design and implementation-plan documents before promoting the branch.
- Stop immediately if a remote URL, ancestry check, staged-file list, or untracked-file checksum differs from the expected value.

---

### Task 1: Install Push Guard and Commit Approved Documentation

**Files:**
- Create: `docs/superpowers/specs/2026-07-28-curated-fork-workflow-design.md`
- Create: `docs/superpowers/plans/2026-07-28-curated-fork-migration.md`
- Preserve: `hooks.json`
- Preserve: `plugin.json`
- Preserve: `skills/evolving-skills/references/observations/archive/2026-07-24-0319-systematic-debugging-failed-during-investigation-for-flaky-test.md`
- Preserve: `skills/evolving-skills/scripts/__pycache__/parse_observations.cpython-313.pyc`

**Interfaces:**
- Consumes: configured `origin` and `upstream` Git remotes, current `self-updating` branch
- Produces: a local `upstream` remote with fetch enabled and push disabled; one documentation commit on `self-updating`

- [ ] **Step 1: Verify the current branch and remote ownership**

Run:

```bash
git status --short --branch
git remote get-url origin
git remote get-url --push origin
git remote get-url upstream
git remote get-url --push upstream
```

Expected:

```text
## self-updating...origin/self-updating
https://github.com/untko/superpowers.git
https://github.com/untko/superpowers.git
https://github.com/obra/superpowers.git
https://github.com/obra/superpowers.git
```

The status output may additionally list the four pre-existing untracked files
and the two approved documentation files. There must be no tracked-file
modifications.

- [ ] **Step 2: Record checksums for the four pre-existing untracked files**

Run:

```bash
shasum hooks.json plugin.json skills/evolving-skills/references/observations/archive/2026-07-24-0319-systematic-debugging-failed-during-investigation-for-flaky-test.md skills/evolving-skills/scripts/__pycache__/parse_observations.cpython-313.pyc
```

Expected checksums:

```text
6a3d1fea189ffcee82831a64300dde189d5daf25  hooks.json
28260dabbdf5f612d9537a2e5c71dc5755ce4b77  plugin.json
846c74a65aa85e27a23c297b080824ec820fd0e4  skills/evolving-skills/references/observations/archive/2026-07-24-0319-systematic-debugging-failed-during-investigation-for-flaky-test.md
84d5d1b167cc267d96040f08012e70dfb7843a5e  skills/evolving-skills/scripts/__pycache__/parse_observations.cpython-313.pyc
```

- [ ] **Step 3: Disable pushes to the original repository**

Run:

```bash
git remote set-url --push upstream DISABLED
git remote get-url upstream
git remote get-url --push upstream
git remote get-url --push origin
```

Expected:

```text
https://github.com/obra/superpowers.git
DISABLED
https://github.com/untko/superpowers.git
```

This changes only local Git configuration. Fetching from `upstream` remains
available, while an accidental `git push upstream` cannot reach GitHub.

- [ ] **Step 4: Stage only the approved documentation**

Run:

```bash
git add -- docs/superpowers/specs/2026-07-28-curated-fork-workflow-design.md docs/superpowers/plans/2026-07-28-curated-fork-migration.md
git diff --cached --name-only
git diff --cached --check
```

Expected staged paths, and no others:

```text
docs/superpowers/plans/2026-07-28-curated-fork-migration.md
docs/superpowers/specs/2026-07-28-curated-fork-workflow-design.md
```

- [ ] **Step 5: Commit the approved documentation locally**

Run:

```bash
git commit -m "docs: define curated fork workflow"
```

Expected: one local commit containing exactly the two documentation files. No
remote operation occurs.

### Task 2: Fast-Forward and Verify the Customized Main Branch

**Files:**
- Modify: Git reference `refs/heads/main`
- Preserve: Git reference `refs/heads/self-updating`
- Test: `skills/evolving-skills/tests/test_parse_observations.py`
- Test: `tests/systematic-debugging/test-find-polluter.sh`
- Test: `tests/hooks/test-session-start.sh`
- Test: `tests/codex/test-marketplace-manifest.sh`

**Interfaces:**
- Consumes: committed `self-updating` tip from Task 1
- Produces: local `main` pointing to the identical verified commit while `self-updating` remains unchanged

- [ ] **Step 1: Prove the migration is a fast-forward**

Run:

```bash
git merge-base --is-ancestor main self-updating
git rev-list --left-right --count main...self-updating
```

Expected: the ancestry command exits `0`, and the count has `0` on the left.
If `main` has unique commits, stop without moving either branch.

- [ ] **Step 2: Fast-forward local `main`**

Run:

```bash
git switch main
git merge --ff-only self-updating
```

Expected: `main` advances without creating a merge commit.

- [ ] **Step 3: Verify both local branches point to the same tree**

Run:

```bash
git rev-parse main
git rev-parse self-updating
git diff --exit-code self-updating..main
```

Expected: both revisions are identical and the diff command exits `0` with no
output.

- [ ] **Step 4: Run focused verification**

Run:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest skills/evolving-skills/tests/test_parse_observations.py
bash tests/systematic-debugging/test-find-polluter.sh
bash tests/hooks/test-session-start.sh
bash tests/codex/test-marketplace-manifest.sh
```

Expected: every test exits `0`. If any test fails, stop before pushing. Keep
both local branch pointers for diagnosis and do not write to either remote.

- [ ] **Step 5: Verify unrelated untracked content remains intact**

Run:

```bash
shasum hooks.json plugin.json skills/evolving-skills/references/observations/archive/2026-07-24-0319-systematic-debugging-failed-during-investigation-for-flaky-test.md skills/evolving-skills/scripts/__pycache__/parse_observations.cpython-313.pyc
git status --short --branch
```

Expected: all four checksums match Task 1, all four files remain untracked, and
no tracked-file modifications exist.

### Task 3: Publish Only to the Fork and Establish the Review Cursor

**Files:**
- Modify: remote reference `origin/main`
- Create: local and remote branch `upstream-reviewed`
- Preserve: remote repository `obra/superpowers` unchanged

**Interfaces:**
- Consumes: verified local `main`, reviewed upstream commit `3dcbd5c4b48e02263fbf4a3c01e3fe4f81d584d9`
- Produces: matching `origin/main` and an `origin/upstream-reviewed` cursor at the reviewed upstream v6.2.0 commit

- [ ] **Step 1: Reconfirm the push boundary immediately before publishing**

Run:

```bash
git remote get-url --push upstream
git remote get-url --push origin
git status --short --branch
```

Expected:

```text
DISABLED
https://github.com/untko/superpowers.git
## main...upstream/main [ahead 10]
```

Untracked paths may follow; there must be no staged or tracked modifications.

- [ ] **Step 2: Push customized `main` only to the fork**

Run:

```bash
git push origin main
```

Expected: `origin/main` fast-forwards. Do not run any command containing
`git push upstream`, `gh pr create`, or a URL under `obra/superpowers`.

- [ ] **Step 3: Create the reviewed-upstream cursor at the already reviewed commit**

Run:

```bash
git merge-base --is-ancestor 3dcbd5c4b48e02263fbf4a3c01e3fe4f81d584d9 upstream/main
git branch upstream-reviewed 3dcbd5c4b48e02263fbf4a3c01e3fe4f81d584d9
git push --set-upstream origin upstream-reviewed
```

Expected: the ancestry command exits `0`; the new branch and its remote-tracking
configuration are created without modifying `upstream/main`.

- [ ] **Step 4: Verify the published refs and safety guard**

Run:

```bash
git fetch origin --prune
git rev-parse main
git rev-parse origin/main
git rev-parse upstream-reviewed
git rev-parse origin/upstream-reviewed
git rev-parse self-updating
git remote get-url upstream
git remote get-url --push upstream
git status --short --branch
```

Expected:

- `main` equals `origin/main`.
- `upstream-reviewed` equals `origin/upstream-reviewed` and
  `3dcbd5c4b48e02263fbf4a3c01e3fe4f81d584d9`.
- `self-updating` still exists at the promoted commit.
- upstream fetch URL remains `https://github.com/obra/superpowers.git`.
- upstream push URL remains `DISABLED`.
- only the four pre-existing untracked files remain.
- no pull request exists or was created by this migration.
