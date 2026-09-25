import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hooks.friction_recorder import record  # noqa: E402


NOW = "2026-09-26T12:00:00+00:00"


def _write_transcript(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def _tool_use(name, tool_input):
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t", "name": name, "input": tool_input}],
        },
    }


def _events(project):
    log = project / ".superpowers" / "friction.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _setup(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    library = tmp_path / "library" / "skills"
    (library / "tdd").mkdir(parents=True)
    (library / "tdd" / "SKILL.md").write_text("---\nname: tdd\n---\n", encoding="utf-8")
    return project, library


def test_tool_failure_appends_one_event_with_short_excerpt(tmp_path):
    project, library = _setup(tmp_path)
    transcript = _write_transcript(tmp_path / "t.jsonl", [_tool_use("Skill", {"skill": "tdd"})])
    payload = {
        "hook_event_name": "PostToolUseFailure",
        "session_id": "s1",
        "transcript_path": str(transcript),
        "cwd": str(project),
        "tool_name": "Bash",
        "tool_input": {"command": "pytest"},
        "error": "E" * 2000,
    }

    record(payload, library_root=library, harness="claude-code", now=NOW)

    events = _events(project)
    assert len(events) == 1
    event = events[0]
    assert event["kind"] == "tool-failure"
    assert event["timestamp"] == NOW
    assert event["harness"] == "claude-code"
    assert event["session_id"] == "s1"
    assert [s["name"] for s in event["skills"]] == ["tdd"]
    assert 0 < len(event["excerpt"]) <= 500


def _prompt_payload(project, prompt):
    return {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "s1",
        "transcript_path": "",
        "cwd": str(project),
        "prompt": prompt,
    }


def test_correction_prompt_appends_correction_event(tmp_path):
    project, library = _setup(tmp_path)

    record(
        _prompt_payload(project, "No, that's wrong. Don't mock the database."),
        library_root=library,
        harness="claude-code",
        now=NOW,
    )

    events = _events(project)
    assert [e["kind"] for e in events] == ["correction"]
    assert "wrong" in events[0]["excerpt"]


def test_ordinary_prompt_appends_nothing(tmp_path):
    project, library = _setup(tmp_path)

    record(
        _prompt_payload(project, "Add a login page with email and password."),
        library_root=library,
        harness="claude-code",
        now=NOW,
    )

    assert _events(project) == []


def test_skills_are_attributed_once_each_with_their_source(tmp_path):
    project, library = _setup(tmp_path)
    local_skill = project / ".claude" / "skills" / "check-inbox"
    local_skill.mkdir(parents=True)
    (local_skill / "SKILL.md").write_text("---\nname: check-inbox\n---\n", encoding="utf-8")
    cli_skills = tmp_path / "home" / ".claude" / "skills"
    cli_skills.mkdir(parents=True)
    (cli_skills / "tdd").symlink_to(library / "tdd")
    transcript = _write_transcript(
        tmp_path / "t.jsonl",
        [
            _tool_use("Skill", {"skill": "tdd"}),
            _tool_use("Read", {"file_path": str(cli_skills / "tdd" / "SKILL.md")}),
            _tool_use("Read", {"file_path": str(local_skill / "SKILL.md")}),
            _tool_use("Read", {"file_path": str(project / "README.md")}),
            _tool_use("Skill", {"skill": "superpowers:tdd"}),
        ],
    )
    payload = _prompt_payload(project, "That's wrong, use the fixture.")
    payload["transcript_path"] = str(transcript)

    record(payload, library_root=library, harness="claude-code", now=NOW)

    assert _events(project)[0]["skills"] == [
        {"name": "tdd", "source": "global"},
        {"name": "check-inbox", "source": "local"},
    ]


SCRIPT = REPO_ROOT / "hooks" / "friction_recorder.py"


def _run_hook(tmp_path, stdin):
    import os
    import subprocess
    import time

    trap_bin = tmp_path / "bin"
    trap_bin.mkdir(exist_ok=True)
    marker = tmp_path / "model-started"
    for model_cli in ("claude", "codex", "gemini"):
        trap = trap_bin / model_cli
        trap.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
        trap.chmod(0o755)
    env = {**os.environ, "PATH": f"{trap_bin}:{os.environ['PATH']}"}
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--harness", "claude-code"],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return result, time.monotonic() - started, marker.exists()


def _assert_silent_success(outcome):
    result, elapsed, model_started = outcome
    assert result.returncode == 0
    assert result.stdout == ""
    assert elapsed < 1.0
    assert not model_started


def test_hook_survives_malformed_json(tmp_path):
    _assert_silent_success(_run_hook(tmp_path, "{not json"))


def test_hook_survives_missing_transcript(tmp_path):
    project, _ = _setup(tmp_path)
    payload = _prompt_payload(project, "that's wrong")
    payload["transcript_path"] = str(tmp_path / "missing.jsonl")

    _assert_silent_success(_run_hook(tmp_path, json.dumps(payload)))

    assert [e["kind"] for e in _events(project)] == ["correction"]


def test_hook_survives_unwritable_log(tmp_path):
    project, _ = _setup(tmp_path)
    (project / ".superpowers").write_text("not a directory", encoding="utf-8")
    payload = _prompt_payload(project, "that's wrong")

    _assert_silent_success(_run_hook(tmp_path, json.dumps(payload)))


def test_hook_records_tool_failure_without_starting_a_model(tmp_path):
    project, _ = _setup(tmp_path)
    payload = {
        "hook_event_name": "PostToolUseFailure",
        "session_id": "s1",
        "transcript_path": "",
        "cwd": str(project),
        "tool_name": "Bash",
        "error": "exit 1",
    }

    _assert_silent_success(_run_hook(tmp_path, json.dumps(payload)))

    assert [e["kind"] for e in _events(project)] == ["tool-failure"]


def _human(text, prompt_id):
    return {"type": "user", "promptId": prompt_id, "origin": {"kind": "human"},
            "message": {"role": "user", "content": text}}


def test_stop_sweep_records_each_session_event_once(tmp_path):
    project, library = _setup(tmp_path)
    transcript = _write_transcript(
        tmp_path / "t.jsonl",
        [
            _human("Add a login page.", "p1"),
            _tool_use("Skill", {"skill": "tdd"}),
            {"type": "user", "isMeta": True, "promptId": "p1",
             "message": {"role": "user", "content": [
                 {"type": "text", "text": "Base directory for this skill. Do not skip red."}]}},
            {"type": "user", "promptId": "p1", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "is_error": True,
                 "content": "Exit code 1"}]}},
            _human("No, that's wrong: the test must fail first.", "p2"),
        ],
    )
    live = _prompt_payload(project, "No, that's wrong: the test must fail first.")
    live["prompt_id"] = "p2"
    live["transcript_path"] = str(transcript)
    stop = {"hook_event_name": "Stop", "session_id": "s1", "cwd": str(project),
            "transcript_path": str(transcript), "stop_hook_active": False}

    record(live, library_root=library, harness="claude-code", now=NOW)
    record(stop, library_root=library, harness="claude-code", now=NOW)
    record(stop, library_root=library, harness="claude-code", now=NOW)

    events = _events(project)
    assert sorted((e["kind"], e["excerpt"]) for e in events) == [
        ("correction", "No, that's wrong: the test must fail first."),
        ("tool-failure", "Exit code 1"),
    ]


def test_user_typed_skill_is_attributed_from_its_injected_base_directory(tmp_path):
    project, library = _setup(tmp_path)
    (library / "implement").mkdir()
    (library / "implement" / "SKILL.md").write_text("---\nname: implement\n---\n", encoding="utf-8")
    cli_skills = tmp_path / "home" / ".claude" / "skills"
    cli_skills.mkdir(parents=True)
    (cli_skills / "implement").symlink_to(library / "implement")
    transcript = _write_transcript(
        tmp_path / "t.jsonl",
        [
            _human("<command-message>implement</command-message>\n<command-name>/implement</command-name>", "p1"),
            {"type": "user", "isMeta": True, "promptId": "p1", "message": {"role": "user", "content": [
                {"type": "text", "text": f"Base directory for this skill: {cli_skills / 'implement'}\n\nImplement it."}]}},
        ],
    )
    payload = _prompt_payload(project, "that's wrong")
    payload["transcript_path"] = str(transcript)

    record(payload, library_root=library, harness="claude-code", now=NOW)

    assert _events(project)[0]["skills"] == [{"name": "implement", "source": "global"}]
