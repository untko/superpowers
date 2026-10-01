---
name: visual-design
description: "Create diagram artifacts: architecture diagrams (HTML/SVG), hand-drawn Excalidraw diagrams, Mermaid diagrams, and tldraw canvases. Frontend UI and page design belongs to the impeccable skill."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [diagrams, visualization, SVG, Excalidraw, Mermaid, architecture, creative]
    related_skills: []
---

# Visual Design Artifacts

Create diagrams in these formats. Pick the section that matches your task. For landing pages, app UI, or other frontend design, use the `impeccable` skill instead.

| Output | Use When | Section |
|--------|----------|---------|
| Dark-themed HTML/SVG architecture diagram | System architecture, cloud infra, microservice maps | → [Architecture Diagrams](#1-architecture-diagrams) |
| Hand-drawn Excalidraw JSON diagram | Whiteboard-style sketches, flowcharts, quick architecture | → [Excalidraw Diagrams](#2-excalidraw-diagrams) |
| Mermaid diagram (SVG/PNG/ASCII) via agentic-mermaid | Flowcharts, sequence diagrams, state machines, Gantt, mindmaps, architecture-beta | → Read [Mermaid Graph](mermaid-graph/SKILL.md) |
| tldraw `.tldr` canvas, written or read back | The request names tldraw, a `.tldr` file, a canvas or whiteboard, or asks to read, cluster, or organize an existing canvas | → Read [tldraw](tldraw/SKILL.md) |

For a one-off hand-drawn sketch with no canvas to read back, default to
Excalidraw; tldraw is for `.tldr` files and for round-tripping a canvas the
user keeps editing.

If a more specialized skill exists for the subject (e.g., a specific diagram type), prefer that. These are general-purpose visual design fallbacks.

---

## 1. Architecture Diagrams

Generate professional, dark-themed technical architecture diagrams as standalone HTML files with inline SVG graphics. No external tools, no API keys — just write the HTML file and open it in a browser.

**Best suited for:** software system architecture, cloud infrastructure, microservice topology, database + API maps, deployment diagrams.

### Workflow
1. User describes their system architecture (components, connections, technologies)
2. Generate the HTML file following the design system below
3. Save with `write_file` to a `.html` file
4. User opens in any browser — works offline, no dependencies

### Color Palette (Semantic Mapping)

| Component Type | Fill (rgba) | Stroke (Hex) |
| :--- | :--- | :--- |
| **Frontend** | `rgba(8, 51, 68, 0.4)` | `#22d3ee` (cyan-400) |
| **Backend** | `rgba(6, 78, 59, 0.4)` | `#34d399` (emerald-400) |
| **Database** | `rgba(76, 29, 149, 0.4)` | `#a78bfa` (violet-400) |
| **AWS/Cloud** | `rgba(120, 53, 15, 0.3)` | `#fbbf24` (amber-400) |
| **Security** | `rgba(136, 19, 55, 0.4)` | `#fb7185` (rose-400) |
| **Message Bus** | `rgba(251, 146, 60, 0.3)` | `#fb923c` (orange-400) |
| **External** | `rgba(30, 41, 59, 0.5)` | `#94a3b8` (slate-400) |

### Typography & Background
- **Font:** JetBrains Mono (Monospace), loaded from Google Fonts
- **Sizes:** 12px (Names), 9px (Sublabels), 8px (Annotations), 7px (Tiny labels)
- **Background:** Slate-950 (`#020617`) with a subtle 40px grid pattern

### Connection Rules
- **Z-Order:** Draw arrows *early* in the SVG so they render behind component boxes
- **Security Flows:** Use dashed lines in rose color (`#fb7185`)
- **Boundaries:** Security Groups: dashed (`4,4`), rose; Regions: large dashed (`8,4`), amber, `rx="12"`

### Spacing
- Standard Height: 60px (Services); 80-120px (Large components)
- Vertical Gap: Minimum 40px between components
- Message Buses: placed *in the gap* between services, not overlapping them
- Legend: placed outside all boundary boxes, at least 20px below the lowest boundary

### Document Structure
1. **Header:** Title with pulsing dot indicator and subtitle
2. **Main SVG:** Diagram in a rounded border card
3. **Summary Cards:** Grid of three cards below the diagram
4. **Footer:** Minimal metadata

### Output Requirements
- Single self-contained `.html` file, all CSS/SVG inline (except Google Fonts)
- No JavaScript — pure CSS for animations
- Must render correctly in any modern browser

Full HTML template: `references/architecture-template.html`

---

## 2. Excalidraw Diagrams

Create diagrams by writing standard Excalidraw element JSON and saving as `.excalidraw` files. Drag-and-drop onto [excalidraw.com](https://excalidraw.com) for viewing and editing.

**Best suited for:** whiteboard-style sketches, flowcharts, sequence diagrams, concept maps, quick architecture overviews.

### Workflow
1. Write the elements JSON — an array of Excalidraw element objects
2. Save with `write_file` to create a `.excalidraw` file
3. Optionally upload for a shareable link using `scripts/upload.py`

### File Format
```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "hermes-agent",
  "elements": [ ... ],
  "appState": { "viewBackgroundColor": "#ffffff" }
}
```

### Element Types
- **Rectangle:** `{ "type": "rectangle", "id": "r1", "x": 100, "y": 100, "width": 200, "height": 100 }`
- **Ellipse:** `{ "type": "ellipse", "id": "e1", "x": 100, "y": 100, "width": 150, "height": 150 }`
- **Diamond:** `{ "type": "diamond", "id": "d1", "x": 100, "y": 100, "width": 150, "height": 150 }`
- **Arrow:** `{ "type": "arrow", "id": "a1", "x": 300, "y": 150, "width": 200, "height": 0, "points": [[0,0],[200,0]], "endArrowhead": "arrow" }`
- **Standalone text:** `{ "type": "text", "id": "t1", "x": 150, "y": 138, "text": "Hello", "fontSize": 20, "fontFamily": 1 }`

### Labeled Shapes (Container Binding)
Do NOT use `"label": { "text": "..." }` on shapes — it's silently ignored. Use container binding:
```json
{ "type": "rectangle", "id": "r1", "x": 100, "y": 100, "width": 200, "height": 80,
  "roundness": { "type": 3 }, "backgroundColor": "#a5d8ff",
  "boundElements": [{ "id": "t_r1", "type": "text" }] },
{ "type": "text", "id": "t_r1", "x": 105, "y": 110, "width": 190, "height": 25,
  "text": "Hello", "fontSize": 20, "fontFamily": 1,
  "containerId": "r1", "originalText": "Hello", "autoResize": true }
```

### Color Palette

| Use | Fill Color |
|-----|-----------|
| Primary / Input | `#a5d8ff` (light blue) |
| Success / Output | `#b2f2bb` (light green) |
| Warning / External | `#ffd8a8` (light orange) |
| Processing / Special | `#d0bfff` (light purple) |
| Error / Critical | `#ffc9c9` (light red) |
| Notes / Decisions | `#fff3bf` (light yellow) |
| Storage / Data | `#c3fae8` (light teal) |

### Sizing
- Minimum fontSize: 16 for body text, 20 for titles, 14 for secondary annotations
- Minimum shape size: 120x60 for labeled rectangles
- Leave 20-30px gaps between elements

### Drawing Order
Array order = z-order (first = back, last = front). Emit: background zones → shape → its bound text → its arrows → next shape.

### References
- `references/excalidraw-colors.md` — full color tables
- `references/excalidraw-dark-mode.md` — dark mode diagrams
- `references/excalidraw-examples.md` — larger examples

---

## 3. Mermaid Diagrams

When the request involves creating, rendering, validating, or editing a Mermaid
diagram, read and follow the nested [Mermaid Graph](mermaid-graph/SKILL.md)
skill. It is the authoritative Mermaid workflow for this visual-design family.

---

## 4. tldraw Canvases

When the request involves a tldraw `.tldr` file, a canvas or whiteboard, or
reading and organizing an existing canvas, read and follow the nested
[tldraw](tldraw/SKILL.md) skill.
