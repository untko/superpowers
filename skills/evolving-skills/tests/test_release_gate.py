"""Tests for the release gate at seam B: fixture proposals against fixture skills."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import eval_runner
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

    def add_cases(self, skill: str, *cases: str) -> None:
        """Create eval cases for a skill; each name is one directory, nested or not."""
        for case in cases:
            case_dir = self.evals / skill / case
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "prompt.md").write_text("Do the thing.\n")

    def check(self, proposal: dict, runner=None) -> release_gate.Report:
        return release_gate.check(
            proposal, library_root=self.library, project=self.project, evals_root=self.evals,
            runner=runner,
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

    def test_unknown_schema_is_rejected(self) -> None:
        self.assertEqual(self.fixture.check(proposal(schema="superpowers-proposal/v9")).reason, "schema")

    def test_missing_operations_are_rejected(self) -> None:
        self.assertEqual(self.fixture.check(proposal(operations=[])).reason, "not-itemized")


class EvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def cite(self, *evidence: tuple[str, str]) -> release_gate.Report:
        """Check with a runner under which every case fails without the edit and passes with it."""
        cited = [{"type": kind, "id": event_id} for kind, event_id in evidence]
        return self.fixture.check(proposal(evidence=cited), runner=FixingRunner())

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
        self.fixture.add_cases("tdd", "skips-red")
        self.assertTrue(self.cite(("case", "skips-red")).passed)

    def test_a_cited_case_without_a_runner_is_unscored(self) -> None:
        self.fixture.add_cases("tdd", "skips-red")
        cited = [{"type": "case", "id": "skips-red"}]
        self.assertEqual(self.fixture.check(proposal(evidence=cited)).reason, "eval-skipped")

    def test_a_case_is_a_directory_not_a_file_stem(self) -> None:
        cases = self.fixture.evals / "tdd"
        cases.mkdir(parents=True)
        (cases / "skips-red.json").write_text("{}")
        (cases / "skips-red").mkdir()
        self.assertEqual(self.cite(("case", "skips-red")).reason, "insufficient-evidence")

    def test_a_nested_case_directory_is_still_a_case(self) -> None:
        self.fixture.add_cases("tdd", "quality/skips-red")
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
        self.skill_md.write_text(ANCHORED_MD.format(budget=25))

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

    def test_growth_within_the_budget_passes_the_budget_check(self) -> None:
        report = self.edit({"op": "add", "file": "SKILL.md", "to": "Keep tests fast."})
        self.assertIn("budget", report.checks)

    def test_shrinking_a_skill_already_over_budget_passes(self) -> None:
        self.skill_md.write_text(ANCHORED_MD.format(budget=10))
        report = self.edit({"op": "remove", "file": "SKILL.md", "line": "Write one assertion per test."})
        self.assertEqual(report.reason, "eval-skipped", report)

    def test_frontmatter_does_not_count_against_the_budget(self) -> None:
        self.skill_md.write_text(ANCHORED_MD.format(budget=14))  # body is 12 words
        report = self.edit({"op": "add", "file": "SKILL.md", "to": "Keep tests fast."})
        self.assertEqual(report.reason, "budget")
        self.assertIn("15 words", report.detail)

    def test_raising_the_budget_is_rejected(self) -> None:
        report = self.edit({"op": "change", "file": "SKILL.md",
                            "line": "word-budget: 25", "to": "word-budget: 4000"})
        self.assertEqual(report.reason, "budget")

    def test_default_budget_is_500_words(self) -> None:
        self.skill_md.write_text(SKILL_MD.format(name="tdd"))
        report = self.edit({"op": "add", "file": "SKILL.md", "to": " ".join(["word"] * 500)})
        self.assertEqual(report.reason, "budget")

    def test_a_blank_line_may_be_written_but_never_named(self) -> None:
        written = self.edit({"op": "add", "file": "SKILL.md", "before": "Write one assertion per test.", "to": ""})
        self.assertIn("itemized", written.checks)
        for anchor in ({"after": " "}, {"before": ""}):
            report = self.edit({"op": "add", "file": "SKILL.md", "to": "Rule.", **anchor})
            self.assertEqual(report.reason, "not-itemized")

    def test_an_add_takes_one_anchor(self) -> None:
        report = self.edit({"op": "add", "file": "SKILL.md", "to": "Rule.",
                            "after": "Write one assertion per test.", "before": "Always run the tests first."})
        self.assertEqual(report.reason, "not-itemized")

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


class ScriptedSkill:
    """Fixture mixin: `tdd` with references, a script and its test; model CLIs trapped on PATH."""

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


class StaticGateTest(ScriptedSkill, unittest.TestCase):
    """Criterion 11: static edits get static checks only and never start a model."""

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


RULE_CHANGE = {"op": "add", "file": "SKILL.md", "after": "Write one assertion per test.",
               "to": "Name tests by behaviour."}
REFERENCE_EDIT = {"op": "add", "file": "references/mocking.md", "after": "Mock at boundaries.",
                  "to": "Prefer fakes to mocks."}


class StubRunner:
    """Answers from a per-arm table and records the skill copy and cases it was handed."""

    cli = "stub-cli"
    model = "stub-model"

    def __init__(self, without: dict[str, float] | None = None, with_edit: dict[str, float] | None = None,
                 failure: str | None = None) -> None:
        if with_edit is None:
            with_edit = without
        self.arms = [without or {}, with_edit or {}]
        self.failure = failure
        self.calls: list[tuple[Path, str, tuple[str, ...]]] = []

    def score(self, skill_dir: Path, cases: list[Path]) -> dict[str, float]:
        self.calls.append((skill_dir, (skill_dir / "SKILL.md").read_text(),
                           tuple(case.name for case in cases)))
        if self.failure is not None:
            raise eval_runner.EvalFailed(self.failure)
        return {case.name: self.arms[len(self.calls) - 1][case.name] for case in cases}


class FixingRunner(StubRunner):
    """Every case scores 0.0 on the original skill and 1.0 on the edited copy."""

    def score(self, skill_dir: Path, cases: list[Path]) -> dict[str, float]:
        self.calls.append((skill_dir, (skill_dir / "SKILL.md").read_text(),
                           tuple(case.name for case in cases)))
        return {case.name: float(len(self.calls) % 2 == 0) for case in cases}


class CitedCaseTest(unittest.TestCase):
    """A cited case is evidence only when it fails without the edit and improves with it."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.tmp.name))
        self.fixture.add_cases("tdd", "skips-red", "other")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def cite(self, runner, operations=None, *extra: dict) -> release_gate.Report:
        evidence = [{"type": "case", "id": "skips-red"}, *extra]
        overrides = {"evidence": evidence}
        if operations is not None:
            overrides["operations"] = operations
        return self.fixture.check(proposal(**overrides), runner=runner)

    def test_a_case_that_already_passes_is_not_evidence(self) -> None:
        report = self.cite(StubRunner(without={"skips-red": 1.0}, with_edit={"skips-red": 1.0}))
        self.assertEqual(report.reason, "case-unproven")
        self.assertIn("skips-red", report.detail)
        self.assertIn("without", report.detail)

    def test_a_case_the_edit_does_not_improve_is_not_evidence(self) -> None:
        report = self.cite(StubRunner(without={"skips-red": 0.5}, with_edit={"skips-red": 0.5}))
        self.assertEqual(report.reason, "case-unproven")
        self.assertIn("skips-red", report.detail)

    def test_a_case_the_edit_fixes_is_evidence_and_is_reported(self) -> None:
        report = self.cite(StubRunner(without={"skips-red": 0.0}, with_edit={"skips-red": 1.0}))
        self.assertTrue(report.passed, report)
        self.assertEqual(report.eval["cases"],
                         {"skips-red": {"without": 0.0, "with": 1.0, "delta": 1.0}})

    def test_a_static_edit_scores_only_the_cited_case(self) -> None:
        runner = StubRunner(without={"skips-red": 0.0}, with_edit={"skips-red": 1.0})
        self.cite(runner)
        self.assertEqual([call[2] for call in runner.calls], [("skips-red",), ("skips-red",)])

    def test_a_rule_change_reuses_its_scores_for_the_cited_case(self) -> None:
        runner = StubRunner(without={"skips-red": 1.0, "other": 0.5},
                            with_edit={"skips-red": 1.0, "other": 0.5})
        report = self.cite(runner, [RULE_CHANGE])
        self.assertEqual(report.reason, "case-unproven")
        self.assertEqual(len(runner.calls), 2)

    def test_a_correction_does_not_excuse_an_unproven_case(self) -> None:
        report = self.cite(StubRunner(without={"skips-red": 1.0}),
                           None, {"type": "correction", "id": "s1:correction:p1"})
        self.assertEqual(report.reason, "case-unproven")

    def test_a_correction_alone_needs_no_runner(self) -> None:
        self.assertTrue(self.fixture.check(proposal()).passed)


class RuleChangeEvalTest(ScriptedSkill, unittest.TestCase):
    """Criteria 12-14: a rule change is scored on every case, before and after the edit."""

    def setUp(self) -> None:
        super().setUp()
        self.fixture.add_cases("tdd", "red-first", "writes-one-test")
        self.runner = StubRunner(without={"red-first": 0.25, "writes-one-test": 0.5},
                                 with_edit={"red-first": 0.75, "writes-one-test": 0.5})

    def rule_change(self, runner: StubRunner | None = None) -> release_gate.Report:
        return self.fixture.check(proposal(operations=[RULE_CHANGE]),
                                  runner=self.runner if runner is None else runner)

    def test_a_passing_rule_change_reports_both_scores(self) -> None:
        report = self.rule_change()
        self.assertTrue(report.passed, report)
        self.assertEqual(report.kind, "rule-change")
        self.assertEqual(report.eval, {
            "cli": "stub-cli",
            "model": "stub-model",
            "cases": {
                "red-first": {"without": 0.25, "with": 0.75, "delta": 0.5},
                "writes-one-test": {"without": 0.5, "with": 0.5, "delta": 0.0},
            },
        })
        self.assertIn("eval", report.checks)
        self.assert_no_model_started()

    def test_every_case_runs_once_on_each_arm(self) -> None:
        self.rule_change()
        self.assertEqual(len(self.runner.calls), 2)
        original, edited = self.runner.calls
        self.assertEqual(original[0], self.fixture.library / "tdd")
        self.assertNotIn("Name tests by behaviour.", original[1])
        self.assertNotEqual(edited[0], original[0])
        self.assertIn("Name tests by behaviour.", edited[1])
        for _, _, case_ids in self.runner.calls:
            self.assertEqual(case_ids, ("red-first", "writes-one-test"))
        self.assert_no_model_started()

    def test_a_skill_with_no_cases_is_untested(self) -> None:
        shutil.rmtree(self.fixture.evals / "tdd")
        report = self.rule_change()
        self.assertEqual(report.reason, "untested")
        self.assertIsNone(report.eval)
        self.assertEqual(self.runner.calls, [])

    def test_a_lower_with_edit_score_is_a_regression(self) -> None:
        runner = StubRunner(without={"red-first": 0.75, "writes-one-test": 0.5},
                            with_edit={"red-first": 0.5, "writes-one-test": 0.75})
        report = self.rule_change(runner)
        self.assertEqual((report.reason, report.detail), ("regression", "score fell on: red-first"))
        self.assertEqual(report.eval["cases"], {
            "red-first": {"without": 0.75, "with": 0.5, "delta": -0.25},
            "writes-one-test": {"without": 0.5, "with": 0.75, "delta": 0.25},
        })

    def test_a_rule_change_that_breaks_its_scripts_is_rejected_before_any_eval(self) -> None:
        report = self.fixture.check(proposal(operations=[
            RULE_CHANGE,
            {"op": "change", "file": "scripts/tool.py", "line": "return 42", "to": "return 41"},
        ]), runner=self.runner)
        self.assertEqual(report.reason, "script-tests")
        self.assertEqual(self.runner.calls, [])

    def test_two_cases_with_one_id_are_an_eval_failure_even_as_evidence(self) -> None:
        self.fixture.add_cases("tdd", "quality/dup", "triggering/dup")
        report = self.fixture.check(proposal(operations=[RULE_CHANGE],
                                             evidence=[{"type": "case", "id": "dup"}]),
                                    runner=self.runner)
        self.assertEqual(report.reason, "eval-failed")
        self.assertIn("dup", report.detail)

    def test_a_runner_failure_is_never_a_score_of_zero(self) -> None:
        report = self.rule_change(StubRunner(failure="auth_failed"))
        self.assertEqual((report.reason, report.detail), ("eval-failed", "auth_failed"))
        self.assertIsNone(report.eval)

    def test_a_static_edit_never_calls_the_runner(self) -> None:
        report = self.fixture.check(proposal(operations=[REFERENCE_EDIT]), runner=self.runner)
        self.assertTrue(report.passed, report)
        self.assertIsNone(report.eval)
        self.assertEqual(self.runner.calls, [])

    def test_a_nested_case_is_found_and_scored(self) -> None:
        self.fixture.add_cases("tdd", "quality/one-assertion")
        scores = {"one-assertion": 0.5, "red-first": 0.5, "writes-one-test": 0.5}
        report = self.rule_change(StubRunner(without=scores, with_edit=scores))
        self.assertTrue(report.passed, report)
        self.assertEqual(sorted(report.eval["cases"]), sorted(scores))


class CommandLineEvalTest(ScriptedSkill, unittest.TestCase):
    """The CLI and model are named in pairs, on the command line."""

    def gate(self, *extra: str, operations=(REFERENCE_EDIT,)) -> tuple[int, str, str]:
        path = Path(self.tmp.name) / "proposal.json"
        path.write_text(json.dumps(proposal(operations=list(operations))))
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            code = release_gate.main([str(path), "--project", str(self.fixture.project),
                                      "--library-root", str(self.fixture.library),
                                      "--evals-root", str(self.fixture.evals), *extra])
        return code, out.getvalue(), err.getvalue()

    def test_a_cli_without_a_model_is_refused(self) -> None:
        code, _, err = self.gate("--cli", "claude")
        self.assertEqual(code, 2)
        self.assertIn("go together", err)

    def test_a_model_without_a_cli_is_refused(self) -> None:
        code, _, err = self.gate("--model", "sonnet")
        self.assertEqual(code, 2)
        self.assertIn("go together", err)

    def test_an_unsupported_cli_is_refused(self) -> None:
        code, _, err = self.gate("--cli", "codex", "--model", "gpt-5")
        self.assertEqual(code, 2)
        self.assertIn("unsupported CLI", err)

    def test_naming_a_cli_and_a_model_builds_the_runner(self) -> None:
        factory = mock.Mock()
        with mock.patch.dict(eval_runner.RUNNERS, {"claude": factory}):
            code, printed, _ = self.gate("--cli", "claude", "--model", "sonnet")
        self.assertEqual(code, 0)
        self.assertEqual(factory.call_args, mock.call("sonnet"))
        self.assertIsNone(json.loads(printed)["eval"])

    def test_the_runner_reaches_the_gate_and_its_scores_the_report(self) -> None:
        self.fixture.add_cases("tdd", "red-first")
        stub = StubRunner(without={"red-first": 0.25}, with_edit={"red-first": 0.75})
        with mock.patch.dict(eval_runner.RUNNERS, {"claude": mock.Mock(return_value=stub)}):
            code, printed, _ = self.gate("--cli", "claude", "--model", "sonnet",
                                         operations=(RULE_CHANGE,))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(printed)["eval"], {
            "cli": "stub-cli", "model": "stub-model",
            "cases": {"red-first": {"without": 0.25, "with": 0.75, "delta": 0.5}},
        })

    def test_without_a_runner_a_rule_change_still_stops(self) -> None:
        self.fixture.add_cases("tdd", "red-first")
        code, printed, _ = self.gate(operations=(RULE_CHANGE,))
        self.assertEqual((code, json.loads(printed)["reason"]), (1, "eval-skipped"))


class HardeningTest(ScriptedSkill, unittest.TestCase):
    """Review findings: inputs that once slipped past or crashed the gate."""

    def test_dot_dot_into_skill_md_is_a_rule_change(self) -> None:
        report = self.edit({"op": "add", "file": "references/../SKILL.md",
                            "after": "Write one assertion per test.", "to": "Never write tests."})
        self.assertEqual(report.kind, "rule-change")
        self.assertFalse(report.passed)

    def test_rule_change_never_runs_proposed_code(self) -> None:
        marker = Path(self.tmp.name) / "ran"
        report = self.edit(
            {"op": "add", "file": "tests/test_evil.py", "to": f"open({str(marker)!r}, 'w').write('x')"},
            {"op": "change", "file": "scripts/tool.py", "line": "return 42", "to": "return 6 * 7"},
        )
        self.assertEqual(report.reason, "eval-skipped")
        self.assertFalse(marker.exists())

    def test_directory_target_is_rejected(self) -> None:
        for file in ("references", "."):
            report = self.edit({"op": "add", "file": file, "to": "x"})
            self.assertEqual(report.reason, "not-itemized", file)

    def test_symlinked_file_cannot_be_edited_through(self) -> None:
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text("Outside line.\n")
        (self.fixture.library / "tdd" / "references" / "shared.md").symlink_to(outside)
        report = self.edit({"op": "add", "file": "references/shared.md", "to": "Injected."})
        self.assertEqual(report.reason, "scope")

    def test_dangling_symlink_does_not_crash(self) -> None:
        (self.fixture.library / "tdd" / "references" / "gone.md").symlink_to("/nonexistent/x.md")
        report = self.edit({"op": "add", "file": "references/mocking.md", "to": "Prefer fakes."})
        self.assertTrue(report.passed, report)

    def test_friction_without_a_session_is_not_a_second_session(self) -> None:
        log = self.fixture.project / ".superpowers" / "friction.jsonl"
        with open(log, "a") as handle:
            handle.write(json.dumps({"id": "anon", "kind": "tool-failure",
                                     "skills": [{"name": "tdd", "source": "global"}]}) + "\n")
        real = self.fixture.log_friction("s2", "tool-failure", "t1")
        report = self.fixture.check(proposal(evidence=[{"type": "friction", "id": real},
                                                       {"type": "friction", "id": "anon"}]))
        self.assertEqual(report.reason, "insufficient-evidence")

    def test_link_outside_the_skills_directory_is_rejected(self) -> None:
        report = self.edit({"op": "add", "file": "references/mocking.md",
                            "to": "[log](../../../../project/.superpowers/friction.jsonl)"})
        self.assertEqual(report.reason, "links")

    def test_rewording_frontmatter_is_a_rule_change(self) -> None:
        report = self.edit({"op": "change", "file": "SKILL.md", "wording": True,
                            "line": "description: Fixture skill.", "to": "description: Load for all work."})
        self.assertEqual(report.kind, "rule-change")

    def test_command_line_reports_an_unreadable_proposal(self) -> None:
        path = Path(self.tmp.name) / "broken.json"
        path.write_text("{not json")
        with mock.patch("sys.stdout"), mock.patch("sys.stderr") as stderr:
            code = release_gate.main([str(path)])
        self.assertEqual(code, 2)
        self.assertIn("broken.json", "".join(c.args[0] for c in stderr.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
