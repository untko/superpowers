---
name: visual-design
description: "Create visual design artifacts: architecture diagrams (HTML/SVG), one-off HTML pages (landing/decks/prototypes), and hand-drawn Excalidraw diagrams. Covers three output formats — pick the right one for your task."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [design, diagrams, visualization, HTML, SVG, Excalidraw, architecture, prototype, creative]
    related_skills: []
---

# Visual Design Artifacts

Create visual output in three formats. Pick the section that matches your task:

| Output | Use When | Section |
|--------|----------|---------|
| Dark-themed HTML/SVG architecture diagram | System architecture, cloud infra, microservice maps | → [Architecture Diagrams](#1-architecture-diagrams) |
| One-off HTML page (landing, deck, prototype) | Polished web artifacts, pitch decks, UI mockups | → [HTML Design](#2-html-design) |
| Hand-drawn Excalidraw JSON diagram | Whiteboard-style sketches, flowcharts, quick architecture | → [Excalidraw Diagrams](#3-excalidraw-diagrams) |
| Mermaid diagram (SVG/PNG/ASCII) via agentic-mermaid | Flowcharts, sequence diagrams, state machines, Gantt, mindmaps, architecture-beta | → Read [Mermaid Graph](mermaid-graph/SKILL.md) |

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

## 2. HTML Design

Design one-off HTML artifacts: landing pages, pitch decks, prototypes. Preserves Claude Design's design taste for CLI/API environments.

**Best suited for:** landing pages, pitch decks, UI prototypes, design artifacts that need to look polished.

### Design Process
1. **Pick a bold, content-informed color palette** — should feel designed for THIS topic
2. **Dominance over equality** — one color dominates (60-70%), 1-2 supporting tones, one sharp accent
3. **Commit to a visual motif** — rounded image frames, icons in colored circles, thick single-side borders
4. **Every slide/page needs a visual element** — image, chart, icon, or shape; text-only is forgettable

### Color Palettes

| Theme | Primary | Secondary | Accent |
|-------|---------|-----------|--------|
| Midnight Executive | `1E2761` | `CADCFC` | `FFFFFF` |
| Forest & Moss | `2C5F2D` | `97BC62` | `F5F5F5` |
| Coral Energy | `F96167` | `F9E795` | `2F3C7E` |
| Warm Terracotta | `B85042` | `E7E8D1` | `A7BEAE` |
| Ocean Gradient | `065A82` | `1C7293` | `21295C` |
| Charcoal Minimal | `36454F` | `F2F2F2` | `212121` |
| Teal Trust | `028090` | `00A896` | `02C39A` |
| Berry & Cream | `6D2E46` | `A26769` | `ECE2D0` |
| Sage Calm | `84B59F` | `69A297` | `50808E` |
| Cherry Bold | `990011` | `FCF6F5` | `2F3C7E` |

### Typography
- Choose an interesting font pairing — don't default to Arial
- Slide titles: 36-44pt bold; Section headers: 20-24pt bold; Body: 14-16pt; Captions: 10-12pt muted

### Common Mistakes to Avoid
- Don't repeat the same layout — vary columns, cards, and callouts
- Don't center body text — left-align paragraphs
- Don't default to blue — pick topic-specific colors
- Don't create text-only slides
- Don't use accent lines under titles (hallmark of AI-generated slides)

### Output
- Single self-contained `.html` file
- Save to user-specified path or `./[name].html`
- Open with `xdg-open` (Linux) or `open` (macOS)

---

## 3. Excalidraw Diagrams

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

## 4. Mermaid Diagrams

When the request involves creating, rendering, validating, or editing a Mermaid
diagram, read and follow the nested [Mermaid Graph](mermaid-graph/SKILL.md)
skill. It is the authoritative Mermaid workflow for this visual-design family.
