/**
 * Friction recorder for OpenCode.
 *
 * OpenCode has no command hooks, so this plugin feeds the same recorder the
 * other CLIs use: on session.idle it writes the session's messages to a temp
 * file and pipes a Stop payload to the script. The repo path comes from this
 * file's own location, so a symlink into ~/.config/opencode/plugins still
 * resolves the real checkout. A hook must never break a session, so every
 * failure here is swallowed.
 */

import { spawn } from "node:child_process";
import { realpathSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = join(dirname(realpathSync(fileURLToPath(import.meta.url))), "..", "..");
const RECORDER = join(REPO, "hooks", "friction_recorder.py");

const record = (payload) =>
  new Promise((resolve) => {
    const child = spawn("python3", [RECORDER, "--harness", "opencode"], {
      stdio: ["pipe", "ignore", "ignore"],
    });
    child.on("error", resolve);
    child.on("close", resolve);
    child.stdin.end(JSON.stringify(payload));
  });

export const FrictionRecorder = async ({ client, directory }) => ({
  event: async ({ event }) => {
    if (event.type !== "session.idle") return;
    const sessionID = event.properties?.sessionID;
    if (!sessionID) return;
    const transcript = join(tmpdir(), `friction-${sessionID}-${process.pid}.json`);
    try {
      const res = await client.session.messages({ path: { id: sessionID } });
      writeFileSync(transcript, JSON.stringify(res?.data ?? res ?? []));
      await record({
        hook_event_name: "Stop",
        session_id: sessionID,
        cwd: directory,
        transcript_path: transcript,
      });
    } catch {
      // capture is best-effort; never surface an error into the session
    } finally {
      try {
        unlinkSync(transcript);
      } catch {}
    }
  },
});
