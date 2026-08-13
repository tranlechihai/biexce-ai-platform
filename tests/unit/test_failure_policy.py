import os
from pathlib import Path
import subprocess
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY_ROOT / "src" / "global" / "runtime" / "failure-policy.js"


class FailurePolicyTests(unittest.TestCase):
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

    def test_failure_policy_is_safe_table_driven_and_fix_bounded(self):
        self.run_node(
            r"""
import assert from "node:assert/strict"
const policy = await import(process.env.MODULE_URL)

const hardCases = [
  "OUTSIDE_PROJECT_WRITE",
  "PROTECTED_PATH_WRITE",
  "SECRET_EXPOSURE",
  "DESTRUCTIVE_OPERATION",
  "PRODUCTION_MUTATION",
  "WRITE_CONFLICT",
  "HUMAN_DECISION_REQUIRED",
  "GATE_REJECTED",
]
for (const code of hardCases) {
  const result = policy.classifyFailure({
    error: new Error("gateway timeout must not hide the boundary"),
    hardBoundary: code,
  })
  assert.equal(result.failure_class, "HARD_BLOCK", code)
  assert.equal(result.action, "BLOCK", code)
  assert.equal(result.reason_code, code, code)
  assert.equal(result.retryable, false, code)
  assert.equal(result.counts_as_fix_round, false, code)
  assert.equal(result.human_required, true, code)
}

for (const code of [
  "CHECK_FAILED",
  "REVIEW_CHANGES_REQUIRED",
  "ACCEPTANCE_FAILED",
]) {
  const result = policy.classifyFailure({ reasonCode: code, fixRound: 1 })
  assert.equal(result.failure_class, "SOURCE_FAILURE", code)
  assert.equal(result.action, "FIX", code)
  assert.equal(result.counts_as_fix_round, true, code)
  assert.equal(result.human_required, false, code)
}

const exhausted = policy.classifyFailure({
  reasonCode: "CHECK_FAILED",
  fixRound: 3,
  maxFixRounds: 3,
})
assert.equal(exhausted.failure_class, "HARD_BLOCK")
assert.equal(exhausted.action, "BLOCK")
assert.equal(exhausted.reason_code, "FIX_CAP_REACHED")
assert.equal(exhausted.human_required, true)

const transport = policy.classifyFailure({
  error: Object.assign(new Error("Bad Gateway"), { status: 502 }),
})
assert.equal(transport.failure_class, "SOFT_FAILURE")
assert.equal(transport.action, "RETRY")
assert.equal(transport.reason_code, "TRANSPORT")
assert.equal(transport.retryable, true)
assert.equal(transport.counts_as_fix_round, false)

const retryExhausted = policy.classifyFailure({
  error: new Error("Bad Gateway 502"),
  retryExhausted: true,
})
assert.equal(retryExhausted.failure_class, "SOFT_FAILURE")
assert.equal(retryExhausted.action, "PAUSE")
assert.equal(retryExhausted.retryable, false)
assert.equal(retryExhausted.human_required, false)

const auth = policy.classifyFailure({ error: new Error("invalid API key") })
assert.equal(auth.failure_class, "SOFT_FAILURE")
assert.equal(auth.action, "PAUSE")
assert.equal(auth.reason_code, "AUTH")
assert.equal(auth.human_required, true)

const cancelled = policy.classifyFailure({
  error: new Error("Request aborted by OpenCode UI"),
})
assert.equal(cancelled.failure_class, "SOFT_FAILURE")
assert.equal(cancelled.action, "PAUSE")
assert.equal(cancelled.reason_code, "CANCELLED")
assert.equal(cancelled.counts_as_fix_round, false)

const unknown = policy.classifyFailure({ error: new Error("unclassified") })
assert.equal(unknown.failure_class, "SOFT_FAILURE")
assert.equal(unknown.action, "PAUSE")
assert.equal(unknown.reason_code, "UNKNOWN")

assert.equal(policy.isHardBoundaryCode("secret-exposure"), true)
assert.equal(policy.isHardBoundaryCode("metadata-drift"), false)
assert.equal(policy.isSourceFailureCode("check-failed"), true)
assert.equal(policy.isSourceFailureCode("transport"), false)

assert.throws(
  () => policy.classifyFailure({ hardBoundary: "MADE_UP_BOUNDARY" }),
  /unknown hard boundary/,
)
assert.throws(() => policy.classifyFailure({ fixRound: -1 }), /fixRound/)
assert.throws(() => policy.classifyFailure({ maxFixRounds: 0 }), /maxFixRounds/)
"""
        )

    def test_protocol_drift_is_soft_but_real_boundary_stays_hard(self):
        self.run_node(
            r"""
import assert from "node:assert/strict"
const policy = await import(process.env.MODULE_URL)

const cases = [
  ["changed_files claim does not match runtime diff", "METADATA_DRIFT"],
  ["child returned without calling biexce_submit_result", "MISSING_SUBMIT"],
  ["runtime diff exceeds writable scope: src/__pycache__/a.pyc", "GENERATED_ARTIFACT"],
  ["runtime diff exceeds writable scope: tests/test_api_crud.py", "PROJECT_SCOPE_DRIFT"],
  ["contract conflict: a read-only test must be updated", "PROJECT_SCOPE_DRIFT"],
  ["verification-only owner role bx-test assigned to bx-code", "ROUTING_MISMATCH"],
  ["declared artifact is missing after tool execution", "REPORT_PATH_DRIFT"],
]

for (const [message, reason] of cases) {
  const result = policy.classifyFailure({ error: new Error(message) })
  assert.equal(result.failure_class, "SOFT_FAILURE", message)
  assert.equal(result.action, "RETRY", message)
  assert.equal(result.reason_code, reason, message)
  assert.equal(result.counts_as_fix_round, false, message)
}

const protectedWrite = policy.classifyFailure({
  error: new Error("runtime diff exceeds writable scope: ../outside.txt"),
  hardBoundary: "OUTSIDE_PROJECT_WRITE",
})
assert.equal(protectedWrite.failure_class, "HARD_BLOCK")
assert.equal(protectedWrite.action, "BLOCK")
assert.equal(protectedWrite.reason_code, "OUTSIDE_PROJECT_WRITE")

const inferredOutside = policy.classifyFailure({
  error: new Error("write escapes the project root"),
})
assert.equal(inferredOutside.failure_class, "HARD_BLOCK")
assert.equal(inferredOutside.reason_code, "OUTSIDE_PROJECT_WRITE")

const inferredProtected = policy.classifyFailure({
  error: new Error("protected project paths changed"),
})
assert.equal(inferredProtected.failure_class, "HARD_BLOCK")
assert.equal(inferredProtected.reason_code, "PROTECTED_PATH_WRITE")

const managedPlanDrift = policy.classifyFailure({
  error: new Error(
    "runtime diff exceeds writable scope: .biexce/MASTER_PLAN.md, " +
    ".biexce/tasks/t-001.md"
  ),
})
assert.equal(managedPlanDrift.failure_class, "SOFT_FAILURE")
assert.equal(managedPlanDrift.reason_code, "METADATA_DRIFT")

const reportedFailure = policy.classifyFailure({
  error: new Error("child reported failure: formatter check failed"),
  fixRound: 1,
})
assert.equal(reportedFailure.failure_class, "SOURCE_FAILURE")
assert.equal(reportedFailure.action, "FIX")
assert.equal(reportedFailure.reason_code, "CHECK_FAILED")
assert.equal(reportedFailure.counts_as_fix_round, true)

const genericContract = policy.classifyFailure({
  error: new Error("agent result is not valid JSON"),
})
assert.equal(genericContract.failure_class, "SOFT_FAILURE")
assert.equal(genericContract.action, "PAUSE")
assert.equal(genericContract.reason_code, "CONTRACT")

assert.equal(policy.failurePolicyMode({}), "v2")
assert.equal(
  policy.failurePolicyMode({ BIEXCE_FAILURE_POLICY_MODE: " SHADOW " }),
  "shadow",
)
assert.throws(
  () => policy.failurePolicyMode({ BIEXCE_FAILURE_POLICY_MODE: "slim" }),
  /must be v2 or shadow/,
)

assert.equal(
  policy.failurePolicyShadowEvent(
    { error: new Error("Bad Gateway"), jobID: "job-1" },
    {},
  ),
  null,
)
const shadow = policy.failurePolicyShadowEvent(
  {
    error: new Error("child returned without calling biexce_submit_result"),
    jobID: "job-1",
    taskID: "t-001",
    phase: "PLAN",
    legacyDisposition: "BLOCK",
  },
  { BIEXCE_FAILURE_POLICY_MODE: "shadow" },
)
assert.equal(shadow.event, "FAILURE_POLICY_SHADOW")
assert.equal(shadow.legacy_disposition, "BLOCK")
assert.equal(shadow.proposed.failure_class, "SOFT_FAILURE")
assert.equal(shadow.proposed.action, "RETRY")
assert.equal(shadow.proposed.reason_code, "MISSING_SUBMIT")
"""
        )


if __name__ == "__main__":
    unittest.main()
