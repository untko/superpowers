---
title: Self-Improving Skills — Record, Propose, Test, Release
date: 2026-09-26
status: approved
---

# Self-Improving Skills — Record, Propose, Test, Release

Evidence base: [docs/research/2026-09-26-self-improving-skills.md](../../research/2026-09-26-self-improving-skills.md).
Supersedes the capture half of [2026-08-03-skill-evolution-capture-and-routing-design.md](2026-08-03-skill-evolution-capture-and-routing-design.md).

## Problem Statement

I want every skill I use, global or repo-specific, to get better from real use, the way my vault's skills already do. Today the global library has the design (observation contract, `evolving-skills`, frozen anchors) but no working loop:

- Nothing records friction. The Stop-hook reviewer is wired into no CLI, because every CLI loads the library as symlinked skills rather than as a plugin, and its config is `dry_run: true`.
- Where it would run, it asks a small model to judge its own session and write an observation. The research shows self-judged skill edits give no average benefit and drift over iterations.
- Nothing tests a skill change. The vault has canaries for its own skills; the global skills have no cases, so a change cannot be checked against the failure that motivated it.

## Solution

A four-stage loop that covers every skill without per-skill setup:

1. **Record.** Every session, a deterministic hook appends friction events to the project's log, tagged with the skills loaded at the time. No model call.
2. **Propose.** On a batch run I start, `evolving-skills` reads the log and proposes itemized edits (add, change, or remove one rule). Each proposal is scoped: **local** (a skill or adapter in this repo) or **global** (the canonical library). A proposal needs outside evidence.
3. **Test.** A release gate checks the proposal's shape and evidence, then runs only as much evaluation as the edit warrants, on whatever CLI and model I pick for that run.
4. **Release.** I approve; the edit lands as one commit in the owning repo carrying the gate report, together with the case for the failure that motivated it. Global edits propagate through `link-skills.sh`. A bad edit is one `git revert`.

## User Stories

1. As a skill user, I want friction from every session recorded without a model call, so that capture is free and never judges its own work.
2. As a skill user, I want each friction event attributed to the skills loaded in that session, so that the proposer knows which skill to look at.
3. As a skill user, I want capture to degrade silently on a missing or malformed payload, so that a hook bug never blocks or slows a session.
4. As a skill owner, I want each proposal scoped local or global and routed to the repo that owns the skill, so that a repo-specific fix never leaks into the library and a general fix is not trapped in one repo.
5. As a skill owner, I want the proposer to emit itemized edits only, never a whole-file rewrite, so that a skill cannot collapse in one step.
6. As a skill owner, I want a proposal rejected unless it cites a user correction, a failing case, or the same friction in at least two sessions, so that edits rest on evidence outside the proposer.
7. As a skill owner, I want testing proportional to the edit, so that a one-line wording or reference change costs a static check, not a batch of eval runs.
8. As a skill owner, I want to choose the CLI and model for each eval run, and have that choice recorded in the report, so that I can run on whatever is available and still compare results later.
9. As a skill owner, I want the proposer unable to read or write the eval cases, so that it cannot game the gate.
10. As a skill owner, I want edits that weaken a frozen anchor or push `SKILL.md` over its word budget rejected, so that safety rules and context cost hold.
11. As a skill owner, I want every released fix to add the case for the failure it fixes, in the owning repo, so that the eval set grows from real failures.
12. As a skill owner, I want each approved edit to land as one commit with the gate report in its message, so that I can audit and revert each edit alone.

## Acceptance Criteria

Recorder (seam A):

1. Given a Claude Code `PostToolUseFailure` payload, when the recorder runs, then it appends one event to `<project>/.superpowers/friction.jsonl` with kind `tool-failure`, timestamp, harness, session id, loaded skill names, and an excerpt of at most 500 characters.
2. Given a `UserPromptSubmit` payload whose prompt matches the correction pattern, when the recorder runs, then it appends one event with kind `correction`; given one that does not match, then it appends nothing.
3. Given a transcript in which the `Skill` tool loaded `tdd` and a repo-local `SKILL.md` for `check-inbox` was read, when any event is recorded, then its skill list is exactly `tdd, check-inbox`, each tagged with its source (global library or repo).
4. Given a missing transcript, malformed JSON, or an unwritable log, when the recorder runs, then it exits 0 within 1 second and writes nothing to stdout.
5. Given any payload, when the recorder runs, then no model process is started.
6. Given the recorder has run on the same `Stop` payload twice, when the log is read, then the session's events appear once.

Release gate (seam B):

7. Given a proposal without a scope, or scoped `global` for a repo-local skill (or `local` for a library skill), when the gate runs, then it rejects with reason `scope`.
8. Given a proposal that replaces a `SKILL.md` wholesale instead of listing itemized operations, when the gate runs, then it rejects with reason `not-itemized` before any eval runs.
9. Given a proposal citing only one session and no correction or failing case, when the gate runs, then it rejects with reason `insufficient-evidence`.
10. Given a proposal that deletes or rewords a frozen-anchor line, or makes `SKILL.md` exceed its word budget, when the gate runs, then it rejects with reason `anchor` or `budget`.
11. Given a valid proposal that changes only `references/` or `scripts/`, or rewords `SKILL.md` without adding, removing, or changing a rule, when the gate runs, then it runs static checks only (links resolve, scripts' own tests pass, budget, anchors) and no model call.
12. Given a valid proposal that adds, removes, or changes a rule, when the gate runs with a CLI and model I name, then it runs each of that skill's cases once, with and without the edit, and reports both scores, the delta, the CLI, and the model.
13. Given a rule-change proposal and no CLI or model named, when the gate runs, then it stops after static checks and reports `eval-skipped: no runner chosen` instead of passing.
14. Given a rule-change proposal whose with-edit score is below the without-edit score on any existing case, when the gate runs, then it reports `regression` and names the case.
15. Given an approved, passing proposal, when it is released, then exactly one commit is created in the owning repo, touching only that skill's directory and its eval cases; the commit adds a case for the motivating failure and its message contains the gate report. For a global edit, `link-skills.sh` then reports no change to the link layout.
16. Given the proposer's working copy, when it lists or reads the eval directory, then the directory is absent.

## Implementation Decisions

- **Recorder** is a new, stateless, deterministic module. It takes a normalized payload and appends one JSON line per event to the friction log in the active project's `.superpowers/` runtime directory. It replaces `skill_review.py`'s reviewer path; the transcript-window reading and correction regex move into it.
- **Retire the reviewer everywhere:** remove the `claude -p` call, `review-model-map`, `review-config` / `dry_run`, the plugin `hooks.json` `Stop` entry for `skill-review`, and the Cursor `stop` entry. Mark the 2026-08-03 spec superseded.
- **Harness adapters** turn each CLI's hook payload into the normalized payload. v1 ships the Claude Code adapter, registered in `~/.claude/settings.json` hooks for `PostToolUseFailure`, `UserPromptSubmit`, and `Stop`, pointing at the repo script (not the plugin path), so it works with symlinked skills.
- **Skill attribution** reads the transcript for `Skill` tool calls and for reads of any `SKILL.md`, and tags each skill as global (resolves into the canonical library) or local (resolves inside the project).
- **Scope** uses the observation contract's existing `candidate.scope` vocabulary. Local proposals are released in the project through its own promotion step (in the vault, `vault-skill-upgrade`); global proposals through `evolving-skills` in the library. The existing rule stands: a global run reads another repo's log only when I start it for that repo.
- **Proposal** is a new artifact in the `superpowers-observation` family: target skill, scope, a list of operations (`add` / `change` / `remove`, each naming one rule line), and evidence references (log event ids, correction ids, or failing case ids). The observation schema itself is unchanged.
- **Proposer** is the `evolving-skills` batch run, started by me. It reads the log and pending observations and writes proposals. It runs in a working copy with the eval directory removed.
- **Release gate** is a new deterministic script. It validates scope, shape, evidence, anchors, and budget itself, classifies the edit (static vs rule change), and runs evals only for rule changes, one run per case. The CLI and model are arguments I pass per run; there is no pinned default.
- **Eval runner** is an interface the gate calls with (skill, cases, CLI, model). v1 implements it with `claude plugin eval` (runs per case set to 1, ablation for the without-edit arm, `--model` from my argument). Other CLIs get their own runner later without changing the gate.
- **Eval cases** live in the repo that owns the skill: global skills in the library repo's `/evals/<skill>/` (un-ignored in `.gitignore`), repo skills in that repo (the vault keeps its `skill_canaries`). Triggering cases (should / should-not load) are separate from output-quality cases.
- **Frozen anchors** are declared per skill in frontmatter, so the gate can check them without parsing prose.
- **Release** is a script step after my approval: apply operations, add the motivating case, commit with the gate report, and for global edits run `link-skills.sh`.

## Testing Decisions

- **Seam A — recorder**, called with fixture payloads and transcripts; checks criteria 1–6. Prior art: `tests/hooks/test_skill_review.py` already drives `process_event` with payload fixtures and an injected runner.
- **Seam B — release gate**, called with fixture proposals against a fixture skill and a stub eval runner for criteria 7–14 and 16; criterion 15 runs against a disposable git repo. One real `claude plugin eval` run on a single case checks that the v1 runner's report maps onto the gate report. Prior art: the vault's `skill_canaries` fixture preparer and grader, and `skills/evolving-skills/tests/`.
- The proposer is an agent and is exercised only through the proposals it produces at seam B.

## Out of Scope

- Hook adapters for Codex, Cursor, Gemini, and OpenCode, and eval runners for CLIs other than Claude Code (v1 is Claude Code only; both seams are adapter-shaped for later).
- Autonomous release: every edit needs my approval.
- Repeated runs per case, pass^k reliability scoring, and automated description search (skill-creator's `run_loop`).
- Seeding eval cases from the vault's archived observations: they concern vault skills and are not tests.
- Changes to the vault's `vault-skill-upgrade`, canaries, or observation store beyond what the local scope needs to consume proposals.
- Model fine-tuning or weight updates.

## Open Questions

None.

## Further Notes

- Anthropic's evals guidance favours cases drawn from real failures; story 11 builds the set that way, one case per released fix.
- Without a pinned model, deltas are comparable only within one gate run (with vs without, same model). Cross-run comparisons read the model from each commit's gate report.
- The research file marks three points unverified: `/skill-doctor` details, Codex eval tooling, and any source-backed batching threshold.
