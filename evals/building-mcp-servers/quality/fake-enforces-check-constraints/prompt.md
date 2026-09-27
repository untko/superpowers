---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Use the building-mcp-servers skill. My MCP gateway's tests run against a fake
of the database REST API. The fake rejects any column the migrations do not
create, so a query the real schema refuses fails in tests too.

I just added an admin action: it calls a database function to change a user's
plan, then inserts an audit row with `result = 'success'`. All tests pass.
What could still go wrong in production, and what should I change before I
ship? Keep it short.
