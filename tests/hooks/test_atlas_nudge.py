import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hooks.atlas_nudge import nudge  # noqa: E402


def _log(project, *events, partial=""):
    log = project / ".superpowers" / "friction.jsonl"
    log.parent.mkdir(exist_ok=True)
    with open(log, "a", encoding="utf-8") as handle:
        handle.writelines(json.dumps(e) + "\n" for e in events)
        handle.write(partial)
    return log


def _event(session, kind="correction"):
    return {"id": f"{session}:{kind}:x", "kind": kind, "session_id": session}


def test_silent_without_a_log(tmp_path):
    assert nudge({"cwd": str(tmp_path), "session_id": "now"}) is None
    assert not (tmp_path / ".superpowers").exists()


def test_counts_earlier_sessions_then_stays_silent(tmp_path):
    _log(tmp_path, _event("a"), _event("a", "tool-failure"), _event("b", "tool-failure"))
    line = nudge({"cwd": str(tmp_path), "session_id": "now"})
    assert "1 user corrections and 2 tool failures across 2 sessions" in line
    assert "update-atlas" in line
    assert nudge({"cwd": str(tmp_path), "session_id": "now"}) is None


def test_new_friction_after_a_nudge_is_counted_alone(tmp_path):
    _log(tmp_path, _event("a"))
    nudge({"cwd": str(tmp_path), "session_id": "s1"})
    _log(tmp_path, _event("b", "tool-failure"))
    line = nudge({"cwd": str(tmp_path), "session_id": "s2"})
    assert "0 user corrections and 1 tool failures across 1 sessions" in line


def test_current_session_friction_does_not_nudge_or_advance(tmp_path):
    _log(tmp_path, _event("now"))
    assert nudge({"cwd": str(tmp_path), "session_id": "now"}) is None
    assert "1 user corrections" in nudge({"cwd": str(tmp_path), "session_id": "later"})


def test_half_written_line_waits_for_the_next_start(tmp_path):
    _log(tmp_path, _event("a"), partial='{"kind": "correction", "sess')
    assert "1 user corrections" in nudge({"cwd": str(tmp_path), "session_id": "now"})
    state = json.loads((tmp_path / ".superpowers" / "atlas-nudge.json").read_text())
    log = tmp_path / ".superpowers" / "friction.jsonl"
    assert state["offset"] < log.stat().st_size


def test_truncated_log_starts_over(tmp_path):
    log = _log(tmp_path, _event("a"), _event("b"))
    nudge({"cwd": str(tmp_path), "session_id": "now"})
    log.write_text(json.dumps(_event("c")) + "\n", encoding="utf-8")
    assert "across 1 sessions" in nudge({"cwd": str(tmp_path), "session_id": "now"})


def test_entry_point_never_fails(tmp_path):
    script = REPO_ROOT / "hooks" / "atlas_nudge.py"
    for stdin in ("", "not json", json.dumps({"cwd": str(tmp_path / "missing")})):
        result = subprocess.run(
            [sys.executable, str(script)], input=stdin, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert result.stdout == ""
