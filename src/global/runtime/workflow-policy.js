import fs from "node:fs"
import path from "node:path"


export const WORKFLOW_POLICY_SCHEMA =
  "https://schemas.biexce.local/runtime/workflow-policy-v1.schema.json"

export const WORKFLOW_PROFILES = [
  "fast",
  "standard",
  "critical",
  "advisory",
]

export const DRIVER_STATUSES = [
  "IDLE",
  "RUNNING",
  "WAITING_AGENT",
  "WAITING_HUMAN",
  "PAUSED",
  "BLOCKED",
  "COMPLETE",
]

const POLICY_KEYS = new Set([
  "$schema",
  "schema_version",
  "project_root",
  "requested_profile",
  "effective_profile",
  "source",
  "risk_flags",
  "policy",
  "driver_status",
  "last_terminal_reason",
  "updated_at_utc",
  "updated_by",
])

const POLICY_VALUE_KEYS = new Set([
  "execute_source",
  "max_batch",
  "require_gate_1",
  "require_gate_2",
  "stop_on_task_blocker",
])

const PROFILE_POLICIES = Object.freeze({
  fast: Object.freeze({
    execute_source: true,
    max_batch: 4,
    require_gate_1: true,
    require_gate_2: true,
    stop_on_task_blocker: false,
  }),
  standard: Object.freeze({
    execute_source: true,
    max_batch: 3,
    require_gate_1: true,
    require_gate_2: true,
    stop_on_task_blocker: false,
  }),
  critical: Object.freeze({
    execute_source: true,
    max_batch: 1,
    require_gate_1: true,
    require_gate_2: true,
    stop_on_task_blocker: true,
  }),
  advisory: Object.freeze({
    execute_source: false,
    max_batch: 0,
    require_gate_1: false,
    require_gate_2: false,
    stop_on_task_blocker: true,
  }),
})

const RISK_PATTERNS = Object.freeze([
  ["authentication", /\b(auth|authentication|authorization|login|password|credential|permission)\b/i],
  ["database-migration", /\b(database\s+migration|schema\s+migration|migrat(?:e|ion|ing))\b/i],
  ["payment", /\b(payment|billing|invoice|financial|checkout)\b/i],
  ["personal-data", /\b(personal\s+data|pii|privacy|health\s+data)\b/i],
  ["production", /\b(production|deploy(?:ment)?|release\s+infrastructure)\b/i],
  ["destructive-operation", /\b(drop\s+table|delete\s+all|irreversible|destructive)\b/i],
])

// Only work that can affect a live environment or perform an irreversible
// operation is promoted automatically. Authentication, migrations and data
// handling remain visible risk flags, but they are normal application work and
// must not silently turn the default workflow into a fail-closed pipeline.
const AUTO_CRITICAL_RISKS = new Set([
  "production",
  "destructive-operation",
])

const AUTO_CRITICAL_INTENT_PATTERNS = Object.freeze([
  [
    "production",
    /\b(?:deploy|publish|release|roll\s*out|migrate|modify|mutate|write|delete)\b[^\n.]{0,80}\b(?:production|live\s+environment)\b|\bproduction\b[^\n.]{0,80}\b(?:deployment|database|infrastructure|environment)\b/i,
  ],
  [
    "destructive-operation",
    /\b(?:drop\s+table|truncate\s+table|delete\s+all|irreversible\s+(?:change|migration|operation))\b/i,
  ],
])

const NEGATED_RISK_LINE =
  /\b(?:non-production|out\s+of\s+scope|do\s+not|don't|must\s+not|no\s+production|without\s+production|avoid|forbid|deny)\b/i


function exactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false
  const keys = Object.keys(value)
  return keys.length === expected.size && keys.every((key) => expected.has(key))
}


function projectRootFor(projectRoot) {
  const root = fs.realpathSync(projectRoot)
  if (!fs.statSync(root).isDirectory()) {
    throw new Error("workflow policy project root is not a directory")
  }
  return root
}


export function workflowPolicyPath(projectRoot) {
  const root = projectRootFor(projectRoot)
  return path.join(root, ".biexce", "state", "AUTOPILOT_POLICY.json")
}


function atomicWriteJson(file, value) {
  const directory = path.dirname(file)
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 })
  const realDirectory = fs.realpathSync(directory)
  const root = fs.realpathSync(path.join(directory, "..", ".."))
  if (!realDirectory.startsWith(root + path.sep)) {
    throw new Error("workflow policy path escapes the project root")
  }
  const temporary = file + "." + process.pid + "." + Date.now() + ".tmp"
  try {
    fs.writeFileSync(temporary, JSON.stringify(value, null, 2) + "\n", {
      encoding: "utf8",
      mode: 0o600,
      flag: "wx",
    })
    fs.renameSync(temporary, file)
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary)
  }
}


function boundedArtifactText(projectRoot) {
  const root = projectRootFor(projectRoot)
  const biexce = path.join(root, ".biexce")
  const candidates = [
    path.join(biexce, "PROJECT_BRIEF.md"),
    path.join(biexce, "MASTER_PLAN.md"),
  ]
  const tasks = path.join(biexce, "tasks")
  if (fs.existsSync(tasks) && fs.statSync(tasks).isDirectory()) {
    for (const name of fs.readdirSync(tasks).sort()) {
      if (/^t-[0-9]{3}\.md$/.test(name)) candidates.push(path.join(tasks, name))
    }
  }
  let size = 0
  const chunks = []
  for (const file of candidates) {
    if (!fs.existsSync(file)) continue
    const stat = fs.lstatSync(file)
    if (!stat.isFile() || stat.isSymbolicLink()) continue
    if (size + stat.size > 2 * 1024 * 1024) break
    chunks.push(fs.readFileSync(file, "utf8"))
    size += stat.size
  }
  return chunks.join("\n")
}


export function detectWorkflowRisks(projectRoot) {
  const text = boundedArtifactText(projectRoot)
  return RISK_PATTERNS
    .filter(([, pattern]) => pattern.test(text))
    .map(([flag]) => flag)
}


function detectsCriticalIntent(projectRoot) {
  const affirmative = boundedArtifactText(projectRoot)
    .split(/\r?\n/)
    .filter((line) => !NEGATED_RISK_LINE.test(line))
    .join("\n")
  return AUTO_CRITICAL_INTENT_PATTERNS.some(([, pattern]) =>
    pattern.test(affirmative)
  )
}


export function profilePolicy(profile) {
  if (!WORKFLOW_PROFILES.includes(profile)) {
    throw new Error("unsupported BIEXCE workflow profile: " + profile)
  }
  return { ...PROFILE_POLICIES[profile] }
}


export function selectWorkflowProfile(
  projectRoot,
  { requestedProfile = "auto", allowCriticalDowngrade = false } = {},
) {
  if (!["auto", ...WORKFLOW_PROFILES].includes(requestedProfile)) {
    throw new Error("unsupported requested workflow profile: " + requestedProfile)
  }
  if (typeof allowCriticalDowngrade !== "boolean") {
    throw new Error("allowCriticalDowngrade must be boolean")
  }
  const riskFlags = detectWorkflowRisks(projectRoot)
  const criticalRisk =
    riskFlags.some((flag) => AUTO_CRITICAL_RISKS.has(flag)) &&
    detectsCriticalIntent(projectRoot)
  let effectiveProfile = requestedProfile
  let source = "explicit"
  if (requestedProfile === "auto") {
    effectiveProfile = criticalRisk ? "critical" : "standard"
    source = "auto"
  } else if (
    requestedProfile !== "critical" &&
    requestedProfile !== "advisory" &&
    criticalRisk
  ) {
    if (allowCriticalDowngrade) {
      source = "explicit-override"
    } else {
      effectiveProfile = "critical"
      source = "risk-escalation"
    }
  }
  return {
    requested_profile: requestedProfile,
    effective_profile: effectiveProfile,
    source,
    risk_flags: riskFlags,
    policy: profilePolicy(effectiveProfile),
  }
}


function validateWorkflowPolicy(document, projectRoot) {
  const root = projectRootFor(projectRoot)
  if (!exactKeys(document, POLICY_KEYS)) {
    throw new Error("workflow policy properties mismatch")
  }
  if (
    document.$schema !== WORKFLOW_POLICY_SCHEMA ||
    document.schema_version !== 1 ||
    path.resolve(document.project_root) !== path.resolve(root)
  ) {
    throw new Error("workflow policy identity is invalid")
  }
  if (
    !["auto", ...WORKFLOW_PROFILES].includes(document.requested_profile) ||
    !WORKFLOW_PROFILES.includes(document.effective_profile) ||
    !Array.isArray(document.risk_flags) ||
    !document.risk_flags.every((value) => typeof value === "string") ||
    !exactKeys(document.policy, POLICY_VALUE_KEYS) ||
    !DRIVER_STATUSES.includes(document.driver_status) ||
    !(document.last_terminal_reason === null || typeof document.last_terminal_reason === "string") ||
    typeof document.updated_at_utc !== "string" ||
    typeof document.updated_by !== "string"
  ) {
    throw new Error("workflow policy content is invalid")
  }
  return document
}


export function selectAndPersistWorkflowPolicy(
  projectRoot,
  {
    requestedProfile = "auto",
    allowCriticalDowngrade = false,
    actor = "biexce-runtime",
  } = {},
) {
  const root = projectRootFor(projectRoot)
  const selection = selectWorkflowProfile(root, {
    requestedProfile,
    allowCriticalDowngrade,
  })
  const document = {
    $schema: WORKFLOW_POLICY_SCHEMA,
    schema_version: 1,
    project_root: root,
    ...selection,
    driver_status: "IDLE",
    last_terminal_reason: null,
    updated_at_utc: new Date().toISOString(),
    updated_by: actor,
  }
  atomicWriteJson(workflowPolicyPath(root), document)
  return document
}


export function loadWorkflowPolicy(projectRoot, { required = false } = {}) {
  const file = workflowPolicyPath(projectRoot)
  if (!fs.existsSync(file)) {
    if (required) throw new Error("workflow policy was not created")
    return null
  }
  const stat = fs.lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error("workflow policy is not a regular file")
  }
  return validateWorkflowPolicy(
    JSON.parse(fs.readFileSync(file, "utf8")),
    projectRoot,
  )
}


export function updateWorkflowPolicy(
  projectRoot,
  { driverStatus, terminalReason = null, actor = "biexce-runtime" },
) {
  if (!DRIVER_STATUSES.includes(driverStatus)) {
    throw new Error("workflow driver status is invalid: " + driverStatus)
  }
  if (!(terminalReason === null || typeof terminalReason === "string")) {
    throw new Error("workflow terminal reason must be null or string")
  }
  const current = loadWorkflowPolicy(projectRoot, { required: true })
  const next = {
    ...current,
    driver_status: driverStatus,
    last_terminal_reason: terminalReason,
    updated_at_utc: new Date().toISOString(),
    updated_by: actor,
  }
  atomicWriteJson(workflowPolicyPath(projectRoot), next)
  return next
}
