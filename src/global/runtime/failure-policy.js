import { classifyRuntimeError } from "./resilience.js"
import {
  scopeFailure,
  SCOPE_FAILURES,
} from "./scope-policy.js"


export const FAILURE_CLASSES = Object.freeze({
  HARD_BLOCK: "HARD_BLOCK",
  SOURCE_FAILURE: "SOURCE_FAILURE",
  SOFT_FAILURE: "SOFT_FAILURE",
})

export const FAILURE_ACTIONS = Object.freeze({
  BLOCK: "BLOCK",
  FIX: "FIX",
  RETRY: "RETRY",
  PAUSE: "PAUSE",
})

export const FAILURE_POLICY_MODES = Object.freeze({
  V2: "v2",
  SHADOW: "shadow",
})

const HARD_BOUNDARY_CODES = new Set([
  "OUTSIDE_PROJECT_WRITE",
  "PROTECTED_PATH_WRITE",
  "SECRET_EXPOSURE",
  "DESTRUCTIVE_OPERATION",
  "PRODUCTION_MUTATION",
  "WRITE_CONFLICT",
  "HUMAN_DECISION_REQUIRED",
  "GATE_REJECTED",
  "FIX_CAP_REACHED",
])

const SOURCE_FAILURE_CODES = new Set([
  "CHECK_FAILED",
  "REVIEW_CHANGES_REQUIRED",
  "ACCEPTANCE_FAILED",
])

const RETRYABLE_SOFT_CODES = new Set([
  "TRANSPORT",
  "RATE_LIMIT",
  "OVERLOADED",
  "MODEL_UNAVAILABLE",
  "CONTEXT_OVERFLOW",
  "TIMEOUT",
  "METADATA_DRIFT",
  "MISSING_SUBMIT",
  "GENERATED_ARTIFACT",
  "ROUTING_MISMATCH",
  "STALE_LEASE",
  "REPORT_PATH_DRIFT",
  "PROJECT_SCOPE_DRIFT",
])

const EXTERNAL_PAUSE_CODES = new Set([
  "AUTH",
  "PERMISSION",
])


function normalizedCode(value) {
  if (typeof value !== "string" || !value.trim()) return null
  return value.trim().toUpperCase().replaceAll("-", "_")
}


function messageText(error) {
  return [error?.code, error?.name, error?.message]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
}


function protocolReason(error) {
  const text = messageText(error)
  if (/changed_files|changed files|claim(?:ed)? files|reporting drift/.test(text)) {
    return "METADATA_DRIFT"
  }
  if (/without calling biexce_submit_result|missing submit|submit result/.test(text)) {
    return "MISSING_SUBMIT"
  }
  const scope = scopeFailure(error)
  if (scope.kind === SCOPE_FAILURES.GENERATED) {
    return "GENERATED_ARTIFACT"
  }
  if (/verification-only|owner role|routing\/ownership|assigned to bx-code/.test(text)) {
    return "ROUTING_MISMATCH"
  }
  if (/declared artifact|report path|artifact is missing/.test(text)) {
    return "REPORT_PATH_DRIFT"
  }
  if (scope.kind === SCOPE_FAILURES.MANAGED_METADATA) return "METADATA_DRIFT"
  if (scope.kind === SCOPE_FAILURES.PROJECT_SCOPE_DRIFT) {
    return "PROJECT_SCOPE_DRIFT"
  }
  return null
}


function inferredHardBoundary(error) {
  const text = messageText(error)
  if (/escapes (?:the )?project root|outside (?:the )?project root/.test(text)) {
    return "OUTSIDE_PROJECT_WRITE"
  }
  if (scopeFailure(error).kind === SCOPE_FAILURES.HARD_BOUNDARY) {
    return "PROTECTED_PATH_WRITE"
  }
  if (/secret exposure|exposed secret|credential leak|private key exposure/.test(text)) {
    return "SECRET_EXPOSURE"
  }
  if (/production mutation/.test(text)) return "PRODUCTION_MUTATION"
  if (/destructive operation|drop database|recursive delete/.test(text)) {
    return "DESTRUCTIVE_OPERATION"
  }
  if (/write conflict|concurrent write/.test(text)) return "WRITE_CONFLICT"
  return null
}


function inferredSourceReason(error) {
  const text = messageText(error)
  if (/child reported failure:/.test(text)) return "CHECK_FAILED"
  return null
}


function decision({
  failureClass,
  action,
  reasonCode,
  runtimeKind,
  retryable = false,
  countsAsFixRound = false,
  humanRequired = false,
}) {
  return Object.freeze({
    failure_class: failureClass,
    action,
    reason_code: reasonCode,
    runtime_kind: runtimeKind,
    retryable,
    counts_as_fix_round: countsAsFixRound,
    human_required: humanRequired,
  })
}


export function classifyFailure({
  error = null,
  reasonCode = null,
  hardBoundary = null,
  sourceFailure = false,
  fixRound = 0,
  maxFixRounds = 3,
  retryExhausted = false,
} = {}) {
  if (!Number.isInteger(fixRound) || fixRound < 0) {
    throw new Error("fixRound must be a non-negative integer")
  }
  if (!Number.isInteger(maxFixRounds) || maxFixRounds < 1) {
    throw new Error("maxFixRounds must be a positive integer")
  }

  const explicitBoundary = normalizedCode(hardBoundary)
  const explicitReason = normalizedCode(reasonCode)
  const runtimeKind = error ? classifyRuntimeError(error) : "UNKNOWN"
  const protocolCode = protocolReason(error)
  const effectiveBoundary = explicitBoundary ||
    (protocolCode === null ? inferredHardBoundary(error) : null)

  if (effectiveBoundary) {
    if (!HARD_BOUNDARY_CODES.has(effectiveBoundary)) {
      throw new Error("unknown hard boundary: " + effectiveBoundary)
    }
    return decision({
      failureClass: FAILURE_CLASSES.HARD_BLOCK,
      action: FAILURE_ACTIONS.BLOCK,
      reasonCode: effectiveBoundary,
      runtimeKind,
      humanRequired: true,
    })
  }

  const sourceReason = sourceFailure
    ? explicitReason || "CHECK_FAILED"
    : SOURCE_FAILURE_CODES.has(explicitReason)
      ? explicitReason
      : inferredSourceReason(error)
  if (sourceReason) {
    if (fixRound >= maxFixRounds) {
      return decision({
        failureClass: FAILURE_CLASSES.HARD_BLOCK,
        action: FAILURE_ACTIONS.BLOCK,
        reasonCode: "FIX_CAP_REACHED",
        runtimeKind,
        humanRequired: true,
      })
    }
    return decision({
      failureClass: FAILURE_CLASSES.SOURCE_FAILURE,
      action: FAILURE_ACTIONS.FIX,
      reasonCode: sourceReason,
      runtimeKind,
      countsAsFixRound: true,
    })
  }

  // Protocol drift is identified from the concrete runtime evidence even when
  // the legacy classifier cannot assign a CONTRACT kind. This keeps recovery
  // independent from model wording and avoids project-specific exceptions.
  const softReason = explicitReason || protocolCode || runtimeKind || "UNKNOWN"
  const retryable = RETRYABLE_SOFT_CODES.has(softReason)
  const externalPause = EXTERNAL_PAUSE_CODES.has(softReason)
  const shouldPause = retryExhausted || !retryable || softReason === "CANCELLED"

  return decision({
    failureClass: FAILURE_CLASSES.SOFT_FAILURE,
    action: shouldPause ? FAILURE_ACTIONS.PAUSE : FAILURE_ACTIONS.RETRY,
    reasonCode: softReason,
    runtimeKind,
    retryable: retryable && !retryExhausted,
    humanRequired: externalPause,
  })
}


export function failurePolicyMode(environment = process.env) {
  const raw = environment?.BIEXCE_FAILURE_POLICY_MODE
  const mode = typeof raw === "string" && raw.trim()
    ? raw.trim().toLowerCase()
    : FAILURE_POLICY_MODES.V2
  if (!Object.values(FAILURE_POLICY_MODES).includes(mode)) {
    throw new Error("BIEXCE_FAILURE_POLICY_MODE must be v2 or shadow")
  }
  return mode
}


export function failurePolicyShadowEvent({
  error = null,
  jobID = null,
  taskID = null,
  phase = null,
  legacyDisposition = null,
  fixRound = 0,
  maxFixRounds = 3,
  retryExhausted = false,
} = {}, environment = process.env) {
  if (failurePolicyMode(environment) !== FAILURE_POLICY_MODES.SHADOW) return null
  return Object.freeze({
    event: "FAILURE_POLICY_SHADOW",
    job_id: jobID,
    task_id: taskID,
    phase,
    legacy_disposition: legacyDisposition,
    proposed: classifyFailure({
      error,
      fixRound,
      maxFixRounds,
      retryExhausted,
    }),
  })
}


export function isHardBoundaryCode(value) {
  return HARD_BOUNDARY_CODES.has(normalizedCode(value))
}


export function isSourceFailureCode(value) {
  return SOURCE_FAILURE_CODES.has(normalizedCode(value))
}
