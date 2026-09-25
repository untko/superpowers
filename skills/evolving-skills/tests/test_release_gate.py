"""Tests for the release gate at seam B: fixture proposals against fixture skills."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import json
import os
from unittest import mock

import release_gate

SKILL_MD = """---
name: {name}
description: Fixture skill.
---

# Fixture

Always run the tests first.
Write one assertion per test.
"""


class Fixture:
    """A library with one global skill and a project with one local skill."""

    def __init__(self, root: Path) -> None:
        self.library = root / "library" / "skills"
        self.project = root / "project"
        self.evals = root / "library" / "evals"
        self.add_skill(self.library / "tdd")
        self.add_skill(self.project / ".claude" / "skills" / "check-inbox")
        self.log_friction("s1", "correction", "p1")

    def log_friction(self, session: str, kind: str, key: str, skills=("tdd", "check-inbox")) -> str:
        """Append a recorder-shaped event to the project's friction log; return its id."""
        event_id = f"{session}:{kind}:{key}"
        log = self.project / ".superpowers" / "friction.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        event = {"id": event_id, "kind": kind, "session_id": session,
                 "skills": [{"name": name, "source": "global"} for name in skills]}
        with open(log, "a") as handle:
            handle.write(json.dumps(event) + "\n")
        return event_id

    @staticmethod
    def add_skill(skill_dir: Path, text: str | None = None) -> None:
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(text or SKILL_MD.format(name=skill_dir.name))

    def check(self, proposal: dict) -> release_gate.Report:
        return release_gate.check(
            proposal, library_root=self.library, project=self.project, evals_root=self.evals
        )


def proposal(skill: str = "tdd", scope: str | None = "global", **overrides) -> dict:
    result = {
        "schema": "superpowers-proposal/v1",
        "skill": skill,
        "scope": scope,
        "operations": [
            {
                "op": "change",
                "file": "SKILL.md",
                "line": "Always run the tests first.",
                "to": "Always run the failing test first.",
                "wording": True,
            }
        ],
        "evidence": [{"type": "correction", "id": "s1:correction:p1"}],
    }
    if scope is None:
        del result["scope"]
    result.update(overrides)
    return result


class ScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_scope_is_rejected(self) -> None:
        self.assertEqual(self.fixture.check(proposal(scope=None)).reason, "scope")

    def test_global_scope_for_repo_skill_is_rejected(self) -> None:
        report = self.fixture.check(proposal(skill="check-inbox", scope="global"))
        self.assertEqual(report.reason, "scope")

    def test_local_scope_for_library_skill_is_rejected(self) -> None:
        self.assertEqual(self.fixture.check(proposal(scope="local")).reason, "scope")

    def test_project_link_to_library_skill_is_global(self) -> None:
        link = self.fixture.project / ".claude" / "skills" / "linked"
        (self.fixture.library / "linked").mkdir()
        (self.fixture.library / "linked" / "SKILL.md").write_text(SKILL_MD.format(name="linked"))
        link.symlink_to(self.fixture.library / "linked")
        self.assertEqual(self.fixture.check(proposal(skill="linked", scope="local")).reason, "scope")

    def test_matching_scopes_pass(self) -> None:
        self.assertTrue(self.fixture.check(proposal()).passed)
        self.assertTrue(self.fixture.check(proposal(skill="check-inbox", scope="local")).passed)


class ItemizedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_wholesale_replacement_is_rejected(self) -> None:
        whole = SKILL_MD.format(name="tdd").replace("first", "last")
        rewrite = [{"op": "replace", "file": "SKILL.md", "to": whole}]
        self.assertEqual(self.fixture.check(proposal(operations=rewrite)).reason, "not-itemized")

    def test_multi_line_operation_is_rejected(self) -> None:
        op = {"op": "add", "file": "SKILL.md", "after": "Write one assertion per test.",
              "to": "Name tests by behaviour.\nKeep them fast."}
        self.assertEqual(self.fixture.check(proposal(operations=[op])).reason, "not-itemized")

    def test_missing_operations_are_rejected(self) -> None:
        self.assertEqual(self.fixture.check(proposal(operations=[])).reason, "not-itemized")


class EvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def cite(self, *evidence: tuple[str, str]) -> release_gate.Report:
        cited = [{"type": kind, "id": event_id} for kind, event_id in evidence]
        return self.fixture.check(proposal(evidence=cited))

    def test_friction_from_one_session_is_insufficient(self) -> None:
        first = self.fixture.log_friction("s2", "tool-failure", "t1")
        second = self.fixture.log_friction("s2", "tool-failure", "t2")
        report = self.cite(("friction", first), ("friction", second))
        self.assertEqual(report.reason, "insufficient-evidence")

    def test_friction_from_two_sessions_is_sufficient(self) -> None:
        first = self.fixture.log_friction("s2", "tool-failure", "t1")
        second = self.fixture.log_friction("s3", "tool-failure", "t1")
        self.assertTrue(self.cite(("friction", first), ("friction", second)).passed)

    def test_one_correction_is_sufficient(self) -> None:
        self.assertTrue(self.cite(("correction", "s1:correction:p1")).passed)

    def test_one_failing_case_is_sufficient(self) -> None:
        cases = self.fixture.evals / "tdd"
        cases.mkdir(parents=True)
        (cases / "skips-red.json").write_text("{}")
        self.assertTrue(self.cite(("case", "skips-red")).passed)

    def test_unknown_ids_are_not_evidence(self) -> None:
        self.assertEqual(self.cite(("correction", "s9:correction:nope")).reason,
                         "insufficient-evidence")
        self.assertEqual(self.cite(("case", "no-such-case")).reason, "insufficient-evidence")

    def test_friction_mislabelled_as_correction_is_not_a_correction(self) -> None:
        failure = self.fixture.log_friction("s2", "tool-failure", "t1")
        self.assertEqual(self.cite(("correction", failure)).reason, "insufficient-evidence")

    def test_friction_about_another_skill_is_not_evidence(self) -> None:
        other = self.fixture.log_friction("s2", "correction", "p2", skills=("wayfinder",))
        self.assertEqual(self.cite(("correction", other)).reason, "insufficient-evidence")


ANCHORED_MD = """---
name: tdd
description: Fixture skill.
metadata:
  frozen:
    red-first: "Always run the tests first."
  word-budget: {budget}
---

# Fixture

Always run the tests first.
Write one assertion per test.
"""


class AnchorAndBudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.tmp.name))
        self.skill_md = self.fixture.library / "tdd" / "SKILL.md"
        self.skill_md.write_text(ANCHORED_MD.format(budget=40))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def edit(self, *operations: dict) -> release_gate.Report:
        return self.fixture.check(proposal(operations=list(operations)))

    def test_rewording_an_anchor_is_rejected(self) -> None:
        report = self.edit({"op": "change", "file": "SKILL.md",
                            "line": "Always run the tests first.", "to": "Run tests when convenient."})
        self.assertEqual(report.reason, "anchor")
        self.assertIn("red-first", report.detail)

    def test_deleting_an_anchor_is_rejected(self) -> None:
        report = self.edit({"op": "remove", "file": "SKILL.md", "line": "Always run the tests first."})
        self.assertEqual(report.reason, "anchor")

    def test_dropping_an_anchor_declaration_is_rejected(self) -> None:
        report = self.edit({"op": "remove", "file": "SKILL.md",
                            "line": 'red-first: "Always run the tests first."'})
        self.assertEqual(report.reason, "anchor")

    def test_editing_around_an_anchor_passes(self) -> None:
        report = self.edit({"op": "change", "file": "SKILL.md", "wording": True,
                            "line": "Write one assertion per test.", "to": "Assert one behaviour per test."})
        self.assertTrue(report.passed, report)

    def test_growing_past_the_budget_is_rejected(self) -> None:
        long_rule = " ".join(["word"] * 20)
        report = self.edit({"op": "add", "file": "SKILL.md",
                            "after": "Write one assertion per test.", "to": long_rule})
        self.assertEqual(report.reason, "budget")

    def test_shrinking_a_skill_already_over_budget_passes(self) -> None:
        self.skill_md.write_text(ANCHORED_MD.format(budget=10))
        report = self.edit({"op": "remove", "file": "SKILL.md", "line": "Write one assertion per test."})
        self.assertEqual(report.reason, "eval-skipped", report)

    def test_raising_the_budget_is_rejected(self) -> None:
        report = self.edit({"op": "change", "file": "SKILL.md",
                            "line": "word-budget: 40", "to": "word-budget: 4000"})
        self.assertEqual(report.reason, "budget")

    def test_default_budget_is_500_words(self) -> None:
        self.skill_md.write_text(SKILL_MD.format(name="tdd"))
        report = self.edit({"op": "add", "file": "SKILL.md", "to": " ".join(["word"] * 500)})
        self.assertEqual(report.reason, "budget")

    def test_operation_on_a_missing_line_is_rejected(self) -> None:
        report = self.edit({"op": "remove", "file": "SKILL.md", "line": "No such rule."})
        self.assertEqual(report.reason, "not-itemized")

    def test_operation_outside_the_skill_is_rejected(self) -> None:
        report = self.edit({"op": "add", "file": "../other/SKILL.md", "to": "Sneaky rule."})
        self.assertEqual(report.reason, "scope")

    def test_the_skill_itself_is_never_modified(self) -> None:
        before = self.skill_md.read_text()
        self.edit({"op": "remove", "file": "SKILL.md", "line": "Write one assertion per test."})
        self.assertEqual(self.skill_md.read_text(), before)


PASSING_TEST = """import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import tool


class ToolTest(unittest.TestCase):
    def test_answer(self):
        self.assertEqual(tool.answer(), 42)
"""


class StaticGateTest(unittest.TestCase):
    """Criterion 11: static edits get static checks only and never start a model."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.fixture = Fixture(root)
        skill = self.fixture.library / "tdd"
        (skill / "references").mkdir()
        (skill / "references" / "mocking.md").write_text("# Mocking\n\nMock at boundaries.\n")
        (skill / "scripts").mkdir()
        (skill / "scripts" / "tool.py").write_text("def answer():\n    return 42\n")
        (skill / "tests").mkdir()
        (skill / "tests" / "test_tool.py").write_text(PASSING_TEST)
        self.trap_log = root / "model-calls.log"
        traps = root / "bin"
        traps.mkdir()
        for name in ("claude", "codex", "gemini", "opencode", "cursor-agent"):
            trap = traps / name
            trap.write_text(f"#!/bin/sh\necho {name} >> '{self.trap_log}'\n")
            trap.chmod(0o755)
        path = mock.patch.dict(os.environ, {"PATH": f"{traps}{os.pathsep}{os.environ['PATH']}"})
        path.start()
        self.addCleanup(path.stop)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def edit(self, *operations: dict) -> release_gate.Report:
        return self.fixture.check(proposal(operations=list(operations)))

    def assert_no_model_started(self) -> None:
        self.assertFalse(self.trap_log.exists(), "a model CLI was started")

    def test_reference_edit_is_static_and_passes(self) -> None:
        report = self.edit({"op": "add", "file": "references/mocking.md",
                            "after": "Mock at boundaries.", "to": "Prefer fakes to mocks."})
        self.assertTrue(report.passed, report)
        self.assertEqual(report.kind, "static")
        self.assertEqual(report.checks, ["scope", "itemized", "evidence", "anchor", "budget", "links"])
        self.assert_no_model_started()

    def test_script_edit_runs_the_skills_own_tests(self) -> None:
        report = self.edit({"op": "change", "file": "scripts/tool.py",
                            "line": "return 42", "to": "return 6 * 7"})
        self.assertTrue(report.passed, report)
        self.assertIn("script-tests", report.checks)
        self.assert_no_model_started()

    def test_script_edit_that_breaks_its_tests_is_rejected(self) -> None:
        report = self.edit({"op": "change", "file": "scripts/tool.py",
                            "line": "return 42", "to": "return 41"})
        self.assertEqual(report.reason, "script-tests")
        self.assert_no_model_started()

    def test_broken_link_is_rejected(self) -> None:
        report = self.edit({"op": "add", "file": "SKILL.md", "wording": True,
                            "after": "Write one assertion per test.",
                            "to": "See [mocking](references/mocks.md)."})
        self.assertEqual(report.reason, "links")

    def test_links_to_files_and_sibling_skills_resolve(self) -> None:
        Fixture.add_skill(self.fixture.library / "debugging")
        report = self.edit({"op": "change", "file": "SKILL.md", "wording": True,
                            "line": "Write one assertion per test.",
                            "to": "Write one assertion per test ([why](references/mocking.md#top), "
                                  "[debugging](../debugging/SKILL.md), [web](https://example.com))."})
        self.assertTrue(report.passed, report)

    def test_claimed_rewording_is_static_and_flagged_for_review(self) -> None:
        report = self.edit({"op": "change", "file": "SKILL.md", "wording": True,
                            "line": "Always run the tests first.", "to": "Always run the failing test first."})
        self.assertTrue(report.passed, report)
        self.assertEqual(report.kind, "static")
        self.assertEqual(report.review, ["wording-only claim: 'Always run the tests first.' -> "
                                         "'Always run the failing test first.'"])

    def test_rule_change_stops_before_eval_without_a_runner(self) -> None:
        report = self.edit({"op": "add", "file": "SKILL.md",
                            "after": "Write one assertion per test.", "to": "Name tests by behaviour."})
        self.assertFalse(report.passed)
        self.assertEqual(report.kind, "rule-change")
        self.assertEqual((report.reason, report.detail), ("eval-skipped", "no runner chosen"))
        self.assert_no_model_started()

    def test_unflagged_skill_md_change_is_a_rule_change(self) -> None:
        report = self.edit({"op": "change", "file": "SKILL.md",
                            "line": "Always run the tests first.", "to": "Always run the failing test first."})
        self.assertEqual(report.kind, "rule-change")

    def test_command_line_prints_the_report_and_exits_nonzero_on_reject(self) -> None:
        path = Path(self.tmp.name) / "proposal.json"
        path.write_text(json.dumps(proposal(scope="local")))
        with mock.patch("sys.stdout") as stdout:
            code = release_gate.main([str(path), "--project", str(self.fixture.project),
                                      "--library-root", str(self.fixture.library),
                                      "--evals-root", str(self.fixture.evals)])
        printed = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(printed)["reason"], "scope")


if __name__ == "__main__":
    unittest.main()
