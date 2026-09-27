---
type: llm
weight: 1
---

Pass if the response does both:

- says the fake must also enforce the schema's CHECK constraints (allowed
  value sets such as the audit `result` column), not only column names, so a
  value the real database refuses fails in tests;
- points out that the change commits before the audit insert, so a refused
  audit insert leaves a change with no audit row, and proposes a remedy such
  as one transaction or a database-side change log that records the change
  regardless.

Fail if it only suggests more unit tests or mocks without naming CHECK
constraints, or misses that the change can land without its audit row.
