#!/usr/bin/env python3
"""Deterministic release gate: validate a skill-edit proposal before any eval runs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from adapter_protocol import parse_frontmatter
from eval_runner import ClaudePluginEval, EvalFailed, Runner, find_cases

SCHEMA = "superpowers-proposal/v1"
PROJECT_SKILL_DIRS = (".claude/skills", ".agents/skills")
FRICTION_LOG = Path(".superpowers") / "friction.jsonl"
MIN_FRICTION_SESSIONS = 2
DEFAULT_WORD_BUDGET = 500
SCRIPT_TEST_TIMEOUT = 300
# Each operation names one line; the fields it must carry, all single-line text.
OPERATION_FIELDS = {"add": ("file", "to"), "change": ("file", "line", "to"), "remove": ("file", "line")}
# Edits confined to these directories cannot change what the skill tells an agent to do.
STATIC_DIRS = ("references", "scripts")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


@dataclass
class Report:
    passed: bool
    kind: str | None = None  # "static" or "rule-change", once the operations apply
    reason: str | None = None
    detail: str = ""
    checks: list[str] = field(default_factory=list)  # checks passed, in order
    review: list[str] = field(default_factory=list)  # claims a human must confirm
    eval: dict | None = None  # cli, model, and per-case scores, once an eval has run


@dataclass(frozen=True)
class Limits:
    """What a SKILL.md declares about itself: frozen anchors (name to line) and word budget."""

    anchors: dict[str, str]
    budget: int
    body: str


class Rejected(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail


class Usage(Exception):
    """A command line the script refuses, with no verdict of its own."""


def _safe_name(value: object) -> bool:
    """One path segment: no separators, not hidden, not empty."""
    return isinstance(value, str) and bool(value) and "/" not in value and not value.startswith(".")


def _skill_dir(name: object, scope: object, library_root: Path, project: Path) -> Path | None:
    """The skill's directory in the repo its scope names, or None if it lives elsewhere."""
    if not _safe_name(name):
        return None
    if scope == "global":
        candidates = [library_root / name]
    elif scope == "local":
        candidates = [project / d / name for d in PROJECT_SKILL_DIRS]
    else:
        return None
    library = library_root.resolve()
    for candidate in candidates:
        # A project link into the library is still a library skill.
        in_library = candidate.resolve().is_relative_to(library)
        if (candidate / "SKILL.md").is_file() and in_library == (scope == "global"):
            return candidate
    return None


def _single_line(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "\n" not in value and "\r" not in value


def _itemized(operations: object) -> bool:
    """A non-empty list of add/change/remove operations, each touching one line."""
    if not isinstance(operations, list) or not operations:
        return False
    for operation in operations:
        if not isinstance(operation, dict):
            return False
        fields = OPERATION_FIELDS.get(operation.get("op"))
        if fields is None or not all(_single_line(operation.get(f)) for f in fields):
            return False
        if "after" in operation and not _single_line(operation["after"]):
            return False
    return True


def _friction_about(skill: str, project: Path) -> dict[str, dict]:
    """Events in the project's friction log attributed to this skill, by id."""
    events = {}
    try:
        with open(project / FRICTION_LOG, encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                skills = event.get("skills") if isinstance(event, dict) else None
                if isinstance(skills, list) and any(
                    isinstance(s, dict) and s.get("name") == skill for s in skills
                ):
                    events[event.get("id")] = event
    except OSError:
        pass
    return events


def _has_case(skill: str, case_id: object, evals_root: Path) -> bool:
    if not _safe_name(case_id):
        return False
    return any(case.name == case_id for case in find_cases(evals_root, skill))


def _sufficient_evidence(skill: str, evidence: object, project: Path, evals_root: Path) -> bool:
    """A correction, a failing case, or friction from at least two sessions, all verifiable."""
    if not isinstance(evidence, list):
        return False
    friction = _friction_about(skill, project)
    sessions = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        kind, item_id = item.get("type"), item.get("id")
        if kind == "case" and _has_case(skill, item_id, evals_root):
            return True
        event = friction.get(item_id) if isinstance(item_id, str) else None
        if event is None:
            continue
        if kind == "correction" and event.get("kind") == "correction":
            return True
        if kind == "friction" and _single_line(event.get("session_id")):
            sessions.add(event["session_id"])
    return len(sessions) >= MIN_FRICTION_SESSIONS


def _normalized(operation: dict, skill_copy: Path) -> dict:
    """The operation with `file` resolved to a plain path inside the skill."""
    target = (skill_copy / operation["file"]).resolve()
    root = skill_copy.resolve()
    if not target.is_relative_to(root):
        raise Rejected("scope", f"{operation['file']} is outside the skill")
    if target == root or target.is_dir():
        raise Rejected("not-itemized", f"{operation['file']} is a directory")
    return {**operation, "file": target.relative_to(root).as_posix()}


def _only_line(lines: list[str], text: str, file: str) -> int:
    matches = [i for i, line in enumerate(lines) if line.strip() == text.strip()]
    if len(matches) != 1:
        found = "no" if not matches else f"{len(matches)}"
        raise Rejected("not-itemized", f"{file}: {found} lines read {text!r}")
    return matches[0]


def _apply(operation: dict, skill_copy: Path) -> None:
    """Apply one line operation to the working copy, keeping the edited line's indentation."""
    target = skill_copy / operation["file"]
    exists = target.is_file()
    if not exists and not (operation["op"] == "add" and "after" not in operation):
        raise Rejected("not-itemized", f"{operation['file']} does not exist")
    lines = target.read_text(encoding="utf-8").splitlines() if exists else []
    if operation["op"] == "add":
        after = operation.get("after")
        index = len(lines) if after is None else _only_line(lines, after, operation["file"]) + 1
        lines.insert(index, operation["to"])
    else:
        index = _only_line(lines, operation["line"], operation["file"])
        if operation["op"] == "remove":
            del lines[index]
        else:
            indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
            lines[index] = indent + operation["to"].strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _limits(skill_md: Path) -> Limits:
    try:
        metadata, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    except ValueError as error:
        raise Rejected("anchor", f"frontmatter unreadable, anchors unknown: {error}") from error
    extra = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    frozen = extra.get("frozen") if isinstance(extra.get("frozen"), dict) else {}
    budget = extra.get("word-budget", DEFAULT_WORD_BUDGET)
    if not isinstance(budget, int) or isinstance(budget, bool):
        raise Rejected("budget", f"word-budget must be an integer, got {budget!r}")
    return Limits({k: str(v) for k, v in frozen.items()}, budget, body)


def _check_anchors(before: Limits, after: Limits) -> None:
    if after.anchors != before.anchors:
        changed = sorted({k for k, _ in set(before.anchors.items()) ^ set(after.anchors.items())})
        raise Rejected("anchor", f"anchor declarations changed: {', '.join(changed)}")
    body = {line.strip() for line in after.body.splitlines()}
    lost = [name for name, line in before.anchors.items() if line.strip() not in body]
    if lost:
        raise Rejected("anchor", f"frozen anchor edited or removed: {', '.join(lost)}")


def _check_budget(before: Limits, after: Limits) -> None:
    """Hold the SKILL.md body to its budget; a skill already over it may shrink but not grow."""
    if after.budget != before.budget:
        raise Rejected("budget", f"word budget changed from {before.budget} to {after.budget}")
    words_before, words_after = len(before.body.split()), len(after.body.split())
    if words_after > before.budget and words_after > words_before:
        raise Rejected("budget", f"SKILL.md grows to {words_after} words, budget {before.budget}")


def _check_links(operations: list[dict], skill_dir: Path, skill_copy: Path) -> None:
    """Every relative link an operation writes resolves in the edited skill or a sibling skill."""
    skills_root = skill_dir.parent.resolve()
    for operation in operations:
        written = "" if operation["op"] == "remove" else operation["to"]
        for target in _LINK.findall(written):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            relative = Path(operation["file"]).parent / target.split("#", 1)[0]
            in_copy = (skill_copy / relative).resolve()
            beside = (skill_dir / relative).resolve()
            if not (
                (in_copy.is_relative_to(skill_copy.resolve()) and in_copy.exists())
                or (beside.is_relative_to(skills_root) and beside.exists())
            ):
                raise Rejected("links", f"{operation['file']}: {target} does not resolve")


def _check_script_tests(skill_copy: Path) -> None:
    """Run the edited skill's own unittest suite; the harness and model play no part."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=skill_copy,
            capture_output=True,
            text=True,
            timeout=SCRIPT_TEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise Rejected("script-tests", f"tests exceeded {SCRIPT_TEST_TIMEOUT}s") from None
    if result.returncode != 0:
        raise Rejected("script-tests", result.stderr.strip().splitlines()[-1] if result.stderr else "")


def _top_dir(operation: dict) -> str:
    return Path(operation["file"]).parts[0]


def _classify(operations: list[dict], before: Limits) -> tuple[str, list[str]]:
    """Static when no operation can change a rule; claimed body rewordings go to human review."""
    body = {line.strip() for line in before.body.splitlines()}
    review = []
    for operation in operations:
        if _top_dir(operation) in STATIC_DIRS:
            continue
        if (
            operation["file"] == "SKILL.md"
            and operation["op"] == "change"
            and operation.get("wording") is True
            and operation["line"].strip() in body
        ):
            review.append(f"wording-only claim: {operation['line']!r} -> {operation['to']!r}")
            continue
        return "rule-change", []
    return "static", review


def _check_rule_change(skill_dir: Path, skill_copy: Path, report: Report, *,
                       runner: Runner, evals_root: Path) -> None:
    """Score every case twice, on the original skill and on the edited copy, and reject any drop."""
    try:
        cases = find_cases(evals_root, skill_dir.name)
        if not cases:
            raise Rejected("untested", f"no cases under {evals_root / skill_dir.name}")
        without = runner.score(skill_dir, cases)
        with_edit = runner.score(skill_copy, cases)
    except EvalFailed as failure:
        raise Rejected("eval-failed", str(failure)) from failure
    report.eval = {
        "cli": runner.cli,
        "model": runner.model,
        "cases": {
            case.name: {
                "without": without[case.name],
                "with": with_edit[case.name],
                "delta": with_edit[case.name] - without[case.name],
            }
            for case in cases
        },
    }
    regressed = sorted(name for name, score in report.eval["cases"].items()
                       if score["with"] < score["without"])
    if regressed:
        raise Rejected("regression", f"score fell on: {', '.join(regressed)}")
    report.checks.append("eval")


def _run_checks(proposal: dict, report: Report, *, library_root: Path, project: Path,
                evals_root: Path, runner: Runner | None) -> None:
    if proposal.get("schema") != SCHEMA:
        raise Rejected("schema", f"expected schema {SCHEMA}")
    skill_dir = _skill_dir(proposal.get("skill"), proposal.get("scope"), library_root, project)
    if skill_dir is None:
        raise Rejected("scope", "skill not found in the repo its scope names")
    report.checks.append("scope")
    if not _itemized(proposal.get("operations")):
        raise Rejected("not-itemized", "operations must each add, change, or remove one line")
    report.checks.append("itemized")
    try:
        sufficient = _sufficient_evidence(skill_dir.name, proposal.get("evidence"), project, evals_root)
    except EvalFailed as failure:  # a malformed case tree, not missing evidence
        raise Rejected("eval-failed", str(failure)) from failure
    if not sufficient:
        raise Rejected(
            "insufficient-evidence",
            "cite a correction, a failing case, or the same friction in two sessions",
        )
    report.checks.append("evidence")
    with tempfile.TemporaryDirectory() as work:
        skill_copy = Path(work) / skill_dir.name
        # Links stay links, so an edit through one resolves outside the copy and is refused.
        shutil.copytree(skill_dir, skill_copy, symlinks=True)
        operations = [_normalized(op, skill_copy) for op in proposal["operations"]]
        for operation in operations:
            _apply(operation, skill_copy)
        before, after = _limits(skill_dir / "SKILL.md"), _limits(skill_copy / "SKILL.md")
        report.kind, report.review = _classify(operations, before)
        _check_anchors(before, after)
        report.checks.append("anchor")
        _check_budget(before, after)
        report.checks.append("budget")
        _check_links(operations, skill_dir, skill_copy)
        report.checks.append("links")
        if report.kind == "rule-change" and runner is None:
            raise Rejected("eval-skipped", "no runner chosen")
        if any(_top_dir(op) == "scripts" for op in operations):
            if (skill_copy / "tests").is_dir():
                _check_script_tests(skill_copy)
                report.checks.append("script-tests")
            else:
                report.review.append("scripts changed and the skill has no tests")
        if report.kind == "rule-change":
            _check_rule_change(skill_dir, skill_copy, report, runner=runner, evals_root=evals_root)


def check(proposal: dict, *, library_root: Path, project: Path, evals_root: Path,
          runner: Runner | None = None) -> Report:
    """Run the gate's own checks on one proposal; the report names the first rejection."""
    report = Report(passed=False)
    try:
        _run_checks(proposal, report, library_root=library_root, project=project,
                    evals_root=evals_root, runner=runner)
    except Rejected as rejection:
        report.reason, report.detail = rejection.reason, rejection.detail
        return report
    report.passed = True
    return report


def build_runner(cli: str | None, model: str | None) -> Runner | None:
    """The eval runner for a --cli/--model pair; None when neither is named."""
    if bool(cli) != bool(model):
        raise Usage("--cli and --model go together")
    if cli and cli != "claude":
        raise Usage(f"unsupported CLI {cli!r}, only 'claude' runs evals")
    return ClaudePluginEval(model) if cli else None


def main(argv: list[str] | None = None) -> int:
    library = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--library-root", type=Path, default=library)
    parser.add_argument("--evals-root", type=Path, default=library.parent / "evals")
    parser.add_argument("--cli", help="model CLI to run evals with, with --model")
    parser.add_argument("--model", help="model to run evals with, with --cli")
    args = parser.parse_args(argv)
    try:
        runner = build_runner(args.cli, args.model)
    except Usage as usage:
        print(f"release-gate: {usage}", file=sys.stderr)
        return 2
    try:
        proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
        if not isinstance(proposal, dict):
            raise ValueError("proposal must be a JSON object")
    except (OSError, ValueError) as error:
        print(f"release-gate: {args.proposal}: {error}", file=sys.stderr)
        return 2
    report = check(
        proposal,
        library_root=args.library_root,
        project=args.project.resolve(),
        evals_root=args.evals_root,
        runner=runner,
    )
    print(json.dumps(asdict(report), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
