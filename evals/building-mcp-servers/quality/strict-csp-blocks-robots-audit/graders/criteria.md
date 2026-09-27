---
type: llm
weight: 1
---

Pass if the response's CSP starts from `default-src 'none'`, allows `style-src`,
`font-src` and `img-src` as `'self'`, and also allows `connect-src 'self'`,
explaining that Lighthouse fetches `/robots.txt` from inside the page for its
SEO audit, which `default-src 'none'` would block.

Fail if the CSP omits `connect-src` (or an equivalent same-origin fetch
allowance), adds `'unsafe-inline'`, or loosens `default-src` to get the score.
