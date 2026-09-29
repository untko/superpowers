---
type: llm
weight: 1
---

Pass if the response does all of the following:
- caps how much Markdown the preview renders, tells the visitor on the page
  that the preview was cut, and still offers the full text unrendered;
- runs the Markdown render off the event loop (a thread pool or equivalent),
  saying it would otherwise stall MCP calls served by the same process;
- computes "N% smaller" from the untruncated size when the output was cut, or
  shows no percentage then, so the cut does not count as a saving.

Fail if the preview renders the whole output on the event loop, or if the
percentage uses the cut size of a truncated output.
