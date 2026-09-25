"""Tests for the eval runner: case discovery, and `claude plugin eval` behind a fake CLI."""

from __future__ import annotations

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

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAKE_CLAUDE = """#!{python}
import os, shutil, sys
from pathlib import Path

argv = sys.argv[1:]
shutil.copytree(argv[2], Path(os.environ["FAKE_CLAUDE_KEEP"]), symlinks=True)
Path(os.environ["FAKE_CLAUDE_ARGV"]).write_text("\\n".join(argv))
report = Path(os.environ["FAKE_CLAUDE_REPORT"])
if not report.exists():
    sys.exit("Error: Not logged in")
Path(argv[argv.index("--json") + 1]).write_text(report.read_text())
sys.exit({exit_code})
"""


def scored(cases: dict[str, float]) -> dict:
    """A report shaped like a real `claude plugin eval --json` run."""
    return {"partial": False, "cases": [
        {"name": name, "dir": f"evals/{name}",
         "arms": {"with": [{"score": score, "passed": score == 1.0, "turns": 1}]}}
        for name, score in cases.items()
    ]}


class FindCasesTest(unittest.TestCase):
    """A case is a directory under `evals/<skill>/`, named by its own directory."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.evals = Path(self.tmp.name) / "evals"

    def case(self, *parts: str, marker: str = "prompt.md") -> Path:
        case = self.evals.joinpath(*parts)
        case.mkdir(parents=True)
        (case / marker).write_text("Do the thing.\n")
        return case

    def test_a_skill_with_no_eval_directory_has_no_cases(self) -> None:
        self.assertEqual(eval_runner.find_cases(self.evals, "tdd"), [])

    def test_a_prompt_directory_is_a_case(self) -> None:
        case = self.case("tdd", "red-first")
        self.assertEqual(eval_runner.find_cases(self.evals, "tdd"), [case])

    def test_a_case_yaml_directory_is_a_case(self) -> None:
        case = self.case("tdd", "one-assertion", marker="case.yaml")
        self.assertEqual(eval_runner.find_cases(self.evals, "tdd"), [case])

    def test_cases_are_found_under_category_directories(self) -> None:
        triggering = self.case("tdd", "triggering", "loads-on-a-bug")
        quality = self.case("tdd", "quality", "names-tests-by-behaviour")
        self.assertEqual(eval_runner.find_cases(self.evals, "tdd"), [triggering, quality])

    def test_cases_come_back_in_id_order(self) -> None:
        second = self.case("tdd", "writes-one-test")
        first = self.case("tdd", "red-first")
        self.assertEqual(eval_runner.find_cases(self.evals, "tdd"), [first, second])

    def test_another_skills_cases_are_not_borrowed(self) -> None:
        self.case("diagnosing-bugs", "red-first")
        self.assertEqual(eval_runner.find_cases(self.evals, "tdd"), [])

    def test_a_directory_without_a_prompt_is_not_a_case(self) -> None:
        (self.evals / "tdd" / "graders").mkdir(parents=True)
        (self.evals / "tdd" / "graders" / "criteria.md").write_text("The test came first.\n")
        self.assertEqual(eval_runner.find_cases(self.evals, "tdd"), [])

    def test_a_loose_file_named_like_a_case_is_not_a_case(self) -> None:
        (self.evals / "tdd").mkdir(parents=True)
        (self.evals / "tdd" / "red-first.json").write_text("{}")
        self.assertEqual(eval_runner.find_cases(self.evals, "tdd"), [])

    def test_two_cases_with_one_id_fail(self) -> None:
        self.case("tdd", "triggering", "red-first")
        self.case("tdd", "quality", "red-first")
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            eval_runner.find_cases(self.evals, "tdd")
        self.assertIn("red-first", str(failure.exception))


class FakeClaude:
    """A fake `claude` on PATH that keeps the staged plugin and writes a canned report."""

    def __init__(self, case: unittest.TestCase, root: Path, report: str, exit_code: int = 1) -> None:
        binary_dir = root / "bin"
        binary_dir.mkdir(exist_ok=True)
        binary = binary_dir / "claude"
        binary.write_text(FAKE_CLAUDE.format(python=sys.executable, exit_code=exit_code))
        binary.chmod(0o755)
        self.argv_log = root / "argv.log"
        self.plugin = root / "staged-plugin"
        self.report = root / "report.json"
        self.report.write_text(report)
        path = mock.patch.dict(os.environ, {
            "PATH": f"{binary_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_CLAUDE_ARGV": str(self.argv_log),
            "FAKE_CLAUDE_KEEP": str(self.plugin),
            "FAKE_CLAUDE_REPORT": str(self.report),
        })
        path.start()
        case.addCleanup(path.stop)

    def argv(self) -> list[str]:
        return self.argv_log.read_text().splitlines()


class ClaudePluginEvalTest(unittest.TestCase):
    """The v1 runner stages a throwaway plugin and reads the report the CLI leaves behind."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.skill = self.root / "skills" / "tdd"
        self.skill.mkdir(parents=True)
        self.skill_md = self.skill / "SKILL.md"
        self.skill_md.write_text("# tdd\n\nAlways run the failing test first.\n")
        self.case = self.root / "evals" / "tdd" / "red-first"
        (self.case / "graders").mkdir(parents=True)
        (self.case / "prompt.md").write_text("Fix the failing test.\n")
        (self.case / "graders" / "criteria.md").write_text("The test came first.\n")
        self.fake = self.fake_cli(scored({"red-first": 0.75}))

    def fake_cli(self, report: str | dict, exit_code: int = 1) -> FakeClaude:
        return FakeClaude(self, self.root, json.dumps(report) if isinstance(report, dict) else report,
                          exit_code)

    def edited_copy(self) -> Path:
        edited = self.root / "edited" / "tdd"
        edited.mkdir(parents=True)
        (edited / "SKILL.md").write_text("# tdd\n\nAlways run the test before the code.\n")
        return edited

    def score(self, skill_dir: Path | None = None) -> dict[str, float]:
        runner = eval_runner.ClaudePluginEval("sonnet")
        return runner.score(self.skill if skill_dir is None else skill_dir, [self.case])

    def test_it_names_the_cli_and_the_model(self) -> None:
        runner = eval_runner.ClaudePluginEval("sonnet", executable="claude")
        self.assertEqual((runner.cli, runner.model), ("claude", "sonnet"))

    def test_it_runs_the_documented_command(self) -> None:
        self.score()
        argv = self.fake.argv()
        self.assertEqual(argv[:2], ["plugin", "eval"])
        self.assertEqual(Path(argv[2]).name, "plugin")
        self.assertEqual(argv[3:9], ["--ablation", "none", "--runs", "1", "--model", "sonnet"])
        self.assertEqual(argv[9], "--json")
        self.assertEqual(Path(argv[10]).name, "result.json")
        self.assertEqual(Path(argv[10]).parent, Path(argv[2]).parent)
        self.assertEqual(argv[11:], ["--no-publish", "--trust-plugin"])

    def test_it_stages_the_skill_and_its_cases_in_a_throwaway_plugin(self) -> None:
        self.score()
        staged = self.fake.plugin
        manifest = json.loads((staged / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual((manifest["name"], manifest["version"]), ("tdd-eval", "0.0.0"))
        self.assertEqual((staged / "skills" / "tdd" / "SKILL.md").read_text(), self.skill_md.read_text())
        self.assertEqual((staged / "evals" / "red-first" / "prompt.md").read_text(),
                         "Fix the failing test.\n")
        self.assertEqual((staged / "evals" / "red-first" / "graders" / "criteria.md").read_text(),
                         "The test came first.\n")

    def test_it_evaluates_the_edited_copy_and_leaves_the_original_alone(self) -> None:
        self.score(self.edited_copy())
        staged = (self.fake.plugin / "skills" / "tdd" / "SKILL.md").read_text()
        self.assertIn("before the code", staged)
        self.assertEqual(self.skill_md.read_text(), "# tdd\n\nAlways run the failing test first.\n")

    def test_it_returns_the_reported_score(self) -> None:
        self.assertEqual(self.score(), {"red-first": 0.75})

    def test_a_score_is_the_mean_of_the_cases_runs(self) -> None:
        report = scored({"red-first": 0.0})
        report["cases"][0]["arms"]["with"].append({"score": 1.0, "passed": True})
        self.fake_cli(report)
        self.assertEqual(self.score(), {"red-first": 0.5})

    def test_it_returns_only_the_cases_it_was_asked_for(self) -> None:
        self.fake_cli(scored({"red-first": 0.75, "writes-one-test": 0.25}))
        self.assertEqual(self.score(), {"red-first": 0.75})

    def test_a_nonzero_exit_still_returns_the_scores(self) -> None:
        self.fake_cli(scored({"red-first": 0.75}), exit_code=1)
        self.assertEqual(self.score(), {"red-first": 0.75})

    def test_a_missing_report_is_a_failure(self) -> None:
        self.fake.report.unlink()
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("no readable eval report", str(failure.exception))

    def test_a_missing_report_carries_what_the_cli_said(self) -> None:
        self.fake.report.unlink()
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("Not logged in", str(failure.exception))

    def test_an_unreadable_report_is_a_failure(self) -> None:
        self.fake_cli("{not json")
        with self.assertRaises(eval_runner.EvalFailed):
            self.score()

    def test_a_partial_run_is_a_failure_naming_its_reason(self) -> None:
        report = json.loads((FIXTURES / "claude-plugin-eval-auth-failed.json").read_text())
        self.assertTrue(report["partial"])
        self.fake_cli(report)
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("auth_failed", str(failure.exception))

    def test_a_failed_run_is_never_a_score_of_zero(self) -> None:
        report = scored({"red-first": 0.0})
        report["cases"][0]["arms"]["with"][0]["error"] = "exit 1: Not logged in · Please run /login"
        self.fake_cli(report)
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("red-first", str(failure.exception))
        self.assertIn("Not logged in", str(failure.exception))

    def test_a_missing_case_is_a_failure(self) -> None:
        self.fake_cli(scored({"writes-one-test": 0.75}))
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("red-first", str(failure.exception))

    def test_a_case_that_is_gone_is_a_failure_not_a_crash(self) -> None:
        shutil.rmtree(self.case)
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("red-first", str(failure.exception))


if __name__ == "__main__":
    unittest.main()
