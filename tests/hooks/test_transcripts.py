import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hooks.friction_recorder import record  # noqa: E402
from hooks.transcripts import normalize  # noqa: E402


NOW = "2026-09-26T12:00:00+00:00"
FIXTURES = Path(__file__).parent / "fixtures"
PLUGIN = REPO_ROOT / "hooks" / "opencode" / "friction-recorder.js"


def _setup(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    library = tmp_path / "library" / "skills"
    for name in ("tdd", "brainstorming"):
        (library / name).mkdir(parents=True)
        (library / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    local = project / ".claude" / "skills" / "check-inbox"
    local.mkdir(parents=True)
    (local / "SKILL.md").write_text("---\nname: check-inbox\n---\n", encoding="utf-8")
    return project, library


def _fixture(name, project, library):
    """A hand-written fixture with its @@...@@ placeholders pointed at real skill files."""
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return (
        text.replace("@@SKILL_MD@@", str(library / "tdd" / "SKILL.md"))
        .replace("@@DECOY_SKILL_MD@@", str(library / "brainstorming" / "SKILL.md"))
        .replace("@@LOCAL_SKILL_MD@@", str(project / ".claude" / "skills" / "check-inbox" / "SKILL.md"))
    )


def _events(project):
    log = project / ".superpowers" / "friction.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _stop(project, transcript, session="s1"):
    return {
        "hook_event_name": "Stop",
        "session_id": session,
        "cwd": str(project),
        "transcript_path": str(transcript),
    }


def test_codex_rollout_sweep_records_failures_and_corrections_with_sources(tmp_path):
    project, library = _setup(tmp_path)
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text(_fixture("codex-rollout.jsonl", project, library), encoding="utf-8")

    events = record(_stop(project, transcript), library_root=library, harness="codex", now=NOW)

    assert [(e["kind"], [s["name"] for s in e["skills"]]) for e in events] == [
        ("tool-failure", ["tdd"]),
        ("correction", ["tdd", "check-inbox"]),
    ]
    assert events[0]["excerpt"] == "exit 1: E   ModuleNotFoundError: No module named 'pytest'"
    assert events[1]["excerpt"] == "No, that's wrong: the test must fail first."
    assert events[0]["skills"] == [{"name": "tdd", "source": "global"}]
    assert events[1]["skills"] == [
        {"name": "tdd", "source": "global"},
        {"name": "check-inbox", "source": "local"},
    ]
    assert {e["harness"] for e in events} == {"codex"}
    assert {e["session_id"] for e in events} == {"s1"}


def test_codex_sweep_logs_each_event_once_across_stops(tmp_path):
    project, library = _setup(tmp_path)
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text(_fixture("codex-rollout.jsonl", project, library), encoding="utf-8")

    record(_stop(project, transcript), library_root=library, harness="codex", now=NOW)
    record(_stop(project, transcript), library_root=library, harness="codex", now=NOW)

    assert [e["kind"] for e in _events(project)] == ["tool-failure", "correction"]


def test_opencode_messages_sweep_records_failures_and_corrections_with_sources(tmp_path):
    project, library = _setup(tmp_path)
    transcript = tmp_path / "messages.json"
    transcript.write_text(_fixture("opencode-messages.json", project, library), encoding="utf-8")

    events = record(_stop(project, transcript, "ses_1"), library_root=library, harness="opencode", now=NOW)

    assert [(e["kind"], [s["name"] for s in e["skills"]]) for e in events] == [
        ("tool-failure", ["tdd"]),
        ("correction", ["tdd", "check-inbox"]),
    ]
    assert events[0]["excerpt"] == "exit 1: no tests collected"
    assert events[1]["excerpt"] == "No, that's wrong: the test must fail first."
    assert events[1]["skills"] == [
        {"name": "tdd", "source": "global"},
        {"name": "check-inbox", "source": "local"},
    ]
    assert {e["harness"] for e in events} == {"opencode"}


def test_claude_transcript_normalizes_to_its_own_records(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        '{"type": "user", "message": {"content": "hi"}}\nnot json\n[1, 2]\n', encoding="utf-8"
    )
    records = [{"type": "user", "message": {"content": "hi"}}]

    assert normalize("claude", str(transcript)) == records
    assert normalize("claude-code", str(transcript)) == records


def test_unknown_harness_or_unreadable_transcript_normalizes_to_nothing(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type": "user"}\n', encoding="utf-8")

    assert normalize("", None) == []
    assert normalize("gemini", str(transcript)) == []
    assert normalize("codex", str(tmp_path / "missing.jsonl")) == []
    assert normalize("opencode", str(tmp_path / "missing.json")) == []


def test_normalizers_survive_a_garbage_transcript(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text('{"type": "event_msg"\n{"type": "response_item", "payload": "nope"}\n', encoding="utf-8")
    messages = tmp_path / "messages.json"
    messages.write_text("{not json", encoding="utf-8")

    assert normalize("codex", str(rollout)) == []
    assert normalize("opencode", str(messages)) == []


def test_opencode_plugin_is_valid_javascript():
    if shutil.which("node") is None:
        return

    result = subprocess.run(
        ["node", "--check", str(PLUGIN)], capture_output=True, text=True, timeout=30
    )

    assert result.returncode == 0, result.stderr
