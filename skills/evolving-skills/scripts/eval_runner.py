#!/usr/bin/env python3
"""Eval runner: score a skill's cases with a model CLI, with and without a proposed edit."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Protocol

CASE_MARKERS = ("prompt.md", "case.yaml")
EVAL_TIMEOUT = 1800


class EvalFailed(Exception):
    """A case could not be scored. Never a score of zero."""


class Runner(Protocol):
    """Scores a skill directory against its cases with one model CLI."""

    cli: str
    model: str

    def score(self, skill_dir: Path, cases: list[Path]) -> dict[str, float]:
        """Return {case id: score in 0..1} for exactly the given cases, or raise EvalFailed."""
        ...


def find_cases(evals_root: Path, skill: str) -> list[Path]:
    """The skill's eval cases, by id, in id order; a case is a directory holding a prompt."""
    root = evals_root / skill
    if not root.is_dir():
        return []
    found: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_dir() or not any((path / marker).is_file() for marker in CASE_MARKERS):
            continue
        if path.name in found:
            raise EvalFailed(f"two cases share the id {path.name!r}: {found[path.name]}, {path}")
        found[path.name] = path
    return [found[case_id] for case_id in sorted(found)]


@dataclass
class ClaudePluginEval:
    """Scores a skill's cases by staging it in a throwaway plugin and running `claude plugin eval`."""

    cli = "claude"
    model: str
    executable: str = "claude"

    def score(self, skill_dir: Path, cases: list[Path]) -> dict[str, float]:
        """Run every case once in a plugin holding this skill, and read the scores the CLI leaves."""
        with tempfile.TemporaryDirectory() as work:
            plugin = Path(work) / "plugin"
            result = Path(work) / "result.json"
            try:
                _stage(plugin, skill_dir, cases)
            except OSError as failure:
                raise EvalFailed(f"could not stage {skill_dir.name} to eval: {failure}") from failure
            argv = [self.executable, "plugin", "eval", str(plugin), "--ablation", "none",
                    "--runs", "1", "--model", self.model, "--json", str(result),
                    "--no-publish", "--trust-plugin"]
            try:
                # A score below the CLI's own threshold exits 1; the report is the only verdict.
                run = subprocess.run(argv, cwd=work, capture_output=True, text=True,
                                     timeout=EVAL_TIMEOUT)
            except (OSError, subprocess.TimeoutExpired) as failure:
                raise EvalFailed(f"{self.cli} plugin eval did not finish: {failure}") from failure
            try:
                return _scores(result, cases)
            except EvalFailed as failure:
                if result.exists() or not run.stderr.strip():
                    raise
                raise EvalFailed(f"{failure}; stderr: {run.stderr.strip()[-500:]}") from failure


def _stage(plugin: Path, skill_dir: Path, cases: list[Path]) -> None:
    """A plugin holding one copy of the skill and one copy of each case, and nothing else."""
    manifest = plugin / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"name": f"{skill_dir.name}-eval", "version": "0.0.0",
                                    "description": f"Throwaway plugin scoring {skill_dir.name} cases."}))
    shutil.copytree(skill_dir, plugin / "skills" / skill_dir.name, symlinks=True)
    for case in cases:
        shutil.copytree(case, plugin / "evals" / case.name, symlinks=True)


def _scores(result: Path, cases: list[Path]) -> dict[str, float]:
    """One score per requested case, the mean of its runs; anything unscoreable raises."""
    try:
        report = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, ValueError) as failure:
        raise EvalFailed(f"no readable eval report at {result}: {failure}") from failure
    if not isinstance(report, dict):
        raise EvalFailed(f"eval report is not an object: {result}")
    if report.get("partial"):
        raise EvalFailed(f"eval was partial: {report.get('partialReason')}")
    scored = {}
    for case in report.get("cases") or []:
        arms = case.get("arms") or {}
        runs = [run for arm in arms.values() if isinstance(arm, list) for run in arm
                if isinstance(run, dict)]
        for run in runs:
            if run.get("error"):
                raise EvalFailed(f"case {case.get('name')}: {run['error']}")
        marks = [run["score"] for run in arms.get("with") or []
                 if isinstance(run, dict) and isinstance(run.get("score"), (int, float))]
        if not marks:
            raise EvalFailed(f"case {case.get('name')} has no scored run")
        scored[case.get("name")] = statistics.fmean(marks)
    missing = [case.name for case in cases if case.name not in scored]
    if missing:
        raise EvalFailed(f"the report is missing: {', '.join(missing)}")
    return {case.name: scored[case.name] for case in cases}
