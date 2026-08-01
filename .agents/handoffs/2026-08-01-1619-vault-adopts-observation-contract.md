---
title: Vault adopts the superpowers observation contract
description: Convert the Obsidian vault's 13 active observation notes to superpowers-observation/v1 and retire the vault's private copy of the observation rules, so one contract serves every project.
status: active
created: 2026-08-01T16:19:27+07:00
updated: 2026-08-01T16:19:27+07:00
author: claude-opus-5
harness: claude-code
---

# Objective

The `superpowers` plugin now owns the observation contract, a generator, and a
tidy command. The Obsidian vault still carries its own private copy of the
rules and its own incompatible note format.

Make the vault use the plugin's contract instead of its own. Success looks
like:

1. The vault's 13 **active** observation notes validate under
   `superpowers-observation/v1`.
2. `vault-skill-upgrade/SKILL.md` no longer defines an observation template or
   lifecycle — it keeps only the rules for promoting an observation into a
   skill change.
3. Anything genuinely vault-specific lives in an adapter file, which the
   protocol already reserves a slot for.

The vault's 14 **archived** notes are deliberately left alone. Archived is a
terminal state; nothing filters or harvests them, so rewriting them costs
effort and buys nothing.

# Current state

## Done — shipped and pushed, needs no further work

Six commits on `main` in `/Users/gugg/Projects/superpowers`, pushed to
`origin` (`untko/superpowers`), range `c194c6d..51684bb`:

| Commit | What it did |
|---|---|
| `e1d76e8` | Validation dispatches on the schema version a note declares |
| `fb7d5bf` | `new_observation.py` — generates notes from derived provenance |
| `13fce8e` | `--tidy` — quarantines unreadable notes |
| `70ccb4f` | `--migrate-legacy` + migrated this repo's one pre-v1 note |
| `acacbc1` | Fix round: 5 review findings, incl. one Critical |
| `f41e4ab` | Docs: bootstrap hook, harvest step, schema-evolution section |

Verified at `51684bb`: 79 Python tests + 22 subtests pass
(`python3 -m pytest skills/evolving-skills/tests/ -q`), plus 7 bash suites
including `tests/hooks/test-session-start.sh`.

## Not done — this handoff's work

The vault at `/Users/gugg/Documents/Obsidian/ObsidianVault-main` still has:

- 13 active notes in `.agents/observations/*.md` in the vault's own format
- 14 archived notes in `.agents/observations/archive/*.md` (leave these)
- `.agents/skills/vault-skill-upgrade/SKILL.md` v0.3.3, still defining its own
  observation template and lifecycle

## The three formats — read this before touching anything

Confusing these is the single most likely way to get this wrong.

**Format A — the vault's format.** 9 keys, measured across all 13 active
files: `type`, `skill`, `skill_version`, `ai_harness`, `ai_model`,
`environment`, `observed`, `session_id` (not in every file), `status`.
Flat, no nesting. Example:

```yaml
---
type: observation
skill: developing
skill_version: unknown
ai_harness: claude-code
ai_model: claude-sonnet-4
environment: worktree
observed: '2026-07-25'
status: candidate
---
```

The body uses three bullets: `**Observed:**`, `**Root Cause:**`, `**Outcome:**`.

**Format B — this repo's old legacy format.** Keys `timestamp`, `skill`,
`phase`, `status`. Exactly one file ever existed and it is already migrated.
`migrate_legacy_note` in `parse_observations.py` converts **B → C**, not
A → C.

**Format C — the current contract, `superpowers-observation/v1`.** Nested,
four blocks. Fully specified in
`skills/evolving-skills/references/local-adapter-protocol.md`.

`migrate_legacy_note` is a *worked example* for the vault converter, not a
drop-in. Its structure is right; its field names are wrong for Format A.

## The mapping gap you must decide about

Format A carries three things Format C has nowhere to put:

| Format A key | Example values in use | Format C home |
|---|---|---|
| `environment` | `darwin`, `linux`, `worktree` | **none** — and it conflates OS with workspace kind |
| `observed` | `'2026-07-25'` | **none** — the date only survives in the filename |
| `session_id` | opaque id | **none** |

Two ways forward. **The recommended one is (1).**

1. **Add them as optional fields.** The contract's additive-only rule permits
   this with no version bump and no migration of existing notes — this is
   exactly the escape hatch it was designed for. Add `runtime.os`,
   `runtime.workspace`, `runtime.session-id`, and `observation.observed` as
   optional strings. Note this also splits the `environment` conflation:
   `darwin`/`linux` are `runtime.os`; `worktree` is `runtime.workspace`.
2. **Drop them into the note body as prose.** Cheaper, but the data stops
   being filterable, which is the reason the schema exists.

If you choose (1), the concrete change is in
`skills/evolving-skills/scripts/adapter_protocol.py`: add an
`_OPTIONAL_STRING_FIELDS` tuple next to the existing `_OPTIONAL_BOOL_FIELDS`
(around line 322), and validate it inside `_validate_observation_v1` with the
same shape as the existing optional-bool loop — present-and-wrong-type is an
error, absent is fine. Then document them in `local-adapter-protocol.md`
under "Schema evolution".

# Next action

Read the contract and one real note side by side, before writing any code:

```bash
sed -n '/## Observation contract/,/## Failure handling/p' \
  /Users/gugg/Projects/superpowers/skills/evolving-skills/references/local-adapter-protocol.md

cat /Users/gugg/Documents/Obsidian/ObsidianVault-main/.agents/observations/2026-07-25-validate-vault-worktree-anchors.md
```

Then decide the mapping-gap question above and tell the user which option you
picked and why. Everything downstream depends on that answer.

# Remaining work

Do these in order. Each one is independently checkable.

1. **Decide the mapping gap** (see above). If option 1, implement the optional
   fields in `adapter_protocol.py` and document them. Add a test asserting an
   absent optional field is valid and a wrong-typed one is an error.
2. **Install the plugin in the vault**, so the vault gets the contract, the
   generator, and `--tidy` without carrying its own copy.
3. **Write the Format A → Format C converter.** Model it on
   `migrate_legacy_note` (`parse_observations.py`, near the bottom). Field
   mapping:

   | Format A | Format C |
   |---|---|
   | `skill` | `skills.global.name` |
   | `skill_version` | `skills.global.plugin-version` |
   | `ai_harness` | `runtime.harness` |
   | `ai_model` | `runtime.model` |
   | `status` | `candidate.status` |
   | `environment` | `runtime.os` / `runtime.workspace` (see gap) |
   | `observed` | `observation.observed` (see gap) |
   | `session_id` | `runtime.session-id` (see gap) |
   | body `**Observed:**` | split into `observation.expected` + `observation.actual` |
   | body `**Root Cause:**` | `observation.evidence`; pick an enum for `observation.diagnosis` |
   | body `**Outcome:**` | fold into `candidate.status` |

   Rules that are easy to get wrong:
   - `observation.diagnosis` is an **enum**, not prose. Allowed:
     `global-skill`, `adapter`, `model`, `harness`, `tool`, `project`,
     `uncertain`, `unknown`. Prose goes in `evidence` or the body.
   - `candidate.scope` enum: `local`, `potentially-global`, `uncertain`,
     `unknown`. `candidate.target` enum: `skill`, `reference`, `script`,
     `test`, `none`, `unknown`.
   - `skills.global.contract` must be the **integer** `1`, not `"1"`.
   - A value that is *present but empty* (`skill_version: ''`) must become
     `unknown`. A `.get(key, "unknown")` default does **not** catch this —
     that bug was already found and fixed once, see `_legacy_field`.
   - **Never invent** a diagnosis, model, or scope a note did not record. Use
     `unknown`. One vault note has `skill: 'general'` — keep it, do not guess
     a real skill name.
   - Validate before writing. A converter that emits an invalid note and
     exits 0 was a review finding here; do not repeat it.
4. **Convert the 13 active notes only.** Leave `archive/` untouched.
5. **Verify every converted note:**
   ```bash
   for f in <vault>/.superpowers/observations/pending/*.md; do
     python3 <skill-dir>/scripts/adapter_protocol.py validate-observation "$f"
   done
   ```
   Every one must report `"status": "valid"` with an empty `errors` array.
6. **Shrink `vault-skill-upgrade/SKILL.md`.** Remove its "Observation
   Template" section and its lifecycle status list — those now live in the
   plugin. Keep its promotion workflow (present diff → get approval →
   patch-bump version → run `python3 scripts/check.py`). Move anything
   genuinely vault-specific into `.agents/superpowers/evolving-skills/adapter.md`.
7. **Optional, low value:** `__pycache__` directories are untracked in the
   superpowers repo and not in `.gitignore`. Add them if it bothers you.

# Decisions and constraints

- **Observations are per-project; only the contract is global.** They cite
  project paths, commits, and skill versions, so a shared pile would be
  uncitable. Do not move vault notes into the superpowers repo.
- **Archived notes are terminal.** Do not convert, rewrite, or re-review the
  vault's 14 archived notes.
- **Additive-only within a schema version.** Adding an *optional* field needs
  no version bump. Adding, removing, or retyping a *required* field requires a
  new version string in `OBSERVATION_VALIDATORS` plus a registered validator
  for the old version — otherwise every existing note silently fails and
  disappears from `--list`. That exact bug was the Critical finding in this
  session's review.
- **Path-safety guards are frozen anchors.** `_require_local_directory`,
  `_require_pending_source`, `_repository_project_root`, and the symlink
  rejections must not be weakened, bypassed, or reimplemented more loosely.
  Every destination check pairs `exists() or is_symlink()` — `exists()` alone
  follows a dangling symlink and writes outside the store. That was also a
  review finding.
- **Zero third-party dependencies.** Python 3 standard library only. No
  PyYAML. The frontmatter parser is hand-rolled and rejects lists, inline
  mappings, and block scalars — every value must be a single-line scalar.
  This is why a `skill: [a, b]` list field is not implementable.
- **`SKILL.md` files stay under 500 words.** `evolving-skills/SKILL.md` is at
  495 and `using-superpowers/SKILL.md` at 598 (the bootstrap is a long-standing
  exception; do not make it longer). Measure with `wc -w`.
- **`tests/hooks/` and `TestInstalledSkillPortabilityContract` assert on exact
  strings in SKILL.md files**, including across line wraps. Editing skill prose
  can break tests. Run the suite after any doc change.
- **Never hand-write observation frontmatter.** Use `new_observation.py`. The
  vault's 6-of-13 `skill_version: unknown` came from schema drift, not model
  error — generation is the fix for both.
- **This is a fork.** `origin` is `untko/superpowers`; `upstream` is
  `obra/superpowers` with push disabled. Push directly to `origin`; no PRs
  upstream.

# Environment

- Superpowers repo: `/Users/gugg/Projects/superpowers`, branch `main` at
  `51684bb`, clean except `__pycache__`, pushed to `origin/main`
- Vault repo: `/Users/gugg/Documents/Obsidian/ObsidianVault-main` — a
  **separate git repository**; verify its branch and cleanliness before editing
- Central skill store: `~/.agents/skills/`, symlinked into `~/.claude/skills/`
- Platform: darwin. Python 3 available as `python3`; `pytest` available

# References

- `skills/evolving-skills/references/local-adapter-protocol.md` — the contract,
  the schema-evolution rules, and the CLI surfaces. **Read this first.**
- `skills/evolving-skills/scripts/adapter_protocol.py` —
  `classify_observation`, `validate_observation`, `_validate_observation_v1`,
  `OBSERVATION_VALIDATORS`, the enums, and the optional-field pattern
- `skills/evolving-skills/scripts/new_observation.py` — the generator;
  `build_metadata` shows exactly how a valid v1 dict is assembled
- `skills/evolving-skills/scripts/parse_observations.py` —
  `migrate_legacy_note` and `_legacy_field` are the worked example for the
  vault converter; `tidy_observations` shows the four-way classification
- `docs/superpowers/plans/2026-08-01-observation-lifecycle-and-schema-drift.md`
  — the plan this session executed, including its "Out of Scope" section which
  explains why the vault work was deferred to here
- `/Users/gugg/Documents/Obsidian/ObsidianVault-main/.agents/skills/vault-skill-upgrade/SKILL.md`
  — v0.3.3, the material to shrink
- Commit `acacbc1` — the five review findings and their fixes; read it before
  writing a new converter, it lists the mistakes already made once

# Suggested skills

- `superpowers:writing-plans` — the converter plus the schema change is a
  multi-step change; plan it before coding
- `superpowers:test-driven-development` — every fix in this session was found
  by a test written first
- `superpowers:evolving-skills` — owns the contract being adopted
- `superpowers:verification-before-completion` — run the validator over all 13
  converted notes before claiming the migration is done
