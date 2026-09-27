---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Use the building-mcp-servers skill. My remote MCP server sits behind Caddy. Beside the `/mcp` endpoint I want to
serve three static pages: a landing page, a setup page and a privacy page. They
have no JavaScript and use only self-hosted CSS, fonts and images.

Write the Caddy `header` block for these pages. Start the Content Security
Policy from `default-src 'none'` and allow only what the pages need. Before
release, the pages must score 95 or more in all four Lighthouse categories.
