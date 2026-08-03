import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hooks.skill_review import (  # noqa: E402
    decide_review,
    load_model_map,
    process_event,
    read_transcript_window,
    resolve_harness,
    resolve_model,
)


def test_model_map_resolves_known_harness_and_inherits_unknown(tmp_path):
    model_map = tmp_path / "review-model-map.json"
    model_map.write_text(
        '{"claude-code": "review-model", "_default": null}\n',
        encoding="utf-8",
    )

    loaded = load_model_map(model_map)

    assert resolve_model(loaded, "claude-code") == "review-model"
    assert resolve_model(loaded, "codex-cli") is None


def test_model_map_rejects_empty_model_strings(tmp_path):
    path = tmp_path / "review-model-map.json"
    path.write_text('{"claude-code": "", "_default": null}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="non-empty string or null"):
        load_model_map(path)


def test_harness_detection_matches_session_start_branch_order():
    assert (
        resolve_harness(
            {"CURSOR_PLUGIN_ROOT": "/plugin", "CLAUDE_PLUGIN_ROOT": "/plugin"}
        )
        == "cursor"
    )
    assert resolve_harness({"CLAUDE_PLUGIN_ROOT": "/plugin"}) == "claude-code"
    assert (
        resolve_harness({"COPILOT_CLI": "1", "CLAUDE_PLUGIN_ROOT": "/plugin"})
        == "copilot-cli"
    )
    assert resolve_harness({}) == "_default"


def test_transcript_window_counts_tool_use_blocks_after_byte_watermarks(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"skills/demo/SKILL.md"}}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"pytest"}},{"type":"tool_use","name":"Edit","input":{"file_path":"references/guide.md"}}]}}\n',
        encoding="utf-8",
    )

    window = read_transcript_window(transcript, tool_offset=0, correction_offset=0)

    assert window.tool_calls == 3
    assert window.substantive is True
    assert window.end_offset == transcript.stat().st_size


def test_transcript_window_detects_user_skill_correction_without_tool_threshold(
    tmp_path,
):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"type":"user","message":{"content":"That skill got this wrong. Fix it."}}\n',
        encoding="utf-8",
    )

    window = read_transcript_window(transcript, tool_offset=0, correction_offset=0)

    assert window.tool_calls == 0
    assert window.explicit_corrections == ("That skill got this wrong. Fix it.",)


def test_threshold_fires_at_exact_boundary_only_when_substantive():
    assert (
        decide_review(
            tool_calls=10,
            threshold=10,
            substantive=True,
            explicit_correction=False,
        ).outcome
        == "review"
    )
    assert (
        decide_review(
            tool_calls=10,
            threshold=10,
            substantive=False,
            explicit_correction=False,
        ).outcome
        == "skip-no-substance"
    )
    assert (
        decide_review(
            tool_calls=2,
            threshold=10,
            substantive=False,
            explicit_correction=False,
        ).outcome
        == "skip-below-threshold"
    )


def test_explicit_correction_bypasses_threshold_without_resetting_tool_watermark():
    decision = decide_review(
        tool_calls=2,
        threshold=10,
        substantive=False,
        explicit_correction=True,
    )

    assert decision.outcome == "review-explicit-correction"
    assert decision.reset_tool_watermark is False


def make_plugin_fixture(tmp_path, *, model_map=None, threshold=10, dry_run=True):
    plugin_root = tmp_path / "plugin"
    hooks = plugin_root / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "review-config.json").write_text(
        json.dumps({"threshold": threshold, "dry_run": dry_run}) + "\n",
        encoding="utf-8",
    )
    (hooks / "review-model-map.json").write_text(
        json.dumps(model_map or {"_default": None}) + "\n",
        encoding="utf-8",
    )
    return plugin_root


def _tool_record(*, substantive=False):
    input_value = {
        "file_path": "skills/demo/SKILL.md"
        if substantive
        else "temporary-output.txt"
    }
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Read",
                    "input": input_value,
                }
            ]
        },
    }


def make_stop_payload(tmp_path, *, tool_use_records, substantive=False, user_text=None):
    transcript = tmp_path / "transcript.jsonl"
    records = [_tool_record(substantive=substantive) for _ in range(tool_use_records)]
    if user_text:
        records.append(
            {"type": "user", "message": {"content": user_text}}
        )
    transcript.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    return {"cwd": str(tmp_path), "transcript_path": str(transcript)}


def append_tool_use_records(transcript_path, count, *, substantive=False):
    with Path(transcript_path).open("a", encoding="utf-8") as handle:
        for _ in range(count):
            handle.write(json.dumps(_tool_record(substantive=substantive)) + "\n")


def fixed_time():
    return "2026-08-04T00:00:00Z"


def test_below_threshold_keeps_tool_watermark_so_counts_accumulate(tmp_path):
    plugin_root = make_plugin_fixture(tmp_path)
    payload = make_stop_payload(tmp_path, tool_use_records=2)
    first = process_event(
        payload,
        plugin_root=plugin_root,
        env={},
        now=fixed_time,
    )
    append_tool_use_records(payload["transcript_path"], 2)
    second = process_event(
        payload,
        plugin_root=plugin_root,
        env={},
        now=fixed_time,
    )

    assert first.outcome == "skip-below-threshold"
    assert second.tool_calls == 4
    assert not (tmp_path / ".superpowers" / "review-state.json").exists()


def test_threshold_review_resets_watermark_to_current_transcript_position(tmp_path):
    plugin_root = make_plugin_fixture(tmp_path)
    payload = make_stop_payload(
        tmp_path,
        tool_use_records=10,
        substantive=True,
    )
    result = process_event(
        payload,
        plugin_root=plugin_root,
        env={"SUPERPOWERS_REVIEW_DRY_RUN": "true"},
        now=fixed_time,
    )

    state = json.loads(
        (tmp_path / ".superpowers" / "review-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert result.outcome == "dry-run-review"
    assert state["tool_watermark"] == Path(payload["transcript_path"]).stat().st_size


def test_no_substance_keeps_tool_watermark_but_advances_correction_watermark(tmp_path):
    plugin_root = make_plugin_fixture(tmp_path)
    payload = make_stop_payload(tmp_path, tool_use_records=10, substantive=False)
    result = process_event(
        payload,
        plugin_root=plugin_root,
        env={},
        now=fixed_time,
    )

    state = json.loads(
        (tmp_path / ".superpowers" / "review-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert result.outcome == "skip-no-substance"
    assert state["tool_watermark"] == 0
    assert state["correction_watermark"] == Path(
        payload["transcript_path"]
    ).stat().st_size


def test_every_invocation_appends_timestamp_count_model_and_outcome(tmp_path):
    plugin_root = make_plugin_fixture(tmp_path)
    payload = make_stop_payload(tmp_path, tool_use_records=1)
    process_event(
        payload,
        plugin_root=plugin_root,
        env={},
        now=fixed_time,
    )

    line = (tmp_path / ".superpowers" / "review-log.md").read_text(
        encoding="utf-8"
    ).strip()
    assert "2026-08-04T00:00:00Z" in line
    assert "tool_calls=1" in line
    assert "model=inherit" in line
    assert "outcome=skip-below-threshold" in line


def test_explicit_correction_runs_reviewer_and_preserves_tool_counter(tmp_path):
    plugin_root = make_plugin_fixture(tmp_path, dry_run=False)
    payload = make_stop_payload(
        tmp_path,
        tool_use_records=2,
        user_text="Stop doing that; this skill is wrong.",
    )
    calls = []

    def fake_reviewer(**kwargs):
        calls.append(kwargs)
        return 0

    result = process_event(
        payload,
        plugin_root=plugin_root,
        env={"SUPERPOWERS_REVIEW_DRY_RUN": "false"},
        run_reviewer=fake_reviewer,
        now=fixed_time,
    )

    state = json.loads(
        (tmp_path / ".superpowers" / "review-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert result.outcome == "review-explicit-correction"
    assert state["tool_watermark"] == 0
    assert calls[0]["reason"] == "explicit-correction"
    assert "new_observation.py" in calls[0]["prompt"]


def test_live_review_passes_model_only_for_non_null_table_entry(tmp_path):
    plugin_root = make_plugin_fixture(
        tmp_path,
        model_map={"claude-code": "review-model-from-config", "_default": None},
        dry_run=False,
    )
    payload = make_stop_payload(tmp_path, tool_use_records=10, substantive=True)
    calls = []

    def fake_reviewer(**kwargs):
        calls.append(kwargs)
        return 0

    process_event(
        payload,
        plugin_root=plugin_root,
        env={
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "SUPERPOWERS_REVIEW_DRY_RUN": "false",
        },
        run_reviewer=fake_reviewer,
        now=fixed_time,
    )

    assert calls[0]["model"] == "review-model-from-config"
