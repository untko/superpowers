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

## danielmiessler/Personal_AI_Infrastructure — Tldraw 1.0.1 (MIT, Copyright (c) 2025-2026 Daniel Miessler)

Source: https://github.com/danielmiessler/Personal_AI_Infrastructure,
`LifeOS/install/skills/Tldraw/` at commit `be9e8ef` (2026-08-14), imported
2026-10-01 to `skills/creative/visual-design/tldraw/` as a nested skill.

`Tools/Tldr.ts` and `References/` are byte-identical to upstream and keep its
directory casing so the tool's `../References/SchemaSnapshot.json` lookup and
future diffs stay trivial. The schema snapshot is pinned to tldraw 5.2.5.

Local edits since import:

- `SKILL.md` rewritten: PAI voice notification, `LIFEOS` customization lookup
  and execution log removed; routing to PAI's `Art`/`Webdesign`/`Remotion`
  removed (routing lives in `visual-design`); tool path resolved from the
  skill's own directory instead of `~/.claude/skills/Tldraw`.
- `Workflows/*.md`: voice notification removed, tool path made relative,
  default output location is the current project.
