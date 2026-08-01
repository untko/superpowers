# Observation Lifecycle and Schema Drift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make repository-local observations survive schema evolution and stay
self-tidying, so an agent can record one mid-session in a single command without
hand-writing frontmatter and without the note silently rotting when the contract
changes.

**Architecture:** Three changes to the existing `evolving-skills` observation
store — no new skill. (1) The validator becomes version-dispatched: a note is
validated against the schema version *it declares*, and classified as `current`,
`outdated`, `unknown-schema`, or `invalid` instead of a bare pass/fail. (2) A new
`new_observation.py` generates valid frontmatter from four prose arguments,
deriving all provenance from git and the environment. (3) `parse_observations.py`
gains `--tidy`, which sweeps `pending/` and moves unreadable notes to a new
`quarantine/` directory. The `record-observations` skill proposed in the
2026-08-01 handoff is **not** built: the contract already lives in
`references/local-adapter-protocol.md` and the write hook already lives in
`using-superpowers/SKILL.md`, which is the only skill guaranteed loaded at
session start on every harness.

**Tech Stack:** Python 3 standard library only. The hand-rolled frontmatter
parser in `adapter_protocol.py` (`parse_frontmatter`). `unittest` for tests.

## Global Constraints

- **Zero third-party dependencies.** Superpowers is a zero-dependency plugin by
  design (`CLAUDE.md`). No PyYAML, no `pip install`. Use `parse_frontmatter`.
- **Python 3 stdlib only**, matching the existing scripts' style: `from __future__
  import annotations`, `pathlib.Path`, `argparse`, type hints on every signature,
  one-line docstrings.
- **The frontmatter parser accepts a strict subset.** `_parse_scalar` in
  `adapter_protocol.py:20` raises on any value starting with `[` or `{`. There are
  **no lists, no inline mappings, and no block scalars.** Every emitted value must
  be a single-line scalar. This is why the handoff's proposed `skill: [developing]`
  list field is not implementable and does not appear in this plan.
- **Do not weaken existing path-safety guards.** `_require_local_directory`,
  `_require_pending_source`, `_repository_project_root`, and the symlink rejections
  added in `4519ff2`, `5921b8e`, and `c194c6d` are frozen anchors. Every new
  directory operation goes through the same guards.
- **`SKILL.md` files stay under 500 words.** Current counts, measured
  2026-08-01: `evolving-skills/SKILL.md` is **497** words — three words of
  headroom. `using-superpowers/SKILL.md` is **598** words and already over budget.
  Doc edits in Task 5 must be net-neutral or net-negative; adding a line means
  cutting one.
- **This is a fork** (`origin` = `untko/superpowers`, `upstream` = `obra/superpowers`,
  push disabled). Do not open upstream PRs. All work lands on this fork.
- **The canonical store shape is `<project>/.superpowers/observations/`.** Nothing
  in this plan may introduce a second observation location.

---

## File Structure

**Modified:**

- `skills/evolving-skills/scripts/adapter_protocol.py` (497 lines) — owns the
  schema contract. Gains the version registry, `classify_observation`, and
  optional-field support. Stays the single source of truth for what a valid
  observation is.
- `skills/evolving-skills/scripts/parse_observations.py` (343 lines) — owns store
  discovery and lifecycle moves. Gains `--tidy` and `--migrate-legacy`. Does not
  gain generation; that would push it past 500 lines and mix two responsibilities.
- `skills/evolving-skills/tests/test_adapter_protocol.py` (481 lines)
- `skills/evolving-skills/tests/test_parse_observations.py` (402 lines)
- `skills/evolving-skills/references/local-adapter-protocol.md` — the contract doc.
- `skills/evolving-skills/SKILL.md`, `skills/using-superpowers/SKILL.md`.

**Created:**

- `skills/evolving-skills/scripts/new_observation.py` — single responsibility:
  turn minimal prose plus derived provenance into one valid note on disk. Separate
  from `parse_observations.py` because generation reads git and the environment,
  while parsing reads only the store; they fail for different reasons and are
  reviewed differently.
- `skills/evolving-skills/tests/test_new_observation.py`

**Deleted:**

- `skills/evolving-skills/references/observations/` — an untracked legacy-format
  store living inside the skill's own references, holding one note. It is a second
  observation location and contradicts the canonical shape. Task 4 migrates its
  contents first, then removes it.

---

### Task 1: Version-dispatched validation and optional fields

This is the drift seam. Today `validate_observation` at
`adapter_protocol.py:388` does `if metadata.get("schema") != OBSERVATION_SCHEMA`
against a single module constant. When the contract moves to v2, every v1 note
fails, and `_repository_observation` (`parse_observations.py:166`) returns `None`,
so `--list` drops the entire existing corpus to stderr warnings. This task makes
the declared version select the validator, and separates "written under an older
contract" from "malformed".

It also adds the first *optional* field, `skills.global.dirty`, which proves the
additive-only rule: a new field appears, old notes lack it, and nothing breaks or
needs migrating. `dirty` exists because a commit SHA alone misleads when the tree
is dirty — the 2026-08-01 incident recorded 81 uncommitted files that no SHA
captured.

**Files:**
- Modify: `skills/evolving-skills/scripts/adapter_protocol.py:14`,
  `:322-449`
- Test: `skills/evolving-skills/tests/test_adapter_protocol.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `OBSERVATION_SCHEMA: str` — unchanged, `"superpowers-observation/v1"`, the
    current version emitted by generators.
  - `OBSERVATION_VALIDATORS: dict[str, Callable[[dict[str, object]], list[str]]]`
    — the version registry. Mutable at runtime so tests can register a fake
    version.
  - `classify_observation(metadata: dict[str, object]) -> tuple[str, list[str]]`
    — returns `(status, errors)` where status is one of `"current"`, `"outdated"`,
    `"unknown-schema"`, `"invalid"`.
  - `validate_observation(metadata: dict[str, object]) -> list[str]` — unchanged
    signature and unchanged error strings, now implemented on top of
    `classify_observation`.

- [ ] **Step 1: Write the failing tests**

Append to `skills/evolving-skills/tests/test_adapter_protocol.py`. Reuse whatever
helper the file already uses to build a valid metadata dict; if none exists, add
`_valid_observation_metadata()` returning the exact structure documented in
`references/local-adapter-protocol.md` lines 64-93.

```python
    def test_classify_returns_current_for_valid_v1(self):
        metadata = _valid_observation_metadata()
        self.assertEqual(
            adapter_protocol.classify_observation(metadata), ("current", [])
        )

    def test_classify_returns_invalid_with_errors_for_malformed_v1(self):
        metadata = _valid_observation_metadata()
        del metadata["observation"]["expected"]
        status, errors = adapter_protocol.classify_observation(metadata)
        self.assertEqual(status, "invalid")
        self.assertIn("observation.expected is required", errors)

    def test_classify_returns_invalid_for_missing_schema(self):
        metadata = _valid_observation_metadata()
        del metadata["schema"]
        status, errors = adapter_protocol.classify_observation(metadata)
        self.assertEqual(status, "invalid")
        self.assertEqual(errors, ["schema is required"])

    def test_classify_returns_unknown_schema_for_unregistered_version(self):
        metadata = _valid_observation_metadata()
        metadata["schema"] = "superpowers-observation/v9"
        status, errors = adapter_protocol.classify_observation(metadata)
        self.assertEqual(status, "unknown-schema")
        self.assertEqual(errors, ["unknown observation schema superpowers-observation/v9"])

    def test_classify_returns_outdated_for_registered_older_version(self):
        metadata = _valid_observation_metadata()
        metadata["schema"] = "superpowers-observation/v0-test"
        adapter_protocol.OBSERVATION_VALIDATORS["superpowers-observation/v0-test"] = (
            lambda _metadata: []
        )
        self.addCleanup(
            adapter_protocol.OBSERVATION_VALIDATORS.pop,
            "superpowers-observation/v0-test",
            None,
        )
        self.assertEqual(
            adapter_protocol.classify_observation(metadata), ("outdated", [])
        )

    def test_validate_observation_message_unchanged_for_unknown_schema(self):
        metadata = _valid_observation_metadata()
        metadata["schema"] = "superpowers-observation/v9"
        self.assertEqual(
            adapter_protocol.validate_observation(metadata),
            ["schema must be superpowers-observation/v1"],
        )

    def test_dirty_flag_is_optional_and_absent_is_valid(self):
        metadata = _valid_observation_metadata()
        self.assertNotIn("dirty", metadata["skills"]["global"])
        self.assertEqual(adapter_protocol.validate_observation(metadata), [])

    def test_dirty_flag_accepts_boolean(self):
        metadata = _valid_observation_metadata()
        metadata["skills"]["global"]["dirty"] = True
        self.assertEqual(adapter_protocol.validate_observation(metadata), [])

    def test_dirty_flag_rejects_non_boolean(self):
        metadata = _valid_observation_metadata()
        metadata["skills"]["global"]["dirty"] = "yes"
        self.assertEqual(
            adapter_protocol.validate_observation(metadata),
            ["skills.global.dirty must be a boolean"],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest skills/evolving-skills/tests/test_adapter_protocol.py -v`

Expected: FAIL. The `classify_*` tests fail with
`AttributeError: module 'adapter_protocol' has no attribute 'classify_observation'`.
The `dirty` tests fail because no optional-field handling exists.

If `pytest` is unavailable, run
`python3 -m unittest discover -s skills/evolving-skills/tests -v` instead and use
that form for every later step.

- [ ] **Step 3: Rename the v1 body and add the registry**

In `adapter_protocol.py`, rename the existing `validate_observation` function body
(currently line 385) to `_validate_observation_v1`, and **delete its first three
lines** — the `if metadata.get("schema") != OBSERVATION_SCHEMA:` check. Schema
identity is now the dispatcher's job, not the field validator's.

```python
def _validate_observation_v1(metadata: dict[str, object]) -> list[str]:
    """Return every field error in v1 observation frontmatter metadata."""
    errors: list[str] = []

    invalid_mappings: set[str] = set()
    # ... existing body from the old validate_observation, unchanged ...
    return errors
```

- [ ] **Step 4: Add optional-field validation to the v1 validator**

Add the constant beside `_STRING_FIELDS` (line 322):

```python
_OPTIONAL_BOOL_FIELDS = ("skills.global.dirty",)
```

Insert this block into `_validate_observation_v1`, immediately before the
`for path, allowed in _ENUMS.items():` loop:

```python
    for path in _OPTIONAL_BOOL_FIELDS:
        if parent_is_invalid(path):
            continue
        exists, value = _lookup(metadata, path)
        if exists and type(value) is not bool:
            errors.append(f"{path} must be a boolean")
```

`type(value) is not bool` rather than `isinstance` matches the existing style at
line 423, and keeps `1`/`0` from passing as booleans.

- [ ] **Step 5: Add the registry and dispatcher**

Beside `OBSERVATION_SCHEMA` at line 14, leave the constant as-is. After
`_validate_observation_v1`, add:

```python
OBSERVATION_VALIDATORS: dict[str, "Callable[[dict[str, object]], list[str]]"] = {
    OBSERVATION_SCHEMA: _validate_observation_v1,
}


def classify_observation(metadata: dict[str, object]) -> tuple[str, list[str]]:
    """Classify frontmatter against the schema version it declares.

    Returns ``(status, errors)`` where status is ``current`` for a valid note on
    the current schema, ``outdated`` for a valid note on a registered older
    schema, ``unknown-schema`` for an unregistered version, and ``invalid`` for
    a note that fails its own declared schema.
    """
    schema = metadata.get("schema")
    if not isinstance(schema, str) or not schema:
        return "invalid", ["schema is required"]
    validator = OBSERVATION_VALIDATORS.get(schema)
    if validator is None:
        return "unknown-schema", [f"unknown observation schema {schema}"]
    errors = validator(metadata)
    if errors:
        return "invalid", errors
    if schema != OBSERVATION_SCHEMA:
        return "outdated", []
    return "current", []


def validate_observation(metadata: dict[str, object]) -> list[str]:
    """Return every validation error, treating a non-current schema as an error."""
    status, errors = classify_observation(metadata)
    if status == "current":
        return []
    if status in {"unknown-schema", "outdated"}:
        return [f"schema must be {OBSERVATION_SCHEMA}"]
    return errors
```

Add `from typing import Callable` to the imports if the file does not already
import it; if it does not use `typing` anywhere, keep the quoted annotation shown
above and skip the import.

- [ ] **Step 6: Run the full adapter test file**

Run: `python3 -m pytest skills/evolving-skills/tests/test_adapter_protocol.py -v`

Expected: PASS, including every pre-existing test. The
`test_validate_observation_message_unchanged_for_unknown_schema` case is the guard
that the 481 lines of existing tests still see the same error strings.

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m pytest skills/evolving-skills/tests/ -v`

Expected: PASS. `parse_observations.py` imports `validate_observation` and its
behaviour is unchanged for every currently valid or invalid note.

- [ ] **Step 8: Commit**

```bash
git add skills/evolving-skills/scripts/adapter_protocol.py skills/evolving-skills/tests/test_adapter_protocol.py
git commit -m "feat(evolving-skills): dispatch observation validation on declared schema"
```

---

### Task 2: Generate observations instead of hand-writing them

The contract is ~25 required keys across four nested blocks. Asking a model to
emit that correctly mid-session, without breaking the user's flow, is the wrong
place to spend tokens and the wrong place to risk a silent drop. This task moves
provenance to derivation: the agent supplies four prose values, the script
supplies everything else from git and the environment.

`--archive-now` covers the "this needs no action" case from the workflow sketch
without weakening `_require_pending_source`: the note is still written to
`pending/` and still archived through the guarded move, just in one invocation.

**Files:**
- Create: `skills/evolving-skills/scripts/new_observation.py`
- Create: `skills/evolving-skills/tests/test_new_observation.py`

**Interfaces:**
- Consumes: `adapter_protocol.validate_observation`,
  `adapter_protocol.OBSERVATION_SCHEMA`, `adapter_protocol.discover_adapter`;
  `parse_observations.ensure_observation_store`,
  `parse_observations.archive_observation`.
- Produces:
  - `render_frontmatter(metadata: dict[str, object]) -> str` — serializes a nested
    dict into the parser's accepted subset.
  - `build_metadata(...) -> dict[str, object]` — assembles the v1 metadata dict.
  - `write_observation(project_root: Path, metadata: dict[str, object], body: str,
    *, archive_now: bool = False) -> Path` — validates, writes to `pending/`,
    optionally archives, returns the final path.

- [ ] **Step 1: Write the failing tests**

Create `skills/evolving-skills/tests/test_new_observation.py`:

```python
"""Tests for deterministic observation generation."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import adapter_protocol
import new_observation


class RenderFrontmatterTest(unittest.TestCase):
    def test_round_trips_through_the_project_parser(self):
        metadata = {
            "schema": adapter_protocol.OBSERVATION_SCHEMA,
            "observation": {"expected": "a value with: a colon and 'quotes'"},
            "skills": {"global": {"dirty": True, "contract": 1}},
        }
        text = new_observation.render_frontmatter(metadata)
        parsed, body = adapter_protocol.parse_frontmatter(text + "body\n")
        self.assertEqual(
            parsed["observation"]["expected"], "a value with: a colon and 'quotes'"
        )
        self.assertIs(parsed["skills"]["global"]["dirty"], True)
        self.assertEqual(parsed["skills"]["global"]["contract"], 1)
        self.assertEqual(body.strip(), "body")

    def test_collapses_newlines_into_single_line_scalars(self):
        metadata = {"observation": {"evidence": "line one\nline two"}}
        text = new_observation.render_frontmatter(metadata)
        self.assertEqual(len(text.strip().splitlines()), 3)


class BuildMetadataTest(unittest.TestCase):
    def test_produces_metadata_that_validates(self):
        metadata = new_observation.build_metadata(
            skill="evolving-skills",
            phase="verification",
            expected="Evidence is recorded without changing global skills.",
            actual="A reusable friction pattern required an explicit local note.",
            evidence="Sanitized command result.",
            diagnosis="uncertain",
            scope="potentially-global",
            target="reference",
            runtime={"model": "test-model"},
            provenance={"git-commit": "abc1234", "dirty": True, "plugin-version": "0"},
            adapter=None,
        )
        self.assertEqual(adapter_protocol.validate_observation(metadata), [])
        self.assertIs(metadata["skills"]["global"]["dirty"], True)
        self.assertEqual(metadata["runtime"]["model"], "test-model")
        self.assertEqual(metadata["runtime"]["harness"], "unknown")
        self.assertEqual(metadata["skills"]["adapter"]["path"], "unknown")


class WriteObservationTest(unittest.TestCase):
    def _metadata(self):
        return new_observation.build_metadata(
            skill="evolving-skills",
            phase="verification",
            expected="expected",
            actual="actual",
            evidence="evidence",
            diagnosis="uncertain",
            scope="local",
            target="none",
            runtime={},
            provenance={},
            adapter=None,
        )

    def test_writes_a_listable_note_into_pending(self):
        with tempfile.TemporaryDirectory() as root:
            path = new_observation.write_observation(
                Path(root), self._metadata(), "Sanitized body."
            )
            self.assertEqual(path.parent.name, "pending")
            import parse_observations

            listed = parse_observations.list_observations(
                parse_observations.observation_root(Path(root))
            )
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["skill"], "evolving-skills")

    def test_archive_now_lands_in_archived_and_leaves_pending_empty(self):
        with tempfile.TemporaryDirectory() as root:
            path = new_observation.write_observation(
                Path(root), self._metadata(), "Sanitized body.", archive_now=True
            )
            self.assertEqual(path.parent.name, "archived")
            pending = Path(root) / ".superpowers" / "observations" / "pending"
            self.assertEqual(list(pending.iterdir()), [])

    def test_refuses_to_write_invalid_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            metadata = self._metadata()
            del metadata["observation"]["expected"]
            with self.assertRaises(ValueError):
                new_observation.write_observation(Path(root), metadata, "body")
            pending = Path(root) / ".superpowers" / "observations" / "pending"
            self.assertFalse(pending.exists() and list(pending.iterdir()))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest skills/evolving-skills/tests/test_new_observation.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'new_observation'`.

- [ ] **Step 3: Write the generator**

Create `skills/evolving-skills/scripts/new_observation.py`:

```python
#!/usr/bin/env python3
"""Generate one valid repository-local observation from minimal prose input."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from adapter_protocol import (
    OBSERVATION_SCHEMA,
    discover_adapter,
    validate_observation,
)
from parse_observations import archive_observation, ensure_observation_store

_SLUG = re.compile(r"[^a-z0-9]+")
_UNKNOWN = "unknown"
_RUNTIME_KEYS = (
    "provider",
    "model",
    "reasoning-effort",
    "harness",
    "harness-version",
    "interface",
)


def _scalar(value: object) -> str:
    """Render one value inside the frontmatter parser's accepted subset."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = " ".join(str(value).split())
    return repr(text)


def render_frontmatter(metadata: dict[str, object]) -> str:
    """Serialize nested metadata as indented single-line scalars."""
    lines = ["---"]

    def emit(mapping: dict[str, object], indent: int) -> None:
        for key, value in mapping.items():
            pad = "  " * indent
            if isinstance(value, dict):
                lines.append(f"{pad}{key}:")
                emit(value, indent + 1)
            else:
                lines.append(f"{pad}{key}: {_scalar(value)}")

    emit(metadata, 0)
    lines.append("---")
    return "\n".join(lines) + "\n"


def build_metadata(
    *,
    skill: str,
    phase: str,
    expected: str,
    actual: str,
    evidence: str,
    diagnosis: str,
    scope: str,
    target: str,
    runtime: dict[str, str],
    provenance: dict[str, object],
    adapter: dict[str, object] | None,
) -> dict[str, object]:
    """Assemble current-schema metadata, defaulting every unknown to 'unknown'."""
    global_block: dict[str, object] = {
        "name": skill,
        "contract": 1,
        "plugin-version": str(provenance.get("plugin-version") or _UNKNOWN),
        "git-commit": str(provenance.get("git-commit") or _UNKNOWN),
    }
    if "dirty" in provenance:
        global_block["dirty"] = bool(provenance["dirty"])
    return {
        "schema": OBSERVATION_SCHEMA,
        "runtime": {key: runtime.get(key) or _UNKNOWN for key in _RUNTIME_KEYS},
        "skills": {
            "global": global_block,
            "adapter": {
                "path": str((adapter or {}).get("path") or _UNKNOWN),
                "version": str((adapter or {}).get("version") or _UNKNOWN),
                "git-commit": str((adapter or {}).get("git-commit") or _UNKNOWN),
            },
        },
        "observation": {
            "phase": phase,
            "expected": expected,
            "actual": actual,
            "evidence": evidence,
            "diagnosis": diagnosis,
        },
        "candidate": {"scope": scope, "target": target, "status": "observed"},
    }


def _filename(metadata: dict[str, object], now: str) -> str:
    """Build a sortable, slugged filename from the observation summary."""
    summary = str(metadata["observation"]["actual"])[:60].lower()
    slug = _SLUG.sub("-", summary).strip("-") or "observation"
    return f"{now}-{slug}.md"


def write_observation(
    project_root: Path,
    metadata: dict[str, object],
    body: str,
    *,
    archive_now: bool = False,
    now: str | None = None,
) -> Path:
    """Validate, write into pending/, and optionally archive in one guarded move."""
    errors = validate_observation(metadata)
    if errors:
        raise ValueError("; ".join(errors))
    from datetime import datetime

    stamp = now or datetime.now().strftime("%Y-%m-%d-%H%M%S")
    store = ensure_observation_store(project_root)
    path = store["pending"] / _filename(metadata, stamp)
    if path.exists():
        raise ValueError(f"observation already exists: {path}")
    path.write_text(
        render_frontmatter(metadata) + body.strip() + "\n", encoding="utf-8"
    )
    if archive_now:
        return Path(archive_observation(path, store["archived"]))
    return path


def _git(skill_root: Path, *args: str) -> str | None:
    """Return trimmed git output, or None when git or the repository is absent."""
    try:
        result = subprocess.run(
            ["git", "-C", str(skill_root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _plugin_provenance(skill_root: Path) -> dict[str, object]:
    """Derive plugin version, commit, and dirty state from the installed skill."""
    provenance: dict[str, object] = {}
    for name in ("plugin.json", "package.json"):
        candidate = skill_root / name
        if candidate.is_file():
            try:
                provenance["plugin-version"] = json.loads(
                    candidate.read_text(encoding="utf-8")
                ).get("version")
            except (OSError, ValueError):
                provenance["plugin-version"] = None
            if provenance.get("plugin-version"):
                break
    commit = _git(skill_root, "rev-parse", "--short", "HEAD")
    if commit:
        provenance["git-commit"] = commit
        status = _git(skill_root, "status", "--porcelain")
        provenance["dirty"] = bool(status)
    return provenance


def _adapter_provenance(project_root: Path, skill: str) -> dict[str, object] | None:
    """Return adapter provenance when a valid adapter is discoverable."""
    try:
        result = discover_adapter(project_root, skill, {1})
    except (OSError, ValueError):
        return None
    if not isinstance(result, dict) or result.get("status") != "valid":
        return None
    metadata = result.get("metadata") or {}
    return {
        "path": result.get("path"),
        "version": metadata.get("adapter-version"),
        "git-commit": _UNKNOWN,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write one valid repository-local observation."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--skill", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--actual", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--diagnosis", default="uncertain")
    parser.add_argument("--scope", default="uncertain")
    parser.add_argument("--target", default="unknown")
    parser.add_argument("--body", default="")
    parser.add_argument("--archive-now", action="store_true")
    for key in _RUNTIME_KEYS:
        parser.add_argument(f"--{key}", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Generate one observation and print its path."""
    args = _build_parser().parse_args(argv)
    skill_root = Path(__file__).resolve().parents[3]
    runtime = {key: getattr(args, key.replace("-", "_")) for key in _RUNTIME_KEYS}
    runtime["harness"] = runtime["harness"] or os.environ.get("SUPERPOWERS_HARNESS")
    runtime["model"] = runtime["model"] or os.environ.get("SUPERPOWERS_MODEL")
    metadata = build_metadata(
        skill=args.skill,
        phase=args.phase,
        expected=args.expected,
        actual=args.actual,
        evidence=args.evidence,
        diagnosis=args.diagnosis,
        scope=args.scope,
        target=args.target,
        runtime=runtime,
        provenance=_plugin_provenance(skill_root),
        adapter=_adapter_provenance(args.project_root, args.skill),
    )
    try:
        path = write_observation(
            args.project_root,
            metadata,
            args.body or args.evidence,
            archive_now=args.archive_now,
        )
    except (OSError, ValueError) as error:
        sys.stderr.write(f"Error: {error}\n")
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`_scalar` uses `repr()` for strings because `_parse_scalar` at
`adapter_protocol.py:25` reads quoted scalars with `ast.literal_eval`, which
round-trips `repr()` output exactly — including embedded colons and quotes. Do not
hand-roll quoting.

`skill_root = Path(__file__).resolve().parents[3]` walks
`scripts/ → evolving-skills/ → skills/ → repo root`. Verify this in Step 4; if the
skill is installed at a different depth, git derivation simply returns `unknown`,
which is a legitimate value, not a failure.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest skills/evolving-skills/tests/test_new_observation.py -v`

Expected: PASS, all seven tests.

- [ ] **Step 5: Verify against the real store, not just fixtures**

```bash
python3 skills/evolving-skills/scripts/new_observation.py \
  --project-root "$PWD" --skill evolving-skills --phase verification \
  --expected "The generator writes a note that --list can read." \
  --actual "Verifying the generator against the real repository store." \
  --evidence "Manual verification during plan execution." \
  --model claude-opus-5 --harness claude-code
python3 skills/evolving-skills/scripts/parse_observations.py --project-root "$PWD" --list
```

Expected: the generator prints a path under `.superpowers/observations/pending/`,
and `--list` returns a one-element JSON array with no stderr warnings. Confirm the
emitted file contains a real `git-commit` and a `dirty` boolean, not `unknown`.
Then delete the note: `rm <printed path>`.

- [ ] **Step 6: Commit**

```bash
git add skills/evolving-skills/scripts/new_observation.py skills/evolving-skills/tests/test_new_observation.py
git commit -m "feat(evolving-skills): generate observations from derived provenance"
```

---

### Task 3: Sweep the pending queue with `--tidy`

`--list` currently drops unreadable notes to a stderr warning and moves on, so a
malformed note stays in `pending/` forever, invisible to every future harvest.
`--tidy` gives it somewhere to go.

`quarantine/` is deliberately **not** added to `_LIFECYCLE_NAMES`.
`_observation_store_exists` (`parse_observations.py:101`) requires every name in
that tuple to be present, so adding it there would make every store created before
this change report as missing. It is created on demand instead, through the same
`_require_local_directory` guard.

Notes classified `outdated` are reported but never moved — they are valid evidence
under an older contract, and quarantining them would recreate the corpus loss this
plan exists to prevent.

**Files:**
- Modify: `skills/evolving-skills/scripts/parse_observations.py:19`, `:78-147`,
  `:284-343`
- Test: `skills/evolving-skills/tests/test_parse_observations.py`

**Interfaces:**
- Consumes: `adapter_protocol.classify_observation` from Task 1;
  `_require_local_directory`, `_require_observation_store`,
  `_resolve_project_root` (existing private helpers).
- Produces:
  - `quarantine_directory(project_root: Path) -> Path` — resolves and creates
    `.superpowers/observations/quarantine/` under the existing symlink guards.
  - `tidy_observations(project_root: Path) -> dict[str, object]` — returns
    `{"kept": [...], "outdated": [...], "quarantined": [...]}`, each a list of
    filenames.
  - CLI flag `--tidy`.

- [ ] **Step 1: Write the failing tests**

Append to `skills/evolving-skills/tests/test_parse_observations.py`. Reuse the
file's existing helper for writing a valid note into a temporary store; if it has
none, add `_write_valid_note(pending, name)` that writes the frontmatter from
`references/local-adapter-protocol.md` lines 64-93 verbatim plus a one-line body.

```python
    def test_tidy_keeps_valid_notes_in_pending(self):
        with tempfile.TemporaryDirectory() as root:
            store = parse_observations.ensure_observation_store(Path(root))
            _write_valid_note(store["pending"], "keep.md")
            report = parse_observations.tidy_observations(Path(root))
            self.assertEqual(report["kept"], ["keep.md"])
            self.assertEqual(report["quarantined"], [])
            self.assertTrue((store["pending"] / "keep.md").is_file())

    def test_tidy_quarantines_malformed_notes(self):
        with tempfile.TemporaryDirectory() as root:
            store = parse_observations.ensure_observation_store(Path(root))
            (store["pending"] / "broken.md").write_text(
                "---\nschema: superpowers-observation/v1\n---\nno fields\n",
                encoding="utf-8",
            )
            report = parse_observations.tidy_observations(Path(root))
            self.assertEqual(report["quarantined"], ["broken.md"])
            self.assertFalse((store["pending"] / "broken.md").exists())
            quarantine = Path(root) / ".superpowers" / "observations" / "quarantine"
            self.assertTrue((quarantine / "broken.md").is_file())

    def test_tidy_quarantines_unparseable_notes(self):
        with tempfile.TemporaryDirectory() as root:
            store = parse_observations.ensure_observation_store(Path(root))
            (store["pending"] / "garbage.md").write_text(
                "not frontmatter at all\n", encoding="utf-8"
            )
            report = parse_observations.tidy_observations(Path(root))
            self.assertEqual(report["quarantined"], ["garbage.md"])

    def test_tidy_reports_outdated_without_moving_it(self):
        with tempfile.TemporaryDirectory() as root:
            store = parse_observations.ensure_observation_store(Path(root))
            _write_valid_note(store["pending"], "old.md")
            text = (store["pending"] / "old.md").read_text(encoding="utf-8")
            (store["pending"] / "old.md").write_text(
                text.replace(
                    "superpowers-observation/v1", "superpowers-observation/v0-test"
                ),
                encoding="utf-8",
            )
            adapter_protocol.OBSERVATION_VALIDATORS[
                "superpowers-observation/v0-test"
            ] = lambda _metadata: []
            self.addCleanup(
                adapter_protocol.OBSERVATION_VALIDATORS.pop,
                "superpowers-observation/v0-test",
                None,
            )
            report = parse_observations.tidy_observations(Path(root))
            self.assertEqual(report["outdated"], ["old.md"])
            self.assertEqual(report["quarantined"], [])
            self.assertTrue((store["pending"] / "old.md").is_file())

    def test_tidy_ignores_symlinked_notes(self):
        with tempfile.TemporaryDirectory() as root:
            store = parse_observations.ensure_observation_store(Path(root))
            target = Path(root) / "outside.md"
            target.write_text("---\nschema: x\n---\n", encoding="utf-8")
            (store["pending"] / "link.md").symlink_to(target)
            report = parse_observations.tidy_observations(Path(root))
            self.assertEqual(report["quarantined"], [])
            self.assertTrue((store["pending"] / "link.md").is_symlink())

    def test_tidy_does_not_overwrite_an_existing_quarantine_entry(self):
        with tempfile.TemporaryDirectory() as root:
            store = parse_observations.ensure_observation_store(Path(root))
            quarantine = parse_observations.quarantine_directory(Path(root))
            (quarantine / "broken.md").write_text("first\n", encoding="utf-8")
            (store["pending"] / "broken.md").write_text(
                "not frontmatter\n", encoding="utf-8"
            )
            report = parse_observations.tidy_observations(Path(root))
            self.assertEqual(report["quarantined"], [])
            self.assertEqual(
                (quarantine / "broken.md").read_text(encoding="utf-8"), "first\n"
            )
```

Add `import adapter_protocol` at the top of the test file if it is not already
imported.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest skills/evolving-skills/tests/test_parse_observations.py -v`

Expected: FAIL with
`AttributeError: module 'parse_observations' has no attribute 'tidy_observations'`.

- [ ] **Step 3: Implement quarantine resolution and the sweep**

In `parse_observations.py`, change the import at line 7 to:

```python
from adapter_protocol import classify_observation, parse_frontmatter, validate_observation
```

Add after `ensure_observation_store` (line 146):

```python
def quarantine_directory(project_root: Path) -> Path:
    """Resolve and create the on-demand quarantine directory for one repository."""
    resolved_project_root = _resolve_project_root(project_root)
    store = _require_observation_store(resolved_project_root, create=False)
    return _require_local_directory(
        store["root"] / "quarantine",
        label="quarantine",
        project_root=resolved_project_root,
        create=True,
    )


def tidy_observations(project_root: Path) -> dict[str, object]:
    """Sweep the pending queue, quarantining notes no harvest can ever read."""
    store = _require_observation_store(_resolve_project_root(project_root), create=False)
    report: dict[str, object] = {"kept": [], "outdated": [], "quarantined": []}
    quarantine: Path | None = None
    for path in sorted(store["pending"].iterdir()):
        if path.is_symlink() or path.suffix != ".md" or path.name == "README.md":
            continue
        if not path.is_file():
            continue
        try:
            frontmatter, _body = parse_frontmatter(path.read_text(encoding="utf-8"))
            status, _errors = classify_observation(frontmatter)
        except (OSError, UnicodeError, ValueError):
            status = "invalid"
        if status == "current":
            report["kept"].append(path.name)
            continue
        if status == "outdated":
            report["outdated"].append(path.name)
            continue
        if quarantine is None:
            quarantine = quarantine_directory(project_root)
        target = quarantine / path.name
        if target.exists() or target.is_symlink():
            sys.stderr.write(
                f"Warning: quarantine destination already exists: {target}\n"
            )
            continue
        shutil.move(str(path), str(target))
        report["quarantined"].append(path.name)
    return report
```

`_require_observation_store(create=False)` is used so `--tidy` refuses to run
against a store that does not exist, rather than silently creating one.

- [ ] **Step 4: Wire the CLI flag**

In `_build_parser`, after the `--archive` argument:

```python
    parser.add_argument(
        "--tidy",
        action="store_true",
        help="Quarantine unreadable pending notes and report outdated ones",
    )
```

In `main`, after the `--list` block and before the `--archive` block:

```python
    if args.tidy:
        if legacy_mode:
            sys.stderr.write("Error: --tidy requires a repository-local store\n")
            return 2
        try:
            print(json.dumps(tidy_observations(args.project_root), indent=2))
        except (OSError, ValueError) as error:
            sys.stderr.write(f"Error: {error}\n")
            return 2
```

Update the final guard to include the new flag:

```python
    if not (args.init or args.list or args.archive or args.tidy):
        parser.print_help()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest skills/evolving-skills/tests/ -v`

Expected: PASS, including every pre-existing test in both files.

- [ ] **Step 6: Commit**

```bash
git add skills/evolving-skills/scripts/parse_observations.py skills/evolving-skills/tests/test_parse_observations.py
git commit -m "feat(evolving-skills): quarantine unreadable notes with --tidy"
```

---

### Task 4: Migrate the legacy store and remove the second location

`skills/evolving-skills/references/observations/archive/` holds one note in the
pre-v1 flat format (`timestamp`, `skill`, `phase`, `status` plus a bulleted body).
It is untracked, it sits inside the skill's own references, and it is a second
observation location — exactly the split-corpus problem this plan is meant to
close. Migrating it also exercises the version seam with a real file rather than a
synthetic one, and produces the converter the Obsidian vault's 13 active notes will
need.

`--obs-dir` legacy mode is **kept**, with a deprecation warning. It is the only
reader for any legacy store still on disk in other repositories, and it is the
input side of this migration. Removing it before those are migrated would strand
them; that removal is a separate decision for a later change.

**Files:**
- Modify: `skills/evolving-skills/scripts/parse_observations.py`
- Test: `skills/evolving-skills/tests/test_parse_observations.py`
- Delete: `skills/evolving-skills/references/observations/`

**Interfaces:**
- Consumes: `_legacy_observation`, `new_observation.build_metadata`,
  `new_observation.render_frontmatter`.
- Produces:
  - `migrate_legacy_note(path: Path) -> dict[str, object]` — returns
    current-schema metadata and the preserved body, as
    `{"metadata": ..., "body": ...}`.
  - CLI flag `--migrate-legacy <path>`, which writes the converted note into the
    project's `archived/` directory and prints the destination.

- [ ] **Step 1: Write the failing test**

The fixture below is the real legacy file, copied verbatim.

```python
_LEGACY_NOTE = """---
timestamp: '2026-07-24T03:19:00+07:00'
skill: systematic-debugging
phase: root_cause_investigation
status: pending_distillation
---

# Fast-Loop Observation Note: Systematic Debugging Flaky Test Fix

- **Observed Failure**: Agent raised timeouts instead of investigating shared state.
- **Proposed Universal Fix**: Prohibit timeout adjustments without isolation checks.
"""


class MigrateLegacyTest(unittest.TestCase):
    def test_converts_a_legacy_note_to_current_schema(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "legacy.md"
            source.write_text(_LEGACY_NOTE, encoding="utf-8")
            result = parse_observations.migrate_legacy_note(source)
            self.assertEqual(adapter_protocol.validate_observation(result["metadata"]), [])
            self.assertEqual(
                result["metadata"]["skills"]["global"]["name"], "systematic-debugging"
            )
            self.assertEqual(
                result["metadata"]["observation"]["phase"], "root_cause_investigation"
            )
            self.assertEqual(result["metadata"]["candidate"]["status"], "observed")

    def test_preserves_the_legacy_body_verbatim(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "legacy.md"
            source.write_text(_LEGACY_NOTE, encoding="utf-8")
            result = parse_observations.migrate_legacy_note(source)
            self.assertIn("Proposed Universal Fix", result["body"])
            self.assertIn("shared state", result["body"])

    def test_records_unavailable_provenance_as_unknown(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "legacy.md"
            source.write_text(_LEGACY_NOTE, encoding="utf-8")
            result = parse_observations.migrate_legacy_note(source)
            self.assertEqual(result["metadata"]["runtime"]["model"], "unknown")
            self.assertEqual(result["metadata"]["skills"]["adapter"]["path"], "unknown")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest skills/evolving-skills/tests/test_parse_observations.py -k Migrate -v`

Expected: FAIL with
`AttributeError: module 'parse_observations' has no attribute 'migrate_legacy_note'`.

- [ ] **Step 3: Implement the converter**

Add to `parse_observations.py`:

```python
def migrate_legacy_note(filepath: Path | str) -> dict[str, object]:
    """Convert one pre-v1 flat note into current-schema metadata and body."""
    from new_observation import build_metadata

    legacy = _legacy_observation(Path(filepath))
    body = str(legacy["content"])
    return {
        "metadata": build_metadata(
            skill=str(legacy["skill"]),
            phase=str(legacy["phase"]),
            expected="A reusable pattern was recorded under the pre-v1 note format.",
            actual=body.splitlines()[0].strip("# ") if body else "unknown",
            evidence="Migrated from a pre-v1 observation note; body preserved below.",
            diagnosis="unknown",
            scope="uncertain",
            target="unknown",
            runtime={},
            provenance={},
            adapter=None,
        ),
        "body": body,
    }
```

Every field the legacy format did not carry becomes `unknown` — a legitimate
value under the contract. Do not infer a diagnosis, a model, or a scope from a
note that never recorded one.

- [ ] **Step 4: Wire the CLI flag**

Add to `_build_parser`:

```python
    parser.add_argument(
        "--migrate-legacy",
        type=Path,
        help="Convert a pre-v1 note and write it into archived/",
    )
```

Add to `main`, before the final guard:

```python
    if args.migrate_legacy:
        from new_observation import render_frontmatter

        try:
            converted = migrate_legacy_note(args.migrate_legacy)
            store = ensure_observation_store(args.project_root)
            target = store["archived"] / args.migrate_legacy.name
            if target.exists() or target.is_symlink():
                raise FileExistsError(f"destination already exists: {target}")
            target.write_text(
                render_frontmatter(converted["metadata"])
                + str(converted["body"]).strip()
                + "\n",
                encoding="utf-8",
            )
        except (OSError, ValueError) as error:
            sys.stderr.write(f"Error: {error}\n")
            return 2
        print(f"Migrated {args.migrate_legacy} -> {target}")
```

Add `args.migrate_legacy` to the final `if not (...)` guard.

Add the deprecation warning at the top of the `if legacy_mode:` branch in `main`:

```python
        sys.stderr.write(
            "Warning: --obs-dir is deprecated; migrate with --migrate-legacy\n"
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest skills/evolving-skills/tests/ -v`

Expected: PASS. Existing `--obs-dir` tests still pass; the warning goes to stderr
and does not change return codes or stdout.

- [ ] **Step 6: Migrate the real file and remove the second location**

```bash
python3 skills/evolving-skills/scripts/parse_observations.py --project-root "$PWD" \
  --migrate-legacy "skills/evolving-skills/references/observations/archive/2026-07-24-0319-systematic-debugging-failed-during-investigation-for-flaky-test.md"
```

Read the printed destination file and confirm the body survived and the
frontmatter validates:

```bash
python3 skills/evolving-skills/scripts/adapter_protocol.py validate-observation \
  ".superpowers/observations/archived/2026-07-24-0319-systematic-debugging-failed-during-investigation-for-flaky-test.md"
```

Expected: no errors. Only then remove the old location, and the stray bytecode
that is also untracked:

```bash
rm -rf skills/evolving-skills/references/observations skills/evolving-skills/scripts/__pycache__
```

- [ ] **Step 7: Commit**

```bash
git add skills/evolving-skills/scripts/parse_observations.py skills/evolving-skills/tests/test_parse_observations.py
git commit -m "feat(evolving-skills): migrate pre-v1 notes and retire the second store"
```

---

### Task 5: Update the contract and the write hook

The scripts are now the interface. The docs still tell an agent to hand-write
frontmatter, which is the behaviour this plan replaces. This task is where the
change actually reaches a running session.

Word budgets are tight and are a frozen constraint: `evolving-skills/SKILL.md` is
at 497 of 500 words and `using-superpowers/SKILL.md` is at 598. Both edits below
replace existing lines rather than adding to them. Measure before and after.

**Files:**
- Modify: `skills/evolving-skills/references/local-adapter-protocol.md`
- Modify: `skills/using-superpowers/SKILL.md:52-63`
- Modify: `skills/evolving-skills/SKILL.md:30-34`

**Interfaces:**
- Consumes: every CLI surface from Tasks 2-4.
- Produces: no code.

- [ ] **Step 1: Record the starting word counts**

Run: `wc -w skills/evolving-skills/SKILL.md skills/using-superpowers/SKILL.md`
Expected: `497` and `598`. Write these down; Step 5 compares against them.

- [ ] **Step 2: Rewrite the fast-loop hook in the bootstrap**

In `skills/using-superpowers/SKILL.md`, replace the three bullets at lines 56-63
(from "For significant reusable friction" through "observe/propose; explicit
global evolution separately generalizes, tests, approves, and releases.") with:

```markdown
- For significant reusable friction, record it with one command from the installed
  `superpowers:evolving-skills` skill, resolved from that skill directory:
  `python3 scripts/new_observation.py --project-root <root> --skill <name>
  --phase <phase> --expected <text> --actual <text> --evidence <text>`.
  It derives provenance and writes valid frontmatter; never hand-write the YAML.
  Add `--archive-now` when the note needs no follow-up. Mention the resulting
  path in your result.
- Ordinary runs neither edit global skills nor scan history. Local notes only
  observe and propose.
```

This is a net reduction. Confirm in Step 5.

- [ ] **Step 3: Point the harvest step at `--tidy`**

In `skills/evolving-skills/SKILL.md`, replace the two sentences of §1 that begin
"Run `python3 \"$SKILL_DIR/scripts/parse_observations.py\"` ... `--list`" with:

```markdown
Run `python3 "$SKILL_DIR/scripts/parse_observations.py" --project-root
"$PROJECT_ROOT" --tidy` to quarantine unreadable notes, then `--list` to fetch the
pending queue. Group results by target skill.
```

Add one row to the Red Flags table:

```markdown
| "I'll write the observation frontmatter by hand" | Use `new_observation.py`. Hand-written provenance drifts and gets dropped. |
```

- [ ] **Step 4: Document schema evolution in the protocol reference**

In `skills/evolving-skills/references/local-adapter-protocol.md`, add `dirty` to
the example frontmatter under `skills.global`:

```yaml
  global:
    name: evolving-skills
    contract: 1
    plugin-version: unknown
    git-commit: unknown
    dirty: false
```

Change the sentence "All listed fields are required." to "All listed fields are
required except `skills.global.dirty`, which is optional and reports whether the
working tree was dirty at the commit named above."

Then add this section immediately before "## Failure handling and adoption":

```markdown
## Schema evolution

A note is validated against the schema version its own `schema:` field declares,
not against the newest one. Validation classifies each note as `current`,
`outdated` (valid under a registered older version), `unknown-schema`, or
`invalid`.

Within a version, **only optional fields may be added**. Adding, removing, or
retyping a required field requires a new version string and a registered
validator for the old one, so existing evidence keeps validating instead of
vanishing from every harvest.

`--tidy` quarantines `invalid` and `unknown-schema` notes into `quarantine/` and
reports `outdated` ones without moving them. Quarantine is reversible: repair the
note and move it back to `pending/`. Convert a pre-v1 note with
`--migrate-legacy`; provenance the old format never recorded stays `unknown`.
```

- [ ] **Step 5: Verify the word budgets held**

Run: `wc -w skills/evolving-skills/SKILL.md skills/using-superpowers/SKILL.md`

Expected: `evolving-skills/SKILL.md` at or below **500**;
`using-superpowers/SKILL.md` at or below its starting **598**. If either exceeded
its budget, cut prose from the section you edited — do not raise the budget.

- [ ] **Step 6: Check every documented command actually runs**

```bash
python3 skills/evolving-skills/scripts/parse_observations.py --project-root "$PWD" --tidy
python3 skills/evolving-skills/scripts/parse_observations.py --project-root "$PWD" --list
python3 skills/evolving-skills/scripts/new_observation.py --help
```

Expected: `--tidy` prints a JSON report naming the migrated archived note under
neither `kept` nor `quarantined` (it is in `archived/`, not `pending/`); `--list`
returns valid JSON; `--help` exits 0. Every command string in the three edited
documents must appear in this check.

- [ ] **Step 7: Run the full suite one final time**

Run: `python3 -m pytest skills/evolving-skills/tests/ -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add skills/evolving-skills/SKILL.md skills/evolving-skills/references/local-adapter-protocol.md skills/using-superpowers/SKILL.md
git commit -m "docs(evolving-skills): document generation, tidy, and schema evolution"
```

---

## Out of Scope

Stated explicitly so a later reader does not mistake these for oversights.

- **No `record-observations` skill.** The contract already lives in
  `references/local-adapter-protocol.md`; the write hook already lives in
  `using-superpowers/SKILL.md`, which the `SessionStart` hook loads on every
  harness. A separate skill would need description-based triggering, and "I just
  hit friction mid-task" is exactly the moment an agent has no reason to go
  looking for a skill.
- **No migration engine.** The version registry is the seam; there are no older
  registered versions to migrate *from* yet. When v2 lands, it registers a
  validator for v1 and a converter alongside it. Building the engine now, with
  zero real migrations, is speculation.
- **The Obsidian vault's 27 notes.** They use a third format
  (`.agents/observations/`, flat `type: observation`), and migrating them is work
  in that repository, not this one. `migrate_legacy_note` from Task 4 is the
  starting point. Migrate the 13 active notes; leave the 14 archived ones alone —
  archived notes are terminal and nothing filters them, so rewriting them buys
  nothing.
- **Removing `--obs-dir`.** Kept with a deprecation warning; see Task 4's rationale.
- **`plugin.json` and `hooks.json` are untracked** in this working tree. If that
  is unintentional, the `SessionStart` hook does not load on a fresh clone and the
  write hook never fires — worth checking, but it is a separate change from this
  plan.

---

## Self-Review

**Spec coverage.** Lifecycle hygiene → Task 3 (`--tidy` + `quarantine/`). Helper
scripts → Tasks 2-4. Write-without-interrupting → Task 2 (one command, four prose
arguments). Format check on write → Task 2 (`write_observation` raises before
touching disk). No-action notes going straight to archive → Task 2
(`--archive-now`, through the guarded `pending/` move). Mentioning the path in
chat → Task 5, Step 2. Lean skill → Task 5 enforces the existing 500-word budget
and both doc edits are net-negative. Lean implementation → one new 200-line
script, no new dependencies, tests are behavioural rather than exhaustive. Schema
drift → Task 1 (version dispatch, `outdated` status, additive-only rule) and
Task 4 (a real converter proving the seam).

**Placeholder scan.** No TBDs. Every code step carries runnable code; every test
step carries real assertions; every verification step names the command and the
expected output.

**Type consistency.** `classify_observation` returns `tuple[str, list[str]]` in
Task 1 and is destructured as `status, _errors` in Task 3.
`OBSERVATION_VALIDATORS` is the registry name in Tasks 1 and 3.
`build_metadata`'s keyword arguments in Task 2 match its call sites in Tasks 2 and
4. `write_observation` returns `Path` and is asserted as `path.parent.name` in
Task 2. `tidy_observations` returns the three-key report asserted in Task 3.
`store["pending"]`, `store["archived"]`, and `store["root"]` match the existing
`_require_observation_store` keys.
