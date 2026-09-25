import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_CONFIGS = sorted((REPO_ROOT / "hooks").glob("hooks*.json"))


def test_hook_configs_exist():
    assert [p.name for p in HOOK_CONFIGS] == ["hooks-cursor.json", "hooks.json"]


def test_no_hook_config_runs_anything_at_session_stop():
    for path in HOOK_CONFIGS:
        events = json.loads(path.read_text(encoding="utf-8"))["hooks"]
        assert not [e for e in events if e.lower() in {"stop", "subagentstop"}], path.name
