---
name: building-mcp-servers
description: Use when building or exposing a remote MCP server, adding OAuth to one, or connecting an MCP client to it
---

# Building MCP Servers

A remote MCP server is a public door to private work. Every step below guards
that door. Each step ends on its completion line.

## 1. Earn the server

Build MCP when many clients, users, or machines need the tool. For one agent on
one machine, a CLI or a skill is cheaper. Done when you can name the second
client.

## 2. Split gateway from backend

The gateway owns identity, policy, limits, audit, and protocol translation. The
backend owns the work. The backend listens privately, trusts only a service
credential, and never sees an end-user token. Done when the backend is
unreachable from outside the host.

## 3. Bind tokens to this resource

Accept only tokens whose audience is this server's resource URL and that carry
an OAuth client id. A token with the provider's shared default audience is
rejected, even when its signature is valid. Details:
[`references/oauth-resource-server.md`](references/oauth-resource-server.md).
Done when a valid plain-session token gets 401.

## 4. Keep URLs and tokens out of logs

Turn off raw access logs. Check the default level of every third-party logger;
HTTP clients log full request URLs at INFO. Log the host and a hash of the URL.
Done when the journal after a real call holds no token, query string, or
output.

## 5. Guard the fetch, not only the gate

Gateway URL checks reject obvious bad input early. The authoritative SSRF check
lives where the fetch happens, after DNS resolution and on every redirect. Done
when the fetch layer blocks a private address reached through a redirect.

## 6. Cap compute where every caller passes

Per-user limits do not bound the sum. Cap active jobs globally and refuse at
once with a retry hint; a queue behind a synchronous call only becomes client
timeouts. If other callers reach the backend directly, the cap lives in the
backend. Done when a saturated call returns the refusal and spends no quota.

## 7. Roll out behind a stub

Bind the server to loopback behind a TLS proxy. Publish a stub that answers
503, point DNS at it, confirm the certificate, then swap in the live site.
Rollback is the stub; removing the site while DNS still points at the host
hands the name to whatever answers by default. Done when rollback is one file
copy.

## 8. Verify with a real client

Connect a real client with a never-seen account: list tools, run one real call,
then send no token and a wrong-audience token and expect 401 twice. Wire
clients with [`references/client-wiring.md`](references/client-wiring.md).

Test with the real client or a disposable test client. A refresh token rotates
on use: exchanging a real client's token outside that client revokes its copy.
