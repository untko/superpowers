---
name: mermaid-graph
description: Use when creating, rendering, validating, or safely editing Mermaid diagrams, including flowcharts, architecture maps, sequence diagrams, state diagrams, Gantt charts, ER/class diagrams, and related visual documentation; when Agentic Mermaid MCP, `agentic-mermaid-mcp`, `am`, or `https://agentic-mermaid.dev/mcp` is available.
---

# Agentic Mermaid — diagram workflow

Use Agentic Mermaid as a typed, verification-first surface for Mermaid. Keep the
Mermaid source reviewable, use deterministic rendering, and choose the least
powerful channel that completes the task.

## Choose a channel

- Connected MCP: use `execute` with the `mermaid.*` facade for multi-step work.
- Hosted MCP: use `https://agentic-mermaid.dev/mcp` with `verify`, `describe`,
  `mutate`, `build`, or the appropriate render tool for bounded, one-shot work.
  It is MCP JSON-RPC, not a REST render endpoint, and has a 64 KB input cap.
- Local JavaScript/TypeScript: import from `agentic-mermaid/agent`.
- Shell only: use `am`; run `am capabilities --json` before choosing a family
  or mutation. The self-hosted server is `npx -y agentic-mermaid mcp` and
  requires Node 22 or newer.

Prefer local library, CLI, or self-hosted MCP for sensitive data, offline work,
large inputs, or local PNG files. The hosted service is a public convenience;
do not send confidential source to it.

## Workflow

For a new diagram, author Mermaid source, then parse, verify, and render it.
For an existing modeled diagram:

1. Parse with `parseRegisteredMermaid(source)`.
2. Narrow to the family (`asFlowchart`, `asState`, or the registry-advertised
   equivalent) before mutating.
3. Apply family-specific typed operations with `mutate`.
4. Run `verifyMermaid` and inspect `ok`, `warnings`, and `layout`.
5. Revert the last operation if verification fails; serialize only after the
   inspected verification passes.

For hosted `mutate` and `build`, accept the returned source only when the
top-level `ok`, top-level `family`, and `verify.ok` all pass; inspect
`verify.warnings`. Call `describe_sdk({ family, detail: 'fields' })` when an
operation schema is unfamiliar. Mutation discriminators are `kind`, not
`type`; never invent operation names or reuse another family’s operations.

Do not concatenate or regenerate source to edit an existing structured diagram
when a typed operation exists. Opaque or unmodeled bodies may be verified,
rendered, and round-tripped, but are not eligible for structured mutation.
Preserve the exact source bytes, including the final newline, for file-backed
hosted requests.

## Output

After verification, render the requested projection from the same validated
diagram: SVG or PNG for documents and decks, ASCII or Unicode for terminal
review, and `verify.layout` for positioned-layout consumers. Use style/palette
options such as `['publication-figure', 'github-light']`; use `seed` only to
vary ink or sketch texture, never to alter layout.

Example local edit:

```js
const parsed = mermaid.parseRegisteredMermaid('flowchart TD\n  API --> DB')
if (!parsed.ok) throw new Error('parse failed')
const flow = mermaid.asFlowchart(parsed.value)
if (!flow) throw new Error('not a structured flowchart')
const next = mermaid.mutate(flow, { kind: 'add_node', id: 'Cache', label: 'Cache' })
if (!next.ok) throw new Error(next.error.message)
const check = mermaid.verifyMermaid(next.value)
if (!check.ok) throw new Error(JSON.stringify(check.warnings))
const source = mermaid.serializeMermaid(next.value)
```

For exact hosted MCP request shapes and current capability details, consult the
[Agentic Mermaid MCP documentation](https://agentic-mermaid.dev/docs/mcp/)
before composing a request.
