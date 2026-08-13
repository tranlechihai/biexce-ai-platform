import { tool } from "@opencode-ai/plugin"
import crypto from "node:crypto"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import {
  acquireJobLease,
  appendJobEvent,
  hasActiveJobLeases,
  loadJobBoard,
  putJob,
  recordJobResult,
  releaseJobLease,
  taskResultHistory,
  workflowResultHistory,
} from "../runtime/job-board.js"
import { failurePolicyShadowEvent } from "../runtime/failure-policy.js"
import { reconcileRuntimeState } from "../runtime/reconciler.js"
import {
  createRuntimeSupervisor,
  isLongLivedServerCommand,
} from "../runtime/supervisor.js"
import {
  classifyRuntimeError,
  executeWithRetry,
  isFallbackKind,
  runtimeModels,
} from "../runtime/resilience.js"
import {
  loadSessionRegistry,
  putSessionRecord,
  resumableSession,
} from "../runtime/session-registry.js"
import {
  claimSchedulerJob,
  completeSchedulerJob,
  initializeScheduler,
  listSchedulerJobs,
  loadSchedulerState,
  planSchedulerBatch,
  releaseSchedulerJob,
  schedulerJob,
} from "../runtime/scheduler.js"
import {
  loadWorkflowPolicy,
  selectAndPersistWorkflowPolicy,
  updateWorkflowPolicy,
} from "../runtime/workflow-policy.js"
import {
  childSessionTitle,
  observabilityUpdate,
  responseUsage,
} from "../runtime/observability.js"
import {
  protectedProjectPath,
  scopeFailure,
  SCOPE_FAILURES,
} from "../runtime/scope-policy.js"


const AGENTS = [
  "bx-director",
  "bx-plan",
  "bx-explore",
  "bx-code",
  "bx-fix",
  "bx-test",
  "bx-review",
]

const CHILD_ALLOWLIST = AGENTS.filter((name) => name !== "bx-director")
const MANAGED_COMMAND_AGENTS = new Set(["bx-code", "bx-fix", "bx-test"])
const SHARED_ACTIVE_CHILDREN = new Map()
const SHARED_SUBMITTED_RESULTS = new Map()
const SHARED_COMMAND_EVIDENCE = new Map()
const SHARED_DIRECTOR_SESSIONS = new Map()
const DIRECTOR_WRITE_SCOPE = [
  ".biexce/PROJECT_BRIEF.md",
  ".biexce/reports/FINAL_REPORT.md",
]
const ROUTING_SCHEMA =
  "https://schemas.biexce.local/control-plane/model-routing-v1.schema.json"
const APPLIED_SCHEMA =
  "https://schemas.biexce.local/control-plane/model-routing-applied-v1.schema.json"
const CONTROL_SCHEMA =
  "https://schemas.biexce.local/control-plane/autopilot-state-v1.schema.json"
const CONTROL_KEYS = new Set([
  "$schema",
  "schema_version",
  "project_root",
  "mode",
  "revision",
  "updated_at_utc",
  "updated_by",
  "reason",
  "source",
  "action",
  "session_id",
])
const WORKFLOW_SCHEMA =
  "https://schemas.biexce.local/control-plane/autopilot-workflow-v2.schema.json"
const LEGACY_WORKFLOW_SCHEMA =
  "https://schemas.biexce.local/control-plane/autopilot-workflow-v1.schema.json"
const TRANSITION_AUTHORITY = "biexce-runtime"
const WORKFLOW_KEYS = new Set([
  "$schema",
  "schema_version",
  "project_root",
  "phase",
  "revision",
  "current_task_id",
  "plan_revision",
  "fix_round",
  "gate_1",
  "gate_1_approved_by",
  "gate_1_approved_at_utc",
  "gate_2",
  "gate_2_approved_by",
  "gate_2_approved_at_utc",
  "last_agent",
  "last_result",
  "blocked_reason",
  "updated_at_utc",
  "updated_by",
  "transition_authority",
])
const LEGACY_WORKFLOW_KEYS = new Set(
  [...WORKFLOW_KEYS].filter((key) => key !== "transition_authority"),
)
const COMMAND_SCHEMA =
  "https://schemas.biexce.local/control-plane/autopilot-command-v1.schema.json"
const COMMAND_KEYS = new Set([
  "$schema",
  "schema_version",
  "project_root",
  "command",
  "reason",
  "requested_by",
  "requested_at_utc",
  "workflow_revision",
  "task_id",
])
const AGENT_RESULT_SCHEMA =
  "https://schemas.biexce.local/runtime/agent-result-v1.schema.json"
const AGENT_RESULT_STATUSES = new Set([
  "SUCCEEDED",
  "FAILED",
  "PASS",
  "FAIL",
  "INCONCLUSIVE",
  "PLAN_OK",
  "PLAN_NEEDS_REVISION",
  "APPROVE",
  "APPROVE_WITH_MINOR_NOTES",
  "CHANGES_REQUIRED",
])
const PHASE_AGENTS = {
  EXPLORE: "bx-explore",
  PLAN: "bx-plan",
  PLAN_REVIEW: "bx-review",
  CODE: "bx-code",
  TEST: "bx-test",
  FIX: "bx-fix",
  TASK_REVIEW: "bx-review",
  INTEGRATION_TEST: "bx-test",
  INTEGRATION_FIX: "bx-fix",
  INTEGRATION_REVIEW: "bx-review",
}
const TASK_STATUSES = new Set([
  "backlog",
  "planning",
  "coding",
  "testing",
  "fixing",
  "reviewing",
  "done",
  "escalated",
])


function exactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false
  const keys = Object.keys(value)
  return keys.length === expected.size && keys.every((key) => expected.has(key))
}


function readJson(file, label) {
  let stat
  try {
    stat = fs.lstatSync(file)
  } catch (error) {
    if (error?.code === 'ENOENT') {
      throw new Error(`${label} was not created: ${file}`)
    }
    throw error
  }
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error(`${label} is not a regular file: ${file}`)
  }
  const raw = fs.readFileSync(file)
  return { raw, value: JSON.parse(raw.toString("utf8")) }
}


function configHome() {
  if (process.env.BIEXCE_CONFIG_HOME) {
    return path.resolve(process.env.BIEXCE_CONFIG_HOME)
  }
  return path.join(os.homedir(), ".config", "biexce")
}


function validateRouting(routing) {
  const rootKeys = new Set([
    "$schema",
    "schema_version",
    "inherit_parent_model",
    "unconfigured_policy",
    "active_profile",
    "revision",
    "updated_at_utc",
    "updated_by",
    "agents",
  ])
  if (!exactKeys(routing, rootKeys)) throw new Error("routing properties mismatch")
  if (
    routing.$schema !== ROUTING_SCHEMA ||
    routing.schema_version !== 1 ||
    routing.inherit_parent_model !== false ||
    routing.unconfigured_policy !== "block"
  ) {
    throw new Error("routing fail-closed fields are invalid")
  }
  if (!exactKeys(routing.agents, new Set(AGENTS))) {
    throw new Error("routing must contain exactly seven BIEXCE agents")
  }
  for (const agent of AGENTS) {
    const binding = routing.agents[agent]
    const bindingKeys = new Set([
      "primary",
      "fallbacks",
      "source",
      "confirmed_cross_zone_fallbacks",
    ])
    if (!exactKeys(binding, bindingKeys)) throw new Error(`${agent} binding invalid`)
    if (typeof binding.primary !== "string" || !binding.primary.includes("/")) {
      throw new Error(`${agent} primary is not configured`)
    }
    if (!Array.isArray(binding.fallbacks)) throw new Error(`${agent} fallbacks invalid`)
    if (
      !Array.isArray(binding.confirmed_cross_zone_fallbacks) ||
      !binding.confirmed_cross_zone_fallbacks.every((value) =>
        binding.fallbacks.includes(value),
      )
    ) {
      throw new Error(`${agent} fallback confirmations invalid`)
    }

    const primaryLocal = binding.primary.startsWith("biexce-local/")
    for (const fallback of binding.fallbacks) {
      const fallbackLocal = fallback.startsWith("biexce-local/")
      if (
        fallbackLocal !== primaryLocal &&
        !binding.confirmed_cross_zone_fallbacks.includes(fallback)
      ) {
        throw new Error(`${agent} cross-zone fallback is not confirmed`)
      }
    }
  }
  return routing
}


function loadAppliedRouting() {
  const home = configHome()
  const sourcePath = path.join(home, "model-routing.json")
  const appliedPath = path.join(home, "model-routing.applied.json")
  const source = readJson(sourcePath, "BIEXCE model routing")
  const applied = readJson(appliedPath, "BIEXCE applied routing").value
  const appliedKeys = new Set([
    "$schema",
    "schema_version",
    "source_path",
    "source_sha256",
    "applied_at_utc",
    "applied_by",
    "routing",
  ])
  if (!exactKeys(applied, appliedKeys)) throw new Error("applied routing invalid")
  if (applied.$schema !== APPLIED_SCHEMA || applied.schema_version !== 1) {
    throw new Error("applied routing schema invalid")
  }
  if (path.resolve(applied.source_path) !== path.resolve(sourcePath)) {
    throw new Error("applied routing references another source")
  }
  const hash = crypto.createHash("sha256").update(source.raw).digest("hex")
  if (applied.source_sha256 !== hash) throw new Error("routing changed after apply")
  if (JSON.stringify(source.value) !== JSON.stringify(applied.routing)) {
    throw new Error("applied routing content drift")
  }
  return validateRouting(applied.routing)
}


function loadRunningState(
  directory,
  sessionID,
  { allowSessionRebind = false } = {},
) {
  const projectRoot = fs.realpathSync(directory)
  const statePath = path.join(projectRoot, ".biexce", "state", "AUTOPILOT_CONTROL.json")
  const realStatePath = fs.realpathSync(statePath)
  if (!realStatePath.startsWith(projectRoot + path.sep)) {
    throw new Error("control state escapes the project root")
  }
  const state = readJson(statePath, "BIEXCE Autopilot control state").value
  if (!exactKeys(state, CONTROL_KEYS)) throw new Error("control state properties mismatch")
  if (state.$schema !== CONTROL_SCHEMA || state.schema_version !== 1) {
    throw new Error("control state schema invalid")
  }
  if (path.resolve(state.project_root) !== path.resolve(projectRoot)) {
    throw new Error("control state belongs to another project")
  }
  if (state.mode !== "RUNNING") throw new Error(`Autopilot is ${state.mode || "OFF"}`)
  if (state.session_id !== null && state.session_id !== sessionID) {
    if (!allowSessionRebind || hasActiveJobLeases(projectRoot)) {
      throw new Error("Autopilot is armed for another session")
    }
    const rebound = {
      ...state,
      revision: state.revision + 1,
      updated_at_utc: new Date().toISOString(),
      updated_by: "biexce-runtime-reconciler",
      reason: "Runtime resumed in a new Director session after restart",
      source: "desktop",
      action: "start",
      session_id: sessionID,
    }
    atomicWriteJson(statePath, rebound)
    return rebound
  }
  return state
}


function stopControlAtRuntime(projectRoot, state) {
  const next = {
    ...state,
    mode: "OFF",
    revision: state.revision + 1,
    updated_at_utc: new Date().toISOString(),
    updated_by: "biexce-control-plugin",
    reason: "Human Gate 2 approved in OpenCode",
    source: "desktop",
    action: "off",
    session_id: null,
  }
  atomicWriteJson(
    path.join(projectRoot, ".biexce", "state", "AUTOPILOT_CONTROL.json"),
    next,
  )
  return next
}


function atomicWriteJson(file, value) {
  const temporary = `${file}.${process.pid}.${Date.now()}.tmp`
  try {
    fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600,
      flag: "wx",
    })
    fs.renameSync(temporary, file)
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary)
  }
}


function atomicWriteText(file, value) {
  const temporary = `${file}.${process.pid}.${Date.now()}.tmp`
  try {
    fs.writeFileSync(temporary, value, { encoding: "utf8", mode: 0o600, flag: "wx" })
    fs.renameSync(temporary, file)
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary)
  }
}


function workflowPath(projectRoot) {
  return path.join(projectRoot, ".biexce", "state", "AUTOPILOT_WORKFLOW.json")
}


function loadWorkflow(projectRoot) {
  const file = workflowPath(projectRoot)
  const realFile = fs.realpathSync(file)
  if (!realFile.startsWith(projectRoot + path.sep)) {
    throw new Error("workflow state escapes the project root")
  }
  let workflow = readJson(file, "BIEXCE Autopilot workflow state").value
  if (
    exactKeys(workflow, LEGACY_WORKFLOW_KEYS) &&
    workflow.$schema === LEGACY_WORKFLOW_SCHEMA &&
    workflow.schema_version === 1
  ) {
    workflow = {
      ...workflow,
      $schema: WORKFLOW_SCHEMA,
      schema_version: 2,
      transition_authority: TRANSITION_AUTHORITY,
      updated_at_utc: new Date().toISOString(),
      updated_by: "biexce-workflow-migration",
    }
    atomicWriteJson(file, workflow)
  }
  if (!exactKeys(workflow, WORKFLOW_KEYS)) {
    throw new Error("workflow state properties mismatch")
  }
  if (
    workflow.$schema !== WORKFLOW_SCHEMA ||
    workflow.schema_version !== 2 ||
    workflow.transition_authority !== TRANSITION_AUTHORITY
  ) {
    throw new Error("workflow state schema invalid")
  }
  if (path.resolve(workflow.project_root) !== path.resolve(projectRoot)) {
    throw new Error("workflow state belongs to another project")
  }
  if (!Number.isInteger(workflow.revision) || workflow.revision < 1) {
    throw new Error("workflow revision invalid")
  }
  if (!Number.isInteger(workflow.plan_revision) || workflow.plan_revision < 0 || workflow.plan_revision > 2) {
    throw new Error("workflow plan revision invalid")
  }
  if (!Number.isInteger(workflow.fix_round) || workflow.fix_round < 0 || workflow.fix_round > 3) {
    throw new Error("workflow fix round invalid")
  }
  if (!(workflow.phase in PHASE_AGENTS) && ![
    "WAITING_GATE_1", "WAITING_GATE_2", "COMPLETE", "BLOCKED",
  ].includes(workflow.phase)) {
    throw new Error(`workflow phase invalid: ${workflow.phase}`)
  }
  if (!["PENDING", "APPROVED"].includes(workflow.gate_1) || ![
    "PENDING", "APPROVED",
  ].includes(workflow.gate_2)) {
    throw new Error("workflow gate status invalid")
  }
  const gate1Metadata =
    typeof workflow.gate_1_approved_by === "string" &&
    typeof workflow.gate_1_approved_at_utc === "string"
  const gate2Metadata =
    typeof workflow.gate_2_approved_by === "string" &&
    typeof workflow.gate_2_approved_at_utc === "string"
  if ((workflow.gate_1 === "APPROVED") !== gate1Metadata) {
    throw new Error("Gate 1 approval metadata is inconsistent")
  }
  if ((workflow.gate_2 === "APPROVED") !== gate2Metadata) {
    throw new Error("Gate 2 approval metadata is inconsistent")
  }
  return workflow
}


function saveWorkflow(projectRoot, workflow, updates) {
  const next = {
    ...workflow,
    ...updates,
    revision: workflow.revision + 1,
    updated_at_utc: new Date().toISOString(),
    updated_by: "biexce-control-plugin",
    transition_authority: TRANSITION_AUTHORITY,
  }
  atomicWriteJson(workflowPath(projectRoot), next)
  return next
}


function projectStatePath(projectRoot) {
  return path.join(projectRoot, ".biexce", "state", "PROJECT_STATE.json")
}


function loadProjectState(projectRoot) {
  const file = projectStatePath(projectRoot)
  const state = readJson(file, "BIEXCE project state").value
  if (!exactKeys(state, new Set(["project", "stage", "updated", "tasks"]))) {
    throw new Error("PROJECT_STATE properties mismatch")
  }
  if (!Array.isArray(state.tasks) || state.tasks.length === 0) {
    throw new Error("PROJECT_STATE tasks are missing")
  }
  for (const task of state.tasks) {
    if (!exactKeys(task, new Set(["id", "title", "status", "round", "agent"]))) {
      throw new Error("PROJECT_STATE task properties mismatch")
    }
    if (!/^t-[0-9]{3}$/.test(task.id) || !TASK_STATUSES.has(task.status)) {
      throw new Error(`PROJECT_STATE task invalid: ${task.id}`)
    }
  }
  return state
}


function saveProjectState(projectRoot, state) {
  atomicWriteJson(projectStatePath(projectRoot), {
    ...state,
    updated: new Date().toISOString(),
  })
}


function runtimeCommandPath(projectRoot) {
  return path.join(projectRoot, ".biexce", "state", "AUTOPILOT_COMMAND.json")
}


function appendRecoveryAudit(projectRoot, event) {
  const file = path.join(projectRoot, ".biexce", "state", "AUTOPILOT_RECOVERY.jsonl")
  let existing = ""
  if (fs.existsSync(file)) {
    const stat = fs.lstatSync(file)
    if (!stat.isFile() || stat.isSymbolicLink()) {
      throw new Error("recovery audit is not a regular file")
    }
    existing = fs.readFileSync(file, "utf8")
    for (const line of existing.split(/\r?\n/).filter((value) => value.trim())) {
      JSON.parse(line)
    }
  }
  const separator = existing && !existing.endsWith("\n") ? "\n" : ""
  atomicWriteText(file, `${existing}${separator}${JSON.stringify(event)}\n`)
}


function applyPendingRuntimeCommand(projectRoot, workflow) {
  const file = runtimeCommandPath(projectRoot)
  if (!fs.existsSync(file)) return workflow
  const command = readJson(file, "BIEXCE runtime command").value
  if (!exactKeys(command, COMMAND_KEYS)) throw new Error("runtime command properties mismatch")
  if (command.$schema !== COMMAND_SCHEMA || command.schema_version !== 1) {
    throw new Error("runtime command schema invalid")
  }
  if (path.resolve(command.project_root) !== path.resolve(projectRoot)) {
    throw new Error("runtime command belongs to another project")
  }
  if (command.command !== "RECOVER_MANUAL_FIX") {
    throw new Error(`unsupported runtime command: ${command.command}`)
  }
  if (command.workflow_revision !== workflow.revision) {
    throw new Error("runtime command targets a stale workflow revision")
  }
  if (
    workflow.phase !== "BLOCKED" ||
    workflow.gate_1 !== "APPROVED" ||
    workflow.current_task_id !== command.task_id ||
    workflow.fix_round !== 3 ||
    workflow.blocked_reason !== `Fix cap reached for ${workflow.current_task_id}`
  ) {
    throw new Error("manual-fix command is invalid for the current workflow")
  }
  const legacyLock = delegationLockPath(projectRoot)
  if (fs.existsSync(legacyLock) || hasActiveJobLeases(projectRoot)) {
    throw new Error("cannot recover while a job lease is active")
  }
  const previousProject = loadProjectState(projectRoot)
  const active = previousProject.tasks.filter((task) =>
    ["planning", "coding", "testing", "fixing", "reviewing"].includes(task.status),
  )
  if (active.length > 0) throw new Error("cannot recover while another task is active")
  const blockedTask = previousProject.tasks.find((task) => task.id === command.task_id)
  if (
    !blockedTask ||
    blockedTask.status !== "escalated" ||
    blockedTask.round !== 3 ||
    blockedTask.agent !== null
  ) {
    throw new Error("blocked task state is invalid for manual-fix recovery")
  }
  const nextProject = setTaskState(
    previousProject,
    command.task_id,
    "fixing",
    "bx-fix",
    3,
  )
  const event = {
    schema_version: 1,
    event: "BLOCKED_RESOLVED",
    action: "manual-fix",
    actor: command.requested_by,
    reason: command.reason,
    project_root: projectRoot,
    task_id: command.task_id,
    fix_round: 3,
    from_phase: "BLOCKED",
    to_phase: "FIX",
    workflow_revision_before: workflow.revision,
    workflow_revision_after: workflow.revision + 1,
    timestamp_utc: new Date().toISOString(),
  }
  saveProjectState(projectRoot, { ...nextProject, stage: "B3" })
  try {
    const next = saveWorkflow(projectRoot, workflow, {
      phase: "FIX",
      last_agent: null,
      last_result: "HUMAN_RECOVERY_APPROVED",
      blocked_reason: null,
    })
    appendRecoveryAudit(projectRoot, event)
    fs.unlinkSync(file)
    return next
  } catch (error) {
    saveProjectState(projectRoot, previousProject)
    atomicWriteJson(workflowPath(projectRoot), workflow)
    throw error
  }
}


function markdownField(text, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const match = text.match(new RegExp(`^${escaped}:\\s*(.+?)\\s*$`, "im"))
  return match ? match[1].trim() : null
}


function derivedProjectID(projectRoot) {
  const basename = path.basename(projectRoot).normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
  const slug = basename.toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
  if (slug) return slug
  return `project-${crypto.createHash("sha256")
    .update(fs.realpathSync(projectRoot))
    .digest("hex")
    .slice(0, 12)}`
}


function ensureManagedArtifactDirectories(projectRoot) {
  for (const relative of [".biexce", ".biexce/reports"]) {
    const directory = path.join(projectRoot, ...relative.split("/"))
    if (fs.existsSync(directory)) {
      const stat = fs.lstatSync(directory)
      if (!stat.isDirectory() || stat.isSymbolicLink()) {
        throw new Error(`${relative} is not a safe managed directory`)
      }
      continue
    }
    fs.mkdirSync(directory, { recursive: true })
  }
}


function ensureProjectBriefMetadata(projectRoot) {
  const briefPath = path.join(projectRoot, ".biexce", "PROJECT_BRIEF.md")
  requireFile(projectRoot, ".biexce/PROJECT_BRIEF.md", "PROJECT_BRIEF")
  const brief = fs.readFileSync(briefPath, "utf8")
  const existing = markdownField(brief, "Project ID")
  if (existing) return existing
  const projectID = derivedProjectID(projectRoot)
  const normalized = brief.replace(/^\uFEFF/, "").trim()
  const lineBreak = normalized.indexOf("\n")
  const content = lineBreak >= 0 && /^#\s+/.test(normalized.slice(0, lineBreak))
    ? `${normalized.slice(0, lineBreak)}\n\nProject ID: ${projectID}\n\n` +
      `${normalized.slice(lineBreak + 1).trimStart()}\n`
    : `Project ID: ${projectID}\n\n${normalized}\n`
  atomicWriteText(briefPath, content)
  return projectID
}


function ensureMasterPlanControlMetadata(projectRoot) {
  const planPath = path.join(projectRoot, ".biexce", "MASTER_PLAN.md")
  requireFile(projectRoot, ".biexce/MASTER_PLAN.md", "MASTER_PLAN")
  const original = fs.readFileSync(planPath, "utf8").replace(/^\uFEFF/, "").trim()
  const requestedWip = Number.parseInt(markdownField(original, "WIP limit") || "", 10)
  const wip = Number.isInteger(requestedWip) && requestedWip >= 1 && requestedWip <= 4
    ? requestedWip
    : 1
  const controlLabels = ["WIP limit", "Fix cap", "Reports path", "Git/deploy"]
  const body = original.split(/\r?\n/).filter((line) =>
    !controlLabels.some((label) =>
      new RegExp(`^${label.replace("/", "\\/")}:\\s*`, "i").test(line.trim()),
    ),
  )
  const firstLine = body.shift() || "# MASTER_PLAN"
  // Removing the previous control block leaves the blank lines that surrounded
  // it. Drop only those leading separators so repeated validation is byte-for-
  // byte idempotent; otherwise every duplicate/restarted driver turn grows the
  // plan and a concurrent read-only PLAN_REVIEW sees a false out-of-scope diff.
  while (body.length > 0 && !body[0].trim()) body.shift()
  const controls = [
    `WIP limit: ${wip}`,
    "Fix cap: 3",
    "Reports path: .biexce/reports",
    "Git/deploy: forbidden",
  ]
  let normalized = [firstLine, "", ...controls, "", ...body].join("\n").trim()
  if (!/^##\s+Human Gates\s*$/im.test(normalized)) {
    normalized += [
      "",
      "",
      "## Human Gates",
      "",
      "- Gate 1: Human approves the reviewed plan before source execution.",
      "- Gate 2: Human accepts integration evidence before project closure.",
    ].join("\n")
  }
  normalized += "\n"
  if (normalized !== `${original}\n`) atomicWriteText(planPath, normalized)
}


function syncProjectStateFromPlan(projectRoot) {
  const projectID = ensureProjectBriefMetadata(projectRoot)
  const taskRoot = path.join(projectRoot, ".biexce", "tasks")
  const names = fs.readdirSync(taskRoot)
    .filter((name) => /^t-[0-9]{3}\.md$/.test(name))
    .sort()
  if (names.length < 1 || names.length > 50) {
    throw new Error(`plan must contain 1-50 task files; found ${names.length}`)
  }
  const tasks = names.map((name) => {
    const id = name.slice(0, -3)
    const text = fs.readFileSync(path.join(taskRoot, name), "utf8")
    const heading = text.match(new RegExp(
      `^#\\s+${id}\\s*(?:[:\\-]|\\u2013|\\u2014)\\s*(.+)$`,
      "m",
    ))
    if (!heading?.[1]?.trim()) throw new Error(`${id}: task title is invalid`)
    return {
      id,
      title: heading[1].trim(),
      status: "backlog",
      round: 0,
      agent: null,
    }
  })
  saveProjectState(projectRoot, {
    project: projectID,
    stage: "B2",
    tasks,
  })
  return tasks
}


function delegationLockPath(projectRoot) {
  return path.join(projectRoot, ".biexce", "state", "AUTOPILOT_DELEGATION.lock")
}


function positiveEnvironmentInteger(name, fallback, minimum, maximum) {
  const raw = process.env[name]
  if (!raw) return fallback
  const parsed = Number.parseInt(raw, 10)
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    return fallback
  }
  return parsed
}


function delegationTimeoutMs() {
  return positiveEnvironmentInteger(
    "BIEXCE_AGENT_TIMEOUT_MS",
    20 * 60 * 1000,
    1000,
    4 * 60 * 60 * 1000,
  )
}


function controlPollMs() {
  return positiveEnvironmentInteger("BIEXCE_CONTROL_POLL_MS", 1000, 100, 10000)
}


function commandTimeoutMs() {
  return positiveEnvironmentInteger(
    "BIEXCE_COMMAND_TIMEOUT_MS",
    2 * 60 * 1000,
    1000,
    60 * 60 * 1000,
  )
}


function commandLogLimitBytes() {
  return positiveEnvironmentInteger(
    "BIEXCE_COMMAND_LOG_LIMIT_BYTES",
    64 * 1024,
    1024,
    4 * 1024 * 1024,
  )
}


function hardKillGraceMs() {
  return positiveEnvironmentInteger(
    "BIEXCE_HARD_KILL_GRACE_MS",
    1000,
    10,
    30000,
  )
}


function transportRetries() {
  return positiveEnvironmentInteger(
    "BIEXCE_TRANSPORT_RETRIES",
    1,
    0,
    3,
  )
}


function retryBackoffMs() {
  return positiveEnvironmentInteger(
    "BIEXCE_RETRY_BACKOFF_MS",
    250,
    0,
    10000,
  )
}


function schedulerOptions() {
  return {
    localConcurrency: positiveEnvironmentInteger(
      "BIEXCE_LOCAL_CONCURRENCY",
      4,
      1,
      8,
    ),
    cloudConcurrency: positiveEnvironmentInteger(
      "BIEXCE_CLOUD_CONCURRENCY",
      3,
      1,
      16,
    ),
    readOnlyConcurrency: positiveEnvironmentInteger(
      "BIEXCE_READ_ONLY_CONCURRENCY",
      4,
      1,
      16,
    ),
  }
}


function taskDependencies(projectRoot, taskID) {
  const file = path.join(projectRoot, ".biexce", "tasks", `${taskID}.md`)
  const text = fs.readFileSync(file, "utf8")
  const match = text.match(/^Depends on:\s*(.+?)(?:\s*[·|]\s*Effort:|$)/im)
  if (!match || match[1].trim().toLowerCase() === "none") return []
  return match[1].match(/t-[0-9]{3}/g) || []
}


function commandOnPath(command, projectRoot) {
  const portable = command.replaceAll(String.fromCharCode(92), "/")
  if (portable.startsWith("./") || portable.includes("/")) {
    const candidate = path.resolve(projectRoot, command)
    return fs.existsSync(candidate) && fs.lstatSync(candidate).isFile()
  }
  const extensions = process.platform === "win32"
    ? (process.env.PATHEXT || ".COM;.EXE;.BAT;.CMD")
      .split(";")
      .filter(Boolean)
    : [""]
  const names = process.platform === "win32" && !path.extname(command)
    ? [command, ...extensions.map((extension) => command + extension)]
    : [command]
  return (process.env.PATH || "").split(path.delimiter).some((directory) =>
    names.some((name) => {
      const candidate = path.join(directory, name)
      try {
        return fs.statSync(candidate).isFile()
      } catch {
        return false
      }
    })
  )
}


function verifyExecutable(verify) {
  const inline = verify.trim().match(/^`+([\s\S]*?)`+$/)
  const command = (inline ? inline[1] : verify).trim()
  if (!command || /^N\/?A\b/i.test(command)) return { command, executable: null }
  const token = command.match(/^(?:"([^"]+)"|'([^']+)'|([^\s|;&]+))/)
  return { command, executable: token ? (token[1] || token[2] || token[3]) : null }
}


function unsafeWritablePattern(value) {
  const portable = value.toLowerCase()
  return ["*", "**", "/"].includes(portable) ||
    portable.startsWith("**/") ||
    portable === ".git" || portable.startsWith(".git/") ||
    portable === ".biexce" || portable.startsWith(".biexce/state/") ||
    portable === ".env" ||
    (portable.startsWith(".env.") && portable !== ".env.example")
}


function planReadiness(projectRoot) {
  const state = loadProjectState(projectRoot)
  const ids = new Set(state.tasks.map((task) => task.id))
  const errors = []
  const warnings = []
  const dependencies = new Map()
  for (const task of state.tasks) {
    const file = path.join(projectRoot, ".biexce", "tasks", `${task.id}.md`)
    let text = ""
    try {
      text = fs.readFileSync(file, "utf8")
    } catch {
      errors.push(`${task.id}: task contract is missing`)
      continue
    }
    const deps = taskDependencies(projectRoot, task.id)
    dependencies.set(task.id, deps)
    for (const dependency of deps) {
      if (!ids.has(dependency)) errors.push(`${task.id}: unknown dependency ${dependency}`)
      if (dependency === task.id) errors.push(`${task.id}: cannot depend on itself`)
    }
    const verify = markdownField(text, "Verify")
    const parsed = verify ? verifyExecutable(verify) : { command: "", executable: null }
    if (!verify || !parsed.command || /^N\/?A\b/i.test(parsed.command)) {
      errors.push(`${task.id}: Verify must contain an executable command`)
    } else if (!parsed.executable) {
      warnings.push(`${task.id}: Verify command could not be statically classified`)
    } else if (!commandOnPath(parsed.executable, projectRoot)) {
      errors.push(`${task.id}: Verify executable is unavailable: ${parsed.executable}`)
    }
    const writable = markdownField(text, "Writable files")
    if (!writable || writable.toLowerCase() === "none") {
      errors.push(`${task.id}: Writable files must be explicit and non-empty`)
      continue
    }
    for (const raw of writable.split(",")) {
      try {
        const normalized = normalizeProjectRelative(raw.trim(), `${task.id} Writable files`)
        if (unsafeWritablePattern(normalized)) {
          errors.push(`${task.id}: unsafe Writable files scope: ${normalized}`)
        }
      } catch (error) {
        errors.push(`${task.id}: ${error.message}`)
      }
    }
  }
  const visiting = new Set()
  const visited = new Set()
  const visit = (id, trail) => {
    if (visiting.has(id)) {
      errors.push(`task DAG contains a cycle: ${[...trail, id].join(" -> ")}`)
      return
    }
    if (visited.has(id)) return
    visiting.add(id)
    for (const dependency of dependencies.get(id) || []) {
      if (ids.has(dependency)) visit(dependency, [...trail, id])
    }
    visiting.delete(id)
    visited.add(id)
  }
  for (const id of ids) visit(id, [])
  return { errors: [...new Set(errors)], warnings: [...new Set(warnings)] }
}


function writePlanReadinessReport(projectRoot) {
  const readiness = planReadiness(projectRoot)
  const lines = [
    "# Gate 1 Preflight Report",
    "",
    "Generated by BIEXCE Runtime from plan and task contracts.",
    "",
    `Result: ${readiness.errors.length === 0 ? "PASS" : "FAIL"}`,
    "",
    "## Errors",
    "",
    ...(readiness.errors.length > 0
      ? readiness.errors.map((item) => `- ${item}`)
      : ["- None."]),
    "",
    "## Warnings",
    "",
    ...(readiness.warnings.length > 0
      ? readiness.warnings.map((item) => `- ${item}`)
      : ["- None."]),
    "",
  ]
  atomicWriteText(
    path.join(projectRoot, ".biexce", "reports", "PREFLIGHT_REPORT.md"),
    lines.join("\n"),
  )
  return readiness
}


function nextReadyTask(projectRoot, state) {
  const done = new Set(
    state.tasks.filter((task) => task.status === "done").map((task) => task.id),
  )
  const pending = state.tasks.filter((task) => task.status === "backlog")
  if (pending.length === 0) {
    if (state.tasks.every((task) => task.status === "done")) return null
    throw new Error("task DAG is blocked or contains an escalated task")
  }
  const ready = pending.find((task) =>
    taskDependencies(projectRoot, task.id).every((dependency) => done.has(dependency)),
  )
  if (!ready) throw new Error("no backlog task has satisfied dependencies")
  return ready.id
}


function setTaskState(state, taskID, status, agent, round) {
  let found = false
  const tasks = state.tasks.map((task) => {
    if (task.id !== taskID) return task
    found = true
    return { ...task, status, agent, round }
  })
  if (!found) throw new Error(`workflow task is missing from PROJECT_STATE: ${taskID}`)
  const active = tasks.filter((task) =>
    ["planning", "coding", "testing", "fixing", "reviewing"].includes(task.status),
  )
  if (active.length > 1) throw new Error("PROJECT_STATE violates WIP=1")
  return { ...state, tasks }
}


function requireFile(projectRoot, relative, label) {
  const file = path.join(projectRoot, ...relative.split("/"))
  const stat = fs.lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink() || !fs.readFileSync(file, "utf8").trim()) {
    throw new Error(`${label} is missing or empty: ${file}`)
  }
}


function requireDirectory(projectRoot, relative, label) {
  const directory = path.join(projectRoot, ...relative.split("/"))
  const stat = fs.lstatSync(directory)
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error(`${label} is missing or invalid: ${directory}`)
  }
}


function validateGateOne(projectRoot) {
  requireFile(projectRoot, ".biexce/PROJECT_BRIEF.md", "PROJECT_BRIEF")
  requireFile(projectRoot, ".biexce/CODEBASE_BRIEF.md", "CODEBASE_BRIEF")
  requireFile(projectRoot, ".biexce/MASTER_PLAN.md", "MASTER_PLAN")
  requireDirectory(projectRoot, ".biexce/reports", "reports path")
  const state = loadProjectState(projectRoot)
  if (state.stage !== "B2") {
    throw new Error(`Gate 1 requires PROJECT_STATE stage B2, found ${state.stage}`)
  }
  if (state.tasks.some((task) => task.status !== "backlog")) {
    throw new Error("Gate 1 requires every task to be in backlog")
  }
  for (const task of state.tasks) {
    requireFile(projectRoot, `.biexce/tasks/${task.id}.md`, `${task.id} contract`)
  }
  const readiness = writePlanReadinessReport(projectRoot)
  if (readiness.errors.length > 0) {
    throw new Error(
      "Gate 1 preflight failed: " + readiness.errors.join(" | "),
    )
  }
  return nextReadyTask(projectRoot, state)
}


function validateGateTwo(projectRoot) {
  const state = loadProjectState(projectRoot)
  if (!["B4", "B5"].includes(state.stage)) {
    throw new Error(`Gate 2 requires PROJECT_STATE stage B4 or B5, found ${state.stage}`)
  }
  if (!state.tasks.every((task) => task.status === "done" && task.agent === null)) {
    throw new Error("Gate 2 requires every task to be done and unassigned")
  }
  requireFile(
    projectRoot,
    ".biexce/reports/INTEGRATION_REPORT.md",
    "INTEGRATION_REPORT",
  )
  requireFile(projectRoot, ".biexce/reports/FINAL_REPORT.md", "FINAL_REPORT")
}


function approveGateAtRuntime(projectRoot, workflow, gate, actor) {
  const now = new Date().toISOString()
  if (gate === 1) {
    if (workflow.phase !== "WAITING_GATE_1" || workflow.gate_1 !== "PENDING") {
      throw new Error(`Gate 1 is invalid during ${workflow.phase}`)
    }
    const taskID = validateGateOne(projectRoot)
    return saveWorkflow(projectRoot, workflow, {
      phase: "CODE",
      current_task_id: taskID,
      gate_1: "APPROVED",
      gate_1_approved_by: actor,
      gate_1_approved_at_utc: now,
      last_agent: null,
      last_result: "GATE_1_APPROVED",
      blocked_reason: null,
    })
  }
  if (gate === 2) {
    if (workflow.phase !== "WAITING_GATE_2" || workflow.gate_2 !== "PENDING") {
      throw new Error(`Gate 2 is invalid during ${workflow.phase}`)
    }
    validateGateTwo(projectRoot)
    return saveWorkflow(projectRoot, workflow, {
      phase: "COMPLETE",
      current_task_id: null,
      gate_2: "APPROVED",
      gate_2_approved_by: actor,
      gate_2_approved_at_utc: now,
      last_agent: null,
      last_result: "GATE_2_APPROVED",
      blocked_reason: null,
    })
  }
  throw new Error("Gate must be 1 or 2")
}


function requirePhaseInput(projectRoot, workflow) {
  ensureManagedArtifactDirectories(projectRoot)
  ensureProjectBriefMetadata(projectRoot)
  if (workflow.phase === "EXPLORE") {
    return
  }
  if (workflow.phase === "PLAN") {
    requireFile(projectRoot, ".biexce/CODEBASE_BRIEF.md", "CODEBASE_BRIEF")
  }
  if (workflow.phase === "PLAN_REVIEW") {
    requireFile(projectRoot, ".biexce/MASTER_PLAN.md", "MASTER_PLAN")
    // PLAN_REVIEW is strictly read-only. The PLAN transition already
    // canonicalizes control metadata before entering this phase. Keeping this
    // precondition free of writes also prevents a duplicate Director turn from
    // changing the plan before it loses the active job-lease race.
  }
  if (["CODE", "TEST", "FIX", "TASK_REVIEW"].includes(workflow.phase)) {
    if (workflow.gate_1 !== "APPROVED" || !workflow.current_task_id) {
      throw new Error("task execution requires approved Gate 1 and a current task")
    }
    requireFile(
      projectRoot,
      `.biexce/tasks/${workflow.current_task_id}.md`,
      "task contract",
    )
  }
}


function normalizeProjectRelative(value, label) {
  if (typeof value !== "string" || !value.trim() || value.length > 4096) {
    throw new Error(`${label} must be a non-empty project-relative path`)
  }
  const trimmed = value.trim()
  const inlineCode = trimmed.match(/^(`+)([\s\S]*?)\1$/)
  const portable = (inlineCode ? inlineCode[2].trim() : trimmed)
    .replaceAll(String.fromCharCode(92), "/")
    .replace(/^\.\//, "")
  if (
    path.posix.isAbsolute(portable) ||
    /^[A-Za-z]:\//.test(portable) ||
    portable.split("/").includes("..") ||
    portable === "."
  ) {
    throw new Error(`${label} escapes the project root: ${value}`)
  }
  return portable
}


const MUTATING_FILE_TOOLS = new Set([
  "edit",
  "edit_file",
  "editfile",
  "write",
  "write_file",
  "writefile",
  "apply_patch",
  "applypatch",
  "patch",
  "multiedit",
  "multi_edit",
])


function schedulerMutationPaths(toolName, args, projectRoot) {
  if (!MUTATING_FILE_TOOLS.has(String(toolName).toLowerCase())) return null
  const values = []
  for (const key of ["filePath", "file_path", "path"]) {
    if (typeof args?.[key] === "string" && args[key].trim()) {
      values.push(args[key].trim())
    }
  }
  for (const key of ["patch", "patchText", "patch_text"]) {
    if (typeof args?.[key] === "string") {
      for (const match of args[key].matchAll(
        /^\*\*\* (?:Update|Add|Delete) File:\s*(.+?)\s*$/gm,
      )) {
        values.push(match[1])
      }
    }
  }
  if (values.length === 0) {
    throw new Error(
      "BIEXCE_SCHEDULER_WRITE_DENY: mutating tool does not expose target paths",
    )
  }
  return [...new Set(values.map((value) => {
    const absolute = path.isAbsolute(value)
      ? path.resolve(value)
      : path.resolve(projectRoot, value)
    if (
      absolute !== projectRoot &&
      !absolute.startsWith(projectRoot + path.sep)
    ) {
      throw new Error(
        "BIEXCE_SCHEDULER_WRITE_DENY: target escapes project root",
      )
    }
    return normalizeProjectRelative(
      path.relative(projectRoot, absolute),
      "scheduler mutation path",
    )
  }))]
}


function permissionMutationPaths(request, projectRoot) {
  const values = []
  for (const value of [
    request?.metadata?.filepath,
    request?.metadata?.filePath,
  ]) {
    if (typeof value === "string" && value.trim()) values.push(value.trim())
  }
  for (const candidate of [request?.pattern, request?.patterns]) {
    if (typeof candidate === "string" && candidate.trim()) {
      values.push(candidate.trim())
    }
    if (!Array.isArray(candidate)) continue
    for (const value of candidate) {
      if (typeof value === "string" && value.trim()) values.push(value.trim())
    }
  }
  return [...new Set(values.flatMap((value) =>
    schedulerMutationPaths("edit", { filePath: value }, projectRoot)
  ))]
}


function validateAgentResult(raw, active, workflow) {
  if (typeof raw !== "string" || !raw.trim() || raw.length > 200000) {
    throw new Error("result_json must be a non-empty JSON document under 200000 characters")
  }
  let result
  try {
    result = JSON.parse(raw)
  } catch (error) {
    throw new Error(`agent result is not valid JSON: ${error.message}`)
  }
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    throw new Error("agent result must be a JSON object")
  }
  if (
    (result.$schema !== undefined && result.$schema !== AGENT_RESULT_SCHEMA) ||
    (result.schema_version !== undefined && result.schema_version !== 1)
  ) {
    throw new Error("agent result schema invalid")
  }
  const identity = {
    workflow_revision: workflow.revision,
    phase: workflow.phase,
    task_id: workflow.current_task_id,
    agent: active.agent,
  }
  for (const [key, expected] of Object.entries(identity)) {
    if (result[key] !== undefined && result[key] !== expected) {
      throw new Error("agent result is stale or belongs to another job")
    }
  }
  const checks = result.checks === undefined ? [] : result.checks
  if (!Array.isArray(checks)) throw new Error("agent result checks is invalid")
  result = {
    $schema: AGENT_RESULT_SCHEMA,
    schema_version: 1,
    ...identity,
    status: result.status,
    summary: typeof result.summary === "string" && result.summary.trim()
      ? result.summary.trim()
      : "Agent completed; runtime evidence is authoritative.",
    changed_files: result.changed_files === undefined ? [] : result.changed_files,
    checks: checks.map((check) => {
      if (!check || typeof check !== "object" || Array.isArray(check)) return check
      return {
        command: typeof check.command === "string" && check.command.trim()
          ? check.command.trim()
          : "unspecified verification",
        exit_code: check.exit_code === undefined ? null : check.exit_code,
        status: check.status,
        output_summary:
          typeof check.output_summary === "string" && check.output_summary.trim()
            ? check.output_summary.trim()
            : "No additional output summary was provided.",
      }
    }),
    artifacts: result.artifacts === undefined ? [] : result.artifacts,
  }
  if (!AGENT_RESULT_STATUSES.has(result.status)) {
    throw new Error(`agent result status is invalid: ${result.status}`)
  }
  const allowedByPhase = {
    EXPLORE: ["SUCCEEDED"],
    PLAN: ["SUCCEEDED"],
    PLAN_REVIEW: ["PLAN_OK", "PLAN_NEEDS_REVISION"],
    CODE: ["SUCCEEDED"],
    FIX: ["SUCCEEDED"],
    TEST: ["PASS", "FAIL", "INCONCLUSIVE"],
    TASK_REVIEW: ["APPROVE", "APPROVE_WITH_MINOR_NOTES", "CHANGES_REQUIRED"],
    INTEGRATION_TEST: ["PASS", "FAIL", "INCONCLUSIVE"],
    INTEGRATION_FIX: ["SUCCEEDED"],
    INTEGRATION_REVIEW: ["APPROVE", "APPROVE_WITH_MINOR_NOTES", "CHANGES_REQUIRED"],
  }[workflow.phase] || []
  if (result.status !== "FAILED" && !allowedByPhase.includes(result.status)) {
    throw new Error(
      `${workflow.phase} does not accept result status ${result.status}`,
    )
  }
  if (typeof result.summary !== "string" || !result.summary.trim() || result.summary.length > 4000) {
    throw new Error("agent result summary is invalid")
  }
  if (!Array.isArray(result.changed_files) || result.changed_files.length > 500) {
    throw new Error("agent result changed_files is invalid")
  }
  result.changed_files = result.changed_files.map((value, index) =>
    normalizeProjectRelative(value, `changed_files[${index}]`),
  )
  if (new Set(result.changed_files).size !== result.changed_files.length) {
    throw new Error("agent result changed_files contains duplicates")
  }
  if (!Array.isArray(result.artifacts) || result.artifacts.length > 100) {
    throw new Error("agent result artifacts is invalid")
  }
  result.artifacts = result.artifacts.map((value, index) =>
    normalizeProjectRelative(value, `artifacts[${index}]`),
  )
  if (new Set(result.artifacts).size !== result.artifacts.length) {
    throw new Error("agent result artifacts contains duplicates")
  }
  if (result.checks.length > 100) {
    throw new Error("agent result checks is invalid")
  }
  for (const [index, check] of result.checks.entries()) {
    const expectedCheckKeys = new Set([
      "command", "exit_code", "status", "output_summary",
    ])
    if (!exactKeys(check, expectedCheckKeys)) throw new Error(`checks[${index}] is invalid`)
    if (
      typeof check.command !== "string" ||
      !check.command.trim() ||
      check.command.length > 4000 ||
      typeof check.output_summary !== "string" ||
      !check.output_summary.trim() ||
      check.output_summary.length > 4000 ||
      !["PASS", "FAIL", "NOT_RUN"].includes(check.status) ||
      !(check.exit_code === null || Number.isInteger(check.exit_code))
    ) {
      throw new Error(`checks[${index}] is invalid`)
    }
  }
  if (result.status === "PASS") {
    if (
      result.checks.length === 0 ||
      result.checks.some((check) => check.status !== "PASS" || check.exit_code !== 0)
    ) {
      throw new Error("PASS requires at least one deterministic check with exit_code 0")
    }
  }
  if (
    ["FAIL", "FAILED"].includes(result.status) &&
    !result.checks.some((check) => check.status === "FAIL")
  ) {
    throw new Error(`${result.status} requires at least one failed check`)
  }
  if (
    result.status === "INCONCLUSIVE" &&
    !result.checks.some((check) => check.status === "NOT_RUN")
  ) {
    throw new Error("INCONCLUSIVE requires at least one NOT_RUN check")
  }
  return result
}


const SNAPSHOT_EXCLUDED_DIRECTORIES = new Set([
  ".git", "node_modules", ".venv", "venv", "Library", "Temp", "Logs",
  "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
])
const SNAPSHOT_EXCLUDED_FILE_NAMES = new Set([
  ".coverage", ".eslintcache",
])
const SNAPSHOT_EXCLUDED_FILE_SUFFIXES = [".pyc", ".pyo"]
const SNAPSHOT_EXCLUDED_FILES = new Set([
  ".biexce/state/AUTOPILOT_DELEGATION.lock",
  ".biexce/state/AUTOPILOT_EVENTS.jsonl",
  ".biexce/state/AUTOPILOT_JOBS.json",
  ".biexce/state/AUTOPILOT_SESSIONS.json",
  ".biexce/state/AUTOPILOT_SCHEDULER.json",
  ".biexce/state/AUTOPILOT_SCHEDULER.lock",
])
const JOB_BASELINE_DIRECTORY = ".biexce/state/job-baselines"
const SNAPSHOT_EXCLUDED_RUNTIME_DIRECTORIES = new Set([
  ".biexce/state",
  ".biexce/state/leases",
  JOB_BASELINE_DIRECTORY,
])


function snapshotProjectFiles(projectRoot) {
  const snapshot = new Map()
  const visit = (directory) => {
    let entries
    try {
      entries = fs.readdirSync(directory, { withFileTypes: true })
    } catch (error) {
      if (error?.code === "ENOENT" && directory !== projectRoot) return
      throw error
    }
    for (const entry of entries) {
      const absolute = path.join(directory, entry.name)
      const relative = path.relative(projectRoot, absolute).replaceAll(String.fromCharCode(92), "/")
      if (
        entry.isDirectory() &&
        (
          SNAPSHOT_EXCLUDED_DIRECTORIES.has(entry.name) ||
          SNAPSHOT_EXCLUDED_RUNTIME_DIRECTORIES.has(relative)
        )
      ) continue
      if (
        SNAPSHOT_EXCLUDED_FILES.has(relative) ||
        SNAPSHOT_EXCLUDED_FILE_NAMES.has(entry.name) ||
        entry.name.startsWith(".coverage.") ||
        SNAPSHOT_EXCLUDED_FILE_SUFFIXES.some((suffix) => entry.name.endsWith(suffix))
      ) continue
      try {
        const stat = fs.lstatSync(absolute)
        if (stat.isDirectory()) visit(absolute)
        else if (stat.isSymbolicLink()) snapshot.set(relative, `link:${fs.readlinkSync(absolute)}`)
        else if (stat.isFile()) {
          const hash = crypto.createHash("sha256").update(fs.readFileSync(absolute)).digest("hex")
          snapshot.set(relative, hash)
        }
      } catch (error) {
        // Editors commonly create and replace temporary files between readdir
        // and lstat/read. A vanished entry is not part of either snapshot.
        if (error?.code !== "ENOENT") throw error
      }
    }
  }
  visit(projectRoot)
  return snapshot
}


function jobBaselinePath(projectRoot, jobID) {
  if (!/^job-[A-Za-z0-9._-]{1,180}$/.test(jobID)) {
    throw new Error(`invalid job id for file baseline: ${jobID}`)
  }
  return path.join(projectRoot, ...JOB_BASELINE_DIRECTORY.split("/"), `${jobID}.json`)
}


function ensureJobBaselineDirectory(projectRoot) {
  const directory = path.join(projectRoot, ...JOB_BASELINE_DIRECTORY.split("/"))
  if (!fs.existsSync(directory)) {
    fs.mkdirSync(directory, { recursive: true, mode: 0o700 })
  }
  const stat = fs.lstatSync(directory)
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error("job file baseline directory is invalid")
  }
  return directory
}


function validateJobBaseline(document, jobID) {
  if (
    !exactKeys(document, new Set(["schema_version", "job_id", "files"])) ||
    document.schema_version !== 1 ||
    document.job_id !== jobID ||
    !Array.isArray(document.files)
  ) {
    throw new Error(`job file baseline is invalid: ${jobID}`)
  }
  const snapshot = new Map()
  for (const entry of document.files) {
    if (
      !Array.isArray(entry) || entry.length !== 2 ||
      typeof entry[0] !== "string" || !entry[0] ||
      typeof entry[1] !== "string" || !entry[1] ||
      snapshot.has(entry[0])
    ) {
      throw new Error(`job file baseline entries are invalid: ${jobID}`)
    }
    snapshot.set(entry[0], entry[1])
  }
  return snapshot
}


function loadOrCreateJobBaseline(projectRoot, jobID) {
  const file = jobBaselinePath(projectRoot, jobID)
  if (fs.existsSync(file)) {
    const stat = fs.lstatSync(file)
    if (!stat.isFile() || stat.isSymbolicLink()) {
      throw new Error(`job file baseline is not a regular file: ${jobID}`)
    }
    return validateJobBaseline(
      JSON.parse(fs.readFileSync(file, "utf8")),
      jobID,
    )
  }
  const snapshot = snapshotProjectFiles(projectRoot)
  ensureJobBaselineDirectory(projectRoot)
  atomicWriteJson(file, {
    schema_version: 1,
    job_id: jobID,
    files: [...snapshot.entries()],
  })
  return snapshot
}


function removeJobBaseline(projectRoot, jobID) {
  const file = jobBaselinePath(projectRoot, jobID)
  if (fs.existsSync(file)) fs.unlinkSync(file)
  const directory = path.dirname(file)
  if (
    fs.existsSync(directory) &&
    fs.lstatSync(directory).isDirectory() &&
    !fs.lstatSync(directory).isSymbolicLink() &&
    fs.readdirSync(directory).length === 0
  ) {
    fs.rmdirSync(directory)
  }
}


function changedProjectFiles(before, after) {
  const changed = new Set()
  for (const file of new Set([...before.keys(), ...after.keys()])) {
    if (before.get(file) !== after.get(file)) changed.add(file)
  }
  return [...changed].sort()
}


function globPattern(pattern) {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&")
  const doubleStar = "__BIEXCE_DOUBLE_STAR__"
  return new RegExp(
    `^${escaped.replaceAll("**", doubleStar).replaceAll("*", "[^/]*").replaceAll(doubleStar, ".*")}$`,
  )
}

function writablePatterns(projectRoot, workflow) {
  if (workflow.phase === "EXPLORE") return [".biexce/CODEBASE_BRIEF.md"]
  if (workflow.phase === "PLAN") {
    return [".biexce/MASTER_PLAN.md", ".biexce/tasks/**"]
  }
  if (workflow.phase === "INTEGRATION_FIX") return ["**"]
  if (!["CODE", "FIX", "TEST"].includes(workflow.phase)) return []
  const task = fs.readFileSync(
    path.join(projectRoot, ".biexce", "tasks", `${workflow.current_task_id}.md`),
    "utf8",
  )
  const writable = markdownField(task, "Writable files")
  if (!writable || writable.toLowerCase() === "none") return []
  const patterns = writable.split(",").map((value) =>
    normalizeProjectRelative(value.trim(), "Writable files"),
  )
  if (workflow.phase !== "TEST") return patterns
  // Test jobs may persist assigned evidence, never product source or tests.
  return patterns.filter((value) => value.startsWith(".biexce/reports/"))
}


function allowedByWriteScope(file, patterns) {
  return patterns.some((pattern) => {
    if (pattern.endsWith("/")) return file.startsWith(pattern)
    if (pattern.includes("*")) return globPattern(pattern).test(file)
    return file === pattern
  })
}


function contractError(message) {
  const error = new Error(message)
  error.biexceKind = "CONTRACT"
  return error
}


function effectiveWorkflowProfile(projectRoot) {
  try {
    return loadWorkflowPolicy(projectRoot)?.effective_profile || "critical"
  } catch {
    return "critical"
  }
}


function standardWorkflow(projectRoot) {
  return ["fast", "standard"].includes(effectiveWorkflowProfile(projectRoot))
}


function protectedRuntimeMutation(file) {
  return protectedProjectPath(file)
}


function childWriteAllowed(child, target) {
  if (allowedByWriteScope(target, child.writeScope || [])) return true
  if (
    !["CODE", "FIX", "INTEGRATION_FIX"].includes(child.phase) ||
    !standardWorkflow(child.projectRoot) ||
    protectedRuntimeMutation(target)
  ) return false
  // Scope discovery is allowed for normal source delivery, but never let one
  // parallel worker trespass on a path explicitly owned by another active job.
  const siblingPatterns = concurrentJobWritePatterns(
    child.projectRoot,
    child.jobID,
  )
  return !allowedByWriteScope(target, siblingPatterns)
}


function verifyResultFiles(
  projectRoot,
  workflow,
  result,
  before,
  concurrentWritePatterns = [],
) {
  const changed = changedProjectFiles(before, snapshotProjectFiles(projectRoot))
  const patterns = writablePatterns(projectRoot, workflow)
  const owned = changed.filter((file) => allowedByWriteScope(file, patterns))
  const concurrent = changed.filter((file) =>
    !allowedByWriteScope(file, patterns) &&
    allowedByWriteScope(file, concurrentWritePatterns)
  )
  const outside = changed.filter((file) =>
    !allowedByWriteScope(file, patterns) &&
    !allowedByWriteScope(file, concurrentWritePatterns)
  )
  const flexibleSourcePhase = ["CODE", "FIX", "INTEGRATION_FIX"].includes(
    workflow.phase,
  )
  const mayExpandScope = flexibleSourcePhase && standardWorkflow(projectRoot)
  const protectedOutside = flexibleSourcePhase
    ? changed.filter(protectedRuntimeMutation)
    : []
  if (protectedOutside.length > 0) {
    throw contractError(
      `protected project paths changed: ${protectedOutside.join(", ")}`,
    )
  }
  if (outside.length > 0 && !mayExpandScope) {
    throw contractError(
      `runtime diff exceeds writable scope: ${outside.join(", ")}`,
    )
  }
  // The filesystem is authoritative. Agent-reported paths are useful context,
  // but reporting drift and a planner's incomplete file prediction must never
  // turn valid in-project source work into a blocker in standard mode. Files
  // owned by concurrently running jobs are excluded from this result.
  const accepted = mayExpandScope
    ? changed.filter((file) => !concurrent.includes(file))
    : owned
  result.changed_files = accepted
  result.artifacts = runtimeArtifacts(projectRoot, workflow, accepted)
  // FAILED with a failed deterministic check is a valid child result. The
  // scheduler routes it to a bounded FIX round. Throwing CONTRACT here used to
  // release and re-run the identical CODE job indefinitely.
  if (
    result.status === "FAILED" &&
    !["CODE", "FIX"].includes(workflow.phase)
  ) {
    throw contractError(`child reported failure: ${result.summary}`)
  }
}


function concurrentJobWritePatterns(projectRoot, currentJobID) {
  const jobs = loadJobBoard(projectRoot).jobs
  const current = jobs[currentJobID]
  const currentStarted = Date.parse(current?.started_at_utc || "")
  if (!Number.isFinite(currentStarted)) return []
  const patterns = []
  for (const job of Object.values(jobs)) {
    if (
      job.job_id === currentJobID ||
      job.task_id === current.task_id ||
      !["CODE", "FIX"].includes(job.phase) ||
      !Array.isArray(job.write_scope)
    ) continue
    const siblingStarted = Date.parse(job.started_at_utc || "")
    const siblingCompleted = job.completed_at_utc
      ? Date.parse(job.completed_at_utc)
      : Number.POSITIVE_INFINITY
    if (
      Number.isFinite(siblingStarted) &&
      siblingStarted <= Date.now() &&
      siblingCompleted >= currentStarted
    ) {
      patterns.push(...job.write_scope)
    }
  }
  return [...new Set(patterns)]
}


function regularProjectFile(projectRoot, relativePath) {
  const file = path.join(projectRoot, ...relativePath.split("/"))
  if (!fs.existsSync(file)) return false
  try {
    const stat = fs.lstatSync(file)
    return stat.isFile() && !stat.isSymbolicLink()
  } catch (error) {
    // OpenCode editors may replace a file between existsSync and lstatSync.
    // Treat a vanished path as absent evidence, not as an UNKNOWN runtime crash.
    if (error?.code === "ENOENT") return false
    throw error
  }
}


function runtimeArtifacts(projectRoot, workflow, changedFiles) {
  const candidates = new Set(changedFiles)
  if (workflow.phase === "EXPLORE") {
    candidates.add(".biexce/CODEBASE_BRIEF.md")
  }
  if (workflow.phase === "PLAN") {
    candidates.add(".biexce/MASTER_PLAN.md")
    const taskRoot = path.join(projectRoot, ".biexce", "tasks")
    try {
      if (fs.existsSync(taskRoot) && fs.lstatSync(taskRoot).isDirectory()) {
        for (const name of fs.readdirSync(taskRoot).sort()) {
          if (/^t-[0-9]+\.md$/i.test(name)) {
            candidates.add(`.biexce/tasks/${name}`)
          }
        }
      }
    } catch (error) {
      if (error?.code !== "ENOENT") throw error
    }
  }
  return [...candidates]
    .filter((file) => regularProjectFile(projectRoot, file))
    .sort()
}


function conciseRuntimeSummary(output, phase) {
  const normalized = String(output || "").replace(/\s+/g, " ").trim()
  if (normalized) return normalized.slice(0, 4000)
  return `BIEXCE runtime finalized ${phase} from filesystem evidence.`
}


function outputVerdict(output, allowed) {
  const allowedSet = new Set(allowed)
  const lines = String(output || "").split(/\r?\n/).map((line) => line.trim())
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index]
    const tagged = line.match(
      /^(?:BIEXCE_STATUS|VERDICT|STATUS)\s*:\s*([A-Z][A-Z0-9_ -]*)[.!]?$/i,
    )
    const token = (tagged?.[1] || line.replace(/[.!]$/, ""))
      .trim()
      .toUpperCase()
      .replace(/[ -]+/g, "_")
    if (allowedSet.has(token)) return token
  }
  return null
}


function runtimeEvidenceResult({
  projectRoot,
  workflow,
  active,
  output,
  before,
  commandEvidence,
}) {
  const changed = changedProjectFiles(before, snapshotProjectFiles(projectRoot))
  const checks = [...(commandEvidence || [])]
  let status = null
  if (["EXPLORE", "PLAN", "CODE", "FIX", "INTEGRATION_FIX"].includes(workflow.phase)) {
    status = "SUCCEEDED"
  } else if (workflow.phase === "PLAN_REVIEW") {
    status = outputVerdict(output, ["PLAN_OK", "PLAN_NEEDS_REVISION"])
      || "PLAN_NEEDS_REVISION"
  } else if (["TEST", "INTEGRATION_TEST"].includes(workflow.phase)) {
    if (checks.length === 0) {
      status = "INCONCLUSIVE"
      checks.push({
        command: "BIEXCE managed verification",
        exit_code: null,
        status: "NOT_RUN",
        output_summary: "Child completed without managed command evidence.",
      })
    } else {
      status = checks.some((check) => check.status === "FAIL") ? "FAIL" : "PASS"
    }
  } else if (["TASK_REVIEW", "INTEGRATION_REVIEW"].includes(workflow.phase)) {
    status = outputVerdict(output, [
      "APPROVE",
      "APPROVE_WITH_MINOR_NOTES",
      "CHANGES_REQUIRED",
    ]) || "CHANGES_REQUIRED"
  }
  if (!status) {
    throw contractError(`runtime cannot derive a result for phase ${workflow.phase}`)
  }
  const artifacts = runtimeArtifacts(projectRoot, workflow, changed)
  const requiredArtifacts = {
    EXPLORE: [".biexce/CODEBASE_BRIEF.md"],
    PLAN: [".biexce/MASTER_PLAN.md"],
  }[workflow.phase] || []
  const missingArtifacts = requiredArtifacts.filter(
    (artifact) => !artifacts.includes(artifact),
  )
  if (missingArtifacts.length > 0) {
    throw contractError(
      "required child artifact is missing after tool execution: " +
      missingArtifacts.join(", "),
    )
  }
  const result = {
    $schema: AGENT_RESULT_SCHEMA,
    schema_version: 1,
    workflow_revision: workflow.revision,
    phase: workflow.phase,
    task_id: workflow.current_task_id,
    agent: active.agent,
    status,
    summary: conciseRuntimeSummary(output, workflow.phase),
    changed_files: changed,
    checks,
    artifacts,
  }
  return validateAgentResult(JSON.stringify(result), active, workflow)
}


function resolveChildResult({
  childID,
  projectRoot,
  workflow,
  output,
  before,
  activeChildren,
  submittedResults,
  commandEvidence,
}) {
  const submitted = submittedResults.get(childID)
  if (submitted) return { result: submitted, source: "agent-submit" }
  const active = activeChildren.get(childID)
  if (!active) throw contractError("active child state is unavailable")
  return {
    result: runtimeEvidenceResult({
      projectRoot,
      workflow,
      active,
      output,
      before,
      commandEvidence: commandEvidence.get(childID) || [],
    }),
    source: "runtime-evidence",
  }
}


function workflowJobID(workflow, agent) {
  const subject = workflow.current_task_id || workflow.phase.toLowerCase()
  return `job-${subject}-${workflow.phase.toLowerCase()}-${agent}-r${workflow.revision}`
}


function workflowReadScope(workflow) {
  const shared = [".biexce/PROJECT_BRIEF.md"]
  if (workflow.phase === "EXPLORE") return shared
  if (workflow.phase === "PLAN") {
    return [...shared, ".biexce/CODEBASE_BRIEF.md"]
  }
  if (workflow.phase === "PLAN_REVIEW") {
    return [
      ...shared,
      ".biexce/CODEBASE_BRIEF.md",
      ".biexce/MASTER_PLAN.md",
      ".biexce/tasks/**",
      ".biexce/reports/PREFLIGHT_REPORT.md",
    ]
  }
  if (["INTEGRATION_TEST", "INTEGRATION_FIX", "INTEGRATION_REVIEW"].includes(workflow.phase)) {
    return [
      ...shared,
      ".biexce/CODEBASE_BRIEF.md",
      ".biexce/MASTER_PLAN.md",
      "**",
    ]
  }
  if (workflow.current_task_id) {
    return [...shared, `.biexce/tasks/${workflow.current_task_id}.md`, "**"]
  }
  return [...shared, "**"]
}


function registerWorkflowJob(projectRoot, workflow, agent, model) {
  const jobID = workflowJobID(workflow, agent)
  const existing = loadJobBoard(projectRoot).jobs[jobID]
  if (existing) return existing
  return putJob(projectRoot, {
    job_id: jobID,
    trace_id: `trace-${workflow.revision}-${workflow.current_task_id || workflow.phase}`,
    task_id: workflow.current_task_id,
    agent,
    phase: workflow.phase,
    status: "QUEUED",
    dependencies: workflow.current_task_id
      ? taskDependencies(projectRoot, workflow.current_task_id)
      : [],
    read_scope: workflowReadScope(workflow),
    write_scope: writablePatterns(projectRoot, workflow),
    model,
  })
}


function requireWorkflowJobLaunchable(job) {
  if (!["FAILED", "BLOCKED", "COMPLETED"].includes(job.status)) return job
  const error = new Error(
    `BIEXCE_AUTOPILOT_TERMINAL_JOB: ${job.job_id} is ${job.status}; ` +
    "the same workflow job cannot be delegated again",
  )
  error.biexceKind = "CONTRACT"
  throw error
}


export function runtimeContract(workflow, agent) {
  const statuses = {
    EXPLORE: "SUCCEEDED",
    PLAN: "SUCCEEDED",
    PLAN_REVIEW: "PLAN_OK or PLAN_NEEDS_REVISION",
    CODE: "SUCCEEDED",
    FIX: "SUCCEEDED",
    TEST: "PASS, FAIL, or INCONCLUSIVE",
    TASK_REVIEW: "APPROVE, APPROVE_WITH_MINOR_NOTES, or CHANGES_REQUIRED",
    INTEGRATION_TEST: "PASS, FAIL, or INCONCLUSIVE",
    INTEGRATION_FIX: "SUCCEEDED",
    INTEGRATION_REVIEW: "APPROVE, APPROVE_WITH_MINOR_NOTES, or CHANGES_REQUIRED",
  }[workflow.phase]
  const preferredStatus = {
    EXPLORE: "SUCCEEDED",
    PLAN: "SUCCEEDED",
    PLAN_REVIEW: "PLAN_OK",
    CODE: "SUCCEEDED",
    FIX: "SUCCEEDED",
    TEST: "PASS",
    TASK_REVIEW: "APPROVE",
    INTEGRATION_TEST: "PASS",
    INTEGRATION_FIX: "SUCCEEDED",
    INTEGRATION_REVIEW: "APPROVE",
  }[workflow.phase]
  const resultTemplate = {
    $schema: AGENT_RESULT_SCHEMA,
    schema_version: 1,
    workflow_revision: workflow.revision,
    phase: workflow.phase,
    task_id: workflow.current_task_id,
    agent,
    status: preferredStatus,
    summary: "<concise result summary>",
    changed_files: [],
    checks: [{
      command: "<exact command or artifact inspection>",
      exit_code: null,
      status: "NOT_RUN",
      output_summary: "<what was or was not verified>",
    }],
    artifacts: [],
  }
  const submission = [
    "Prefer calling `biexce_submit_result` exactly once before returning.",
    "Pass one `result_json` string using the canonical fields in this valid JSON " +
      "template. The runtime fills omitted non-security metadata and ignores " +
      "unknown reporting fields, while identity and verification evidence remain " +
      "strictly validated:",
    JSON.stringify(resultTemplate, null, 2),
    `workflow_revision=${workflow.revision}; phase=${workflow.phase}; ` +
      `task_id=${workflow.current_task_id || "null"}; agent=${agent}; ` +
      `status=${statuses}; use FAILED only when the assigned work cannot be ` +
      `completed, and include at least one failed check.`,
    "Report project-relative changed_files and existing artifact paths when known.",
    "The runtime derives final changed_files and artifacts from the filesystem. " +
      "Reporting drift is normalized; any real out-of-scope change remains a " +
      "terminal CONTRACT failure.",
    "Each check should provide command, exit_code, status, and output_summary. " +
      "Remove the template check only when no check applies.",
    "For PASS, include at least one check with status PASS and integer exit_code 0.",
    "Use `biexce_run_command` for bounded verification commands so timeout, " +
      "log limits, cancellation, and process cleanup remain runtime-owned.",
    "Do not start a persistent development server directly. Use TestClient or " +
      "a test runner-owned Playwright webServer that exits with the test run.",
    "End the response with one exact `BIEXCE_STATUS: <status>` line. This is a " +
      "safe fallback when structured submission is unavailable; filesystem and " +
      "managed-command evidence remain authoritative.",
  ].join(" ")
  if (workflow.phase === 'EXPLORE') {
    return (
      'Create or update the managed artifact at exactly ' +
      '`.biexce/CODEBASE_BRIEF.md` before returning. A green-field or empty ' +
      'repository is valid: record that fact and the planned layout instead ' +
      `of skipping the artifact. Do not return only a chat summary. ${submission}`
    )
  }
  if (["TEST", "INTEGRATION_TEST"].includes(workflow.phase)) {
    return (
      "Independently verify acceptance and the applicable project quality " +
      "pipeline in this order: formatter check, lint/static analysis, " +
      "typecheck, focused/unit tests, affected integration/contract/E2E, " +
      "then build/package. Discover commands from trusted project " +
      "instructions/scripts or the deterministic BIEXCE test catalog. When " +
      "a Python standard-library project declares unittest and contains " +
      "tests/test*.py, the catalog command is `python -m unittest discover " +
      "-s tests -v`; run it through `biexce_run_command` even when a legacy " +
      "story says Verify N/A. Omit a category only " +
      "when it is genuinely N/A and explain why in the summary. A required " +
      "check that cannot run requires INCONCLUSIVE with a NOT_RUN check. " +
      "A failing check requires FAIL with its failed check evidence. Do not " +
      `repair source or tests. ${submission}`
    )
  }
  if (agent === "bx-review" && workflow.phase === "PLAN_REVIEW") {
    return (
      "Review only the Brief, Master Plan, and task artifacts. PLAN_REVIEW " +
      "does not authorize raw source or raw diff access. Remain read-only, " +
      `do not run checks or repair artifacts. ${submission}`
    )
  }
  if (
    agent === "bx-review" &&
    ["TASK_REVIEW", "INTEGRATION_REVIEW"].includes(workflow.phase)
  ) {
    const reviewScope = workflow.phase === "TASK_REVIEW"
      ? "the current task diff and minimum surrounding source"
      : "the integrated diff and minimum surrounding source"
    return (
      "The user-applied bx-review binding authorizes the standing Zone A " +
      `review exception for ${reviewScope}. This is read-only: never edit, ` +
      "repair, mutate Git, or delegate. Never read, quote, summarize, or echo " +
      "Zone C secrets, credentials, signing material, or production personal/" +
      `sensitive data. Do not expand into an unrelated repository audit. ${submission}`
    )
  }
  return `Complete the requested artifact/result and return concise evidence. ${submission}`
}


function beginTaskDelegation(projectRoot, workflow) {
  if (!["CODE", "TEST", "FIX", "TASK_REVIEW"].includes(workflow.phase)) return null
  const previous = loadProjectState(projectRoot)
  const status = {
    CODE: "coding",
    TEST: "testing",
    FIX: "fixing",
    TASK_REVIEW: "reviewing",
  }[workflow.phase]
  const next = setTaskState(
    previous,
    workflow.current_task_id,
    status,
    PHASE_AGENTS[workflow.phase],
    workflow.fix_round,
  )
  saveProjectState(projectRoot, { ...next, stage: "B3" })
  return previous
}


function blockWorkflow(projectRoot, workflow, agent, result, reason) {
  if (workflow.current_task_id) {
    const state = loadProjectState(projectRoot)
    const next = setTaskState(
      state,
      workflow.current_task_id,
      "escalated",
      null,
      workflow.fix_round,
    )
    saveProjectState(projectRoot, next)
  }
  return saveWorkflow(projectRoot, workflow, {
    phase: "BLOCKED",
    last_agent: agent,
    last_result: result,
    blocked_reason: reason,
  })
}


function routeFix(projectRoot, workflow, agent, result) {
  if (workflow.fix_round >= 3) {
    return blockWorkflow(
      projectRoot,
      workflow,
      agent,
      result,
      `Fix cap reached for ${workflow.current_task_id}`,
    )
  }
  const round = workflow.fix_round + 1
  const state = loadProjectState(projectRoot)
  saveProjectState(
    projectRoot,
    setTaskState(state, workflow.current_task_id, "fixing", "bx-fix", round),
  )
  return saveWorkflow(projectRoot, workflow, {
    phase: "FIX",
    fix_round: round,
    last_agent: agent,
    last_result: result,
    blocked_reason: null,
  })
}


function recoverPlanReviewBaselineDrift(projectRoot, workflow) {
  if (
    workflow.phase !== "BLOCKED" ||
    workflow.current_task_id !== null ||
    workflow.gate_1 !== "PENDING"
  ) return workflow

  const prefix = "Terminal CONTRACT failure in "
  const marker = ": runtime diff exceeds writable scope: "
  const reason = workflow.blocked_reason || ""
  if (!reason.startsWith(prefix) || !reason.includes(marker)) return workflow
  const [jobID, rawFiles] = reason.slice(prefix.length).split(marker, 2)
  const changedFiles = (rawFiles || "").split(", ")
    .map((value) => value.trim())
    .filter(Boolean)
  const managedPlanArtifact = (file) =>
    file === ".biexce/MASTER_PLAN.md" ||
    file === ".biexce/reports/PREFLIGHT_REPORT.md" ||
    /^\.biexce\/tasks\/t-[0-9]{3}\.md$/.test(file)
  if (
    !jobID ||
    changedFiles.length === 0 ||
    !changedFiles.every(managedPlanArtifact) ||
    hasActiveJobLeases(projectRoot)
  ) return workflow

  const board = loadJobBoard(projectRoot)
  const job = board.jobs[jobID]
  if (
    !job ||
    job.phase !== "PLAN_REVIEW" ||
    job.agent !== "bx-review" ||
    job.status !== "FAILED" ||
    !String(job.error || "").includes("runtime diff exceeds writable scope")
  ) return workflow
  const priorRecoverableFailures = Object.values(board.jobs).filter((entry) =>
    entry.phase === "PLAN_REVIEW" &&
    entry.agent === "bx-review" &&
    entry.status === "FAILED" &&
    String(entry.error || "").includes("runtime diff exceeds writable scope")
  ).length
  // Retry against a new stable baseline at most twice. A continuously changing
  // plan remains blocked instead of consuming unbounded model calls.
  if (priorRecoverableFailures > 2) return workflow

  requireFile(projectRoot, ".biexce/MASTER_PLAN.md", "MASTER_PLAN")
  requireDirectory(projectRoot, ".biexce/tasks", "task contracts")
  const next = saveWorkflow(projectRoot, workflow, {
    phase: "PLAN_REVIEW",
    last_agent: null,
    last_result: "RUNTIME_REBASED_PLAN_REVIEW",
    blocked_reason: null,
  })
  appendRecoveryAudit(projectRoot, {
    schema_version: 1,
    event: "PLAN_REVIEW_BASELINE_REBASED",
    actor: "biexce-runtime",
    project_root: projectRoot,
    failed_job_id: jobID,
    changed_files: changedFiles,
    workflow_revision_before: workflow.revision,
    workflow_revision_after: next.revision,
    timestamp_utc: new Date().toISOString(),
  })
  return next
}


const STANDARD_RECOVERY_PHASES = new Set([
  "EXPLORE",
  "PLAN",
  "PLAN_REVIEW",
  "CODE",
  "TEST",
  "FIX",
  "TASK_REVIEW",
  "INTEGRATION_TEST",
  "INTEGRATION_FIX",
  "INTEGRATION_REVIEW",
])


const FLEXIBLE_PROJECT_SCOPE_PHASES = new Set([
  "CODE",
  "FIX",
  "INTEGRATION_FIX",
])


function unsafeRuntimeFailure(message, phase = null) {
  const value = String(message || "")
  const scope = scopeFailure(value)
  if (scope.kind === SCOPE_FAILURES.HARD_BOUNDARY) return true
  if (
    scope.kind === SCOPE_FAILURES.PROJECT_SCOPE_DRIFT &&
    phase !== null &&
    !FLEXIBLE_PROJECT_SCOPE_PHASES.has(phase)
  ) return true
  return /protected project paths changed/i.test(value) ||
    /escapes (?:the )?project root/i.test(value) ||
    /secret|credential|private key|production mutation/i.test(value)
}


function recordFailurePolicyShadow(projectRoot, details) {
  try {
    const event = failurePolicyShadowEvent(details)
    if (event !== null) appendJobEvent(projectRoot, event)
  } catch {
    // Shadow telemetry must never change the V2 runtime decision.
  }
}


function latestFailedWorkflowJob(projectRoot, workflow, phase = null) {
  const candidates = Object.values(loadJobBoard(projectRoot).jobs).filter((job) =>
    ["FAILED", "BLOCKED", "TIMED_OUT", "CANCELLED", "RETRYING"].includes(job.status) &&
    (phase === null || job.phase === phase) &&
    (workflow.current_task_id === null || job.task_id === workflow.current_task_id)
  )
  return candidates.sort((left, right) => {
    const leftTime = Date.parse(left.completed_at_utc || left.started_at_utc || "") || 0
    const rightTime = Date.parse(right.completed_at_utc || right.started_at_utc || "") || 0
    return rightTime - leftTime
  })[0] || null
}


function standardPhaseFailureCount(projectRoot, workflow, phase) {
  return Object.values(loadJobBoard(projectRoot).jobs).filter((job) =>
    job.phase === phase &&
    job.task_id === workflow.current_task_id &&
    ["FAILED", "BLOCKED", "TIMED_OUT", "CANCELLED", "RETRYING"].includes(job.status)
  ).length
}


function retryStandardWorkflowFailure(projectRoot, workflow, phase, error) {
  if (
    !standardWorkflow(projectRoot) ||
    !STANDARD_RECOVERY_PHASES.has(phase) ||
    unsafeRuntimeFailure(error?.message || error, phase)
  ) return workflow
  if (standardPhaseFailureCount(projectRoot, workflow, phase) > 3) return workflow
  const next = saveWorkflow(projectRoot, workflow, {
    phase,
    last_agent: null,
    last_result: "RUNTIME_RETRY",
    blocked_reason: null,
  })
  appendRecoveryAudit(projectRoot, {
    schema_version: 1,
    event: "STANDARD_WORKFLOW_RETRY",
    actor: "biexce-runtime",
    phase,
    task_id: workflow.current_task_id,
    error: String(error?.message || error || "runtime failure").slice(0, 2000),
    workflow_revision_before: workflow.revision,
    workflow_revision_after: next.revision,
    timestamp_utc: new Date().toISOString(),
  })
  return next
}


function recoverStandardBlockedWorkflow(projectRoot, workflow) {
  if (!standardWorkflow(projectRoot) || workflow.phase !== "BLOCKED") {
    return workflow
  }
  if (unsafeRuntimeFailure(workflow.blocked_reason)) return workflow

  const failed = latestFailedWorkflowJob(projectRoot, workflow)
  let phase = failed?.phase || null
  if (!phase && /plan revision cap/i.test(workflow.blocked_reason || "")) {
    phase = "PLAN"
  }
  if (!phase && /integration test result/i.test(workflow.blocked_reason || "")) {
    phase = "INTEGRATION_FIX"
  }
  if (!phase && /integration review/i.test(workflow.blocked_reason || "")) {
    phase = "INTEGRATION_FIX"
  }
  if (!STANDARD_RECOVERY_PHASES.has(phase)) return workflow
  if (
    unsafeRuntimeFailure(
      failed?.error || workflow.blocked_reason,
      phase,
    )
  ) return workflow

  if (workflow.current_task_id) {
    const recovery = reconcileRuntimeState(projectRoot, {
      recoverBlockers: true,
      allowStandard: true,
      phaseByTask: { [workflow.current_task_id]: phase },
    })
    if (!recovery.recovered_tasks.includes(workflow.current_task_id)) {
      return workflow
    }
  }
  const next = saveWorkflow(projectRoot, workflow, {
    phase,
    last_agent: null,
    last_result: "RUNTIME_RECOVERED",
    blocked_reason: null,
  })
  appendRecoveryAudit(projectRoot, {
    schema_version: 1,
    event: "STANDARD_WORKFLOW_RECOVERED",
    actor: "biexce-runtime",
    phase,
    task_id: workflow.current_task_id,
    failed_job_id: failed?.job_id || null,
    workflow_revision_before: workflow.revision,
    workflow_revision_after: next.revision,
    timestamp_utc: new Date().toISOString(),
  })
  return next
}


function advanceWorkflow(projectRoot, workflow, agent, submission) {
  if (workflow.phase === "EXPLORE") {
    requireFile(projectRoot, ".biexce/CODEBASE_BRIEF.md", "CODEBASE_BRIEF")
    return saveWorkflow(projectRoot, workflow, {
      phase: "PLAN",
      last_agent: agent,
      last_result: "CODEBASE_BRIEF_READY",
      blocked_reason: null,
    })
  }
  if (workflow.phase === "PLAN") {
    requireFile(projectRoot, ".biexce/MASTER_PLAN.md", "MASTER_PLAN")
    ensureMasterPlanControlMetadata(projectRoot)
    syncProjectStateFromPlan(projectRoot)
    writePlanReadinessReport(projectRoot)
    return saveWorkflow(projectRoot, workflow, {
      phase: "PLAN_REVIEW",
      last_agent: agent,
      last_result: "PLAN_READY",
      blocked_reason: null,
    })
  }
  if (workflow.phase === "PLAN_REVIEW") {
    const readiness = writePlanReadinessReport(projectRoot)
    const result = readiness.errors.length > 0
      ? "PLAN_NEEDS_REVISION"
      : submission.status
    if (result === "PLAN_OK") {
      return saveWorkflow(projectRoot, workflow, {
        phase: "WAITING_GATE_1",
        last_agent: agent,
        last_result: "PLAN OK",
        blocked_reason: null,
      })
    }
    if (workflow.plan_revision >= 2) {
      if (standardWorkflow(projectRoot)) {
        return saveWorkflow(projectRoot, workflow, {
          phase: "WAITING_GATE_1",
          last_agent: agent,
          last_result: "PLAN REVIEW WARNINGS",
          blocked_reason: null,
        })
      }
      return blockWorkflow(
        projectRoot,
        workflow,
        agent,
        "PLAN NEEDS REVISION",
        "Plan revision cap reached",
      )
    }
    return saveWorkflow(projectRoot, workflow, {
      phase: "PLAN",
      plan_revision: workflow.plan_revision + 1,
      last_agent: agent,
      last_result: "PLAN NEEDS REVISION",
      blocked_reason: null,
    })
  }
  if (workflow.phase === "CODE" || workflow.phase === "FIX") {
    const state = loadProjectState(projectRoot)
    saveProjectState(
      projectRoot,
      setTaskState(
        state,
        workflow.current_task_id,
        "testing",
        "bx-test",
        workflow.fix_round,
      ),
    )
    return saveWorkflow(projectRoot, workflow, {
      phase: "TEST",
      last_agent: agent,
      last_result: workflow.phase === "CODE" ? "CODE_COMPLETE" : "FIX_COMPLETE",
      blocked_reason: null,
    })
  }
  if (workflow.phase === "TEST") {
    const result = submission.status
    if (result === "FAIL") return routeFix(projectRoot, workflow, agent, result)
    if (result === "INCONCLUSIVE") {
      if (workflow.last_result !== "INCONCLUSIVE") {
        return saveWorkflow(projectRoot, workflow, {
          phase: "TEST",
          last_agent: agent,
          last_result: result,
          blocked_reason: null,
        })
      }
      return blockWorkflow(
        projectRoot,
        workflow,
        agent,
        result,
        `Test remained inconclusive after one automatic retry for ${workflow.current_task_id}`,
      )
    }
    const state = loadProjectState(projectRoot)
    saveProjectState(
      projectRoot,
      setTaskState(
        state,
        workflow.current_task_id,
        "reviewing",
        "bx-review",
        workflow.fix_round,
      ),
    )
    return saveWorkflow(projectRoot, workflow, {
      phase: "TASK_REVIEW",
      last_agent: agent,
      last_result: result,
      blocked_reason: null,
    })
  }
  if (workflow.phase === "TASK_REVIEW") {
    const result = submission.status
    if (result === "CHANGES_REQUIRED") {
      return routeFix(projectRoot, workflow, agent, result)
    }
    let state = loadProjectState(projectRoot)
    state = setTaskState(
      state,
      workflow.current_task_id,
      "done",
      null,
      workflow.fix_round,
    )
    const nextTask = nextReadyTask(projectRoot, state)
    if (nextTask === null) {
      saveProjectState(projectRoot, { ...state, stage: "B4" })
      return saveWorkflow(projectRoot, workflow, {
        phase: "INTEGRATION_TEST",
        current_task_id: null,
        fix_round: 0,
        last_agent: agent,
        last_result: result,
        blocked_reason: null,
      })
    }
    saveProjectState(projectRoot, state)
    return saveWorkflow(projectRoot, workflow, {
      phase: "CODE",
      current_task_id: nextTask,
      fix_round: 0,
      last_agent: agent,
      last_result: result,
      blocked_reason: null,
    })
  }
  if (workflow.phase === "INTEGRATION_TEST") {
    const result = submission.status
    if (result === "INCONCLUSIVE" && workflow.last_result !== "INCONCLUSIVE") {
      return saveWorkflow(projectRoot, workflow, {
        phase: "INTEGRATION_TEST",
        last_agent: agent,
        last_result: result,
        blocked_reason: null,
      })
    }
    if (result !== "PASS") {
      if (workflow.fix_round < 3) {
        return saveWorkflow(projectRoot, workflow, {
          phase: "INTEGRATION_FIX",
          fix_round: workflow.fix_round + 1,
          last_agent: agent,
          last_result: result,
          blocked_reason: null,
        })
      }
      return blockWorkflow(
        projectRoot,
        workflow,
        agent,
        result,
        `Integration test result: ${result}`,
      )
    }
    return saveWorkflow(projectRoot, workflow, {
      phase: "INTEGRATION_REVIEW",
      last_agent: agent,
      last_result: result,
      blocked_reason: null,
    })
  }
  if (workflow.phase === "INTEGRATION_FIX") {
    return saveWorkflow(projectRoot, workflow, {
      phase: "INTEGRATION_TEST",
      last_agent: agent,
      last_result: "INTEGRATION_FIX_COMPLETE",
      blocked_reason: null,
    })
  }
  if (workflow.phase === "INTEGRATION_REVIEW") {
    const result = submission.status
    if (result === "CHANGES_REQUIRED") {
      if (workflow.fix_round < 3) {
        return saveWorkflow(projectRoot, workflow, {
          phase: "INTEGRATION_FIX",
          fix_round: workflow.fix_round + 1,
          last_agent: agent,
          last_result: result,
          blocked_reason: null,
        })
      }
      return blockWorkflow(
        projectRoot,
        workflow,
        agent,
        result,
        "Integration review requires human-directed revision",
      )
    }
    const state = loadProjectState(projectRoot)
    saveProjectState(projectRoot, { ...state, stage: "B5" })
    return saveWorkflow(projectRoot, workflow, {
      phase: "WAITING_GATE_2",
      last_agent: agent,
      last_result: result,
      blocked_reason: null,
    })
  }
  throw new Error(`workflow cannot advance from phase ${workflow.phase}`)
}


function splitModel(model) {
  const separator = model.indexOf("/")
  if (separator <= 0 || separator === model.length - 1) {
    throw new Error(`Invalid configured model: ${model}`)
  }
  return { providerID: model.slice(0, separator), modelID: model.slice(separator + 1) }
}


function resultData(result, label) {
  if (result?.error || !result?.data) {
    const detail = result?.error ? JSON.stringify(result.error) : "empty response"
    throw new Error(`${label} failed: ${detail}`)
  }
  return result.data
}


function persistedChildPermissionContext(directory, sessionID) {
  if (typeof directory !== "string" || !directory || !sessionID) return null
  try {
    const projectRoot = fs.realpathSync(directory)
    const registry = loadSessionRegistry(projectRoot)
    const session = Object.values(registry.sessions).find((record) =>
      record.session_id === sessionID &&
      ["ACTIVE", "RETRYING"].includes(record.status),
    )
    if (!session) return null
    const job = loadJobBoard(projectRoot).jobs[session.job_id]
    if (!job || !Array.isArray(job.write_scope)) return null
    return {
      agent: session.agent,
      jobID: session.job_id,
      projectRoot,
      taskID: job.task_id,
      phase: job.phase,
      writeScope: job.write_scope,
    }
  } catch {
    return null
  }
}


async function sessionCanResume(client, record, directory) {
  if (!record || typeof client?.session?.get !== "function") return Boolean(record)
  try {
    const result = await client.session.get({
      path: { id: record.session_id },
      query: { directory },
    })
    return !result?.error && Boolean(result?.data)
  } catch {
    return false
  }
}


function schedulerWorkflowContext(workflow, job) {
  return {
    ...workflow,
    phase: job.phase,
    current_task_id: job.task_id,
  }
}


function scheduledTaskPrompt(projectRoot, job) {
  const contract = fs.readFileSync(
    path.join(projectRoot, ".biexce", "tasks", job.task_id + ".md"),
    "utf8",
  )
  const action = {
    CODE: "Implement only the bounded task contract.",
    FIX: "Apply the smallest evidence-backed fix for this task.",
    TEST: "Verify the acceptance criteria without editing source.",
    TASK_REVIEW: "Review the task diff and evidence without editing files.",
  }[job.phase]
  const history = taskResultHistory(projectRoot, job.task_id)
  const relevantPhases = {
    TEST: new Set(["CODE", "FIX"]),
    TASK_REVIEW: new Set(["CODE", "FIX", "TEST"]),
    FIX: new Set(["CODE", "TEST", "TASK_REVIEW"]),
    CODE: new Set(),
  }[job.phase] || new Set()
  const latestByPhase = new Map()
  for (const event of history) {
    if (relevantPhases.has(event.phase)) latestByPhase.set(event.phase, event)
  }
  const priorEvidence = [...latestByPhase.values()].map((event) => ({
    job_id: event.job_id,
    phase: event.phase,
    agent: event.agent,
    result_source: event.result_source,
    status: event.result.status,
    summary: event.result.summary.slice(0, 3000),
    changed_files: event.result.changed_files.slice(0, 100),
    checks: event.result.checks.slice(0, 20).map((check) => ({
      command: check.command.slice(0, 1000),
      exit_code: check.exit_code,
      status: check.status,
      output_summary: check.output_summary.slice(0, 1500),
    })),
    artifacts: event.result.artifacts.slice(0, 50),
  }))
  const declaredWritable = markdownField(contract, "Writable files")
  const taskWriteScope = !declaredWritable || declaredWritable.toLowerCase() === "none"
    ? []
    : declaredWritable.split(",").map((value) =>
        normalizeProjectRelative(value.trim(), "Writable files")
      )
  const currentScopeFiles = [...snapshotProjectFiles(projectRoot).keys()]
    .filter((file) => taskWriteScope.some((pattern) =>
      allowedByWriteScope(file, [pattern])
    ))
    .slice(0, 200)
  const repairScopePolicy =
    ["CODE", "FIX"].includes(job.phase) && standardWorkflow(projectRoot)
      ? [
          "[STANDARD RUNTIME REPAIR AUTHORITY]",
          "The planned write_scope is the expected baseline, not an immutable " +
            "file allowlist. If deterministic acceptance or regression evidence " +
            "proves that a minimal in-project source or test update outside that " +
            "baseline is necessary, the runtime authorizes that update for this " +
            "job. This never authorizes .biexce state, Git metadata, secrets, " +
            "credentials, generated/vendor content, production mutation, or an " +
            "unrelated refactor.",
          "An existing test whose expected behavior is directly superseded by " +
            "the approved task acceptance may be updated while preserving the " +
            "original invariant with an equivalent still-valid case. Do not " +
            "delete, disable, skip, or broadly weaken tests merely to get green.",
        ].join("\n")
      : [
          "[STRICT RUNTIME SCOPE]",
          "The declared write_scope is strict for this workflow profile. Report " +
            "a precise scope conflict instead of editing outside it.",
        ].join("\n")
  return [
    "[BIEXCE SCHEDULED JOB]",
    "job_id=" + job.job_id,
    "task_id=" + job.task_id,
    "phase=" + job.phase,
    "agent=" + job.agent,
    "write_scope=" + JSON.stringify(job.write_scope),
    "read_scope=" + JSON.stringify(job.read_scope),
    "",
    action,
    "Use only relevant role/task skills. Do not delegate another agent.",
    "",
    "[TASK CONTRACT]",
    contract,
    "",
    "[RUNTIME-AUTHORITATIVE PRIOR TASK EVIDENCE]",
    priorEvidence.length > 0
      ? JSON.stringify(priorEvidence, null, 2)
      : "No prior result was recorded for this task.",
    "",
    "[CURRENT TASK SOURCE SCOPE]",
    JSON.stringify(currentScopeFiles),
    "",
    repairScopePolicy,
    "Use the evidence above directly. Do not reject this job merely because " +
      "a separate chat report or raw Git diff was not attached. Inspect only " +
      "the listed task source scope when additional confirmation is needed.",
  ].join("\n")
}


function compactWorkflowEvidence(events) {
  return events.map((event) => ({
    job_id: event.job_id,
    phase: event.phase,
    agent: event.agent,
    result_source: event.result_source,
    status: event.result.status,
    summary: event.result.summary.slice(0, 3000),
    checks: event.result.checks.slice(0, 30).map((check) => ({
      command: check.command.slice(0, 1000),
      exit_code: check.exit_code,
      status: check.status,
      output_summary: check.output_summary.slice(0, 1500),
    })),
    artifacts: event.result.artifacts.slice(0, 50),
  }))
}


function preExecutionPhasePrompt(projectRoot, workflow) {
  if (workflow.phase === "EXPLORE") {
    return [
      "Inspect the workspace and create `.biexce/CODEBASE_BRIEF.md`.",
      "For a green-field project, explicitly record that there is no existing " +
        "source and describe the intended layout, toolchain and constraints.",
      "Do not edit application source, delegate, or start a persistent server.",
    ].join(" ")
  }
  if (workflow.phase === "PLAN") {
    const priorReviews = compactWorkflowEvidence(
      workflowResultHistory(projectRoot).filter((event) =>
        event.phase === "PLAN_REVIEW"
      ),
    )
    return [
      "Read PROJECT_BRIEF.md and CODEBASE_BRIEF.md, then create or revise " +
        "`.biexce/MASTER_PLAN.md` and 1-50 small `.biexce/tasks/t-NNN.md` contracts.",
        "Every task must have a bounded Writable files scope, executable Verify " +
          "command, explicit dependencies and acceptance criteria. When new " +
          "acceptance intentionally replaces behavior asserted by existing tests, " +
          "include those tests in Writable files; do not freeze them as read-only. " +
          "Keep the DAG " +
        "acyclic and implementation-ready. Do not edit application source.",
      priorReviews.length > 0
        ? "Apply the prior plan-review findings below before submitting:\n" +
          JSON.stringify(priorReviews, null, 2)
        : "This is the first planning pass.",
    ].join("\n")
  }
  if (workflow.phase === "PLAN_REVIEW") {
    const readiness = writePlanReadinessReport(projectRoot)
    return [
      "Red-team the Brief, Codebase Brief, Master Plan and every task contract.",
        "Check scope, dependencies, acceptance criteria, security, runnable Verify " +
          "commands and bounded writable paths. Reject a plan that makes a test " +
          "read-only while the same task intentionally supersedes its asserted " +
          "behavior. Remain read-only.",
      "Return PLAN_OK only when the plan can execute without human repair; " +
        "otherwise return PLAN_NEEDS_REVISION with concrete findings.",
      "Runtime Gate 1 preflight:\n" + JSON.stringify(readiness, null, 2),
    ].join(" ")
  }
  throw new Error(`unsupported pre-execution phase: ${workflow.phase}`)
}


function integrationPhasePrompt(projectRoot, workflow) {
  const prior = compactWorkflowEvidence(
    workflowResultHistory(projectRoot).filter((event) =>
      ["INTEGRATION_TEST", "INTEGRATION_FIX", "INTEGRATION_REVIEW"].includes(event.phase)
    ),
  )
  if (workflow.phase === "INTEGRATION_TEST") {
    return [
      "Run the complete applicable project verification pipeline now.",
      "Use repository instructions and deterministic commands through " +
        "biexce_run_command. Verify integration/regression and build/package " +
        "where applicable. Do not edit source and do not delegate.",
      "Return PASS only when every required runnable check exits successfully.",
    ].join(" ")
  }
  if (workflow.phase === "INTEGRATION_FIX") {
    return [
      "Apply the smallest source fix required by the latest integration test " +
        "or integration review evidence.",
      "Do not change BIEXCE runtime state, Git history, credentials or unrelated " +
        "features. Add or update focused tests when needed, then return so the " +
        "runtime can rerun the complete integration pipeline.",
      "[RUNTIME-AUTHORITATIVE INTEGRATION EVIDENCE]",
      prior.length > 0
        ? JSON.stringify(prior, null, 2)
        : "No integration result has been recorded.",
    ].join("\n")
  }
  return [
    "Perform the final integrated read-only review against the approved Brief, " +
      "Master Plan, task contracts, current source and integration evidence.",
    "Do not edit, delegate or demand a duplicate report. Return APPROVE, " +
      "APPROVE_WITH_MINOR_NOTES, or CHANGES_REQUIRED with actionable findings.",
    "",
    "[RUNTIME-AUTHORITATIVE INTEGRATION EVIDENCE]",
    prior.length > 0
      ? JSON.stringify(prior, null, 2)
      : "No integration result has been recorded.",
  ].join("\n")
}


function markdownCell(value) {
  return String(value ?? "-").replaceAll("|", "\\|").replace(/\s+/g, " ").trim()
}


function persistIntegrationReport(projectRoot, submission) {
  const reports = path.join(projectRoot, ".biexce", "reports")
  fs.mkdirSync(reports, { recursive: true, mode: 0o700 })
  const checks = submission.checks.length > 0
    ? submission.checks.map((check) =>
        `| ${markdownCell(check.command)} | ${markdownCell(check.exit_code)} | ` +
        `${markdownCell(check.status)} | ${markdownCell(check.output_summary)} |`
      )
    : ["| - | - | NOT_RUN | No deterministic check was recorded. |"]
  atomicWriteText(
    path.join(reports, "INTEGRATION_REPORT.md"),
    [
      "# Integration Report",
      "",
      "Generated by BIEXCE Runtime from runtime-owned command evidence.",
      "",
      `Verdict: **${submission.status}**`,
      "",
      "## Summary",
      "",
      submission.summary,
      "",
      "## Checks",
      "",
      "| Command | Exit code | Status | Evidence |",
      "|---|---:|---|---|",
      ...checks,
      "",
    ].join("\n"),
  )
}


function persistFinalReport(projectRoot, submission) {
  const reports = path.join(projectRoot, ".biexce", "reports")
  fs.mkdirSync(reports, { recursive: true, mode: 0o700 })
  const project = loadProjectState(projectRoot)
  const taskRows = project.tasks.map((task) =>
    `| ${markdownCell(task.id)} | ${markdownCell(task.title)} | ` +
      `${markdownCell(task.status)} | ${markdownCell(task.round)} |`
  )
  atomicWriteText(
    path.join(reports, "FINAL_REPORT.md"),
    [
      "# Final Report",
      "",
      "Generated by BIEXCE Runtime after integration verification and review.",
      "",
      `Project: **${markdownCell(project.project)}**`,
      `Review verdict: **${submission.status}**`,
      "",
      "## Review Summary",
      "",
      submission.summary,
      "",
      "## Tasks",
      "",
      "| ID | Title | Status | Fix rounds |",
      "|---|---|---|---:|",
      ...taskRows,
      "",
      "## Evidence",
      "",
      "- `.biexce/reports/INTEGRATION_REPORT.md`",
      "- `.biexce/state/AUTOPILOT_EVENTS.jsonl`",
      "",
    ].join("\n"),
  )
}


function registerScheduledBoardJob(projectRoot, job, workflowRevision) {
  const existing = loadJobBoard(projectRoot).jobs[job.job_id]
  if (existing) return existing
  return putJob(projectRoot, {
    job_id: job.job_id,
    trace_id:
      "trace-scheduler-" + job.task_id + "-" + job.phase.toLowerCase() +
      "-r" + workflowRevision,
    task_id: job.task_id,
    agent: job.agent,
    session_id: null,
    phase: job.phase,
    status: "QUEUED",
    dependencies: job.dependencies,
    read_scope: job.read_scope,
    write_scope: job.write_scope,
    model: job.model,
    attempt: 1,
    recovery_count: 0,
    started_at_utc: null,
    deadline_at_utc: null,
    completed_at_utc: null,
    result_status: null,
    error: null,
  })
}


export const BiexceControlPlugin = async ({ client, directory: pluginDirectory }) => {
  let defaultAgent = "bx-code"
  let executeWorkflowDelegation = null
  const activeChildren = SHARED_ACTIVE_CHILDREN
  const submittedResults = SHARED_SUBMITTED_RESULTS
  const commandEvidence = SHARED_COMMAND_EVIDENCE
  const directorSessions = SHARED_DIRECTOR_SESSIONS
  const supervisor = createRuntimeSupervisor({
    client,
    logLimitBytes: commandLogLimitBytes(),
    hardKillGraceMs: hardKillGraceMs(),
  })

  const replyPermission = async (request, response, directory) => {
    const failures = []
    if (typeof client.permission?.reply === "function") {
      try {
        resultData(await client.permission.reply({
          requestID: request.id,
          directory,
          reply: response,
        }), "OpenCode permission reply")
        return
      } catch (error) {
        failures.push(error.message)
      }
    }
    if (typeof client.postSessionIdPermissionsPermissionId === "function") {
      try {
        resultData(await client.postSessionIdPermissionsPermissionId({
          path: { id: request.sessionID, permissionID: request.id },
          query: { directory },
          body: { response },
        }), "OpenCode legacy permission reply")
        return
      } catch (error) {
        failures.push(error.message)
      }
    }
    throw new Error(
      failures.length > 0
        ? failures.join(" | ")
        : "OpenCode permission reply API is unavailable",
    )
  }

  const executeScheduledJob = async (
    { taskID = null, requestedAgent = null },
    context,
  ) => {
    if (context.agent !== "bx-director") {
      throw new Error("BIEXCE_SCHEDULER_DENY: only bx-director may start jobs")
    }
    loadRunningState(context.directory, context.sessionID)
    const projectRoot = fs.realpathSync(context.directory)
    reconcileRuntimeState(projectRoot)
    let workflow = loadWorkflow(projectRoot)
    workflow = applyPendingRuntimeCommand(projectRoot, workflow)
    workflow = recoverPlanReviewBaselineDrift(projectRoot, workflow)
    if (
      workflow.gate_1 !== "APPROVED" ||
      !["CODE", "TEST", "FIX", "TASK_REVIEW"].includes(workflow.phase)
    ) {
      throw new Error(
        "BIEXCE_SCHEDULER_GATE: task jobs require approved Gate 1 execution",
      )
    }
    const timeoutMs = delegationTimeoutMs()
    let claimed = null
    let binding = null
    let jobLease = null
    let boardRegistered = false
    let childID = null
    let fileSnapshot = null
    let previousSession = null
    let usedModel = null
    let attemptCount = 0
    let sessionResumed = false
    let jobCompleted = false
    try {
      const routing = loadAppliedRouting()
      const options = schedulerOptions()
      initializeScheduler(projectRoot, options)
      claimed = claimSchedulerJob({
        projectRoot,
        taskID,
        requestedAgent,
        routing: routing.agents,
        options,
      })
      binding = routing.agents[claimed.agent]
      if (!binding?.primary) {
        throw new Error(
          "BIEXCE_MODEL_BLOCKED: " + claimed.agent + " is unconfigured",
        )
      }
      registerScheduledBoardJob(projectRoot, claimed, workflow.revision)
      boardRegistered = true
      jobLease = acquireJobLease(
        projectRoot,
        claimed.job_id,
        context.sessionID,
        timeoutMs,
      )
      putJob(projectRoot, {
        job_id: claimed.job_id,
        status: "RUNNING",
        session_id: context.sessionID,
        model: binding.primary,
        started_at_utc: new Date().toISOString(),
        deadline_at_utc: jobLease.deadline_at_utc,
        completed_at_utc: null,
        result_status: null,
        error: null,
      })
      previousSession = resumableSession(
        projectRoot,
        claimed.job_id,
        claimed.agent,
      )
      if (
        previousSession &&
        await sessionCanResume(client, previousSession, context.directory)
      ) {
        childID = previousSession.session_id
        attemptCount = previousSession.attempt
        sessionResumed = true
      } else {
        if (previousSession) {
          putSessionRecord(projectRoot, {
            job_id: claimed.job_id,
            status: "FAILED",
            last_error: "Stored child session is unavailable",
          })
        }
        const created = resultData(
          await client.session.create({
            body: {
              parentID: context.sessionID,
              title: childSessionTitle({
                agent: claimed.agent,
                phase: claimed.phase,
                taskId: claimed.task_id,
              }),
            },
            query: { directory: context.directory },
          }),
          "scheduled child session creation",
        )
        childID = created.id
      }
      putSessionRecord(projectRoot, {
        job_id: claimed.job_id,
        session_id: childID,
        parent_session_id: context.sessionID,
        agent: claimed.agent,
        model: binding.primary,
        status: "ACTIVE",
        attempt: Math.max(1, attemptCount || 1),
        last_error: null,
      })
      putJob(projectRoot, {
        job_id: claimed.job_id,
        session_id: childID,
        attempt: Math.max(1, attemptCount || 1),
      })
      const jobWorkflow = schedulerWorkflowContext(workflow, claimed)
      fileSnapshot = loadOrCreateJobBaseline(projectRoot, claimed.job_id)
      activeChildren.set(childID, {
        agent: claimed.agent,
        jobID: claimed.job_id,
        model: binding.primary,
        attempt: Math.max(1, attemptCount || 1),
        projectRoot,
        taskID: claimed.task_id,
        phase: claimed.phase,
        workflowRevision: workflow.revision,
        scheduler: true,
        writeScope: claimed.write_scope,
      })
      context.metadata?.(observabilityUpdate({
        parentSessionId: context.sessionID,
        sessionId: childID,
        jobId: claimed.job_id,
        traceId: "trace-scheduler-" + claimed.task_id + "-" +
          claimed.phase.toLowerCase() + "-r" + workflow.revision,
        agent: claimed.agent,
        phase: claimed.phase,
        taskId: claimed.task_id,
        status: "RUNNING",
        configuredModel: binding.primary,
        attempt: Math.max(1, attemptCount || 1),
        sessionResumed,
        schedulerRevision: claimed.scheduler_revision,
        dependencies: claimed.dependencies,
      }))
      const attemptOffset = sessionResumed ? attemptCount : 0
      const configuredCandidates = runtimeModels(binding)
      const resumedModelIndex = sessionResumed
        ? configuredCandidates.findIndex(
            (candidate) => candidate.model === previousSession.model,
          )
        : -1
      const runtimeCandidates = resumedModelIndex > 0
        ? configuredCandidates.slice(resumedModelIndex)
        : configuredCandidates
      const prompt = [
        scheduledTaskPrompt(projectRoot, claimed),
        "",
        "[BIEXCE RUNTIME CONTRACT]",
        runtimeContract(jobWorkflow, claimed.agent),
      ].join("\n")
      const promptOutcome = await executeWithRetry({
        candidates: runtimeCandidates,
        retriesPerModel: transportRetries(),
        backoffMs: retryBackoffMs(),
        execute: async ({
          model,
          zone,
          fallback,
          attempt: runtimeAttempt,
        }) => {
          const attempt = attemptOffset + runtimeAttempt
          usedModel = model
          attemptCount = attempt
          submittedResults.delete(childID)
          commandEvidence.delete(childID)
          const active = activeChildren.get(childID)
          if (active) {
            active.model = model
            active.attempt = attempt
          }
          putJob(projectRoot, {
            job_id: claimed.job_id,
            status: "RUNNING",
            model,
            attempt,
            error: null,
          })
          putSessionRecord(projectRoot, {
            job_id: claimed.job_id,
            model,
            status: "ACTIVE",
            attempt,
            last_error: null,
          })
          context.metadata?.(observabilityUpdate({
            parentSessionId: context.sessionID,
            sessionId: childID,
            jobId: claimed.job_id,
            traceId: "trace-scheduler-" + claimed.task_id + "-" +
              claimed.phase.toLowerCase() + "-r" + workflow.revision,
            agent: claimed.agent,
            phase: claimed.phase,
            taskId: claimed.task_id,
            status: fallback
              ? "FALLBACK"
              : attempt > 1 ? "RETRYING" : "RUNNING",
            configuredModel: binding.primary,
            actualModel: model,
            modelZone: zone,
            attempt,
            fallbackUsed: fallback,
            sessionResumed,
            schedulerRevision: claimed.scheduler_revision,
            dependencies: claimed.dependencies,
          }))
          return resultData(await supervisor.supervisePrompt({
            childID,
            directory: context.directory,
            timeoutMs,
            signal: context.abort,
            controlCheck: () =>
              loadRunningState(projectRoot, context.sessionID),
            pollMs: controlPollMs(),
            body: {
              agent: claimed.agent,
              model: splitModel(model),
              parts: [{ type: "text", text: prompt }],
            },
          }), "scheduled child session prompt")
        },
        onRetry: async ({ model, attempt: runtimeAttempt, kind, error }) => {
          const attempt = attemptOffset + runtimeAttempt
          putJob(projectRoot, {
            job_id: claimed.job_id,
            status: "RETRYING",
            model,
            attempt,
            error: kind + ": " + error.message,
          })
          putSessionRecord(projectRoot, {
            job_id: claimed.job_id,
            model,
            status: "RETRYING",
            attempt,
            last_error: kind + ": " + error.message,
          })
        },
        onFallback: async ({ to, attempt: runtimeAttempt, kind, error }) => {
          const attempt = attemptOffset + runtimeAttempt
          putJob(projectRoot, {
            job_id: claimed.job_id,
            status: "FALLBACK",
            model: to.model,
            attempt,
            error: kind + ": " + error.message,
          })
          putSessionRecord(projectRoot, {
            job_id: claimed.job_id,
            model: to.model,
            status: "RETRYING",
            attempt,
            last_error: kind + ": " + error.message,
          })
        },
      })
      const response = promptOutcome.value
      usedModel = promptOutcome.model
      attemptCount = attemptOffset + promptOutcome.attempt
      const output = response.parts
        .filter((part) => part.type === "text")
        .map((part) => part.text)
        .join("\n")
      const currentWorkflow = loadWorkflow(projectRoot)
      if (
        currentWorkflow.revision !== workflow.revision ||
        currentWorkflow.gate_1 !== "APPROVED"
      ) {
        throw new Error(
          "workflow changed while the scheduled child session was running",
        )
      }
      const resolvedSubmission = resolveChildResult({
        childID,
        projectRoot,
        workflow: jobWorkflow,
        output,
        before: fileSnapshot,
        activeChildren,
        submittedResults,
        commandEvidence,
      })
      const submission = resolvedSubmission.result
      verifyResultFiles(
        projectRoot,
        jobWorkflow,
        submission,
        fileSnapshot,
        concurrentJobWritePatterns(projectRoot, claimed.job_id),
      )
      recordJobResult(
        projectRoot,
        claimed.job_id,
        submission,
        resolvedSubmission.source,
      )
      const schedulerResult = completeSchedulerJob(
        projectRoot,
        claimed.job_id,
        submission.status,
      )
      putJob(projectRoot, {
        job_id: claimed.job_id,
        status: "COMPLETED",
        session_id: childID,
        model: usedModel,
        attempt: attemptCount,
        completed_at_utc: new Date().toISOString(),
          result_status: submission.status,
        error: null,
      })
      putSessionRecord(projectRoot, {
        job_id: claimed.job_id,
        model: usedModel,
        status: "COMPLETED",
        attempt: attemptCount,
        last_error: null,
      })
      jobCompleted = true
      removeJobBaseline(projectRoot, claimed.job_id)
      let nextWorkflow = currentWorkflow
      const nextJobs = schedulerResult.all_done
        ? []
        : listSchedulerJobs(projectRoot, routing.agents).jobs
      const hasRunnableTask = nextJobs.some((job) => job.status === "READY")
      if (schedulerResult.all_done) {
        nextWorkflow = saveWorkflow(projectRoot, currentWorkflow, {
          phase: "INTEGRATION_TEST",
          current_task_id: null,
          fix_round: 0,
          last_agent: claimed.agent,
          last_result: "ALL_TASKS_DONE",
          blocked_reason: null,
        })
      } else if (
        schedulerResult.blocked_task_id &&
        !schedulerResult.has_active &&
        !hasRunnableTask
      ) {
        nextWorkflow = saveWorkflow(projectRoot, currentWorkflow, {
          phase: "BLOCKED",
          current_task_id: schedulerResult.blocked_task_id,
          last_agent: claimed.agent,
          last_result: submission.status,
          blocked_reason:
            "Scheduler blocked task " + schedulerResult.blocked_task_id,
        })
      }
      context.metadata?.(observabilityUpdate({
        parentSessionId: context.sessionID,
        sessionId: childID,
        jobId: claimed.job_id,
        traceId: "trace-scheduler-" + claimed.task_id + "-" +
          claimed.phase.toLowerCase() + "-r" + workflow.revision,
        agent: claimed.agent,
        phase: claimed.phase,
        taskId: claimed.task_id,
        status: "DONE",
        configuredModel: binding.primary,
        actualModel: usedModel,
        attempt: attemptCount,
        fallbackUsed: usedModel !== binding.primary,
        sessionResumed,
        schedulerRevision: schedulerResult.scheduler_revision,
        dependencies: claimed.dependencies,
        nextPhase: schedulerResult.task.phase,
          resultStatus: submission.status,
          resultSource: resolvedSubmission.source,
        usage: responseUsage(response),
        evidence: submission.artifacts,
      }))
      return {
        title:
          claimed.agent + ": " + claimed.task_id + " " + claimed.phase,
        output: output || "Scheduled child completed without a text response.",
        metadata: {
          parentSessionId: context.sessionID,
          sessionId: childID,
          child_session_id: childID,
          job_id: claimed.job_id,
          agent: claimed.agent,
          configured_model: binding.primary,
          actual_model: usedModel,
          fallback_used: usedModel !== binding.primary,
          attempt_count: attemptCount,
          session_resumed: sessionResumed,
          task_id: claimed.task_id,
          completed_phase: claimed.phase,
          task_next_phase: schedulerResult.task.phase,
          workflow_phase: nextWorkflow.phase,
          scheduler_revision: schedulerResult.scheduler_revision,
          all_tasks_done: schedulerResult.all_done,
          next_jobs: nextJobs,
          result: submission,
          result_source: resolvedSubmission.source,
        },
      }
    } catch (error) {
      const errorKind = error.biexceKind || classifyRuntimeError(error)
      const cancelled =
        errorKind === "CANCELLED" ||
        ["CANCELLED", "CONTROL_STOPPED"].includes(error.code)
      const timedOut = [
        "TIMEOUT",
        "COMMAND_TIMEOUT",
      ].includes(error.code)
      const recoverableRuntime = isFallbackKind(errorKind)
      const standardRecoverable =
        standardWorkflow(projectRoot) &&
        !unsafeRuntimeFailure(error.message, claimed?.phase || workflow?.phase)
      const schedulerRecoverable =
        recoverableRuntime ||
        cancelled ||
        timedOut ||
        standardRecoverable
      recordFailurePolicyShadow(projectRoot, {
        error,
        jobID: claimed?.job_id || null,
        taskID: claimed?.task_id || taskID,
        phase: claimed?.phase || "WORK",
        legacyDisposition: schedulerRecoverable ? "RETRY" : "BLOCK",
        fixRound: claimed?.fix_round || workflow?.fix_round || 0,
      })
      if (claimed && !jobCompleted) {
        try {
          releaseSchedulerJob(
            projectRoot,
            claimed.job_id,
            errorKind + ": " + error.message,
            { recoverable: schedulerRecoverable },
          )
        } catch {
          // Preserve the original runtime error.
        }
      }
      if (boardRegistered && !jobCompleted) {
        try {
          const failureStatus = timedOut
            ? "TIMED_OUT"
            : cancelled
              ? "CANCELLED"
              : recoverableRuntime || standardRecoverable
                ? "RETRYING"
                : "FAILED"
          putJob(projectRoot, {
            job_id: claimed.job_id,
            status: failureStatus,
            model: usedModel || binding?.primary || claimed.model,
            attempt: Math.max(1, attemptCount || 1),
            completed_at_utc:
              ["RETRYING", "FALLBACK"].includes(failureStatus)
                ? null
                : new Date().toISOString(),
            error: errorKind + ": " + error.message,
          })
          if (childID !== null) {
            putSessionRecord(projectRoot, {
              job_id: claimed.job_id,
              model: usedModel || binding.primary,
              status:
                cancelled || timedOut
                  ? "CANCELLED"
                  : schedulerRecoverable
                    ? "RETRYING"
                    : "FAILED",
              attempt: Math.max(1, attemptCount || 1),
              last_error: errorKind + ": " + error.message,
            })
          }
        } catch {
          // Preserve the original runtime error.
        }
      }
      context.metadata?.(observabilityUpdate({
        parentSessionId: context.sessionID,
        sessionId: childID,
        jobId: claimed?.job_id || null,
        agent: claimed?.agent || requestedAgent || "scheduler",
        phase: claimed?.phase || "WORK",
        taskId: claimed?.task_id || taskID,
        status: timedOut ? "TIMED_OUT" : cancelled ? "CANCELLED" : "ERROR",
        actualModel: usedModel,
        attempt: Math.max(1, attemptCount || 1),
        sessionResumed,
        errorCode: error.code || null,
        errorKind,
      }))
      const wrapped = new Error(
        "BIEXCE_SCHEDULER_ERROR [" + errorKind + "]: " + error.message,
      )
      wrapped.code = error.code
      wrapped.biexceKind = errorKind
      throw wrapped
    } finally {
      if (childID !== null) {
        await supervisor.closeSession(childID)
        activeChildren.delete(childID)
        submittedResults.delete(childID)
        commandEvidence.delete(childID)
      }
      if (jobLease !== null) releaseJobLease(projectRoot, jobLease)
    }
  }

  const driveScheduledWorkflow = async (args, context) => {
    if (context.agent !== "bx-director") {
      throw new Error("BIEXCE_DRIVER_DENY: only bx-director may drive Autopilot")
    }
    const projectRoot = fs.realpathSync(context.directory)
    const runtimeReconciliation = reconcileRuntimeState(projectRoot)
    loadRunningState(context.directory, context.sessionID, {
      allowSessionRebind: true,
    })
    let workflow = loadWorkflow(projectRoot)
    workflow = applyPendingRuntimeCommand(projectRoot, workflow)
    // Apply the requested profile before legacy-state reconciliation. A
    // project created by an older runtime may still persist `critical`; the
    // explicit standard downgrade for this drive must govern recovery in the
    // same turn instead of requiring a second Director prompt.
    let policy = selectAndPersistWorkflowPolicy(projectRoot, {
      requestedProfile: args.profile,
      allowCriticalDowngrade: args.allow_critical_downgrade,
      actor: "biexce-drive",
    })
    let recoveredInLastPass = []
    const recoveredDuringDrive = new Set()
    const recoveryRoutesDuringDrive = {}
    const recoveryReasonsDuringDrive = {}
    const recoverKnownSchedulerBlockers = (current) => {
      const schedulerPath = path.join(
        projectRoot,
        ".biexce",
        "state",
        "AUTOPILOT_SCHEDULER.json",
      )
      if (!fs.existsSync(schedulerPath)) return current
      const phaseByTask = {}
      if (standardWorkflow(projectRoot)) {
        const failedJobs = Object.values(loadJobBoard(projectRoot).jobs)
          .filter((job) =>
            job.task_id &&
            ["CODE", "TEST", "FIX", "TASK_REVIEW"].includes(job.phase) &&
            (
              ["FAILED", "BLOCKED", "TIMED_OUT", "CANCELLED", "RETRYING"].includes(job.status) ||
              (
                job.status === "COMPLETED" &&
                ["FAILED", "FAIL", "CHANGES_REQUIRED", "INCONCLUSIVE"].includes(
                  job.result_status,
                )
              )
            ) &&
            !unsafeRuntimeFailure(job.error, job.phase)
          )
          .sort((left, right) =>
            (Date.parse(right.completed_at_utc || right.started_at_utc || "") || 0) -
            (Date.parse(left.completed_at_utc || left.started_at_utc || "") || 0)
          )
        for (const job of failedJobs) {
          if (phaseByTask[job.task_id]) continue
          phaseByTask[job.task_id] = job.phase
        }
      }
      const recovery = reconcileRuntimeState(projectRoot, {
        recoverBlockers: true,
        allowStandard: standardWorkflow(projectRoot),
        phaseByTask,
      })
      const recovered = recovery.recovered_tasks
      recoveredInLastPass = [...new Set(recovered)]
      for (const taskID of recovered) {
        recoveredDuringDrive.add(taskID)
        recoveryRoutesDuringDrive[taskID] =
          recovery.recovered_routes[taskID] || null
        recoveryReasonsDuringDrive[taskID] =
          recovery.recovery_reasons[taskID] || null
      }
      if (recovered.length === 0) return current
      const scheduler = loadSchedulerState(projectRoot)
      const recoveredTaskID = recovered.includes(current.current_task_id)
        ? current.current_task_id
        : recovered.length === 1 ? recovered[0] : null
      if (!recoveredTaskID) return current
      const recoveredTask = scheduler.tasks[recoveredTaskID]
      if (!recoveredTask || recoveredTask.status !== "READY") return current
      const runningTasks = Object.values(scheduler.tasks).filter(
        (task) => task.status === "RUNNING",
      )
      const currentTask = current.current_task_id
        ? scheduler.tasks[current.current_task_id] || null
        : null
      const staleExecutionPointer =
        ["CODE", "TEST", "FIX", "TASK_REVIEW"].includes(current.phase) &&
        runningTasks.length === 0 &&
        (!currentTask || ["DONE", "BLOCKED"].includes(currentTask.status))
      if (current.phase !== "BLOCKED" && !staleExecutionPointer) return current
      return saveWorkflow(projectRoot, current, {
        phase: recovery.recovered_routes[recoveredTaskID] || "TEST",
        current_task_id: recoveredTaskID,
        fix_round: recoveredTask.fix_round,
        last_agent: null,
        last_result: "RUNTIME_RECOVERED",
        blocked_reason: null,
      })
    }
    workflow = recoverKnownSchedulerBlockers(workflow)
    workflow = recoverPlanReviewBaselineDrift(projectRoot, workflow)
    workflow = recoverStandardBlockedWorkflow(projectRoot, workflow)
    let batches = 0
    let completedJobs = 0
    let noProgressPasses = 0
    const failures = []

    const finish = (driverStatus, terminalReason, currentWorkflow, extra = {}) => {
      policy = updateWorkflowPolicy(projectRoot, {
        driverStatus,
        terminalReason,
        actor: "biexce-drive",
      })
      const metadata = {
        profile: policy.effective_profile,
        requested_profile: policy.requested_profile,
        profile_source: policy.source,
        risk_flags: policy.risk_flags,
        driver_status: policy.driver_status,
        terminal_reason: terminalReason,
        workflow_phase: currentWorkflow.phase,
        next_agent: PHASE_AGENTS[currentWorkflow.phase] || null,
        batches,
        completed_jobs: completedJobs,
        failed_jobs: failures.length,
        failures,
        reconciled_jobs: runtimeReconciliation.released_scheduler_jobs,
        recovered_tasks: [...recoveredDuringDrive],
        recovered_routes: recoveryRoutesDuringDrive,
        recovery_reasons: recoveryReasonsDuringDrive,
        ...extra,
      }
      context.metadata?.({
        title:
          "BIEXCE Auto | " + policy.driver_status + " | " +
          currentWorkflow.phase,
        metadata,
      })
      return {
        title: "BIEXCE autonomous driver",
        output: JSON.stringify(metadata, null, 2),
        metadata,
      }
    }

    const workflowBlocker = () => {
      try {
        const routing = loadAppliedRouting()
        const blockedJobs = listSchedulerJobs(projectRoot, routing.agents).jobs
          .filter((job) => job.status === "BLOCKED")
        return {
          reason: blockedJobs.length > 0 ? "TASK_BLOCKED" : "WORKFLOW_BLOCKED",
          blocked_tasks: blockedJobs.map((job) => job.task_id),
          blocker_details: blockedJobs.map((job) => ({
            task_id: job.task_id,
            phase: job.phase,
            reason: job.reason,
            job_id: job.job_id,
          })),
        }
      } catch {
        return {
          reason: "WORKFLOW_BLOCKED",
          blocked_tasks: [],
          blocker_details: [],
        }
      }
    }

    // A second Director turn can arrive while the first turn is still waiting
    // for a visible child session. Do not create duplicate work or burn retry
    // budget in that case; report the active jobs and let the existing turn
    // finish. The job-board lease remains the single source of truth.
    if (hasActiveJobLeases(projectRoot)) {
      const activeJobs = Object.values(loadJobBoard(projectRoot).jobs)
        .filter((job) => job.status === "RUNNING")
        .map((job) => job.job_id)
      return finish("WAITING_AGENT", "ACTIVE_JOBS_IN_PROGRESS", workflow, {
        active_jobs: activeJobs,
      })
    }

    if (!policy.policy.execute_source) {
      return finish("COMPLETE", "ADVISORY_ONLY", workflow)
    }
    if (["WAITING_GATE_1", "WAITING_GATE_2"].includes(workflow.phase)) {
      return finish("WAITING_HUMAN", workflow.phase, workflow)
    }
    if (workflow.phase === "BLOCKED") {
      const blocker = workflowBlocker()
      return finish("BLOCKED", blocker.reason, workflow, {
        blocked_tasks: blocker.blocked_tasks,
        blocker_details: blocker.blocker_details,
      })
    }
    if (workflow.phase === "COMPLETE") {
      return finish("COMPLETE", "WORKFLOW_COMPLETE", workflow)
    }
    if (![
      "EXPLORE",
      "PLAN",
      "PLAN_REVIEW",
      "CODE",
      "TEST",
      "FIX",
      "TASK_REVIEW",
      "INTEGRATION_TEST",
      "INTEGRATION_FIX",
      "INTEGRATION_REVIEW",
    ].includes(workflow.phase)) {
      return finish("BLOCKED", "UNSUPPORTED_WORKFLOW_PHASE", workflow)
    }

    updateWorkflowPolicy(projectRoot, {
      driverStatus: "RUNNING",
      terminalReason: null,
      actor: "biexce-drive",
    })
    const maximumBatches = positiveEnvironmentInteger(
      "BIEXCE_DRIVER_MAX_BATCHES",
      50,
      1,
      100,
    )

    try {
      while (batches < maximumBatches) {
        loadRunningState(projectRoot, context.sessionID)
        workflow = loadWorkflow(projectRoot)
        workflow = recoverKnownSchedulerBlockers(workflow)
        workflow = recoverPlanReviewBaselineDrift(projectRoot, workflow)
        workflow = recoverStandardBlockedWorkflow(projectRoot, workflow)
        if (["WAITING_GATE_1", "WAITING_GATE_2"].includes(workflow.phase)) {
          return finish("WAITING_HUMAN", workflow.phase, workflow)
        }
        if (workflow.phase === "BLOCKED") {
          const blocker = workflowBlocker()
          return finish("BLOCKED", blocker.reason, workflow, {
            blocked_tasks: blocker.blocked_tasks,
            blocker_details: blocker.blocker_details,
          })
        }
        if (workflow.phase === "COMPLETE") {
          return finish("COMPLETE", "WORKFLOW_COMPLETE", workflow)
        }
        if (["EXPLORE", "PLAN", "PLAN_REVIEW"].includes(workflow.phase)) {
          if (typeof executeWorkflowDelegation !== "function") {
            throw new Error("workflow delegation runtime is unavailable")
          }
          const preExecutionAgent = PHASE_AGENTS[workflow.phase]
          const preExecutionPhase = workflow.phase
          batches += 1
          try {
            await executeWorkflowDelegation({
              agent: preExecutionAgent,
              description: {
                EXPLORE: "Create the codebase brief",
                PLAN: "Create or revise the implementation plan",
                PLAN_REVIEW: "Red-team the implementation plan",
              }[preExecutionPhase],
              prompt: preExecutionPhasePrompt(projectRoot, workflow),
            }, context)
          } catch (error) {
            const blocked = loadWorkflow(projectRoot)
            const recovered = recoverPlanReviewBaselineDrift(
              projectRoot,
              blocked,
            )
            if (recovered.revision !== blocked.revision) {
              workflow = recovered
              continue
            }
            const retried = retryStandardWorkflowFailure(
              projectRoot,
              blocked,
              preExecutionPhase,
              error,
            )
            if (retried.revision !== blocked.revision) {
              workflow = retried
              continue
            }
            if (
              standardWorkflow(projectRoot) &&
              !unsafeRuntimeFailure(error.message, preExecutionPhase)
            ) {
              failures.push({
                job_id: null,
                task_id: blocked.current_task_id,
                error: error.message,
              })
              return finish("PAUSED", "PHASE_RETRY_EXHAUSTED", blocked)
            }
            throw error
          }
          completedJobs += 1
          workflow = loadWorkflow(projectRoot)
          continue
        }
        if (["INTEGRATION_TEST", "INTEGRATION_FIX", "INTEGRATION_REVIEW"].includes(workflow.phase)) {
          if (typeof executeWorkflowDelegation !== "function") {
            throw new Error("workflow delegation runtime is unavailable")
          }
          const integrationAgent = PHASE_AGENTS[workflow.phase]
          const integrationPhase = workflow.phase
          batches += 1
          try {
            await executeWorkflowDelegation({
              agent: integrationAgent,
              description: integrationPhase === "INTEGRATION_TEST"
                ? "Run final integration verification"
                : integrationPhase === "INTEGRATION_FIX"
                  ? "Fix integration findings"
                  : "Review integrated delivery",
              prompt: integrationPhasePrompt(projectRoot, workflow),
            }, context)
          } catch (error) {
            const blocked = loadWorkflow(projectRoot)
            const retried = retryStandardWorkflowFailure(
              projectRoot,
              blocked,
              integrationPhase,
              error,
            )
            if (retried.revision !== blocked.revision) {
              workflow = retried
              continue
            }
            if (
              standardWorkflow(projectRoot) &&
              !unsafeRuntimeFailure(error.message, integrationPhase)
            ) {
              failures.push({
                job_id: null,
                task_id: null,
                error: error.message,
              })
              return finish("PAUSED", "PHASE_RETRY_EXHAUSTED", blocked)
            }
            throw error
          }
          completedJobs += 1
          workflow = loadWorkflow(projectRoot)
          continue
        }
        if (!["CODE", "TEST", "FIX", "TASK_REVIEW"].includes(workflow.phase)) {
          return finish("WAITING_AGENT", "WORKFLOW_AGENT_REQUIRED", workflow)
        }

        const routing = loadAppliedRouting()
        initializeScheduler(projectRoot, schedulerOptions())
        const batch = planSchedulerBatch(
          projectRoot,
          routing.agents,
          policy.policy.max_batch,
        ).jobs
        if (batch.length === 0) {
          const snapshot = listSchedulerJobs(projectRoot, routing.agents).jobs
          const active = snapshot.filter((job) => job.status === "RUNNING")
          const blocked = snapshot.filter((job) => job.status === "BLOCKED")
          if (active.length > 0) {
            return finish("WAITING_AGENT", "ACTIVE_JOBS_IN_PROGRESS", workflow, {
              active_jobs: active.map((job) => job.job_id),
            })
          }
          if (blocked.length > 0) {
            return finish("BLOCKED", "TASK_BLOCKED", workflow, {
              blocked_tasks: blocked.map((job) => job.task_id),
            })
          }
          if (snapshot.every((job) => job.status === "DONE")) {
            workflow = loadWorkflow(projectRoot)
            if (workflow.phase === "INTEGRATION_TEST") continue
          }
          return finish("BLOCKED", "NO_RUNNABLE_JOBS", workflow, {
            scheduler_jobs: snapshot,
          })
        }

        batches += 1
        const settled = await Promise.allSettled(
          batch.map((job) => executeScheduledJob({
            taskID: job.task_id,
            requestedAgent: job.agent,
          }, context)),
        )
        let batchCompleted = 0
        for (let index = 0; index < settled.length; index += 1) {
          const outcome = settled[index]
          if (outcome.status === "fulfilled") {
            batchCompleted += 1
            completedJobs += 1
          } else {
            failures.push({
              job_id: batch[index].job_id,
              task_id: batch[index].task_id,
              error: outcome.reason?.message || String(outcome.reason),
            })
          }
        }
        workflow = loadWorkflow(projectRoot)
        workflow = recoverKnownSchedulerBlockers(workflow)
        const recoveredAfterBatch = [...recoveredInLastPass]
        if (batchCompleted === 0) {
          if (recoveredAfterBatch.length > 0) continue
          if (standardWorkflow(projectRoot) && noProgressPasses < 2) {
            noProgressPasses += 1
            continue
          }
          if (standardWorkflow(projectRoot)) {
            return finish("PAUSED", "AGENT_RETRY_EXHAUSTED", workflow)
          }
          return finish("BLOCKED", "DRIVER_NO_PROGRESS", workflow)
        }
        noProgressPasses = 0
        const scheduler = listSchedulerJobs(projectRoot, routing.agents).jobs
        const blocked = scheduler.filter((job) => job.status === "BLOCKED")
        if (blocked.length > 0 && policy.policy.stop_on_task_blocker) {
          return finish("BLOCKED", "TASK_BLOCKED", workflow, {
            blocked_tasks: blocked.map((job) => job.task_id),
          })
        }
      }
      workflow = loadWorkflow(projectRoot)
      return finish(
        standardWorkflow(projectRoot) ? "PAUSED" : "BLOCKED",
        "DRIVER_BATCH_LIMIT",
        workflow,
      )
    } catch (error) {
      workflow = loadWorkflow(projectRoot)
      if (/^Autopilot is (OFF|PAUSED|ON_IDLE|ARMED)/.test(error.message)) {
        return finish("PAUSED", "CONTROL_STOPPED", workflow)
      }
      failures.push({ job_id: null, task_id: null, error: error.message })
      return finish(
        standardWorkflow(projectRoot) ? "PAUSED" : "BLOCKED",
        "DRIVER_RUNTIME_ERROR",
        workflow,
      )
    }
  }

  return {
    config: async (config) => {
      defaultAgent = config.default_agent || defaultAgent
      config.agent ||= {}
      let routing = null
      try {
        routing = loadAppliedRouting()
      } catch {
        routing = null
      }
      for (const agent of AGENTS) {
        config.agent[agent] ||= {}
        if (routing) config.agent[agent].model = routing.agents[agent].primary
        if (agent !== "bx-director") {
          config.agent[agent].permission ||= {}
          config.agent[agent].permission.edit = agent === "bx-test"
            ? {
                "*": "deny",
                ".biexce/reports/**": "allow",
                "**/.biexce/reports/**": "allow",
              }
            : ["bx-explore", "bx-plan", "bx-code", "bx-fix"].includes(agent)
              ? "allow"
              : "deny"
          config.agent[agent].permission.biexce_submit_result = "allow"
          config.agent[agent].permission.biexce_run_command =
            MANAGED_COMMAND_AGENTS.has(agent) ? "allow" : "deny"
        }
      }
      config.agent['bx-director'].permission ||= {}
      config.agent['bx-director'].permission.biexce_delegate = 'allow'
      config.agent['bx-director'].permission.biexce_gate = 'allow'
      config.agent['bx-director'].permission.biexce_gate_approval = 'ask'
      config.agent['bx-director'].permission.biexce_drive = 'allow'
      config.agent['bx-director'].permission.biexce_run_next = 'allow'
      config.agent['bx-director'].permission.biexce_start_job = 'allow'
      config.agent['bx-director'].permission.biexce_job_status = 'allow'
      config.agent['bx-director'].permission.biexce_cancel_job = 'allow'
      config.agent['bx-director'].permission.biexce_resume_job = 'allow'
    },

    event: async ({ event }) => {
      if (!["permission.asked", "permission.updated"].includes(event.type)) return
      const request = event.properties || event.data
      const child = request?.sessionID
        ? activeChildren.get(request.sessionID) ||
          persistedChildPermissionContext(pluginDirectory, request.sessionID)
        : null
      const directorRoot = request?.sessionID
        ? directorSessions.get(request.sessionID)
        : null
      const permissionType = request?.type || request?.permission
      if ((!child && !directorRoot) || permissionType !== "edit") return

      let allowed = false
      const projectRoot = child?.projectRoot || directorRoot
      const writeScope = child?.writeScope || DIRECTOR_WRITE_SCOPE
      try {
        const targets = permissionMutationPaths(request, projectRoot)
        allowed = targets.length > 0 && targets.every((target) => child
          ? childWriteAllowed(child, target)
          : allowedByWriteScope(target, writeScope))
      } catch {
        allowed = false
      }

      // Legacy permission.updated events can collapse a multi-file patch to
      // an ambiguous "*" pattern before permission.asked publishes the exact
      // paths. Never reject that early event: approve only proven in-scope
      // requests and let OpenCode/tool.execute.before fail closed otherwise.
      if (!allowed) return
      try {
        await replyPermission(request, "once", projectRoot)
      } catch {
        // Keep the native OpenCode permission prompt available as a safe fallback.
      }
    },

    "permission.ask": async (input, output) => {
      const permissionType = input.type || input.permission
      if (permissionType === "biexce_gate_approval") {
        output.status = "ask"
        return
      }
      const child = input.sessionID
        ? activeChildren.get(input.sessionID) ||
          persistedChildPermissionContext(pluginDirectory, input.sessionID)
        : null
      const directorRoot = input.sessionID
        ? directorSessions.get(input.sessionID)
        : null
      if ((!child && !directorRoot) || permissionType !== "edit") return
      try {
        const projectRoot = child?.projectRoot || directorRoot
        const writeScope = child?.writeScope || DIRECTOR_WRITE_SCOPE
        const targets = permissionMutationPaths(input, projectRoot)
        output.status = targets.length > 0 && targets.every((target) => child
          ? childWriteAllowed(child, target)
          : allowedByWriteScope(target, writeScope)) ? "allow" : "deny"
      } catch {
        output.status = "deny"
      }
    },

    "tool.execute.before": async (input, output) => {
      const child = activeChildren.get(input.sessionID)
      const directorRoot = directorSessions.get(input.sessionID)
      if (!child && !directorRoot) return
      const projectRoot = child?.projectRoot || directorRoot
      const writeScope = child?.writeScope || DIRECTOR_WRITE_SCOPE
      if (Array.isArray(writeScope)) {
        const targets = schedulerMutationPaths(
          input.tool,
          output.args,
          projectRoot,
        )
        if (
          targets &&
          targets.some(
            (target) =>
              child
                ? !childWriteAllowed(child, target)
                : !allowedByWriteScope(target, writeScope),
          )
        ) {
          throw new Error(
            child
              ? "BIEXCE_SCHEDULER_WRITE_DENY: file is outside job write scope"
              : "BIEXCE_DIRECTOR_WRITE_DENY: Director may write only " +
                "PROJECT_BRIEF.md and FINAL_REPORT.md",
          )
        }
      }
      if (!["bash", "shell"].includes(input.tool)) return
      if (isLongLivedServerCommand(output.args?.command)) {
        throw new Error(
          "BIEXCE_AUTOPILOT_PROCESS_DENY: long-lived development servers are " +
          "not allowed inside an Autopilot task. Use an in-process TestClient, " +
          "a test runner-owned webServer, or a bounded command that exits.",
        )
      }
    },

    "shell.env": async (input, output) => {
      const child = input.sessionID ? activeChildren.get(input.sessionID) : null
      if (!child) return
      output.env.BIEXCE_AUTOPILOT = "1"
      output.env.BIEXCE_AGENT = child.agent
      output.env.BIEXCE_TASK_ID = child.taskID || ""
    },

    "chat.message": async (input) => {
      const agent = input.agent || defaultAgent
      if (!AGENTS.includes(agent)) return
      if (agent === "bx-director" && input.directory && input.sessionID) {
        const projectRoot = fs.realpathSync(input.directory)
        reconcileRuntimeState(projectRoot)
        loadRunningState(input.directory, input.sessionID, {
          allowSessionRebind: true,
        })
        directorSessions.set(input.sessionID, projectRoot)
        applyPendingRuntimeCommand(projectRoot, loadWorkflow(projectRoot))
      }
      const routing = loadAppliedRouting()
      if (!routing.agents[agent]?.primary) {
        throw new Error(`BIEXCE_MODEL_BLOCKED: ${agent} is unconfigured`)
      }
      if (!input.model) throw new Error("BIEXCE_MODEL_BLOCKED: actual model is unavailable")

    },

    tool: {
      biexce_drive: tool({
        description:
          "Run the full BIEXCE workflow from Explore and Plan through safe " +
          "DAG-ready execution, Integration Test and Review until a Human Gate, " +
          "pause/off, completion, or a real blocker.",
        args: {
          profile: tool.schema.enum([
            "auto",
            "fast",
            "standard",
            "critical",
            "advisory",
          ]),
          allow_critical_downgrade: tool.schema.boolean(),
        },
        async execute(args, context) {
          return driveScheduledWorkflow(args, context)
        },
      }),
      biexce_run_command: tool({
        description:
          "Run one bounded command under the BIEXCE supervisor. Output is capped, " +
          "timeout/cancel cleans the process tree, and persistent servers are denied.",
        args: {
          command: tool.schema.string().min(1).max(30000),
        },
        async execute(args, context) {
          const active = activeChildren.get(context.sessionID)
          if (!active || context.agent !== active.agent) {
            throw new Error("BIEXCE_COMMAND_DENY: no matching active child job")
          }
          if (!MANAGED_COMMAND_AGENTS.has(active.agent)) {
            throw new Error(
              `BIEXCE_COMMAND_DENY: ${active.agent} is an artifact/read-only role`,
            )
          }
          const projectRoot = fs.realpathSync(context.directory)
          if (projectRoot !== active.projectRoot) {
            throw new Error("BIEXCE_COMMAND_DENY: child command belongs to another project")
          }
          const timeoutMs = commandTimeoutMs()
          const result = await supervisor.runCommand({
            sessionID: context.sessionID,
            directory: projectRoot,
            command: args.command,
            timeoutMs,
            signal: context.abort,
            environment: {
              BIEXCE_AUTOPILOT: "1",
              BIEXCE_AGENT: active.agent,
              BIEXCE_TASK_ID: active.taskID || "",
              PYTHONDONTWRITEBYTECODE: "1",
            },
          })
          const output = [
            "EXIT_CODE: " + result.exit_code,
            "DURATION_MS: " + result.duration_ms,
            "OUTPUT_TRUNCATED: " + result.truncated,
            "STDOUT:",
            result.stdout,
            "STDERR:",
            result.stderr,
          ].join("\n")
          const evidence = commandEvidence.get(context.sessionID) || []
          const commandOutput = [result.stdout, result.stderr]
            .filter(Boolean)
            .join("\n")
            .replace(/\s+/g, " ")
            .trim()
          evidence.push({
            command: args.command.slice(0, 4000),
            exit_code: Number.isInteger(result.exit_code) ? result.exit_code : 1,
            status: result.exit_code === 0 ? "PASS" : "FAIL",
            output_summary: commandOutput.slice(0, 4000) ||
              `Command exited with code ${result.exit_code}.`,
          })
          commandEvidence.set(context.sessionID, evidence.slice(-100))
          return {
            title: active.agent + " managed command",
            output,
            metadata: {
              agent: active.agent,
              job_id: active.jobID,
              task_id: active.taskID,
              exit_code: result.exit_code,
              signal: result.signal,
              duration_ms: result.duration_ms,
              output_truncated: result.truncated,
              timeout_ms: timeoutMs,
            },
          }
        },
      }),
      biexce_submit_result: tool({
        description:
          "Submit one normalized, schema-validated result for the active BIEXCE " +
          "child job. The runtime supplies omitted non-security metadata and " +
          "ignores unknown reporting fields, but rejects invalid evidence, stale " +
          "identity and write-scope drift.",
        args: {
          result_json: tool.schema.string().min(2).max(200000),
        },
        async execute(args, context) {
          const active = activeChildren.get(context.sessionID)
          if (!active || context.agent !== active.agent) {
            throw new Error("BIEXCE_RESULT_DENY: no matching active child job")
          }
          if (submittedResults.has(context.sessionID)) {
            throw new Error("BIEXCE_RESULT_DENY: this child already submitted a result")
          }
          const projectRoot = fs.realpathSync(context.directory)
          if (projectRoot !== active.projectRoot) {
            throw new Error("BIEXCE_RESULT_DENY: child result belongs to another project")
          }
          const projectWorkflow = loadWorkflow(projectRoot)
          const workflow = active.scheduler
            ? {
                ...projectWorkflow,
                revision: active.workflowRevision,
                phase: active.phase,
                current_task_id: active.taskID,
              }
            : projectWorkflow
          let result
          try {
            result = validateAgentResult(args.result_json, active, workflow)
          } catch (error) {
            throw contractError(error.message)
          }
          submittedResults.set(context.sessionID, result)
          return {
            title: `${active.agent} result accepted`,
            output: "Structured result accepted by BIEXCE runtime.",
            metadata: {
              agent: active.agent,
              phase: workflow.phase,
              task_id: workflow.current_task_id,
              workflow_revision: workflow.revision,
              scheduler: Boolean(active.scheduler),
              status: result.status,
            },
          }
        },
      }),
      biexce_gate: tool({
        description:
          "Request explicit Human Gate approval inside OpenCode. Only BX Director " +
          "may call this at WAITING_GATE_1 or WAITING_GATE_2.",
        args: {
          gate: tool.schema.enum(["1", "2"]),
          summary: tool.schema.string().min(1).max(2000),
        },
        async execute(args, context) {
          if (context.agent !== "bx-director") {
            throw new Error("BIEXCE_GATE_DENY: only bx-director may request approval")
          }
          loadRunningState(context.directory, context.sessionID)
          const projectRoot = fs.realpathSync(context.directory)
          const gate = Number(args.gate)
          const expectedPhase = gate === 1 ? "WAITING_GATE_1" : "WAITING_GATE_2"
          let workflow = loadWorkflow(projectRoot)
          workflow = applyPendingRuntimeCommand(projectRoot, workflow)
          if (workflow.phase !== expectedPhase) {
            throw new Error(
              `BIEXCE_GATE_DENY: Gate ${gate} is invalid during ${workflow.phase}`,
            )
          }
          await context.ask({
            permission: "biexce_gate_approval",
            patterns: [`gate-${gate}:revision-${workflow.revision}`],
            always: [],
            metadata: {
              title: `BIEXCE Human Gate ${gate}`,
              gate,
              project: projectRoot,
              phase: workflow.phase,
              summary: args.summary,
            },
          })
          const control = loadRunningState(context.directory, context.sessionID)
          const current = loadWorkflow(projectRoot)
          if (
            current.phase !== workflow.phase ||
            current.revision !== workflow.revision
          ) {
            throw new Error("BIEXCE_GATE_DENY: workflow changed while awaiting approval")
          }
          const actor = `opencode-human:${context.sessionID}`
          const next = approveGateAtRuntime(projectRoot, current, gate, actor)
          let controlMode = control.mode
          if (gate === 2) {
            try {
              controlMode = stopControlAtRuntime(projectRoot, control).mode
            } catch (error) {
              atomicWriteJson(workflowPath(projectRoot), current)
              throw error
            }
          }
          return {
            title: `Human Gate ${gate} approved`,
            output:
              gate === 1
                ? `Gate 1 approved. Continue with ${PHASE_AGENTS[next.phase] || "the next task"}.`
                : "Gate 2 approved. Workflow is complete and Autopilot is OFF.",
            metadata: {
              gate,
              approved: true,
              next_phase: next.phase,
              next_agent: gate === 1
                ? "biexce scheduler"
                : PHASE_AGENTS[next.phase] || null,
              control_mode: controlMode,
            },
          }
        },
      }),
      biexce_run_next: tool({
        description:
          "Run the next DAG-ready task phase through the BIEXCE scheduler. " +
          "Use task_id=auto for the highest-priority ready task.",
        args: {
          task_id: tool.schema.string().min(3).max(16),
        },
        async execute(args, context) {
          const taskID = args.task_id === "auto" ? null : args.task_id
          if (taskID !== null && !/^t-[0-9]{3}$/.test(taskID)) {
            throw new Error("BIEXCE_SCHEDULER_DENY: task_id must be auto or t-NNN")
          }
          return executeScheduledJob({ taskID }, context)
        },
      }),
      biexce_start_job: tool({
        description:
          "Start one exact scheduler task/capability. Independent calls may run " +
          "in parallel when DAG, write scope, WIP and model quota all allow it.",
        args: {
          task_id: tool.schema.string().min(5).max(5),
          capability: tool.schema.enum([
            "bx-code",
            "bx-test",
            "bx-fix",
            "bx-review",
          ]),
        },
        async execute(args, context) {
          if (!/^t-[0-9]{3}$/.test(args.task_id)) {
            throw new Error("BIEXCE_SCHEDULER_DENY: task_id must match t-NNN")
          }
          return executeScheduledJob({
            taskID: args.task_id,
            requestedAgent: args.capability,
          }, context)
        },
      }),
      biexce_job_status: tool({
        description:
          "Read scheduler and persistent job-board state for one BIEXCE job.",
        args: {
          job_id: tool.schema.string().min(5).max(240),
        },
        async execute(args, context) {
          if (context.agent !== "bx-director") {
            throw new Error("BIEXCE_SCHEDULER_DENY: only bx-director may inspect jobs")
          }
          loadRunningState(context.directory, context.sessionID)
          const projectRoot = fs.realpathSync(context.directory)
          const routing = loadAppliedRouting()
          const scheduled = schedulerJob(
            projectRoot,
            args.job_id,
            routing.agents,
          )
          const persisted = loadJobBoard(projectRoot).jobs[args.job_id] || null
          if (!scheduled && !persisted) {
            throw new Error("BIEXCE_SCHEDULER_UNKNOWN_JOB: " + args.job_id)
          }
          return {
            title: "BIEXCE job " + args.job_id,
            output: JSON.stringify({ scheduler: scheduled, job: persisted }, null, 2),
            metadata: {
              job_id: args.job_id,
              scheduler_status: scheduled?.status || null,
              runtime_status: persisted?.status || null,
              task_id: scheduled?.task_id || persisted?.task_id || null,
              agent: scheduled?.agent || persisted?.agent || null,
              model: persisted?.model || scheduled?.model || null,
            },
          }
        },
      }),
      biexce_cancel_job: tool({
        description:
          "Cancel one active scheduler child session owned by this OpenCode runtime.",
        args: {
          job_id: tool.schema.string().min(5).max(240),
          reason: tool.schema.string().min(1).max(500),
        },
        async execute(args, context) {
          if (context.agent !== "bx-director") {
            throw new Error("BIEXCE_SCHEDULER_DENY: only bx-director may cancel jobs")
          }
          loadRunningState(context.directory, context.sessionID)
          const projectRoot = fs.realpathSync(context.directory)
          const active = [...activeChildren.entries()].find(
            ([, value]) =>
              value.scheduler &&
              value.projectRoot === projectRoot &&
              value.jobID === args.job_id,
          )
          if (!active) {
            throw new Error(
              "BIEXCE_SCHEDULER_NOT_OWNED: active job is not in this runtime",
            )
          }
          await supervisor.cancelSession(
            active[0],
            "CANCELLED",
            args.reason,
          )
          return {
            title: "BIEXCE job cancellation requested",
            output:
              args.job_id + " is aborting; scheduler state will return to READY.",
            metadata: {
              job_id: args.job_id,
              task_id: active[1].taskID,
              agent: active[1].agent,
              cancelled: true,
            },
          }
        },
      }),
      biexce_resume_job: tool({
        description:
          "Resume a retryable, timed-out or cancelled scheduler job from its " +
          "persistent task/session state.",
        args: {
          job_id: tool.schema.string().min(5).max(240),
        },
        async execute(args, context) {
          if (context.agent !== "bx-director") {
            throw new Error("BIEXCE_SCHEDULER_DENY: only bx-director may resume jobs")
          }
          const projectRoot = fs.realpathSync(context.directory)
          const routing = loadAppliedRouting()
          const persisted = loadJobBoard(projectRoot).jobs[args.job_id]
          if (
            !persisted ||
            !["RETRYING", "TIMED_OUT", "CANCELLED", "FAILED"].includes(
              persisted.status,
            )
          ) {
            throw new Error(
              "BIEXCE_SCHEDULER_RESUME_DENY: job is not resumable",
            )
          }
          const scheduled = schedulerJob(
            projectRoot,
            args.job_id,
            routing.agents,
          )
          if (!scheduled?.task_id || !scheduled?.agent) {
            throw new Error(
              "BIEXCE_SCHEDULER_RESUME_DENY: scheduler task is unavailable",
            )
          }
          return executeScheduledJob({
            taskID: scheduled.task_id,
            requestedAgent: scheduled.agent,
          }, context)
        },
      }),
      biexce_delegate: tool({
        description:
          "Delegate exactly one BIEXCE Autopilot task. Fails closed unless the " +
          "current agent is bx-director and project state is RUNNING.",
        args: {
          agent: tool.schema.enum(CHILD_ALLOWLIST),
          description: tool.schema.string().min(1).max(120),
          prompt: tool.schema.string().min(1).max(30000),
        },
        execute: executeWorkflowDelegation = async (args, context) => {
          if (context.agent !== "bx-director") {
            throw new Error("BIEXCE_AUTOPILOT_DENY: only bx-director may delegate")
          }
          loadRunningState(context.directory, context.sessionID)
          const projectRoot = fs.realpathSync(context.directory)
          reconcileRuntimeState(projectRoot)
          let workflow = loadWorkflow(projectRoot)
          workflow = applyPendingRuntimeCommand(projectRoot, workflow)
          const expectedAgent = PHASE_AGENTS[workflow.phase]
          if (!expectedAgent) {
            throw new Error(
              `BIEXCE_AUTOPILOT_GATE: workflow is ${workflow.phase}; no delegation is allowed`,
            )
          }
          if (args.agent !== expectedAgent) {
            throw new Error(
              `BIEXCE_AUTOPILOT_ORDER: ${workflow.phase} requires ${expectedAgent}, not ${args.agent}`,
            )
          }
          requirePhaseInput(projectRoot, workflow)
          const timeoutMs = delegationTimeoutMs()
          let jobLease = null
          let jobID = null
          let jobOwned = false
          let projectSnapshot = null
          let fileSnapshot = null
          let childID = null
          let transitionCommitted = false
          let jobCompleted = false
          let binding = null
          let usedModel = null
          let attemptCount = 0
          let sessionResumed = false
          try {
            const routing = loadAppliedRouting()
            binding = routing.agents[args.agent]
            if (!binding?.primary) {
              throw new Error(`BIEXCE_MODEL_BLOCKED: ${args.agent} is unconfigured`)
            }
            const job = registerWorkflowJob(
              projectRoot, workflow, args.agent, binding.primary,
            )
            requireWorkflowJobLaunchable(job)
            jobID = job.job_id
            jobLease = acquireJobLease(
              projectRoot, jobID, context.sessionID, timeoutMs,
            )
            jobOwned = true
            putJob(projectRoot, {
              job_id: jobID,
              status: "RUNNING",
              session_id: context.sessionID,
              started_at_utc: new Date().toISOString(),
              deadline_at_utc: jobLease.deadline_at_utc,
              completed_at_utc: null,
              result_status: null,
              error: null,
            })
            projectSnapshot = beginTaskDelegation(projectRoot, workflow)
            const previousSession = resumableSession(
              projectRoot,
              jobID,
              args.agent,
            )
            if (
              previousSession &&
              await sessionCanResume(client, previousSession, context.directory)
            ) {
              childID = previousSession.session_id
              attemptCount = previousSession.attempt
              sessionResumed = true
            } else {
              if (previousSession) {
                putSessionRecord(projectRoot, {
                  job_id: jobID,
                  status: "FAILED",
                  last_error: "Stored child session is unavailable",
                })
              }
              const created = resultData(
                await client.session.create({
                  body: {
                    parentID: context.sessionID,
                    title: childSessionTitle({
                      agent: args.agent,
                      phase: workflow.phase,
                      taskId: workflow.current_task_id,
                    }),
                  },
                  query: { directory: context.directory },
                }),
                "child session creation",
              )
              childID = created.id
            }
            putSessionRecord(projectRoot, {
              job_id: jobID,
              session_id: childID,
              parent_session_id: context.sessionID,
              agent: args.agent,
              model: binding.primary,
              status: "ACTIVE",
              attempt: Math.max(1, attemptCount || 1),
              last_error: null,
            })
            putJob(projectRoot, {
              job_id: jobID,
              session_id: childID,
              attempt: Math.max(1, attemptCount || 1),
            })
            fileSnapshot = loadOrCreateJobBaseline(projectRoot, jobID)
            activeChildren.set(childID, {
              agent: args.agent,
              jobID,
              model: binding.primary,
              attempt: Math.max(1, attemptCount || 1),
              projectRoot,
              taskID: workflow.current_task_id,
              phase: workflow.phase,
              workflowRevision: workflow.revision,
              scheduler: false,
              writeScope: writablePatterns(projectRoot, workflow),
            })
            context.metadata?.(observabilityUpdate({
              parentSessionId: context.sessionID,
              sessionId: childID,
              jobId: jobID,
              agent: args.agent,
              phase: workflow.phase,
              taskId: workflow.current_task_id,
              status: "RUNNING",
              configuredModel: binding.primary,
              attempt: Math.max(1, attemptCount || 1),
              sessionResumed,
            }))
            loadRunningState(context.directory, context.sessionID)
            const attemptOffset = sessionResumed ? attemptCount : 0
            const configuredCandidates = runtimeModels(binding)
            const resumedModelIndex = sessionResumed
              ? configuredCandidates.findIndex(
                  (candidate) => candidate.model === previousSession.model,
                )
              : -1
            const runtimeCandidates = resumedModelIndex > 0
              ? configuredCandidates.slice(resumedModelIndex)
              : configuredCandidates
            const promptOutcome = await executeWithRetry({
              candidates: runtimeCandidates,
              retriesPerModel: transportRetries(),
              backoffMs: retryBackoffMs(),
              execute: async ({ model, zone, fallback, attempt: runtimeAttempt }) => {
                const attempt = attemptOffset + runtimeAttempt
                usedModel = model
                attemptCount = attempt
                submittedResults.delete(childID)
                commandEvidence.delete(childID)
                const active = activeChildren.get(childID)
                if (active) {
                  active.model = model
                  active.attempt = attempt
                }
                putJob(projectRoot, {
                  job_id: jobID,
                  status: "RUNNING",
                  model,
                  attempt,
                  error: null,
                })
                putSessionRecord(projectRoot, {
                  job_id: jobID,
                  model,
                  status: "ACTIVE",
                  attempt,
                  last_error: null,
                })
                context.metadata?.(observabilityUpdate({
                  parentSessionId: context.sessionID,
                  sessionId: childID,
                  jobId: jobID,
                  agent: args.agent,
                  phase: workflow.phase,
                  taskId: workflow.current_task_id,
                  status: fallback
                    ? "FALLBACK"
                    : attempt > 1 ? "RETRYING" : "RUNNING",
                  configuredModel: binding.primary,
                  actualModel: model,
                  modelZone: zone,
                  attempt,
                  fallbackUsed: fallback,
                  sessionResumed,
                }))
                return resultData(await supervisor.supervisePrompt({
                  childID,
                  directory: context.directory,
                  timeoutMs,
                  signal: context.abort,
                  controlCheck: () =>
                    loadRunningState(projectRoot, context.sessionID),
                  pollMs: controlPollMs(),
                  body: {
                    agent: args.agent,
                    model: splitModel(model),
                    parts: [{
                      type: "text",
                      text: [
                        args.prompt,
                        "",
                        "[BIEXCE JOB SCOPE]",
                        "write_scope=" + JSON.stringify(job.write_scope),
                        "read_scope=" + JSON.stringify(job.read_scope),
                        "Files outside write_scope are read-only.",
                        "",
                        "[BIEXCE RUNTIME CONTRACT]",
                        runtimeContract(workflow, args.agent),
                      ].join("\n"),
                    }],
                  },
                }), "child session prompt")
              },
              onRetry: async ({ model, attempt: runtimeAttempt, kind, error }) => {
                const attempt = attemptOffset + runtimeAttempt
                putJob(projectRoot, {
                  job_id: jobID,
                  status: "RETRYING",
                  model,
                  attempt,
                  error: `${kind}: ${error.message}`,
                })
                putSessionRecord(projectRoot, {
                  job_id: jobID,
                  model,
                  status: "RETRYING",
                  attempt,
                  last_error: `${kind}: ${error.message}`,
                })
              },
              onFallback: async ({ to, attempt: runtimeAttempt, kind, error }) => {
                const attempt = attemptOffset + runtimeAttempt
                putJob(projectRoot, {
                  job_id: jobID,
                  status: "FALLBACK",
                  model: to.model,
                  attempt,
                  error: `${kind}: ${error.message}`,
                })
                putSessionRecord(projectRoot, {
                  job_id: jobID,
                  model: to.model,
                  status: "RETRYING",
                  attempt,
                  last_error: `${kind}: ${error.message}`,
                })
              },
            })
            const response = promptOutcome.value
            usedModel = promptOutcome.model
            attemptCount = attemptOffset + promptOutcome.attempt
            const output = response.parts
              .filter((part) => part.type === "text")
              .map((part) => part.text)
              .join("\n")
            const currentWorkflow = loadWorkflow(projectRoot)
            if (
              currentWorkflow.revision !== workflow.revision ||
              currentWorkflow.phase !== workflow.phase
            ) {
              throw new Error("workflow changed while the child session was running")
            }
            const resolvedSubmission = resolveChildResult({
              childID,
              projectRoot,
              workflow,
              output,
              before: fileSnapshot,
              activeChildren,
              submittedResults,
              commandEvidence,
            })
            const submission = resolvedSubmission.result
            verifyResultFiles(projectRoot, workflow, submission, fileSnapshot)
            recordJobResult(
              projectRoot,
              jobID,
              submission,
              resolvedSubmission.source,
            )
            if (
              workflow.phase === "INTEGRATION_TEST" &&
              submission.status === "PASS"
            ) {
              persistIntegrationReport(projectRoot, submission)
            }
            if (
              workflow.phase === "INTEGRATION_REVIEW" &&
              ["APPROVE", "APPROVE_WITH_MINOR_NOTES"].includes(
                submission.status,
              )
            ) {
              persistFinalReport(projectRoot, submission)
            }
            const nextWorkflow = advanceWorkflow(
              projectRoot,
              workflow,
              args.agent,
              submission,
            )
            transitionCommitted = true
            putJob(projectRoot, {
              job_id: jobID,
              status: "COMPLETED",
              session_id: childID,
              model: usedModel,
              attempt: attemptCount,
              completed_at_utc: new Date().toISOString(),
              result_status: submission.status,
              error: null,
            })
            putSessionRecord(projectRoot, {
              job_id: jobID,
              model: usedModel,
              status: "COMPLETED",
              attempt: attemptCount,
              last_error: null,
            })
            jobCompleted = true
            removeJobBaseline(projectRoot, jobID)
            projectSnapshot = null
            context.metadata?.(observabilityUpdate({
              parentSessionId: context.sessionID,
              sessionId: childID,
              jobId: jobID,
              agent: args.agent,
              phase: workflow.phase,
              taskId: workflow.current_task_id,
              status: "DONE",
              configuredModel: binding.primary,
              actualModel: usedModel,
              attempt: attemptCount,
              fallbackUsed: usedModel !== binding.primary,
              sessionResumed,
              nextPhase: nextWorkflow.phase,
              nextAgent: PHASE_AGENTS[nextWorkflow.phase] || null,
              resultStatus: submission.status,
              resultSource: resolvedSubmission.source,
              usage: responseUsage(response),
              evidence: submission.artifacts,
            }))
            return {
              title: `${args.agent}: ${args.description}`,
              output: output || "Child completed without a text response.",
              metadata: {
                parentSessionId: context.sessionID,
                sessionId: childID,
                child_session_id: childID,
                job_id: jobID,
                agent: args.agent,
                configured_model: binding.primary,
                fallbacks: binding.fallbacks,
                actual_model: usedModel,
                fallback_used: usedModel !== binding.primary,
                attempt_count: attemptCount,
                session_resumed: sessionResumed,
                completed_phase: workflow.phase,
                next_phase: nextWorkflow.phase,
                next_agent: PHASE_AGENTS[nextWorkflow.phase] || null,
                current_task_id: nextWorkflow.current_task_id,
                fix_round: nextWorkflow.fix_round,
                result: submission,
                result_source: resolvedSubmission.source,
              },
            }
          } catch (error) {
            const errorKind = error.biexceKind || classifyRuntimeError(error)
            const cancelled =
              errorKind === "CANCELLED" ||
              ["CANCELLED", "CONTROL_STOPPED"].includes(error.code)
            const timedOut = [
              "TIMEOUT",
              "COMMAND_TIMEOUT",
            ].includes(error.code)
            const recoverable = isFallbackKind(errorKind)
            recordFailurePolicyShadow(projectRoot, {
              error,
              jobID,
              taskID: workflow.current_task_id,
              phase: workflow.phase,
              legacyDisposition: recoverable ? "RETRY" : "BLOCK",
              fixRound: workflow.fix_round,
            })
            context.metadata?.(observabilityUpdate({
              parentSessionId: context.sessionID,
              sessionId: childID,
              jobId: jobID,
              agent: args.agent,
              phase: workflow.phase,
              taskId: workflow.current_task_id,
              status: timedOut
                ? "TIMED_OUT"
                : cancelled ? "CANCELLED" : "ERROR",
              configuredModel: binding?.primary || null,
              actualModel: usedModel,
              attempt: Math.max(1, attemptCount || 1),
              sessionResumed,
              errorCode: error.code || null,
              errorKind,
            }))
            if (projectSnapshot !== null) {
              saveProjectState(projectRoot, projectSnapshot)
            }
            if (transitionCommitted && !jobCompleted) {
              atomicWriteJson(workflowPath(projectRoot), workflow)
            }
            if (jobOwned && !jobCompleted) {
              try {
                const failureStatus = timedOut
                  ? "TIMED_OUT"
                  : cancelled
                    ? "CANCELLED"
                    : recoverable
                      ? "RETRYING"
                      : "FAILED"
                putJob(projectRoot, {
                  job_id: jobID,
                  status: failureStatus,
                  model: usedModel || binding?.primary || null,
                  attempt: Math.max(1, attemptCount || 1),
                  completed_at_utc:
                    recoverable ? null : new Date().toISOString(),
                  error: `${errorKind}: ${error.message}`,
                })
                if (childID !== null) {
                  putSessionRecord(projectRoot, {
                    job_id: jobID,
                    model: usedModel || binding.primary,
                    status:
                      cancelled || timedOut
                        ? "CANCELLED"
                        : recoverable
                          ? "RETRYING"
                          : "FAILED",
                    attempt: Math.max(1, attemptCount || 1),
                    last_error: `${errorKind}: ${error.message}`,
                  })
                }
              } catch {
                // Preserve the original runtime error if job persistence also fails.
              }
            }
            if (jobOwned && !recoverable && errorKind === "CONTRACT") {
              try {
                saveWorkflow(projectRoot, workflow, {
                  phase: "BLOCKED",
                  blocked_reason:
                    `Terminal ${errorKind} failure in ${jobID}: ${error.message}`,
                  last_agent: args.agent,
                  last_result: "CONTRACT_FAILED",
                })
                removeJobBaseline(projectRoot, jobID)
              } catch {
                // Preserve the original contract error if terminal persistence fails.
              }
            }
            if (jobOwned && !jobCompleted && standardWorkflow(projectRoot)) {
              try {
                removeJobBaseline(projectRoot, jobID)
              } catch {
                // A stale baseline is non-authoritative in standard recovery.
              }
            }
            const wrapped = new Error(
              `BIEXCE_AUTOPILOT_ERROR [${errorKind}]: ${error.message}`,
            )
            wrapped.code = error.code
            wrapped.biexceKind = errorKind
            throw wrapped
          } finally {
            if (childID !== null) {
              await supervisor.closeSession(childID)
              activeChildren.delete(childID)
              submittedResults.delete(childID)
              commandEvidence.delete(childID)
            }
            if (jobLease !== null) releaseJobLease(projectRoot, jobLease)
          }
        },
      }),
    },
  }
}
