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

## Pages that render caller output

A page that renders caller-sized output, such as Markdown to HTML, runs on the
request path of the process that serves MCP traffic. Parse time and page
weight grow with the output. Cap the input the page renders, say on the page
that it was cut, and keep the full text available unrendered. Render off the
event loop so a long output cannot stall tool calls.

A size comparison must not count the cap as a saving: compare the full size,
or show no figure.

## Done

Lighthouse scores 95 or more in every category, and the page headers still
carry no `'unsafe-inline'`.

An output over the cap renders a cut notice, and the full text is still on the
page.
