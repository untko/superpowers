---
type: llm
weight: 1
---

Before writing or showing any test code, the response names the public interface or seam it intends to test (for example the `slugify` function's input and output) and asks the user to confirm it. A response that starts with test code, or writes tests without asking which seams to test, fails.
