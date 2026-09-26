---
name: evolving-skills
description: Use when evolving skills, turning recorded friction into a skill-edit proposal, or maintaining the skill library
metadata:
  frozen:
    failing-test: "No skill without a failing test."
    path-boundaries: "Never violate path boundaries."
  word-budget: 450
---

# Evolving Skills

Propose skill edits from real friction. `$SKILL_DIR` is this skill's directory;
`$PROJECT` is the project root you were started in. `W` is the work directory
`prepare` prints. Every step is one command or one decision, and ends when the
next line prints. You never write a proposal by hand and never edit a skill
outside `W/workspace/`.

No skill without a failing test.
Never violate path boundaries.

## 1. Stage the run

```sh
python3 "$SKILL_DIR/scripts/propose.py" prepare --project "$PROJECT"
```

Read `W/brief.md`: one section per candidate, its scope, its correction, session
and event counts, and one bullet per friction excerpt. Stage another repository
only when your human partner named that repository on the command line.

When your human partner names a skill to change, add `--skill <name>` (and
`--scope local` for a project skill). With no friction behind it, write a
failing case first and cite it: `collect ... --case <id>`.

## 2. Judge each candidate

For each name `prepare` printed, in that order. Friction is tagged with every
skill loaded when it happened, so most candidates are innocent.

Not this skill's fault:

```sh
python3 "$SKILL_DIR/scripts/propose.py" dismiss "$W" <skill> --project "$PROJECT"
```

It stops when the file is gone from `W/proposals/`.

This skill's fault: make the smallest edit in `W/workspace/<skill>/` that would
have prevented this friction. Prefer `references/` over `SKILL.md`. Strip
project names, paths and secrets. Done when the edited file says the new rule
in one line.

## 3. Collect and gate

```sh
python3 "$SKILL_DIR/scripts/propose.py" collect "$W" <skill> --project "$PROJECT"
```

Add `--wording` when a `SKILL.md` line is reworded without changing a rule. It
stops when the JSON report prints. Read `reason` and `detail`, fix
`W/workspace/<skill>/`, collect again. Repeat until the report says `passed`, or
until it says `eval-skipped` for a rule change — then ask your human partner for
a `--cli` and `--model`, and collect again with them. `references/proposer.md`
maps every rejection reason to the edit it needs.

## 4. Ask

Show each passing proposal: its `operations` and its report. Release is never
yours. Release: after approval, apply with the release step (see references).
