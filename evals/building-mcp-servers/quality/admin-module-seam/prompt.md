---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Use the building-mcp-servers skill. I run a remote MCP gateway in Python. I am
its only operator. Today I change users' plans, set per-user limit overrides and
suspend accounts by hand-written SQL in the database console, and nothing
records who changed what.

Design the admin tooling. Say which surfaces to build now, how admin code
relates to the serving gateway, and how each change is recorded. Keep it short.
