#!/usr/bin/env python3
"""Eval runner: score a skill's cases with a model CLI, with and without a proposed edit."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Protocol

CASE_MARKERS = ("prompt.md", "case.yaml")
EVAL_TIMEOUT = 1800
OPENCODE_TIMEOUT = 900
GRADER_PROMPT = """You are grading one agent transcript against one criterion.

Criterion:
{criterion}

Transcript:
{transcript}

Score only what the criterion asks for, and ignore everything else. Use 1 when
the transcript plainly meets the criterion, 0 when it plainly fails, and a
number between for anything in between.

Answer with one short sentence, then a final line exactly:
SCORE: <number from 0 to 1>
"""
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


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


@dataclass
class OpencodeEval:
    """Scores a skill's cases by running each prompt in an isolated opencode and grading it."""

    cli = "opencode"
    model: str
    grader_model: str | None = None
    executable: str = "opencode"

    def __post_init__(self) -> None:
        self.grader_model = self.model if self.grader_model is None else self.grader_model

    def score(self, skill_dir: Path, cases: list[Path]) -> dict[str, float]:
        """Run every case once against a copy of this skill, and mean its graders' scores."""
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "home"
            home.mkdir()
            try:
                _link_auth(home)
            except OSError as failure:
                raise EvalFailed(f"could not isolate HOME for the run: {failure}") from failure
            return {case.name: self._score_case(skill_dir, case, Path(root), home)
                    for case in cases}

    def _score_case(self, skill_dir: Path, case: Path, root: Path, home: Path) -> float:
        """One case: run its prompt, then grade the transcript once per criterion."""
        prompt, allowed = _case_prompt(case)
        try:
            criteria = _criteria(case)
        except OSError as failure:
            raise EvalFailed(f"{case.name}: {failure}") from failure
        work = root / "work" / case.name
        try:
            shutil.copytree(skill_dir, work / ".opencode" / "skills" / skill_dir.name, symlinks=True)
        except OSError as failure:
            raise EvalFailed(f"{case.name}: could not stage {skill_dir.name} to eval: "
                             f"{failure}") from failure
        env = _opencode_env(home, _permission(allowed))
        run = self._run(self.model, work, prompt, env, case.name)
        transcript = _transcript(_parts(run.stdout))
        if not transcript:
            raise EvalFailed(f"{case.name}: opencode printed no transcript: {_complaint(run)}")
        return statistics.fmean([
            self._grade(index, criterion, transcript, root, env, case.name)
            for index, criterion in enumerate(criteria)
        ])

    def _grade(self, index: int, criterion: tuple[str, str], transcript: str, root: Path,
               env: dict[str, str], case: str) -> float:
        """One criterion, judged in a directory of its own that holds no skill."""
        work = root / "grade" / f"{case}-{index}"
        work.mkdir(parents=True, exist_ok=True)
        what = f"{case}: grader {criterion[0]}"
        run = self._run(self.grader_model, work,
                        GRADER_PROMPT.format(criterion=criterion[1], transcript=transcript),
                        env, what)
        answer = _text(_parts(run.stdout))
        _, marker, tail = answer.rpartition("SCORE:")
        if not marker:
            raise EvalFailed(f"{what}: the grader gave no SCORE: line")
        match = _NUMBER.match(tail.strip())
        if match is None:
            raise EvalFailed(f"{what}: the grader's SCORE: line is not a number")
        score = float(match.group())
        if not 0.0 <= score <= 1.0:
            raise EvalFailed(f"{what}: the grader scored {score}, which is not from 0 to 1")
        return score

    def _run(self, model: str, work: Path, prompt: str, env: dict[str, str],
             case: str) -> subprocess.CompletedProcess[str]:
        """One `opencode run`, in `work`, on the isolated environment."""
        # --auto: nobody can answer a permission prompt here; explicit denies still hold.
        argv = [self.executable, "run", "--auto", "-m", model, "--format", "json", "--dir", str(work), prompt]
        try:
            # A piped stdin makes `opencode run` wait to read it.
            run = subprocess.run(argv, cwd=work, capture_output=True, text=True,
                                 stdin=subprocess.DEVNULL, timeout=OPENCODE_TIMEOUT, env=env)
        except (OSError, subprocess.TimeoutExpired) as failure:
            raise EvalFailed(f"{case}: opencode did not finish: {failure}") from failure
        if run.returncode != 0:
            raise EvalFailed(f"{case}: opencode exited {run.returncode}: {_complaint(run)}")
        return run


def _case_prompt(case: Path) -> tuple[str, list[str]]:
    """The case's task prompt, and the tools its frontmatter allows."""
    prompt = case / "prompt.md"
    if not prompt.is_file():
        raise EvalFailed(f"{case.name}: opencode runs prompt.md cases only")
    try:
        text = prompt.read_text(encoding="utf-8")
    except OSError as failure:
        raise EvalFailed(f"{case.name}: {failure}") from failure
    metadata, body = _frontmatter(text)
    allowed = metadata.get("allowed_tools")
    tools = [allowed] if isinstance(allowed, str) else list(allowed or [])
    return body.strip(), [str(tool) for tool in tools]


def _criteria(case: Path) -> list[tuple[str, str]]:
    """The case's graders by file name, each one's criterion with its frontmatter stripped."""
    directory = case / "graders"
    graders = sorted(directory.glob("*.md")) if directory.is_dir() else []
    if not graders:
        raise EvalFailed(f"{case.name}: no graders/*.md to score the case")
    criteria = []
    for grader in graders:
        criterion = _frontmatter(grader.read_text(encoding="utf-8"))[1].strip()
        if not criterion:
            raise EvalFailed(f"{case.name}: grader {grader.name} has no criterion")
        criteria.append((grader.name, criterion))
    return criteria


def _frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split a case file's YAML-ish frontmatter from its body.

    Only the forms these cases use are read: `key: value`, `key: [a, b]`, and
    `key:` followed by `- item` lines. Anything else is left out.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return _metadata(lines[1:index]), "\n".join(lines[index + 1:])
    return {}, text


def _metadata(lines: list[str]) -> dict[str, object]:
    """Each frontmatter key with its value: a scalar, an inline list, or a list of items."""
    metadata: dict[str, object] = {}
    items: list[str] | None = None
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text.startswith("-"):
            if items is not None:
                items.append(text.lstrip("-").strip())
            continue
        if ":" not in text:
            continue
        key, _, value = text.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            metadata[key] = [item.strip() for item in value[1:-1].split(",") if item.strip()]
            items = None
        elif value:
            metadata[key] = value
            items = None
        else:
            items = metadata[key] = []
    return metadata


def _permission(allowed: list[str]) -> str:
    """Deny the tools a case does not allow, and anything outside the work dir."""
    denied = {}
    if "Bash" not in allowed:
        denied["bash"] = "deny"
    if not ({"Edit", "Write"} & set(allowed)):
        denied["edit"] = "deny"
    denied["external_directory"] = "deny"
    return json.dumps(denied)


def _opencode_env(home: Path, permission: str) -> dict[str, str]:
    """An environment that sees the PATH, the API keys, and its own empty home, and nothing else."""
    env = {name: value for name, value in os.environ.items()
           if name == "PATH" or name.endswith("_API_KEY")}
    env.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
        "OPENCODE_DISABLE_CLAUDE_CODE": "1",
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "OPENCODE_PERMISSION": permission,
    })
    return env


def _link_auth(home: Path) -> None:
    """Point the isolated home at the real credentials, so the provider can still authenticate."""
    real_home = Path.home()
    real = real_home / ".local" / "share" / "opencode" / "auth.json"
    if not real.is_file():
        return
    staged = home / real.relative_to(real_home)
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.symlink_to(real)


def _events(stdout: str) -> list[dict]:
    """The JSON events of a `--format json` run, in the order the CLI printed them."""
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _parts(stdout: str) -> list[dict]:
    """The event parts of a `--format json` run, in the order the CLI printed them."""
    return [event["part"] for event in _events(stdout) if isinstance(event.get("part"), dict)]


def _complaint(run: subprocess.CompletedProcess) -> str:
    """Why an opencode run failed: its JSON error events, else the end of its stderr."""
    errors = []
    for event in _events(run.stdout):
        error = event.get("error") if event.get("type") == "error" else None
        if isinstance(error, dict):
            data = error.get("data")
            message = data.get("message") if isinstance(data, dict) else None
            errors.append(f"{error.get('name', 'error')}: {message or json.dumps(error)[:300]}")
    return "; ".join(errors)[-500:] or _tail(run.stderr)


def _transcript(parts: list[dict]) -> str:
    """A plain transcript: what the agent said, and one line for every tool it called."""
    lines = []
    for part in parts:
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            if part["text"].strip():
                lines.append(part["text"].strip())
        elif part.get("type") == "tool":
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            lines.append(f"[tool {part.get('tool')}] {json.dumps(state.get('input'), sort_keys=True)}")
    return "\n".join(lines)


def _text(parts: list[dict]) -> str:
    """Only what the model said, with every tool call left out."""
    return "\n".join(part["text"] for part in parts
                     if part.get("type") == "text" and isinstance(part.get("text"), str))


def _tail(stderr: str) -> str:
    """The end of what a CLI complained about, or a plain note when it said nothing."""
    return stderr.strip()[-500:] or "(nothing on stderr)"


RUNNERS: dict[str, type] = {"claude": ClaudePluginEval, "opencode": OpencodeEval}

