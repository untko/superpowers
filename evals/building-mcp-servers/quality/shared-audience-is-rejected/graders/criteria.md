---
type: llm
weight: 1
---

The response binds the verifier's audience to the MCP server's own resource URL (for example by adding it to `aud` with an access-token hook) and requires an OAuth client id claim. It says that accepting `authenticated` alone would admit tokens issued for other clients or plain sessions. A response that configures the verifier to accept `aud: "authenticated"` fails.
