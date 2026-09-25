---
title: Skill-Edit Proposal Format and Release Gate
---

# Skill-edit proposals

A proposal is a JSON file naming one skill, its scope, a list of line
operations, and the evidence behind them. `scripts/release_gate.py` checks it
and prints a JSON report; it exits 0 only when the proposal passes.

```json
{
  "schema": "superpowers-proposal/v1",
  "skill": "tdd",
  "scope": "global",
  "operations": [
    {"op": "change", "file": "SKILL.md", "line": "Old rule.", "to": "New rule.", "wording": true},
    {"op": "add", "file": "references/mocking.md", "after": "Existing line.", "to": "New line."},
    {"op": "remove", "file": "SKILL.md", "line": "Obsolete rule."}
  ],
  "evidence": [
    {"type": "correction", "id": "<session>:correction:<prompt id>"},
    {"type": "friction", "id": "<session>:tool-failure:<tool use id>"},
    {"type": "case", "id": "<case id>"}
  ]
}
```

- **scope**: `global` for a skill in the library's `skills/`, `local` for one
  in the project's `.claude/skills/` or `.agents/skills/`. A project link into
  the library is global.
- **operations**: each names one line by its text (whitespace-trimmed, unique
  in the file) and carries single-line text. `add` without `after` appends,
  creating the file if needed. `wording: true` claims a `SKILL.md` change
  rewords without changing a rule; the report lists the claim for review.
- **evidence**: ids from the project's `.superpowers/friction.jsonl`
  attributed to this skill, or case ids under `evals/<skill>/`. It passes with
  one correction, one case, or friction from two sessions.

## Eval cases

A case is a directory under `evals/<skill>/`, named by its own directory, and
it holds a `prompt.md` or a `case.yaml`. The layout is `claude plugin eval`'s:

```
evals/tdd/
  triggering/red-before-green/prompt.md   # should the skill load at all
  triggering/does-not-load-on-tidyup/prompt.md
  quality/one-assertion-per-test/prompt.md
    graders/criteria.md                   # what a passing answer looks like
```

Cases with no `prompt.md` are ignored, and two cases with one name are an
error. Ids are unique across the categories, because the name alone is the id.

## Frozen anchors and word budget

Declare them in the skill's frontmatter:

```yaml
metadata:
  frozen:
    red-first: "Write the failing test before the code."
  word-budget: 800
```

The gate rejects edits that remove or reword an anchor line or change either
declaration. The budget defaults to 500 words; a `SKILL.md` over it may shrink
but not grow. Only the body after the frontmatter counts.

## Gate report

Rejection reasons, in check order: `schema`, `scope`, `not-itemized`,
`insufficient-evidence`, `anchor`, `budget`, `links`, `eval-skipped`,
`untested`, `eval-failed`, `regression`, `script-tests`.
Operations confined to `references/` or `scripts/`, and claimed rewordings,
are `static` and finish after the checks above, without a model. Any other
edit is a `rule-change`: it runs every case of the skill once on the
unedited skill and once on the edited copy, and stops with `eval-skipped`
until you name a CLI and a model. A case that scores lower with the edit is a
`regression`; a skill with no cases is `untested`; a CLI that cannot answer is
`eval-failed`, never a score of zero. A static edit under `scripts/` runs the
skill's own tests on the edited copy, so it executes the proposed code as you:
read it before running the gate.

The report carries the scores in `eval`, so a rejected regression is still
auditable:

```json
{
  "passed": false,
  "kind": "rule-change",
  "reason": "regression",
  "detail": "score fell on: red-before-green",
  "checks": ["scope", "itemized", "evidence", "anchor", "budget", "links"],
  "review": [],
  "eval": {
    "cli": "claude",
    "model": "sonnet",
    "cases": {
      "red-before-green": {"without": 0.5, "with": 0.25, "delta": -0.25}
    }
  }
}
```

```sh
python3 "$SKILL_DIR/scripts/release_gate.py" proposal.json --project . \
  --cli claude --model sonnet
```

`--cli` and `--model` go together; the only CLI is `claude` today.
