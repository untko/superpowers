---
type: llm
weight: 1
---

Pass if the response does all of these:

- puts every admin read and write in one admin module or service that any
  adapter (command-line tool now, web page later) must call;
- builds only a command-line tool now and defers a web admin page until there
  is a second admin or a need to administer without shell access;
- keeps the admin module out of the serving gateway and enforces that with an
  automated check, such as an architecture or import-boundary test;
- records changes both in an application audit row naming the acting admin and
  in a database-side change log (for example a trigger) that also catches
  hand-run SQL.

Fail if it builds a web admin page now, lets the serving gateway import the
admin code, or relies only on application-written audit rows.
