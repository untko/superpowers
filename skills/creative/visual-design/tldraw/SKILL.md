---
name: tldraw
description: Use when reading, creating, or editing tldraw `.tldr` canvas files - sketching a hand-drawn diagram onto a canvas or whiteboard, or reading a rough canvas back as structured data to cluster and organize it.
---

# tldraw canvases

Deterministic read/write for tldraw canvases. The `.tldr` format is plain JSON
(`{tldrawFileFormatVersion: 1, schema, records}`); `Tools/Tldr.ts` writes
records that pass tldraw's own validator, so generated files open in the tldraw
web editor, the VS Code tldraw extension, or the desktop app. Two directions:
model → canvas (sketch a diagram) and canvas → model (read and structure a
human's rough thinking).

## Workflows

| Request | Read |
|---------|------|
| "sketch a diagram", "draw this on a canvas", "put this on the whiteboard" | [Workflows/SketchDiagram.md](Workflows/SketchDiagram.md) |
| "structure my canvas", "organize my whiteboard", "read my canvas", "cluster my sticky notes" | [Workflows/StructureCanvas.md](Workflows/StructureCanvas.md) |

## Tool

`Tools/Tldr.ts` sits beside this file and needs only `bun`. Resolve it from
this file's own directory, not from a CLI-specific skills path:

```bash
T=<directory of this SKILL.md>/Tools/Tldr.ts
bun $T <create|inspect|add|remove|move|settext|validate> <file.tldr> [flags]
```

- Record shapes, spec format, enums, coordinates: [References/TldrFormat.md](References/TldrFormat.md)
- Vendored schema (tldraw 5.2.5): `References/SchemaSnapshot.json`, read by
  `create`. Re-snapshot it per the Maintenance section of `TldrFormat.md` if
  generated files stop opening after a tldraw major release.

## Gotchas

- **zsh `echo` mangles spec JSON.** It expands `\n` inside strings into real
  newlines, breaking the JSON. Write the spec to a file and pass
  `--spec <file>`; `--spec -` reads stdin, but only feed it from something that
  does not reinterpret escapes.
- **Text is `richText`, never a plain string.** Labels are ProseMirror doc
  JSON, and a bare string prop is rejected by tldraw's validator. `Tldr.ts`
  builds it; never hand-write a `text` prop.
- **Raw records need every prop.** Records written to the file bypass editor
  defaulting, so one missing prop (e.g. `growY` on geo, `terminal` on an arrow
  binding) fails validation on load. Always go through `Tldr.ts add`; never
  append hand-rolled records.
- **Fractional index strings order shapes.** `index` values (`a1`, `a2`, …)
  are base62, lexicographic, and never end in `0`. The tool generates them;
  duplicates cause z-order glitches.
- **The desktop app's `.tldraw` format is different.** That native save is a
  zip (sqlite + assets), not this JSON. This skill targets portable `.tldr`
  JSON, which the web editor, VS Code extension, and desktop app all open.
- **Editors hold files in memory.** If the canvas is open while it is edited
  on disk, the editor may not reload, or may overwrite the change on save.
  Edit while it is closed, or tell the user to reopen after the write.
- **`validate` is structural only.** It checks records, bindings, parents and
  colors; it does not render. Report "validated structurally; open it to check
  the layout", never "it looks good".

## Opening a canvas

- **VS Code / Cursor**: the official tldraw extension opens `.tldr` files
  in-editor. Fully local; the right choice for private content.
- **tldraw.com**: File → Open. Content goes to a third-party web app; only for
  content that is already meant to be public.
- **Export to image**: from any tldraw surface, select all → Export as
  SVG/PNG. No headless export ships with this skill.
