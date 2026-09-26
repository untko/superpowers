"""Tests for the proposer batch run: prepare, collect, dismiss, against temp fixtures."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import propose
import new_observation
import release_gate
import eval_runner
from adapter_protocol import parse_frontmatter

SKILL_MD = """---
name: {name}
description: Fixture skill.
---

# Fixture

Always run the tests first.
Write one assertion per test.
"""


class Fixture:
    """A library with two skills, a project with one local skill, and a friction log."""

    def __init__(self, root: Path) -> None:
        self.library = root / "library" / "skills"
        self.project = root / "project"
        self.evals = root / "library" / "evals"
        self.project.mkdir(parents=True)
        self.add_skill(self.library / "tdd")
        self.add_skill(self.library / "wayfinder")
        self.add_skill(self.library / "diagnosis")
        self.add_skill(self.project / ".claude" / "skills" / "check-inbox")

    @staticmethod
    def add_skill(skill_dir: Path, text: str | None = None) -> None:
        """Write a skill directory holding one SKILL.md."""
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(text or SKILL_MD.format(name=skill_dir.name))

    def add_cases(self, skill: str, *cases: str) -> None:
        """Create eval cases for a skill; each name is one directory."""
        for case in cases:
            case_dir = self.evals / skill / case
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "prompt.md").write_text("Do the thing.\n")

    def log(self, session: str, kind: str, key: str, skills: list[tuple[str, str]],
            excerpt: str = "boom") -> str:
        """Append a recorder-shaped event to the project's friction log; return its id."""
        event_id = f"{session}:{kind}:{key}"
        log = self.project / ".superpowers" / "friction.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        event = {"id": event_id, "kind": kind, "session_id": session,
                 "skills": [{"name": name, "source": source} for name, source in skills],
                 "excerpt": excerpt}
        with open(log, "a") as handle:
            handle.write(json.dumps(event) + "\n")
        return event_id

    def log_raw(self, line: str) -> None:
        """Append a raw line to the friction log, malformed or not."""
        log = self.project / ".superpowers" / "friction.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a") as handle:
            handle.write(line + "\n")

    def handle(self, *ids: str) -> None:
        """Mark friction ids as already handled."""
        path = self.project / ".superpowers" / "friction-handled.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{event_id}\n" for event_id in ids))


class ProposerTest(unittest.TestCase):
    """Fixture mixin: drive propose.main and read back what it wrote."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fixture = Fixture(self.root)
        self.out = self.root / "work"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def two_sessions(self, skill: str, source: str, *, key: str = "t",
                     before: str | None = None) -> tuple[str, str]:
        """Log the same friction in two sessions, with the named skill loaded last."""
        loaded = ([(before, source)] if before else []) + [(skill, source)]
        return (self.fixture.log("s2", "tool-failure", f"{key}0", loaded),
                self.fixture.log("s3", "tool-failure", f"{key}1", loaded))

    def propose(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            code = propose.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def prepare(self, *extra: str) -> tuple[int, str, str]:
        return self.propose("prepare", "--project", str(self.fixture.project),
                            "--library-root", str(self.fixture.library),
                            "--out", str(self.out), *extra)

    @staticmethod
    def names(printed: str) -> list[str]:
        """The candidate names a prepare run printed, one per line after the work path."""
        return [line.split()[0] for line in printed.split("\n")[1:] if line.strip()
                and not line.startswith("no candidates")]

    def skeleton(self, skill: str) -> dict:
        return json.loads((self.out / "proposals" / f"{skill}.json").read_text())

    def collect(self, skill: str, *extra: str) -> tuple[int, str, str]:
        return self.propose("collect", str(self.out), skill, "--project", str(self.fixture.project),
                            "--library-root", str(self.fixture.library),
                            "--evals-root", str(self.fixture.evals), *extra)

    def workspace(self, skill: str, name: str) -> Path:
        """The agent's copy of one file inside a staged skill."""
        return self.out / "workspace" / skill / name

    def add_reference(self, skill: str, text: str) -> Path:
        """Give a library skill a reference file, so a run can edit it."""
        reference = self.fixture.library / skill / "references" / "mocking.md"
        reference.parent.mkdir(parents=True, exist_ok=True)
        reference.write_text(text)
        return reference


class PrepareTest(ProposerTest):
    def test_two_sessions_of_friction_write_one_skeleton(self) -> None:
        self.two_sessions("tdd", "global")
        code, printed, _ = self.prepare()
        self.assertEqual(code, 0)
        self.assertIn(str(self.out), printed)
        self.assertEqual(self.names(printed), ["tdd"])
        self.assertEqual(self.skeleton("tdd"), {
            "schema": "superpowers-proposal/v1", "skill": "tdd", "scope": "global",
            "operations": [],
            "evidence": [{"type": "friction", "id": "s2:tool-failure:t0"},
                         {"type": "friction", "id": "s3:tool-failure:t1"}],
        })

    def test_a_correction_alone_is_a_candidate(self) -> None:
        self.fixture.log("s1", "correction", "p1", [("tdd", "global")], "stop doing that")
        code, printed, _ = self.prepare()
        self.assertEqual(code, 0)
        self.assertEqual(self.names(printed), ["tdd"])
        self.assertEqual(self.skeleton("tdd")["evidence"],
                         [{"type": "correction", "id": "s1:correction:p1"}])

    def test_one_session_of_tool_failure_is_not_a_candidate(self) -> None:
        self.fixture.log("s2", "tool-failure", "t1", [("tdd", "global")])
        code, printed, _ = self.prepare()
        self.assertEqual(code, 0)
        self.assertEqual(self.names(printed), [])
        self.assertIn("no candidates", printed)
        self.assertEqual(list((self.out / "proposals").iterdir()), [])

    def test_friction_without_a_session_is_not_a_second_session(self) -> None:
        self.fixture.log("s2", "tool-failure", "t1", [("tdd", "global")])
        self.fixture.log_raw(json.dumps({"id": "anon", "kind": "tool-failure",
                                         "skills": [{"name": "tdd", "source": "global"}]}))
        _, printed, _ = self.prepare()
        self.assertIn("no candidates", printed)

    def test_malformed_lines_are_skipped(self) -> None:
        self.two_sessions("tdd", "global")
        self.fixture.log_raw("{not json")
        self.fixture.log_raw(json.dumps(["not an object"]))
        self.assertEqual(self.prepare()[0], 0)
        self.assertEqual(len(self.skeleton("tdd")["evidence"]), 2)

    def test_a_skill_that_does_not_resolve_is_skipped(self) -> None:
        self.two_sessions("ghost", "global")
        self.two_sessions("tdd", "global", key="u")
        code, printed, _ = self.prepare()
        self.assertEqual(code, 0)
        self.assertEqual(self.names(printed), ["tdd"])
        self.assertFalse((self.out / "workspace" / "ghost").exists())

    def test_scope_follows_the_event_source_tag(self) -> None:
        self.two_sessions("tdd", "global")
        self.two_sessions("check-inbox", "local", key="c")
        self.prepare()
        self.assertEqual(self.skeleton("tdd")["scope"], "global")
        self.assertEqual(self.skeleton("check-inbox")["scope"], "local")
        self.assertTrue((self.out / "workspace" / "check-inbox" / "SKILL.md").is_file())

    def test_the_workspace_holds_only_candidate_copies_and_no_evals(self) -> None:
        self.fixture.add_cases("tdd", "red-first")
        self.two_sessions("tdd", "global")
        self.two_sessions("wayfinder", "global", key="w")
        self.prepare()
        self.assertEqual(sorted(path.name for path in (self.out / "workspace").iterdir()),
                         ["tdd", "wayfinder"])
        self.assertEqual(sorted(path.name for path in self.out.iterdir()),
                         [".proposer", "brief.md", "proposals", "workspace"])
        self.assertEqual([path for path in self.out.rglob("evals")], [])
        self.assertEqual((self.out / "workspace" / "tdd" / "SKILL.md").read_text(),
                         (self.fixture.library / "tdd" / "SKILL.md").read_text())

    def test_the_brief_names_the_skill_its_counts_and_its_excerpts(self) -> None:
        self.fixture.log("s1", "tool-failure", "z", [("tdd", "global")], "line one\nline two")
        self.two_sessions("tdd", "global")
        self.fixture.log("s4", "correction", "p9", [("tdd", "global")], "stop doing that")
        self.prepare()
        brief = (self.out / "brief.md").read_text()
        self.assertIn("tdd", brief)
        self.assertIn("global", brief)
        self.assertIn("corrections: 1", brief)
        self.assertIn("sessions: 4", brief)
        self.assertIn("events: 4", brief)
        self.assertIn("- tool-failure: line one line two", brief)
        self.assertIn("- correction: stop doing that", brief)

    def test_brief_excerpts_are_truncated(self) -> None:
        self.two_sessions("tdd", "global")
        self.fixture.log("s4", "tool-failure", "t9", [("tdd", "global")], "x" * 500)
        self.prepare()
        brief = (self.out / "brief.md").read_text()
        self.assertIn("x" * 300 + "\n", brief)
        self.assertNotIn("x" * 301, brief)

    def test_handled_ids_are_skipped(self) -> None:
        first, second = self.two_sessions("tdd", "global")
        third = self.fixture.log("s4", "tool-failure", "t2", [("tdd", "global")])
        self.fixture.handle(third)
        self.prepare()
        self.assertEqual(self.skeleton("tdd")["evidence"],
                         [{"type": "friction", "id": first}, {"type": "friction", "id": second}])

    def test_more_corrections_rank_first(self) -> None:
        self.two_sessions("tdd", "global")
        self.fixture.log("s9", "correction", "q", [("wayfinder", "global")])
        _, printed, _ = self.prepare()
        self.assertEqual(self.names(printed), ["wayfinder", "tdd"])

    def test_more_sessions_rank_second(self) -> None:
        self.two_sessions("tdd", "global")
        self.two_sessions("wayfinder", "global", key="w")
        self.fixture.log("s4", "tool-failure", "w2", [("wayfinder", "global")])
        _, printed, _ = self.prepare()
        self.assertEqual(self.names(printed), ["wayfinder", "tdd"])

    def test_the_most_recently_loaded_skill_ranks_first(self) -> None:
        self.two_sessions("tdd", "global")
        self.two_sessions("wayfinder", "global", key="w", before="tdd")
        _, printed, _ = self.prepare()
        self.assertEqual(self.names(printed), ["tdd", "wayfinder"])

    def test_limit_caps_the_candidates(self) -> None:
        self.two_sessions("wayfinder", "global", key="w")
        self.two_sessions("check-inbox", "local", key="c")
        self.fixture.log("s9", "correction", "q", [("tdd", "global")])
        code, printed, _ = self.prepare("--limit", "1")
        self.assertEqual(code, 0)
        self.assertEqual(self.names(printed), ["tdd"])
        self.assertEqual([path.name for path in (self.out / "proposals").iterdir()], ["tdd.json"])

    def test_a_second_run_replaces_a_work_directory_it_marked(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        (self.out / "brief.md").write_text("stale")
        code, _, _ = self.prepare()
        self.assertEqual(code, 0)
        self.assertNotIn("stale", (self.out / "brief.md").read_text())

    def test_an_unmarked_work_directory_is_refused(self) -> None:
        self.two_sessions("tdd", "global")
        self.out.mkdir()
        (self.out / "notes.txt").write_text("mine")
        code, _, err = self.prepare()
        self.assertEqual(code, 2)
        self.assertIn(str(self.out), err)
        self.assertEqual(sorted(path.name for path in self.out.iterdir()), ["notes.txt"])

    def test_another_projects_log_is_never_read(self) -> None:
        self.fixture.log("s2", "correction", "p2", [("wayfinder", "global")])
        other = self.root / "other"
        other.mkdir()
        log = other / ".superpowers" / "friction.jsonl"
        log.parent.mkdir(parents=True)
        log.write_text(json.dumps({"id": "s2:correction:p3", "kind": "correction",
                                   "session_id": "s2", "skills": [{"name": "ghost", "source": "global"}]}) + "\n")
        self.fixture.add_skill(self.fixture.library / "ghost")
        code, printed, _ = self.prepare()
        self.assertEqual(code, 0)
        self.assertEqual(self.names(printed), ["wayfinder"])
        self.assertFalse((self.out / "workspace" / "ghost").exists())

    def test_the_brief_lists_pending_observations_as_context_only(self) -> None:
        self.two_sessions("tdd", "global")
        new_observation.write_observation(
            self.fixture.project,
            new_observation.build_metadata(
                skill="tdd", phase="delivery", expected="A failing test before the fix.",
                actual="The edit landed without a red test.", evidence="two sessions of friction",
                diagnosis="uncertain", scope="potentially-global", target="skill", runtime={},
                provenance={}, adapter=None),
            "The edit landed without a red test.\n\nIt passed on the first run.",
            now="2026-09-26-101112")
        self.prepare()
        brief = (self.out / "brief.md").read_text()
        self.assertIn("Pending observations (context, not evidence):", brief)
        self.assertIn("2026-09-26-101112-the-edit-landed-without-a-red-test: "
                      "The edit landed without a red test.", brief)
        self.assertEqual(self.skeleton("tdd")["evidence"],
                         [{"type": "friction", "id": "s2:tool-failure:t0"},
                          {"type": "friction", "id": "s3:tool-failure:t1"}])

    def test_the_work_directory_defaults_into_the_project(self) -> None:
        self.two_sessions("tdd", "global")
        code, printed, _ = self.propose("prepare", "--project", str(self.fixture.project),
                                        "--library-root", str(self.fixture.library))
        default = self.fixture.project / ".superpowers" / "proposer"
        self.assertEqual((code, printed.split("\n")[0]), (0, str(default.resolve())))
        self.assertTrue((default / "proposals" / "tdd.json").is_file())

    def test_the_default_limit_is_three(self) -> None:
        for skill in ("tdd", "wayfinder", "diagnosis"):
            self.two_sessions(skill, "global", key=skill)
        self.two_sessions("check-inbox", "local", key="c")
        code, printed, _ = self.prepare()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.names(printed)), 3)
        self.assertEqual(len(list((self.out / "proposals").iterdir())), 3)

    def test_a_limit_below_one_is_refused(self) -> None:
        self.two_sessions("tdd", "global")
        code, _, err = self.prepare("--limit", "0")
        self.assertEqual(code, 2)
        self.assertIn("--limit", err)
        self.assertFalse(self.out.exists())


class NamedSkillTest(ProposerTest):
    """A skill your human partner names is staged without friction; a case is its evidence."""

    def test_a_named_skill_is_staged_without_friction(self) -> None:
        code, printed, _ = self.prepare("--skill", "wayfinder")
        self.assertEqual(code, 0)
        self.assertEqual(self.names(printed), ["wayfinder"])
        self.assertEqual(self.skeleton("wayfinder")["evidence"], [])
        self.assertEqual(self.skeleton("wayfinder")["scope"], "global")
        self.assertTrue(self.workspace("wayfinder", "SKILL.md").is_file())
        self.assertIn("named by your human partner", (self.out / "brief.md").read_text())

    def test_a_named_skill_stages_only_that_skill(self) -> None:
        self.two_sessions("tdd", "global")
        _, printed, _ = self.prepare("--skill", "wayfinder")
        self.assertEqual(self.names(printed), ["wayfinder"])
        self.assertFalse((self.out / "workspace" / "tdd").exists())

    def test_a_named_skill_keeps_its_own_friction_as_evidence(self) -> None:
        first, second = self.two_sessions("tdd", "global")
        self.prepare("--skill", "tdd")
        self.assertEqual(self.skeleton("tdd")["evidence"],
                         [{"type": "friction", "id": first}, {"type": "friction", "id": second}])

    def test_a_named_local_skill_resolves_in_the_project(self) -> None:
        code, printed, _ = self.prepare("--skill", "check-inbox", "--scope", "local")
        self.assertEqual((code, self.names(printed)), (0, ["check-inbox"]))
        self.assertEqual(self.skeleton("check-inbox")["scope"], "local")

    def test_a_named_skill_that_does_not_resolve_is_refused(self) -> None:
        code, _, err = self.prepare("--skill", "nowhere")
        self.assertEqual(code, 2)
        self.assertIn("nowhere", err)
        self.assertFalse(self.out.exists())

    def test_a_cited_case_is_the_evidence_the_gate_accepts(self) -> None:
        self.fixture.add_cases("wayfinder", "strict-csp")
        self.prepare("--skill", "wayfinder")
        self.workspace("wayfinder", "references/csp.md").parent.mkdir(parents=True)
        self.workspace("wayfinder", "references/csp.md").write_text("Allow connect-src self.\n")
        code, printed, _ = self.collect("wayfinder", "--case", "strict-csp")
        report = json.loads(printed)
        self.assertEqual((code, report["passed"]), (0, True), report)
        self.assertEqual(self.skeleton("wayfinder")["evidence"], [{"type": "case", "id": "strict-csp"}])

    def test_a_case_is_cited_once_across_collects(self) -> None:
        self.fixture.add_cases("wayfinder", "strict-csp")
        self.prepare("--skill", "wayfinder")
        self.workspace("wayfinder", "references/csp.md").parent.mkdir(parents=True)
        self.workspace("wayfinder", "references/csp.md").write_text("Allow connect-src self.\n")
        self.collect("wayfinder", "--case", "strict-csp")
        self.collect("wayfinder", "--case", "strict-csp")
        self.assertEqual(self.skeleton("wayfinder")["evidence"], [{"type": "case", "id": "strict-csp"}])

    def test_a_named_skill_without_a_case_is_insufficient(self) -> None:
        self.prepare("--skill", "wayfinder")
        self.workspace("wayfinder", "references/csp.md").parent.mkdir(parents=True)
        self.workspace("wayfinder", "references/csp.md").write_text("Allow connect-src self.\n")
        code, printed, _ = self.collect("wayfinder")
        self.assertEqual((code, json.loads(printed)["reason"]), (1, "insufficient-evidence"))

    def test_a_case_that_does_not_exist_is_insufficient(self) -> None:
        self.prepare("--skill", "wayfinder")
        self.workspace("wayfinder", "references/csp.md").parent.mkdir(parents=True)
        self.workspace("wayfinder", "references/csp.md").write_text("Allow connect-src self.\n")
        code, printed, _ = self.collect("wayfinder", "--case", "missing")
        self.assertEqual((code, json.loads(printed)["reason"]), (1, "insufficient-evidence"))


class CollectTest(ProposerTest):
    def test_a_new_reference_file_writes_a_proposal_the_static_gate_accepts(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").parent.mkdir(parents=True)
        self.workspace("tdd", "references/mocking.md").write_text("Mock at boundaries.\n")
        code, printed, _ = self.collect("tdd")
        report = json.loads(printed)
        self.assertEqual(code, 0)
        self.assertEqual((report["passed"], report["kind"]), (True, "static"), report)
        self.assertEqual(self.skeleton("tdd")["operations"],
                         [{"op": "add", "file": "references/mocking.md", "to": "Mock at boundaries."}])
        self.assertEqual(self.skeleton("tdd")["evidence"],
                         [{"type": "friction", "id": "s2:tool-failure:t0"},
                          {"type": "friction", "id": "s3:tool-failure:t1"}])

    def test_a_changed_line_becomes_one_change_operation(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "SKILL.md").write_text(
            SKILL_MD.format(name="tdd").replace("Always run the tests first.",
                                               "Always run the failing test first."))
        code, printed, _ = self.collect("tdd")
        self.assertEqual((code, json.loads(printed)["kind"]), (1, "rule-change"))
        self.assertEqual(self.skeleton("tdd")["operations"], [{
            "op": "change", "file": "SKILL.md",
            "line": "Always run the tests first.", "to": "Always run the failing test first."}])

    def test_wording_claims_a_skill_md_change_and_saves_the_static_check(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "SKILL.md").write_text(
            SKILL_MD.format(name="tdd").replace("Always run the tests first.",
                                               "Always run the failing test first."))
        code, printed, _ = self.collect("tdd", "--wording")
        report = json.loads(printed)
        self.assertEqual((code, report["passed"], report["kind"]), (0, True, "static"), report)
        self.assertEqual(report["review"], ["wording-only claim: 'Always run the tests first.' -> "
                                            "'Always run the failing test first.'"])
        self.assertTrue(self.skeleton("tdd")["operations"][0]["wording"])

    def test_wording_never_claims_a_reference_change(self) -> None:
        self.add_reference("tdd", "Mock at boundaries.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").write_text("Mock at the boundary.\n")
        code, _, _ = self.collect("tdd", "--wording")
        operation = self.skeleton("tdd")["operations"][0]
        self.assertEqual(code, 0)
        self.assertNotIn("wording", operation)

    def test_lines_added_at_the_end_append_in_order(self) -> None:
        self.add_reference("tdd", "Mock at boundaries.\nPrefer fakes.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").write_text(
            "Mock at boundaries.\nPrefer fakes.\nStub the clock.\nFreeze the time.\n")
        code, _, _ = self.collect("tdd")
        self.assertEqual(code, 0)
        self.assertEqual(self.skeleton("tdd")["operations"], [
            {"op": "add", "file": "references/mocking.md", "to": "Stub the clock."},
            {"op": "add", "file": "references/mocking.md", "to": "Freeze the time."}])

    def test_lines_added_above_a_blank_line_anchor_after_the_line_above(self) -> None:
        self.add_reference("tdd", "Mock at boundaries.\n\nPrefer fakes.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").write_text(
            "Mock at boundaries.\nStub the clock.\nFreeze the time.\n\nPrefer fakes.\n")
        code, out, err = self.collect("tdd")
        self.assertEqual(code, 0, err + out)
        self.assertEqual([operation.get("after") for operation in self.skeleton("tdd")["operations"]],
                         ["Mock at boundaries.", "Mock at boundaries."])

    def test_a_removed_line_becomes_a_remove_operation(self) -> None:
        self.add_reference("tdd", "Mock at boundaries.\nPrefer fakes.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").write_text("Mock at boundaries.\n")
        code, _, _ = self.collect("tdd")
        self.assertEqual(code, 0)
        self.assertEqual(self.skeleton("tdd")["operations"],
                         [{"op": "remove", "file": "references/mocking.md", "line": "Prefer fakes."}])

    def test_removed_lines_before_a_change_keep_their_order(self) -> None:
        self.add_reference("tdd", "Gone soon.\nStays.\nAlso gone.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").write_text("Stays.\n")
        code, _, _ = self.collect("tdd")
        self.assertEqual(code, 0)
        self.assertEqual([operation["op"] for operation in self.skeleton("tdd")["operations"]],
                         ["remove", "remove"])

    def test_a_line_appearing_twice_is_refused(self) -> None:
        self.fixture.library.joinpath("tdd", "SKILL.md").write_text(
            SKILL_MD.format(name="tdd") + "Keep it small.\nKeep it small.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "SKILL.md").write_text(
            SKILL_MD.format(name="tdd") + "Keep it small.\nKeep it tiny.\nKeep it small.\n")
        code, _, err = self.collect("tdd")
        self.assertEqual(code, 2)
        self.assertIn("SKILL.md", err)
        self.assertIn("make the edited lines unique, or edit fewer lines", err)
        self.assertEqual(self.skeleton("tdd")["operations"], [])

    def test_a_line_added_after_a_blank_line_anchors_on_the_next_line(self) -> None:
        self.add_reference("tdd", "Mock at boundaries.\n\nPrefer fakes.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").write_text(
            "Mock at boundaries.\n\nStub the clock.\n\nPrefer fakes.\n")
        code, out, err = self.collect("tdd")
        self.assertEqual(code, 0, err + out)
        self.assertEqual(self.skeleton("tdd")["operations"], [
            {"op": "add", "file": "references/mocking.md", "before": "Prefer fakes.", "to": "Stub the clock."},
            {"op": "add", "file": "references/mocking.md", "before": "Prefer fakes.", "to": ""},
        ])

    def test_a_new_markdown_file_with_blank_lines_is_proposed(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").parent.mkdir(parents=True)
        self.workspace("tdd", "references/mocking.md").write_text("# Mocking\n\nMock at boundaries.\n")
        code, out, err = self.collect("tdd")
        self.assertEqual(code, 0, err + out)
        self.assertEqual([operation["to"] for operation in self.skeleton("tdd")["operations"]],
                         ["# Mocking", "", "Mock at boundaries."])

    def test_a_line_added_above_the_first_line_anchors_before_it(self) -> None:
        self.add_reference("tdd", "Mock at boundaries.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").write_text("# Mocking\n\nMock at boundaries.\n")
        code, out, err = self.collect("tdd")
        self.assertEqual(code, 0, err + out)

    def test_an_insert_below_an_earlier_growing_hunk_is_anchored_on_the_edited_file(self) -> None:
        self.add_reference("tdd", "One.\nTwo.\nThree.\nFour.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").write_text(
            "One.\nOne and a half.\nOne and two thirds.\nTwo.\nThree.\nThree and a half.\nFour.\n")
        code, out, err = self.collect("tdd")
        self.assertEqual(code, 0, err + out)

    def test_a_removed_blank_line_is_refused(self) -> None:
        self.add_reference("tdd", "Mock at boundaries.\n\nPrefer fakes.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").write_text(
            "Mock at boundaries.\nPrefer fakes.\n")
        code, _, err = self.collect("tdd")
        self.assertEqual(code, 2)
        self.assertIn("blank line", err)
        self.assertEqual(self.skeleton("tdd")["operations"], [])

    def test_a_deleted_file_is_refused(self) -> None:
        self.add_reference("tdd", "Mock at boundaries.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").unlink()
        code, _, err = self.collect("tdd")
        self.assertEqual(code, 2)
        self.assertIn("references/mocking.md", err)
        self.assertEqual(self.skeleton("tdd")["operations"], [])

    def test_no_edit_at_all_is_refused(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        code, _, err = self.collect("tdd")
        self.assertEqual(code, 2)
        self.assertIn("no edit in workspace", err)
        self.assertEqual(self.skeleton("tdd")["operations"], [])

    def test_the_original_skill_is_never_touched(self) -> None:
        self.add_reference("tdd", "Mock at boundaries.\n")
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").write_text("Mock at the boundary.\n")
        before = self.fixture.library.joinpath("tdd", "references/mocking.md").read_text()
        self.collect("tdd")
        self.assertEqual(self.fixture.library.joinpath("tdd", "references/mocking.md").read_text(),
                         before)

    def test_collecting_a_skill_that_was_never_staged_is_refused(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        code, _, err = self.collect("wayfinder")
        self.assertEqual(code, 2)
        self.assertIn("wayfinder", err)

    def test_a_cli_without_a_model_is_refused(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "references/mocking.md").parent.mkdir(parents=True)
        self.workspace("tdd", "references/mocking.md").write_text("Mock at boundaries.\n")
        code, _, err = self.collect("tdd", "--cli", "claude")
        self.assertEqual(code, 2)
        self.assertIn("go together", err)

    def test_an_unsupported_cli_is_refused(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        code, _, err = self.collect("tdd", "--cli", "codex", "--model", "gpt-5")
        self.assertEqual(code, 2)
        self.assertIn("unsupported CLI", err)
        self.assertEqual(self.skeleton("tdd")["operations"], [])

    def test_a_runner_is_built_and_the_report_prints(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        self.workspace("tdd", "SKILL.md").write_text(
            SKILL_MD.format(name="tdd").replace("Always run the tests first.",
                                               "Always run the failing test first."))
        stub = mock.Mock(cli="claude", model="sonnet", score=lambda *_: {})
        factory = mock.Mock(return_value=stub)
        with mock.patch.dict(eval_runner.RUNNERS, {"claude": factory}):
            code, printed, _ = self.collect("tdd", "--cli", "claude", "--model", "sonnet")
        self.assertEqual((code, factory.call_args), (1, mock.call("sonnet")))
        self.assertEqual(json.loads(printed)["reason"], "untested")


class DismissTest(ProposerTest):
    def dismiss(self, skill: str, *extra: str) -> tuple[int, str, str]:
        return self.propose("dismiss", str(self.out), skill,
                            "--project", str(self.fixture.project), *extra)

    def test_dismiss_records_the_evidence_and_removes_the_staged_copy(self) -> None:
        first, second = self.two_sessions("tdd", "global")
        self.prepare()
        code, printed, _ = self.dismiss("tdd")
        self.assertEqual(code, 0)
        self.assertIn("tdd", printed)
        self.assertFalse((self.out / "proposals" / "tdd.json").exists())
        self.assertFalse((self.out / "workspace" / "tdd").exists())
        self.assertEqual(self.fixture.project.joinpath(".superpowers", "friction-handled.txt")
                         .read_text().split(), [first, second])

    def test_dismissed_friction_is_not_proposed_again(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        self.dismiss("tdd")
        self.fixture.log("s2", "correction", "p9", [("wayfinder", "global")])
        _, printed, _ = self.prepare()
        self.assertEqual(self.names(printed), ["wayfinder"])
        self.assertEqual([path.name for path in (self.out / "proposals").iterdir()],
                         ["wayfinder.json"])

    def test_dismissing_a_skill_that_was_never_staged_is_refused(self) -> None:
        self.two_sessions("tdd", "global")
        self.prepare()
        code, _, err = self.dismiss("wayfinder")
        self.assertEqual(code, 2)
        self.assertIn("wayfinder", err)
        self.assertFalse((self.fixture.project / ".superpowers" / "friction-handled.txt").exists())


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
FROZEN_LINES = ("No skill without a failing test.", "Never violate path boundaries.")


class SkillDocumentTest(unittest.TestCase):
    """The skill body an agent follows: short, anchored, and pointing at its references."""

    def setUp(self) -> None:
        self.limits = release_gate._limits(SKILL)

    def test_the_body_stays_under_its_budget(self) -> None:
        self.assertLess(len(self.limits.body.split()), 450)

    def test_every_frozen_anchor_is_declared_and_kept_verbatim(self) -> None:
        self.assertEqual(self.limits.anchors, {
            "failing-test": FROZEN_LINES[0], "path-boundaries": FROZEN_LINES[1]})
        body = {line.strip() for line in self.limits.body.splitlines()}
        for line in FROZEN_LINES:
            self.assertIn(line, body)

    def test_the_body_runs_the_three_commands_of_the_loop(self) -> None:
        for command in ("prepare", "collect", "dismiss"):
            self.assertIn(f"scripts/propose.py\" {command}", self.limits.body)

    def test_the_description_names_its_triggers(self) -> None:
        metadata, _body = parse_frontmatter(SKILL.read_text())
        self.assertEqual(metadata["name"], "evolving-skills")
        for trigger in ("evolving skills", "friction", "proposal"):
            self.assertIn(trigger, str(metadata["description"]).lower())

    def test_the_rejection_cheat_sheet_is_reachable(self) -> None:
        self.assertIn("references/proposer.md", self.limits.body)
        self.assertTrue((SKILL.parent / "references" / "proposer.md").is_file())


if __name__ == "__main__":
    unittest.main()
