---
name: to-spec
description: "Turn the current conversation into a spec and publish it to the project issue tracker: no interview, just synthesis of what you've already discussed."
disable-model-invocation: true
---

This skill synthesizes the current conversation and codebase understanding into a spec. The conversation is the interview; this skill writes it down. There is exactly one checkpoint with the user: the draft review in step 4.

The issue tracker and triage label vocabulary should have been provided to you. If not, tell the user to run `/setup-matt-pocock-skills`.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching.

2. Sketch the seams at which the feature will be tested. Prefer existing seams to new ones. Use the highest seam possible; if a new seam is needed, propose it at the highest point you can. The fewer seams the better; the ideal number is one.

3. Draft the spec using the template below. Every decision in it traces to something said in the conversation or found in the code. Anything the conversation left unsettled goes under **Open Questions**, stated as a question with the options you can see; it never becomes a guessed decision elsewhere in the spec.

4. Show the user the full draft, with the seams called out, and ask for corrections. Revise until they approve. Done when the user has approved this exact text.

5. Publish the approved spec to the project issue tracker with the `enhancement` category role and a state role set by its Open Questions section:
   - empty: `ready-for-agent`
   - non-empty: `needs-info`, and tell the user which questions block it

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A numbered list with one story per distinct behaviour, in the format:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

Cover every behaviour the feature adds or changes, including edge and failure cases. A story earns its place only if it adds an acceptance criterion no other story implies; merge any that don't.

## Acceptance Criteria

A numbered checklist of observable outcomes, each checkable at the seam from step 2. Phrase each as "Given <state>, when <action>, then <observable result>". Together they define done: an implementer who satisfies every criterion has built the feature, and `/to-tickets` slices along them.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified, named in the project's vocabulary
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Name modules and interfaces; leave out file paths and code snippets, which go stale quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo.

## Testing Decisions

- The seam(s) from step 2, and which acceptance criteria each one checks
- Which modules will be tested
- Prior art: similar tests already in the codebase

Tests exercise external behaviour at the seam, not implementation details.

## Out of Scope

What this spec deliberately leaves out.

## Open Questions

Decisions the conversation did not settle, each with the options you can see and what it blocks. Write "None." when everything is settled.

## Further Notes

Any further notes about the feature.

</spec-template>
