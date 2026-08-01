---
title: Local Adapter and Skill Evolution Protocol
---

# Local Adapter and Observation Protocol

Repository-local adapters and observations let a project report useful
evidence to the skill library without granting either side write access to the
other. They are data and proposals, not instructions to mutate a different
repository.

## Storage classes and authority

Each project owns `.agents/superpowers/<skill>/adapter.md` and
`.superpowers/observations/`. The observation store has three ignored classes:
`pending/` for new evidence, `proposed/` for a durable proposal under local
review, and `archived/` for processed evidence. Initialize it with:

```sh
python3 "$SKILL_DIR/scripts/parse_observations.py" \
  --project-root "$PROJECT_ROOT" --init
```

Here `SKILL_DIR` means the directory containing the loaded, installed
`evolving-skills/SKILL.md`; `PROJECT_ROOT` means the active project root.

Local repositories may observe and propose. Only an explicit global evolution
run may generalize an observation, run the global tests, obtain approval, and
release a global change. It must not auto-write the source repository.
Conversely, a global release does not auto-write adapters or observations in
any repository; a project adopts it deliberately and may update its own
adapter. Neither direction is automatic.

## Adapter contract and path safety

The only adapter location is
`.agents/superpowers/<skill-name>/adapter.md`. Its constrained YAML
frontmatter is:

```yaml
---
schema: superpowers-adapter/v1
extends: <skill-name>
contract: 1
adapter-version: 1
---
```

Discover it with `python3 "$SKILL_DIR/scripts/adapter_protocol.py" discover
"$PROJECT_ROOT" <skill-name> --supported-contract 1`. An absent adapter selects
global defaults; invalid frontmatter is an error, not a fallback. Adapter
resources must be relative files within the adapter directory: absolute paths,
`..`, missing files, directories, and symlinks resolving outside it are
rejected.

## Observation contract

Write minimally sanitized, durable evidence in `pending/*.md`. Do not include
secrets, project paths, raw transcripts, or identifying customer data. Validate
before promotion with `python3 "$SKILL_DIR/scripts/adapter_protocol.py"
validate-observation <note>`.

```yaml
---
schema: superpowers-observation/v1
runtime:
  provider: openai
  model: gpt-5.6-sol
  reasoning-effort: high
  harness: codex-app
  harness-version: unknown
  interface: desktop
skills:
  global:
    name: evolving-skills
    contract: 1
    plugin-version: unknown
    git-commit: unknown
    dirty: false
  adapter:
    path: unknown
    version: unknown
    git-commit: unknown
observation:
  phase: verification
  expected: Evidence is recorded without changing global skills.
  actual: A reusable friction pattern required an explicit local note.
  evidence: Sanitized command result and concise symptom.
  diagnosis: uncertain
candidate:
  scope: potentially-global
  target: reference
  status: observed
---
Concise, sanitized body with the relevant context and proposed universal rule.
```

Write notes with `python3 "$SKILL_DIR/scripts/new_observation.py"
--project-root "$PROJECT_ROOT" --skill <name> --phase <phase> --expected <text>
--actual <text> --evidence <text>`, which derives provenance and refuses to
write frontmatter that does not validate. Add `--archive-now` for a note that
needs no follow-up; it still moves through the guarded `pending/` queue.

All listed fields are required except `skills.global.dirty`, which is optional
and reports whether the working tree was dirty at the commit named above — a
commit alone misleads when the tree is not clean. It stays absent when the
state could not be determined. `skills.global.contract` is integer `1`;
`skills.adapter.version` is a positive integer or non-empty string. Use
`unknown` when provenance is unavailable. Allowed enums are:

| Field | Values |
| --- | --- |
| `observation.diagnosis` | `global-skill`, `adapter`, `model`, `harness`, `tool`, `project`, `uncertain`, `unknown` |
| `candidate.scope` | `local`, `potentially-global`, `uncertain`, `unknown` |
| `candidate.target` | `skill`, `reference`, `script`, `test`, `none`, `unknown` |

`candidate.status` is a required non-empty durable lifecycle label. Keep the
proposal fields intact while it moves from `observed` in `pending/`, through
local review in `proposed/`, to `archived/` after an explicit decision. Archive
only a file resolved inside the sibling `pending/`; no move may overwrite an
existing archive entry.

## Schema evolution

A note is validated against the schema version its own `schema:` field
declares, not against the newest one. Validation classifies each note as
`current`, `outdated` (valid under a registered older version),
`unknown-schema` (an unregistered version, almost always a note written by a
newer plugin than this checkout can validate), or `invalid`.

Within a version, **only optional fields may be added**. Adding, removing, or
retyping a required field requires a new version string and a registered
validator for the old one, so existing evidence keeps validating instead of
vanishing from every harvest. `--list` returns `current` and `outdated` notes
alike, tagging each with `schema_status`.

`--tidy` reports four buckets — `kept`, `outdated`, `unknown_schema`, and
`quarantined` — and moves only `invalid` notes, into `quarantine/`. Outdated
and unknown-schema notes stay in `pending/`: both are readable evidence, and
quarantining them would cause the corpus loss this classification exists to
prevent. Quarantine is reversible — repair the note and move it back.

Convert a pre-v1 note with `--migrate-legacy`; provenance the old format never
recorded stays `unknown`, and a note that cannot be converted into a valid
one raises rather than being written.

## Failure handling and adoption

Invalid, unreadable, malformed, or unsafe observations are ignored with a
warning and remain unpromoted. Repair or discard them locally; never infer
missing evidence. A global reviewer may reject an observation as local-only,
uncertain, or insufficiently abstract. When a global release is relevant,
adopt it by explicitly updating the installed global skill and then, if needed,
the repository's adapter; validate and test that local change independently.
