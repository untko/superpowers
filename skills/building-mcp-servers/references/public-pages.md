# Public pages beside the server

Human pages such as a landing page, setup, or privacy often share the host
with the MCP endpoint. Serve them statically from the proxy, with their own
strict headers, so they stay up while the server restarts.

## Content Security Policy

Start at `default-src 'none'` and allow only what the pages load: `style-src`,
`img-src`, `font-src`, each `'self'`. Never add `'unsafe-inline'`; move the
style into a stylesheet.

Add `connect-src 'self'` when you audit the pages with Lighthouse. Its
robots.txt audit fetches `/robots.txt` from inside the page, so
`default-src 'none'` blocks it. The audit then reports "unable to download"
even though the file is served. On pages that allow no script, the directive
grants nothing else.

## Done

Lighthouse scores 95 or more in every category, and the page headers still
carry no `'unsafe-inline'`.
