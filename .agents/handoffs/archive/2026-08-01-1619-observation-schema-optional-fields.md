---
title: Add optional provenance fields to superpowers-observation/v1
description: Extend the observation schema with four optional fields — OS, workspace kind, session id, and observed date — so notes can record provenance the current contract has no home for, without a version bump or a migration.
status: active
created: 2026-08-01T16:19:27+07:00
updated: 2026-08-01T16:47:00+07:00
author: claude-opus-5
harness: claude-code
---

# Objective

Add four **optional** string fields to `superpowers-observation/v1`:

| Field | Holds | Example |
|---|---|---|
| `runtime.os` | operating system | `darwin`, `linux` |
| `runtime.workspace` | workspace kind | `production`, `worktree`, `sandbox` |
| `runtime.session-id` | harness session identifier | opaque string |
| `observation.observed` | the date the friction occurred | `2026-07-25` |

Because they are optional, the additive-only rule permits this with **no
version bump and no migration** — every existing note stays valid. That is
exactly the escape hatch the rule was designed to provide, and this change is
its first real exercise.

Success: an observation may carry any subset of the four; absent is valid; a
present-but-wrong-typed value is an error; all existing tests still pass.

**Scope: this repository only.** Do not edit the Obsidian vault from this
session. Cross-repository edits require explicit user approval, and the vault
has its own handoff for its own work — see "Why now" below.

# Why now

The current contract has nowhere to put three things that real observations
already record. The Obsidian vault's 13 active notes carry `environment`
(values in use: `darwin`, `linux`, `worktree`), `observed`, and `session_id`,
and a conversion to v1 would have to discard all three or bury them as prose
in the note body — which stops them being filterable, the main reason the
schema exists.

`environment` also conflates two different things. Splitting it into
`runtime.os` and `runtime.workspace` is the fix, and it is why this is four
fields rather than three.

The alternative — putting them in the body as prose — is a legitimate cheaper
option, but it forfeits filtering. This handoff assumes the fields; if the
user chooses prose instead, close this handoff as `finished` and say so.

# Current state

Shipped and pushed on `main`, range `c194c6d..8b24eca`:

| Commit | What it did |
|---|---|
| `e1d76e8` | Validation dispatches on the schema version a note declares |
| `fb7d5bf` | `new_observation.py` — generates notes from derived provenance |
| `13fce8e` | `--tidy` — quarantines unreadable notes |
| `70ccb4f` | `--migrate-legacy` + migrated this repo's one pre-v1 note |
| `acacbc1` | Fix round: five review findings including one Critical |
| `f41e4ab` | Docs: bootstrap hook, harvest step, schema-evolution section |
| `51684bb` | The plan this work executed |
| `8b24eca` | This handoff's first version |

Verified at `51684bb`: 79 Python tests + 22 subtests
(`python3 -m pytest skills/evolving-skills/tests/ -q`), plus 7 bash suites
including `tests/hooks/test-session-start.sh`.

**The pattern to copy already exists.** `skills.global.dirty` is an optional
**boolean**, added by the same rule. Everything below mirrors it for strings.

# Next action

Read the existing optional-field implementation — it is the template:

```bash
grep -n "_OPTIONAL_BOOL_FIELDS" -A 12 \
  /Users/gugg/Projects/superpowers/skills/evolving-skills/scripts/adapter_protocol.py
```

You will see a constant tuple near the other field constants (~line 322) and a
validation loop inside `_validate_observation_v1` placed just before the
`for path, allowed in _ENUMS.items():` loop. Write the string equivalent.

# Remaining work

1. **Write the failing tests first** in
   `skills/evolving-skills/tests/test_adapter_protocol.py`. Cover, for each of
   the four fields: absent is valid; a non-empty string is valid; a wrong type
   (integer or boolean) produces the error
   `"<path> must be a non-empty string"`; an empty string is an error. Mirror
   the existing `test_dirty_flag_*` tests in that file.
2. **Run them and confirm they fail** before writing any implementation:
   `python3 -m pytest skills/evolving-skills/tests/test_adapter_protocol.py -v`
3. **Implement.** Add beside `_OPTIONAL_BOOL_FIELDS`:
   ```python
   _OPTIONAL_STRING_FIELDS = (
       "runtime.os",
       "runtime.workspace",
       "runtime.session-id",
       "observation.observed",
   )
   ```
   and inside `_validate_observation_v1`, immediately before the `_ENUMS`
   loop:
   ```python
   for path in _OPTIONAL_STRING_FIELDS:
       if parent_is_invalid(path):
           continue
       exists, value = _lookup(metadata, path)
       if exists and (not isinstance(value, str) or not value):
           errors.append(f"{path} must be a non-empty string")
   ```
4. **Teach the generator to emit them.** In
   `skills/evolving-skills/scripts/new_observation.py`, add `--os`,
   `--workspace`, and `--session-id` CLI flags and an `--observed` flag, and
   thread them through `build_metadata` the way `dirty` is threaded through
   `provenance`. Follow the existing rule: **omit an unknown optional field
   entirely rather than writing a placeholder.** `dirty` does this
   deliberately — recording an unverified value is worse than recording
   nothing. Derive `os` from `sys.platform` since that is reliable; leave
   `workspace` and `session-id` to explicit flags.
5. **Document them** in
   `skills/evolving-skills/references/local-adapter-protocol.md`: add them to
   the example frontmatter, and extend the sentence that currently reads "All
   listed fields are required except `skills.global.dirty`…" to cover all
   five optional fields. Note in the "Schema evolution" section that this
   addition needed no version bump — it is the rule working as intended.
6. **Verify.** Full suite green, and generate one real note end to end:
   ```bash
   python3 skills/evolving-skills/scripts/new_observation.py \
     --project-root "$PWD" --skill evolving-skills --phase verification \
     --expected e --actual a --evidence v --workspace production
   python3 skills/evolving-skills/scripts/parse_observations.py \
     --project-root "$PWD" --list
   ```
   Confirm `runtime.os` appears, `runtime.workspace` is `production`, and
   `session-id`/`observed` are absent rather than `unknown`. Delete the note
   afterward.
7. **Tell the user when this lands**, because the vault handoff is blocked on
   it. See `References`.

# Decisions and constraints

- **Optional means optional.** Absent must stay valid. If any of these four
  becomes required, every existing note breaks and a version bump plus a
  registered validator for the old version is mandatory — that failure was
  this session's Critical review finding.
- **Omit unknowns; do not write placeholders.** `dirty` is left out entirely
  when `git status` fails, rather than recording a false `false`. Match that.
- **Zero third-party dependencies.** Python 3 standard library only. No
  PyYAML.
- **The frontmatter parser accepts a strict subset.** It rejects lists, inline
  mappings, and block scalars — every value must be a single-line scalar.
- **Path-safety guards are frozen anchors.** `_require_local_directory`,
  `_require_pending_source`, `_repository_project_root`, and the symlink
  rejections must not be weakened. Destination checks pair
  `exists() or is_symlink()`; `exists()` alone follows a dangling symlink and
  writes outside the store.
- **`SKILL.md` files stay under 500 words.** `evolving-skills/SKILL.md` is at
  495; `using-superpowers/SKILL.md` at 598 and must not grow. Measure with
  `wc -w`. This task should not need to touch either.
- **Tests assert on exact strings in SKILL.md files**, including across line
  wraps — see `TestInstalledSkillPortabilityContract` in
  `tests/test_parse_observations.py`. Run the suite after any doc edit.
- **This is a fork.** `origin` is `untko/superpowers`; `upstream` is
  `obra/superpowers` with push disabled. Push to `origin`; no upstream PRs.

# Environment

- Project root: `/Users/gugg/Projects/superpowers`
- Branch `main` at `8b24eca`, clean except untracked `__pycache__`, in sync
  with `origin/main`
- Platform: darwin. `python3` and `pytest` available.

# References

- `skills/evolving-skills/scripts/adapter_protocol.py` — `_OPTIONAL_BOOL_FIELDS`
  and its validation loop are the template to copy
- `skills/evolving-skills/scripts/new_observation.py` — `build_metadata` and
  `_plugin_provenance`; the latter shows the omit-unknowns pattern
- `skills/evolving-skills/references/local-adapter-protocol.md` — the contract
  and its "Schema evolution" section
- `docs/superpowers/plans/2026-08-01-observation-lifecycle-and-schema-drift.md`
  — the plan that built the version seam these fields exercise
- `/Users/gugg/Documents/Obsidian/ObsidianVault-main/.agents/handoffs/` — the
  vault's own handoff, which is **blocked on this work**. It is a separate
  repository; do not edit it from this session.

# Suggested skills

- `superpowers:test-driven-development` — the tests here are small and
  specific; write them first
- `superpowers:evolving-skills` — owns the contract being extended
- `superpowers:verification-before-completion` — generate a real note and read
  it before claiming this works
