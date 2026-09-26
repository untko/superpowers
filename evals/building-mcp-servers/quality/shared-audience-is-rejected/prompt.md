---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

I'm adding OAuth to my remote MCP server. Our identity provider signs every token it issues with `aud: "authenticated"`, including plain web sign-in sessions. Tell me exactly what audience and claims the MCP server's JWT verifier should require so tokens from our provider work.
