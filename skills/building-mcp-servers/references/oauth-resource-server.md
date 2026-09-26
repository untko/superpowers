# OAuth resource server

The MCP server is an OAuth resource server. The identity provider is the
authorization server.

- Serve protected-resource metadata at
  `/.well-known/oauth-protected-resource/<mcp path>`. Answer an unauthenticated
  call with 401 and a `WWW-Authenticate` header that points at it.
- Verify the signature against the provider's JWKS, then the issuer, expiry,
  and audience.
- Require the OAuth client id claim. A token without it is a plain sign-in
  session, not a grant to an MCP client.
- Many providers put one shared audience on every token they issue. Add the
  resource URL to `aud` with an access-token hook, only for tokens that carry a
  client id. Configure the verifier with the resource URL, never the shared
  value. A verifier that accepts the shared value accepts tokens meant for
  every other client of that provider.

## Hook gotchas seen in practice

- The RFC 8707 `resource` parameter may be ignored. The hook can be the only
  binding.
- `aud` arrives as a string or an array. Overwrite it; do not append.
- The hook output may replace the claims wholesale. Return every input claim
  with `aud` changed, never a partial object.
- Prove the hook on the hosted provider with one real decoded token before
  cutover. A local run does not prove the hosted one.

## Client registration

The MCP authorization spec deprecates Dynamic Client Registration in favour of
Client ID Metadata Documents. Enable DCR only as a compatibility choice while
clients and the provider still need it.
