---
title: Proposer Reference
---

# Proposer reference

`scripts/propose.py` does every deterministic step of a batch run. You judge and
edit text; the script reads the log, stages the skills, turns your edit into line
operations, and runs the gate.

## The work directory

`prepare --project P [--out W] [--limit N]` writes `W` (default
`P/.superpowers/proposer`, default limit 3) and prints its path:

```
W/brief.md              what to read first
W/workspace/<skill>/    your copy of the skill; edit only here
W/proposals/<skill>.json   the skeleton you fill in through collect
```

It replaces `W` only when `W/.proposer` is there, so it never deletes a directory
it did not create. There is no `evals` directory anywhere under `W`: you never
read the cases, so you cannot write to the gate's tests. The script reads only
`P/.superpowers/friction.jsonl`, and skips ids in `P/.superpowers/friction-handled.txt`.

A skill is a candidate when its friction holds a correction, or the same friction
in two sessions. Ranked by corrections, then sessions, then the most recently
loaded skill, then name.

## A named skill

`prepare --project P --skill S [--scope local]` stages only `S`, whether or not
it has friction, and marks it in the brief as named by your human partner. Its
skeleton keeps any friction `S` has; with none, the evidence is empty and the
gate refuses it until you cite a case.

The case comes first: a directory under `evals/<skill>/` holding the prompt that
fails without the edit. The gate scores it on both arms and accepts it only if
it scores below 1.0 without the edit and higher with it. Your human partner approves it at release with the
edit. Cite it with `collect W S --case <id>`; it is recorded once, however many
times you collect.

## collect

`collect W <skill> [--wording] [--project P] [--cli claude --model M]` diffs
`W/workspace/<skill>/` against the skill it was copied from, writes the
operations into `W/proposals/<skill>.json`, and prints the gate report.

| Exit | Meaning |
|------|---------|
| 0 | the gate passed |
| 1 | the gate rejected; read `reason` and `detail` |
| 2 | nothing was written: the edit cannot be a proposal, or the command line is wrong |

Exit 2 always says which file, and never leaves a proposal behind. The refusals:

- `make the edited lines unique, or edit fewer lines` — an anchor line appears
  more than once, or the operations do not reproduce your file exactly.
- `the gate cannot name a blank line to change or remove` — keep blank lines
  where they are; change the lines with text.
- `sits between blank lines` — an added line needs a neighbour with text above
  or below it.
- `is deleted; a proposal can only add, change, or remove lines` — empty the
  file's lines instead of removing the file.
- `is not text, and the gate edits lines` — a binary file changed.

## Rejection reasons

The gate reports the first failure, in this order. `references/proposal-format.md`
defines the report and the proposal.

| reason | what to change in the workspace |
|--------|----------------------------------|
| `not-itemized` | the edit cannot be expressed as line operations; see the refusals above |
| `insufficient-evidence` | the cited friction is gone; rerun `prepare` instead |
| `scope` | the skill moved; the skeleton's scope is stale |
| `anchor` | you edited or removed a frozen anchor line; restore it |
| `budget` | `SKILL.md` grew past 450 words; move detail into `references/` |
| `links` | a relative link the operation writes does not resolve; fix the path |
| `eval-skipped` | a rule change or a cited case needs a CLI and model: rerun with `--cli claude --model <model>` |
| `untested` | the skill has no eval case; the release step adds one |
| `script-tests` | your `scripts/` edit breaks the skill's own tests |
| `eval-failed` | the CLI could not score; rerun, it is never a score of zero |
| `regression` | a case scored lower with the edit; revert that part |
| `case-unproven` | a cited case passes without the edit or does not improve with it; make the case harder, or drop the edit if the model does not need it |

## dismiss

`dismiss W <skill> --project P` appends the skeleton's evidence ids to
`P/.superpowers/friction-handled.txt` and removes the proposal and the workspace
copy. Use it when the friction was not this skill's fault, so the next run does
not propose it again.

## The observation archive

`prepare` lists pending observations about each candidate as context in
`W/brief.md`; they are never evidence. Once a run has used them, archive the note
in the project that owns it (`$SKILL_DIR` and `$PROJECT` are the two directories
`SKILL.md` names):

```sh
python3 "$SKILL_DIR/scripts/parse_observations.py" \
  --project-root "$PROJECT" --archive <path/to/pending-note.md>
```

To read the whole pending queue instead, the same script with `--list`; to create
the store where there is none, `--init`.

## Release

Release is a separate step, after your human partner approves each passing
proposal: apply the operations, add the motivating case, commit with the gate
report in the message, and run `link-skills.sh` for a global edit. Ask; never
release on your own.
