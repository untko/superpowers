# Imported skills

Skills copied from other libraries. To sync, diff against the upstream at a
newer version and port changes by hand; local edits win.

## mattpocock/skills v1.2.3 (MIT, Copyright (c) 2026 Matt Pocock)

Source: https://github.com/mattpocock/skills, imported 2026-09-26 from the
Claude plugin cache (`claude-plugins-official/mattpocock-skills/1.2.3`).

- engineering: codebase-design, diagnosing-bugs, domain-modeling,
  grill-with-docs, implement, improve-codebase-architecture, prototype,
  research, resolving-merge-conflicts, setup-matt-pocock-skills, tdd, to-spec,
  to-tickets, triage, wayfinder, wizard
- engineering/code-review, renamed `review-since` so it does not shadow
  Claude Code's built-in `/code-review`
- productivity: grill-me, grilling, teach, to-questionnaire, wait-what,
  writing-for-agents
- misc: git-guardrails-claude-code, migrate-to-shoehorn, scaffold-exercises,
  setup-pre-commit
- in-progress: loop-me, writing-beats, writing-fragments, writing-shape

Local edits since import:

- `implement` and `tdd` point at `review-since`.
- `to-spec`: one checkpoint (draft review, seams included) before publishing;
  Open Questions and Acceptance Criteria sections; one story per distinct
  behaviour; `needs-info` label while questions stay open.
