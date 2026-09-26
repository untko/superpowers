# Client wiring

Config keys change between client releases. Fetch the client's current docs
before writing its config.

## OAuth servers

Add the URL and let the client run its own flow and refreshes. Never paste a
token from the identity provider into the client.

- Claude Code: `claude mcp add --transport http <name> <url>`. Run the flow
  from the shell with `claude mcp login <name>`.

## Static-bearer servers

A private server that predates OAuth takes a shared bearer token. Keep the
token in a `0600` file outside every repository and reference the file; never
inline the token in a config file.

- opencode: a `remote` server with `"oauth": false` and the header
  `Authorization` set to `Bearer {file:~/path/to/token}`.

## Done

List the tools from the client itself. A config that parses is not a connected
server.
