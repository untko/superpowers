---
title: Observation Format
---

# Observation Format

Observations capture significant reusable friction, a recurring error, or a
plausible skill improvement. They live in the active repository under
`.superpowers/observations/pending/` (active) and
`.superpowers/observations/archived/` (resolved).

The schema identifier is `superpowers-observation/v1`.

## Filename convention

`YYYY-MM-DD-HHMM-<kebab-case-slug>.md`

Example: `2026-08-09-0051-cleanup-deletions-lost-substantive-notes.md`

## Frontmatter

Required fields are marked **(required)**; everything else is optional but
encouraged. Use `unknown` for unavailable provenance; never infer it.

```yaml
---
title: <one-line description>
created: <YYYY-MM-DD-HHMM>
updated: <YYYY-MM-DD-HHMM>            # (required) same as created on write
status: <pending>                     # (required) pending | dismissed | archived | fixed
status-date: <YYYY-MM-DD-HHMM>        # when the status transition happened
model-slug: <model identifier>        # e.g. deepseek-v4-flash-free
thinking-level: <low|medium|high>     # if known
harness: <codex|codex-cli|claude|opencode|unknown>
harness-version: <version>
is-subagent: <true|false|unknown>
is-sandboxed: <true|false|unknown>
git-branch: <branch or worktree name>
git-commit: <commit at observation time, not the fix commit>
---
```

## Status lifecycle

| status | meaning | file location |
|---|---|---|
| `pending` | friction captured, not yet resolved | `observations/pending/` |
| `dismissed` | investigated and declined (record why in Recommendation) | move to `observations/archived/` |
| `archived` | superseded or no longer relevant (record why) | move to `observations/archived/` |
| `fixed` | resolved; the Fix section documents what changed | move to `observations/archived/` |

On any transition, set `status`, `status-date`, and `updated`, then move the
file to `observations/archived/`.

## Body sections

### ## Expected behavior

What should have happened, stated concretely.

### ## Observation

What actually happened, with minimal evidence (command outputs, error text,
repro counts). Add an optional `### Reproduction` subsection with the steps
to re-trigger when the cause is not obvious.

### ## Possible explanation

Best available diagnosis at write time. Distinguish hypothesis from
confirmed cause.

### ## Recommendation

The change that would prevent recurrence: skill text, script behavior,
contract wording, or a process rule. Note the candidate scope
(`local` repository / `global` skill library) and target (skill, script,
contract, tooling).

### ## Fix

Only present once resolved: what changed, in which file, and how it was
verified. Absent while `status: pending`.

### ## Related skills and versions

Skills involved, each pinned by name and version or commit, e.g.
`vault-edit-contract@<commit>`, `knowledge-gardening@6.2.0`.

## Promotion

Raw evidence stays in the active repository. Promotion into a global skill
library happens only during an explicitly authorized global `evolving-skills`
run; ordinary wrap-up neither scans the archive nor edits installed skills.
