"""Tests for the eval runner: case discovery, `claude plugin eval`, and `opencode run`."""

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
# A fake `opencode run`: records the call it was handed, then answers. Its own paths and
# score table are baked in, so it needs nothing from the environment the runner passes.
FAKE_OPENCODE = """#!{python}
import json, os, sys
from pathlib import Path

LOG = Path({log!r})
SCORES = {scores}
EXIT_CODE = {exit_code}

argv = sys.argv[1:]
prompt = argv[-1]
work = Path(argv[argv.index("--dir") + 1])
home = Path(os.environ["HOME"])
answer = SCORES.get("default", "0.75")
for needle, value in SCORES.items():
    if needle != "default" and needle in prompt:
        answer = value
skills = {{path.parent.name: path.read_text()
          for path in sorted((work / ".opencode" / "skills").glob("*/SKILL.md"))}}
auth = home / ".local" / "share" / "opencode" / "auth.json"
with LOG.open("a") as handle:
    handle.write(json.dumps({{
        "argv": argv,
        "prompt": prompt,
        "env": dict(os.environ),
        "cwd": os.getcwd(),
        "listing": sorted(os.listdir(work)),
        "skills": skills,
        "auth": str(auth.resolve()) if auth.exists() else None,
    }}) + "\\n")

parts = [{{"type": "text", "text": "Before I write a test, which seam am I testing?"}}]
if "SCORE:" in prompt:
    text = "The transcript meets the criterion."
    if answer not in ("silent", "none"):
        if answer.startswith("after "):
            text += "\\nSCORE: 0\\nSCORE: " + answer[6:]
        else:
            text += "\\nSCORE: " + answer
    parts = [{{"type": "text", "text": text}}]
else:
    parts.append({{"type": "tool", "tool": "read",
                   "state": {{"input": {{"filePath": "app.py"}}, "status": "completed"}}}})
if answer != "silent":
    for part in parts:
        print(json.dumps({{"type": "message.part.updated", "part": part}}))
sys.stderr.write({stderr!r} + "\\n")
sys.exit(EXIT_CODE)
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

    def test_it_reads_a_real_scored_report(self) -> None:
        case = self.root / "evals" / "tdd" / "quality" / "seams-agreed-first"
        shutil.copytree(self.case, case)
        self.fake_cli((FIXTURES / "claude-plugin-eval-scored.json").read_text())
        runner = eval_runner.ClaudePluginEval("haiku")
        self.assertEqual(runner.score(self.skill, [case]), {"seams-agreed-first": 1.0})

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

    def test_a_run_that_is_not_an_object_is_a_failure_not_a_crash(self) -> None:
        self.fake_cli({"partial": False, "cases": [{"name": "red-first", "arms": {"with": ["boom"]}}]})
        with self.assertRaises(eval_runner.EvalFailed):
            self.score()

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


class FakeOpencode:
    """A fake `opencode` on PATH that records every call and answers as an agent or a grader.

    The score table maps a needle in the prompt to the SCORE the grader reports, with
    `default` for any needle that does not match. `silent` prints nothing at all and
    `none` prints an answer with no `SCORE:` line.
    """

    def __init__(self, case: unittest.TestCase, root: Path, *, scores: dict[str, str] | None = None,
                 exit_code: int = 0, stderr: str = "") -> None:
        binary_dir = root / "bin"
        binary_dir.mkdir(exist_ok=True)
        self.log = root / "opencode-calls.jsonl"
        binary = binary_dir / "opencode"
        binary.write_text(FAKE_OPENCODE.format(
            python=sys.executable, log=str(self.log),
            scores=json.dumps(scores if scores is not None else {"default": "0.75"}),
            exit_code=exit_code, stderr=stderr))
        binary.chmod(0o755)
        environment = mock.patch.dict(os.environ, {
            "PATH": f"{binary_dir}{os.pathsep}{os.environ['PATH']}",
            "LEAKED_SETTING": "from the parent environment",
        })
        environment.start()
        case.addCleanup(environment.stop)

    def calls(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines() if line.strip()]

    def agent_calls(self) -> list[dict]:
        return [call for call in self.calls() if "SCORE:" not in call["prompt"]]

    def grader_calls(self) -> list[dict]:
        return [call for call in self.calls() if "SCORE:" in call["prompt"]]


class OpencodeEvalTest(unittest.TestCase):
    """The opencode runner runs each prompt in a work dir of its own and grades the transcript."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.skill = self.root / "skills" / "tdd"
        self.skill.mkdir(parents=True)
        self.skill_md = self.skill / "SKILL.md"
        self.skill_md.write_text(
            "---\nname: tdd\ndescription: Test first.\n---\n\n# tdd\n\nAgree the seam before the test.\n")
        self.case = self.root / "evals" / "tdd" / "quality" / "seams-agreed-first"
        (self.case / "graders").mkdir(parents=True)
        self.write_prompt(self.case, "allowed_tools: [Read, Glob, Grep, Skill]",
                          "Let's do this test-first. I need a `slugify(title)` function. Go.")
        self.write_grader(self.case, "criteria.md", "The response names the seam it intends to test.")
        self.write_grader(self.case, "names-tests.md", "Tests are named by behaviour.")
        self.fake = FakeOpencode(self, self.root)

    def write_prompt(self, case: Path, frontmatter: str, body: str) -> None:
        (case / "prompt.md").write_text(f"---\nmax_turns: 6\n{frontmatter}\n---\n\n{body}\n")

    def write_grader(self, case: Path, name: str, body: str) -> None:
        (case / "graders").mkdir(parents=True, exist_ok=True)
        (case / "graders" / name).write_text(f"---\ntype: llm\nweight: 1\n---\n\n{body}\n")

    def edited_copy(self) -> Path:
        edited = self.root / "edited" / "tdd"
        edited.mkdir(parents=True)
        (edited / "SKILL.md").write_text(
            "---\nname: tdd\ndescription: Test first.\n---\n\n# tdd\n\nWrite the test, then the seam.\n")
        return edited

    def score(self, skill_dir: Path | None = None, cases: list[Path] | None = None,
              runner: eval_runner.OpencodeEval | None = None) -> dict[str, float]:
        runner = eval_runner.OpencodeEval("openrouter/qwen3-max") if runner is None else runner
        return runner.score(self.skill if skill_dir is None else skill_dir,
                            [self.case] if cases is None else cases)

    def agent(self, call: int = 0) -> dict:
        return self.fake.agent_calls()[call]

    def test_it_names_the_cli_the_model_and_the_grader(self) -> None:
        runner = eval_runner.OpencodeEval("openrouter/qwen3-max", grader_model="anthropic/haiku")
        self.assertEqual((runner.cli, runner.model, runner.grader_model),
                         ("opencode", "openrouter/qwen3-max", "anthropic/haiku"))

    def test_the_grader_defaults_to_the_model(self) -> None:
        self.assertEqual(eval_runner.OpencodeEval("openrouter/qwen3-max").grader_model,
                         "openrouter/qwen3-max")

    def test_it_runs_the_documented_command(self) -> None:
        self.score()
        argv = self.agent()["argv"]
        self.assertEqual(argv[:6], ["run", "-m", "openrouter/qwen3-max", "--format", "json", "--dir"])
        self.assertEqual(argv[7], "Let's do this test-first. I need a `slugify(title)` function. Go.")

    def test_the_case_runs_in_the_directory_it_names(self) -> None:
        self.score()
        call = self.agent()
        work = Path(call["argv"][6])
        self.assertEqual(Path(call["cwd"]).resolve(), work.resolve())
        self.assertEqual(call["listing"], [".opencode"])
        self.assertEqual(work.name, "seams-agreed-first")

    def test_the_grader_runs_in_an_empty_directory_of_its_own(self) -> None:
        self.score()
        grader = self.fake.grader_calls()[0]
        work = Path(grader["argv"][6])
        self.assertEqual(Path(grader["cwd"]).resolve(), work.resolve())
        self.assertEqual(grader["listing"], [])
        self.assertNotEqual(work, Path(self.agent()["argv"][6]))

    def test_the_grader_runs_its_own_model(self) -> None:
        self.score(runner=eval_runner.OpencodeEval("openrouter/qwen3-max", grader_model="anthropic/haiku"))
        self.assertEqual(self.agent()["argv"][2], "openrouter/qwen3-max")
        self.assertEqual(self.fake.grader_calls()[0]["argv"][2], "anthropic/haiku")

    def test_it_scores_the_mean_of_the_cases_graders(self) -> None:
        FakeOpencode(self, self.root, scores={"The response names the seam": "1",
                                               "Tests are named by behaviour": "0.5"})
        self.assertEqual(self.score(), {"seams-agreed-first": 0.75})

    def test_the_grader_is_asked_about_the_criterion_without_its_frontmatter(self) -> None:
        self.score()
        prompts = [call["prompt"] for call in self.fake.grader_calls()]
        self.assertEqual(len(prompts), 2)
        self.assertIn("The response names the seam it intends to test.", prompts[0])
        self.assertIn("Tests are named by behaviour.", prompts[1])
        for prompt in prompts:
            self.assertNotIn("weight: 1", prompt)
            self.assertNotIn("type: llm", prompt)
            self.assertIn("SCORE:", prompt)

    def test_the_transcript_carries_the_answer_and_its_tool_calls(self) -> None:
        self.score()
        prompt = self.fake.grader_calls()[0]["prompt"]
        self.assertIn("Before I write a test, which seam am I testing?", prompt)
        self.assertIn('[tool read] {"filePath": "app.py"}', prompt)

    def test_it_stages_the_skill_where_opencode_finds_skills(self) -> None:
        self.score()
        self.assertEqual(list(self.agent()["skills"]), ["tdd"])
        self.assertEqual(self.agent()["skills"]["tdd"], self.skill_md.read_text())

    def test_it_evaluates_the_edited_copy_and_leaves_the_original_alone(self) -> None:
        self.score(self.edited_copy())
        self.assertIn("Write the test, then the seam.", self.agent()["skills"]["tdd"])
        self.assertIn("Agree the seam before the test.", self.skill_md.read_text())

    def test_the_run_gets_a_home_of_its_own(self) -> None:
        self.score()
        env = self.agent()["env"]
        self.assertNotEqual(env["HOME"], str(Path.home()))
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            self.assertTrue(env[name].startswith(env["HOME"]), name)
        self.assertEqual(env["OPENCODE_DISABLE_CLAUDE_CODE"], "1")
        self.assertEqual(env["OPENCODE_DISABLE_AUTOUPDATE"], "1")

    def test_the_run_keeps_the_path_and_drops_the_rest_of_the_environment(self) -> None:
        self.score()
        env = self.agent()["env"]
        self.assertEqual(env["PATH"], os.environ["PATH"])
        self.assertIsNone(env.get("LEAKED_SETTING"))

    def test_the_run_keeps_the_api_keys(self) -> None:
        with mock.patch.dict(os.environ, {"SOME_API_KEY": "kept"}):
            self.score()
        self.assertEqual(self.agent()["env"].get("SOME_API_KEY"), "kept")

    def test_it_links_the_providers_credentials_into_the_isolated_home(self) -> None:
        real = self.root / "real-home"
        auth = real / ".local" / "share" / "opencode" / "auth.json"
        auth.parent.mkdir(parents=True)
        auth.write_text("{}\n")
        with mock.patch.object(Path, "home", return_value=real):
            self.score()
        self.assertEqual(self.agent()["auth"], str(auth.resolve()))

    def test_a_case_that_allows_no_bash_or_edit_denies_both(self) -> None:
        self.score()
        self.assertEqual(json.loads(self.agent()["env"]["OPENCODE_PERMISSION"]),
                         {"bash": "deny", "edit": "deny"})

    def test_a_case_that_allows_both_asks_for_no_permission_at_all(self) -> None:
        self.write_prompt(self.case, "allowed_tools: [Read, Write, Bash]", "Go.")
        self.score()
        self.assertEqual(json.loads(self.agent()["env"]["OPENCODE_PERMISSION"]), {})

    def test_allowed_tools_reads_a_list_of_items_too(self) -> None:
        self.write_prompt(self.case, "allowed_tools:\n  - Read\n  - Write", "Go.")
        self.score()
        self.assertEqual(json.loads(self.agent()["env"]["OPENCODE_PERMISSION"]), {"bash": "deny"})

    def test_a_case_with_no_allowed_tools_denies_both(self) -> None:
        (self.case / "prompt.md").write_text("Just answer the question.\n")
        self.score()
        self.assertEqual(json.loads(self.agent()["env"]["OPENCODE_PERMISSION"]),
                         {"bash": "deny", "edit": "deny"})

    def test_every_case_runs_in_a_work_dir_of_its_own(self) -> None:
        second = self.root / "evals" / "tdd" / "quality" / "one-assertion"
        second.mkdir(parents=True)
        self.write_prompt(second, "allowed_tools: [Read]", "One assertion per test.")
        self.write_grader(second, "criteria.md", "Every test asserts one thing.")
        FakeOpencode(self, self.root, scores={"default": "1"})
        self.assertEqual(self.score(cases=[self.case, second]),
                         {"seams-agreed-first": 1.0, "one-assertion": 1.0})
        work_dirs = [call["argv"][6] for call in self.fake.agent_calls()]
        self.assertEqual(len(work_dirs), 2)
        self.assertEqual(len(set(work_dirs)), 2)

    def test_a_case_without_a_prompt_is_a_failure(self) -> None:
        (self.case / "prompt.md").unlink()
        (self.case / "case.yaml").write_text("name: seams\n")
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertEqual(str(failure.exception),
                         "seams-agreed-first: opencode runs prompt.md cases only")

    def test_a_case_with_no_graders_is_a_failure(self) -> None:
        for grader in (self.case / "graders").iterdir():
            grader.unlink()
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("seams-agreed-first", str(failure.exception))
        self.assertIn("graders", str(failure.exception))

    def test_a_case_that_is_gone_is_a_failure_not_a_crash(self) -> None:
        shutil.rmtree(self.case)
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("seams-agreed-first", str(failure.exception))

    def test_a_grader_that_gives_no_score_is_a_failure(self) -> None:
        FakeOpencode(self, self.root, scores={"default": "none"})
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("seams-agreed-first", str(failure.exception))
        self.assertIn("SCORE", str(failure.exception))

    def test_a_score_outside_zero_to_one_is_a_failure(self) -> None:
        FakeOpencode(self, self.root, scores={"default": "3"})
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("3", str(failure.exception))

    def test_only_the_last_score_line_counts(self) -> None:
        FakeOpencode(self, self.root, scores={"default": "after 0.6"})
        self.assertEqual(self.score(), {"seams-agreed-first": 0.6})

    def test_an_agent_run_that_exits_nonzero_is_a_failure(self) -> None:
        FakeOpencode(self, self.root, exit_code=1, stderr="Error: not logged in")
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("seams-agreed-first", str(failure.exception))
        self.assertIn("not logged in", str(failure.exception))

    def test_an_agent_that_says_nothing_is_a_failure(self) -> None:
        FakeOpencode(self, self.root, scores={"default": "silent"})
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score()
        self.assertIn("seams-agreed-first", str(failure.exception))

    def test_a_cli_that_is_not_there_is_a_failure(self) -> None:
        runner = eval_runner.OpencodeEval("openrouter/qwen3-max", executable="opencode-not-here")
        with self.assertRaises(eval_runner.EvalFailed) as failure:
            self.score(runner=runner)
        self.assertIn("seams-agreed-first", str(failure.exception))


class RunnerSelectionTest(unittest.TestCase):
    """`--cli` names one runner; build_runner is the only place that knows the list."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proposal = Path(self.tmp.name) / "proposal.json"
        self.proposal.write_text("{}")

    def gate(self, *extra: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            code = release_gate.main([str(self.proposal), *extra])
        return code, err.getvalue()

    def test_the_registry_offers_exactly_the_two_clis(self) -> None:
        self.assertEqual(sorted(eval_runner.RUNNERS), ["claude", "opencode"])

    def test_it_builds_a_runner_for_every_known_cli(self) -> None:
        for cli, expected in (("claude", eval_runner.ClaudePluginEval),
                              ("opencode", eval_runner.OpencodeEval)):
            with self.subTest(cli=cli):
                runner = release_gate.build_runner(cli, "some/model")
                self.assertIsInstance(runner, expected)
                self.assertEqual(runner.model, "some/model")

    def test_it_builds_no_runner_when_neither_cli_nor_model_is_named(self) -> None:
        self.assertIsNone(release_gate.build_runner(None, None))

    def test_an_unknown_cli_is_refused_and_names_the_known_ones(self) -> None:
        with self.assertRaises(release_gate.Usage) as refusal:
            release_gate.build_runner("nope", "some/model")
        message = str(refusal.exception)
        self.assertIn("nope", message)
        self.assertIn("claude", message)
        self.assertIn("opencode", message)

    def test_the_gate_exits_two_on_an_unknown_cli(self) -> None:
        code, err = self.gate("--cli", "nope", "--model", "some/model")
        self.assertEqual(code, 2)
        self.assertIn("nope", err)


if __name__ == "__main__":
    unittest.main()
