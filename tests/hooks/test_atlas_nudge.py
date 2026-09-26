import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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


T0 = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)


def _at(tmp_path, session, when=T0):
    return nudge({"cwd": str(tmp_path), "session_id": session}, now=when)


def test_counts_earlier_sessions_then_stays_silent(tmp_path):
    _log(tmp_path, _event("a"), _event("a", "tool-failure"), _event("b"))
    line = _at(tmp_path, "now")
    assert "2 user corrections and 1 tool failures across 2 sessions" in line
    assert "update-atlas" in line
    assert _at(tmp_path, "now") is None


def test_one_correction_waits_for_another(tmp_path):
    _log(tmp_path, _event("a"), _event("a", "tool-failure"), _event("b", "tool-failure"))
    assert _at(tmp_path, "now") is None
    _log(tmp_path, _event("c"))
    assert "2 user corrections and 2 tool failures across 3 sessions" in _at(tmp_path, "later")


def test_tool_failures_alone_never_nudge(tmp_path):
    _log(tmp_path, *(_event(s, "tool-failure") for s in "abcdef"))
    assert _at(tmp_path, "now") is None


def test_cooldown_holds_new_friction_until_a_week_has_passed(tmp_path):
    _log(tmp_path, _event("a"), _event("b"))
    assert _at(tmp_path, "s1") is not None
    _log(tmp_path, _event("c"), _event("d"))
    assert _at(tmp_path, "s2", T0 + timedelta(days=6)) is None
    line = _at(tmp_path, "s3", T0 + timedelta(days=7))
    assert "2 user corrections and 0 tool failures across 2 sessions" in line


def test_current_session_friction_does_not_count(tmp_path):
    _log(tmp_path, _event("now"), _event("a"))
    assert _at(tmp_path, "now") is None
    assert "2 user corrections" in _at(tmp_path, "later")


def test_half_written_line_waits_for_the_next_start(tmp_path):
    _log(tmp_path, _event("a"), _event("b"), partial='{"kind": "correction", "sess')
    assert "2 user corrections" in _at(tmp_path, "now")
    state = json.loads((tmp_path / ".superpowers" / "atlas-nudge.json").read_text())
    log = tmp_path / ".superpowers" / "friction.jsonl"
    assert state["offset"] < log.stat().st_size


def test_truncated_log_starts_over(tmp_path):
    log = _log(tmp_path, _event("a"), _event("b"), _event("c"))
    _at(tmp_path, "now")
    log.write_text(json.dumps(_event("d")) + "\n" + json.dumps(_event("e")) + "\n",
                   encoding="utf-8")
    assert "across 2 sessions" in _at(tmp_path, "now", T0 + timedelta(days=8))


def test_reads_the_main_checkout_log_from_a_worktree(tmp_path):
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    (main / ".git" / "worktrees" / "wt" / "commondir").write_text("../..\n")
    worktree = main / ".worktrees" / "wt"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n")
    _log(main, _event("a"), _event("b"))
    assert _at(worktree, "now") is not None
    assert not (worktree / ".superpowers").exists()


def test_entry_point_never_fails(tmp_path):
    script = REPO_ROOT / "hooks" / "atlas_nudge.py"
    for stdin in ("", "not json", json.dumps({"cwd": str(tmp_path / "missing")})):
        result = subprocess.run(
            [sys.executable, str(script)], input=stdin, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert result.stdout == ""
