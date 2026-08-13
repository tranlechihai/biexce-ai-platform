import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_PATH = (
    REPOSITORY_ROOT / "src" / "global" / "runtime" / "supervisor.js"
)


@unittest.skipUnless(shutil.which("node"), "Node.js is required for supervisor tests")
class RuntimeSupervisorTests(unittest.TestCase):
    def test_timeout_cancel_log_cap_and_process_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = textwrap.dedent(
                """
                const {
                  createRuntimeSupervisor,
                  isLongLivedServerCommand,
                } = await import(process.env.SUPERVISOR_URL)

                let aborts = 0
                const client = { session: {
                  prompt: async () => new Promise(() => {}),
                  abort: async () => {
                    aborts += 1
                    return await new Promise(() => {})
                  },
                }}
                const supervisor = createRuntimeSupervisor({
                  client,
                  logLimitBytes: 64,
                  hardKillGraceMs: 50,
                })
                const executable = JSON.stringify(process.execPath)
                const noisyCommand = executable + " -e " +
                  JSON.stringify("process.stdout.write('x'.repeat(200))")
                const hangingCommand = executable + " -e " +
                  JSON.stringify("setInterval(() => {}, 1000)")

                const quick = await supervisor.runCommand({
                  sessionID: "command-session",
                  directory: process.env.PROJECT,
                  command: noisyCommand,
                  timeoutMs: 2000,
                })
                if (quick.exit_code !== 0 || !quick.truncated) {
                  throw new Error("managed command output cap failed")
                }
                if (Buffer.byteLength(quick.stdout) > 64) {
                  throw new Error("managed command exceeded log cap")
                }

                let commandTimeout = null
                try {
                  await supervisor.runCommand({
                    sessionID: "command-session",
                    directory: process.env.PROJECT,
                    command: hangingCommand,
                    timeoutMs: 150,
                  })
                } catch (error) {
                  commandTimeout = error.code
                }
                await supervisor.closeSession("command-session")

                let promptTimeout = null
                try {
                  await supervisor.supervisePrompt({
                    childID: "prompt-timeout",
                    directory: process.env.PROJECT,
                    body: {},
                    timeoutMs: 120,
                    pollMs: 50,
                    controlCheck: () => {},
                  })
                } catch (error) {
                  promptTimeout = error.code
                }
                await supervisor.closeSession("prompt-timeout")

                let controlStopped = null
                try {
                  await supervisor.supervisePrompt({
                    childID: "control-off",
                    directory: process.env.PROJECT,
                    body: {},
                    timeoutMs: 2000,
                    pollMs: 50,
                    controlCheck: () => { throw new Error("Autopilot is OFF") },
                  })
                } catch (error) {
                  controlStopped = error.code
                }
                await supervisor.closeSession("control-off")

                const controller = new AbortController()
                setTimeout(() => controller.abort(), 25)
                let userCancelled = null
                try {
                  await supervisor.supervisePrompt({
                    childID: "user-cancel",
                    directory: process.env.PROJECT,
                    body: {},
                    timeoutMs: 2000,
                    pollMs: 100,
                    signal: controller.signal,
                    controlCheck: () => {},
                  })
                } catch (error) {
                  userCancelled = error.code
                }
                await supervisor.closeSession("user-cancel")

                console.log(JSON.stringify({
                  commandTimeout,
                  promptTimeout,
                  controlStopped,
                  userCancelled,
                  aborts,
                  active: supervisor.activeSessionCount(),
                  rawServerDenied: isLongLivedServerCommand(
                    "python -m uvicorn app.main:app --port 8000"
                  ),
                  playwrightAllowed: !isLongLivedServerCommand(
                    "npx playwright test"
                  ),
                }))
                """
            )
            environment = os.environ.copy()
            environment["SUPERVISOR_URL"] = SUPERVISOR_PATH.resolve().as_uri()
            environment["PROJECT"] = temporary
            result = subprocess.run(
                [shutil.which("node"), "--input-type=module", "-e", script],
                cwd=REPOSITORY_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["commandTimeout"], "COMMAND_TIMEOUT")
            self.assertEqual(payload["promptTimeout"], "TIMEOUT")
            self.assertEqual(payload["controlStopped"], "CONTROL_STOPPED")
            self.assertEqual(payload["userCancelled"], "CANCELLED")
            self.assertEqual(payload["aborts"], 3)
            self.assertEqual(payload["active"], 0)
            self.assertTrue(payload["rawServerDenied"])
            self.assertTrue(payload["playwrightAllowed"])


if __name__ == "__main__":
    unittest.main()
