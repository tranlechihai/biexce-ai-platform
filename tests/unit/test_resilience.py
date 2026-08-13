import os
from pathlib import Path
import subprocess
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY_ROOT / "src" / "global" / "runtime" / "resilience.js"


class RuntimeResilienceTests(unittest.TestCase):
    def run_node(self, script):
        environment = os.environ.copy()
        environment["MODULE_URL"] = MODULE_PATH.resolve().as_uri()
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_classifier_retry_fallback_and_zone_boundary(self):
        self.run_node(
            r"""
import assert from "node:assert/strict"
const runtime = await import(process.env.MODULE_URL)

assert.equal(
  runtime.classifyRuntimeError(Object.assign(new Error("socket reset"), {
    code: "ECONNRESET",
  })),
  "TRANSPORT",
)
assert.equal(
  runtime.classifyRuntimeError(new Error("invalid API key")),
  "AUTH",
)
assert.equal(
  runtime.classifyRuntimeError(new Error("Request aborted by OpenCode UI")),
  "CANCELLED",
)
assert.equal(
  runtime.classifyRuntimeError(
    new Error("agent result is not valid JSON: unexpected end"),
  ),
  "CONTRACT",
)
assert.equal(
  runtime.classifyRuntimeError(
    new Error("PASS requires deterministic evidence from biexce_submit_result"),
  ),
  "CONTRACT",
)

const unconfirmed = runtime.runtimeModels({
  primary: "biexce-local/vllm/local-model",
  fallbacks: ["cloud/backup"],
  confirmed_cross_zone_fallbacks: [],
})
assert.deepEqual(
  unconfirmed.map((candidate) => candidate.model),
  ["biexce-local/vllm/local-model"],
)
const confirmed = runtime.runtimeModels({
  primary: "biexce-local/vllm/local-model",
  fallbacks: ["cloud/backup"],
  confirmed_cross_zone_fallbacks: ["cloud/backup"],
})
assert.deepEqual(
  confirmed.map((candidate) => candidate.model),
  ["biexce-local/vllm/local-model", "cloud/backup"],
)

const retryAttempts = []
const retried = await runtime.executeWithRetry({
  candidates: [{ model: "local/primary", zone: "cloud", fallback: false }],
  retriesPerModel: 1,
  backoffMs: 0,
  execute: async ({ model, attempt }) => {
    retryAttempts.push({ model, attempt })
    if (attempt === 1) {
      throw Object.assign(new Error("connection reset"), { code: "ECONNRESET" })
    }
    return "retry-pass"
  },
})
assert.equal(retried.value, "retry-pass")
assert.equal(retried.attempt, 2)
assert.equal(retryAttempts.length, 2)

const invoked = []
const fallback = await runtime.executeWithRetry({
  candidates: confirmed,
  retriesPerModel: 0,
  backoffMs: 0,
  execute: async ({ model }) => {
    invoked.push(model)
    if (model.includes("local-model")) {
      throw new Error("model unavailable")
    }
    return "fallback-pass"
  },
})
assert.equal(fallback.model, "cloud/backup")
assert.equal(fallback.value, "fallback-pass")
assert.deepEqual(invoked, [
  "biexce-local/vllm/local-model",
  "cloud/backup",
])

let authAttempts = 0
await assert.rejects(
  runtime.executeWithRetry({
    candidates: confirmed,
    retriesPerModel: 2,
    backoffMs: 0,
    execute: async () => {
      authAttempts += 1
      throw new Error("invalid API key")
    },
  }),
  (error) => error.biexceKind === "AUTH",
)
assert.equal(authAttempts, 1)

let contractAttempts = 0
await assert.rejects(
  runtime.executeWithRetry({
    candidates: confirmed,
    retriesPerModel: 2,
    backoffMs: 0,
    execute: async () => {
      contractAttempts += 1
      throw new Error("changed_files claim has no runtime diff")
    },
  }),
  (error) => error.biexceKind === "CONTRACT",
)
assert.equal(contractAttempts, 1)
"""
        )


if __name__ == "__main__":
    unittest.main()
