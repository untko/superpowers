---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Use the building-mcp-servers skill. My remote MCP server is one Starlette
process: it serves `/mcp` (Streamable HTTP) and a server-rendered `/try` page
where a visitor pastes a link and sees what the tool returns. The tool's
output is Markdown; paid plans allow up to a million characters, and the
backend cuts longer output and reports `truncated` and the untruncated size.

Add two things to the result page: a rendered HTML preview of the Markdown
(I'll use markdown-it-py), and a stat "N% smaller" comparing the fetched
HTML's size with the Markdown's. Show me the route and view code.
