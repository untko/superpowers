import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "luna_worker.py"


class LunaWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="luna-worker-test-")
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.fake = self.root / "fake codex"
        self.fake.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "pathlib.Path(os.environ['PROBE_CAPTURE']).write_text(json.dumps({'args': args, 'stdin': sys.stdin.read()}))\n"
            "code = int(os.environ.get('PROBE_EXIT', '0'))\n"
            "if code == 0 and not os.environ.get('PROBE_EMPTY'):\n"
            "    pathlib.Path(args[args.index('-o') + 1]).write_text('WORKER_OK\\n')\n"
            "else:\n"
            "    print('MODEL_REJECTED', file=sys.stderr)\n"
            "sys.exit(code)\n"
        )
        self.fake.chmod(0o755)
        self.capture = self.root / "capture.json"
        self.env = dict(os.environ, LUNA_CODEX_BIN=str(self.fake), PROBE_CAPTURE=str(self.capture))

    def tearDown(self):
        self.tmp.cleanup()

    def run_worker(self, *extra, task="Read only: literal `code`, $variable, and $(no execution).\n", **env):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--dir", str(self.repo), "--mode", "read-only", *extra],
            input=task, capture_output=True, text=True, env=dict(self.env, **env),
        )

    def test_luna6_max_and_literal_brief(self):
        run = self.run_worker()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "exit=0\nWORKER_OK\n")
        captured = json.loads(self.capture.read_text())
        args = captured["args"]
        self.assertEqual(args[args.index("-m") + 1], "gpt-6-luna")
        self.assertIn("model_reasoning_effort=max", args)
        self.assertEqual(args[args.index("-s") + 1], "read-only")
        self.assertEqual(Path(args[args.index("-C") + 1]), self.repo.resolve())
        self.assertIn("--ephemeral", args)
        self.assertNotIn("--skip-git-repo-check", args)
        self.assertTrue(captured["stdin"].endswith("TASK:\nRead only: literal `code`, $variable, and $(no execution).\n"))

    def test_backend_failure_keeps_exit_and_diagnostics(self):
        run = self.run_worker(PROBE_EXIT="7")
        self.assertEqual(run.returncode, 7)
        self.assertTrue(run.stdout.startswith("exit=7\n"))
        self.assertIn("MODEL_REJECTED", run.stdout)
        self.assertEqual(json.loads(self.capture.read_text())["args"].count("exec"), 1)

    def test_empty_handoff_is_a_failure(self):
        run = self.run_worker(PROBE_EMPTY="1")
        self.assertNotEqual(run.returncode, 0)
        self.assertTrue(run.stdout.startswith("exit=0\n"))
        self.assertIn("no final message", run.stdout)

    def test_empty_brief_never_launches_codex(self):
        run = self.run_worker(task=" \n")
        self.assertEqual(run.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_explicit_binary_overrides_environment(self):
        run = self.run_worker("--codex-bin", str(self.fake), LUNA_CODEX_BIN="/missing/codex")
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_unavailable_explicit_binary_never_falls_back(self):
        run = self.run_worker("--codex-bin", "/missing/codex")
        self.assertEqual(run.returncode, 2)
        self.assertFalse(self.capture.exists())
        self.assertIn("Codex executable unavailable", run.stderr)

    def test_timeout_reports_termination(self):
        self.fake.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(30)\n")
        run = self.run_worker("--timeout", "1")
        self.assertEqual(run.returncode, 124)
        self.assertTrue(run.stdout.startswith("exit="))
        self.assertIn("worker timed out after 1 seconds", run.stdout)

    def test_default_prefers_app_bundle_on_macos(self):
        spec = importlib.util.spec_from_file_location("luna_worker", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.dict(os.environ, {}, clear=True), patch.object(module.sys, "platform", "darwin"), patch.object(module.os, "access", return_value=True), patch.object(module.Path, "is_file", return_value=True), patch.object(module.shutil, "which", return_value="/older/codex"):
            self.assertEqual(module.resolve_codex(None), module.MAC_APP_CODEX)


if __name__ == "__main__":
    unittest.main()
