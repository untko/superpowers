# Operator admin

Admin replaces hand-written SQL in the database console. Hand-run SQL leaves
no record of who changed what, so admin must record every change.

## One module, the adapters you need now

Put every admin read and write in one admin module. Each adapter calls it, and
none has a route or command of its own. The module:

- checks the actor against the table of platform admins on every call;
- writes only through database functions that set the acting admin for the
  transaction;
- appends one audit row per change, with the target and the old and new values;
- writes nothing when the new value equals the old one, and reports that.

Build only the adapter you need. With one operator, that is a command-line tool
on the server that names the acting admin on every run. Defer a web admin page
until there is a second admin or a need to administer without shell access.

Keep the admin module out of the serving gateway. An import-boundary test
enforces it, so the public process carries no admin code.

## Two records of each change

The application writes its audit row after the change commits. If that insert
fails, the change stays with no audit row. A database trigger that writes an
append-only change log records the change in the same transaction, including
hand-run SQL, where the acting admin is empty. In the trigger, record the role
in effect, not the login role: an API layer logs in as one shared role.

A read that reveals sensitive data, such as a user's submitted content, writes
its audit row before the read. If the audit write fails, the read does not run.

## Test fakes enforce CHECK constraints

A fake database that rejects unknown columns still accepts a value the real
schema's CHECK constraint refuses. Copy the allowed value sets from the
migrations into the fake, so a refused value fails in tests, not in production.
