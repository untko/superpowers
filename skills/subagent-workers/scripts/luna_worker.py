#!/usr/bin/env python3
"""Run one bounded Codex Luna worker from any host with a shell and Python 3."""

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile


MAC_APP_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
WORKER_RULES = """You are a bounded worker. Execute only the task below. Restate the outcome
and exact files or questions you own first. Inspect applicable project instructions.
Preserve unrelated work and stay within the assigned scope. Do not edit credentials
or user-level configuration. Do not commit, push, open pull requests, send external
messages, spawn agents, or use destructive reset or checkout. For a read-only task,
leave files unchanged. Run the narrowest relevant checks and report their outcomes.
Stop and report blockers rather than guessing. Finish with: result, files changed
(or none), checks and outcomes, remaining risks, and any decision for the parent.

TASK:
"""


def resolve_codex(explicit):
    selected = explicit or os.environ.get("LUNA_CODEX_BIN")
    if selected:
        expanded = os.path.expanduser(selected)
        binary = shutil.which(expanded)
        if not binary:
            raise ValueError(f"Codex executable unavailable: {expanded}")
        return binary
    if sys.platform == "darwin" and Path(MAC_APP_CODEX).is_file() and os.access(MAC_APP_CODEX, os.X_OK):
        return MAC_APP_CODEX
    binary = shutil.which("codex")
    if not binary:
        raise ValueError("Codex not found; install and authenticate it, or set LUNA_CODEX_BIN")
    return binary


def diagnostics(path):
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        handle.seek(max(0, handle.tell() - 65536))
        return handle.read().decode("utf-8", errors="replace").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="authorized git repository or isolated worktree")
    parser.add_argument("--mode", required=True, choices=("read-only", "workspace-write"))
    parser.add_argument("--model", default="gpt-6-luna", choices=("gpt-6-luna", "gpt-5.6-luna"))
    parser.add_argument("--codex-bin", help="Codex executable; overrides LUNA_CODEX_BIN and discovery")
    parser.add_argument("--timeout", type=int, default=540, help="worker time limit in seconds (default: 540)")
    args = parser.parse_args()
    task = sys.stdin.read()
    try:
        if not task.strip():
            raise ValueError("the bounded brief on stdin is empty")
        if args.timeout < 1:
            raise ValueError("timeout must be positive")
        root = Path(args.dir).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"worker directory does not exist: {root}")
        binary = resolve_codex(args.codex_bin)
    except ValueError as error:
        print(f"launcher_error={error}", file=sys.stderr)
        return 2

    print(f"codex_binary={binary}", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="codex-luna-worker-") as temporary:
        output = Path(temporary) / "last-message.txt"
        errors = Path(temporary) / "stderr.log"
        command = [binary, "exec", "-m", args.model, "-c", "model_reasoning_effort=max",
                   "-s", args.mode, "-C", str(root), "--ephemeral", "--color", "never", "-o", str(output), "-"]
        timed_out = False
        try:
            with errors.open("wb") as error_stream:
                worker = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                          stderr=error_stream, text=True, encoding="utf-8",
                                          start_new_session=(os.name == "posix"))
                try:
                    worker.communicate(WORKER_RULES + task, timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    if os.name == "posix":
                        os.killpg(worker.pid, signal.SIGKILL)
                    else:
                        worker.kill()
                    worker.communicate()
        except OSError as error:
            print(f"launcher_error={error}", file=sys.stderr)
            return 2

        print(f"exit={worker.returncode}")
        if timed_out:
            print(f"launcher_error=worker timed out after {args.timeout} seconds")
        message = output.read_text(encoding="utf-8") if output.exists() else ""
        if worker.returncode == 0 and not timed_out and message.strip():
            sys.stdout.write(message)
            if not message.endswith("\n"):
                sys.stdout.write("\n")
            return 0
        if worker.returncode == 0:
            print("launcher_error=Codex returned no final message")
        diagnostic = diagnostics(errors)
        if diagnostic:
            print(diagnostic)
        return 124 if timed_out else (worker.returncode if worker.returncode > 0 else 1)


if __name__ == "__main__":
    sys.exit(main())
