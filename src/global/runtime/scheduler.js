import crypto from "node:crypto"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

import {
  classifyFailure,
  FAILURE_ACTIONS,
} from "./failure-policy.js"
import {
  loadJobBoard,
  taskRecoveryHistory,
} from "./job-board.js"
import {
  generatedRuntimePath,
  protectedProjectPath,
  runtimeScopeErrorPaths,
  scopeFailure,
  SCOPE_FAILURES,
} from "./scope-policy.js"


export const SCHEDULER_SCHEMA =
  "https://schemas.biexce.local/runtime/scheduler-state-v1.schema.json"

const ROOT_KEYS = new Set([
  "$schema",
  "schema_version",
  "project_root",
  "revision",
  "wip_limit",
  "local_concurrency",
  "cloud_concurrency",
  "read_only_concurrency",
  "tasks",
  "updated_at_utc",
])

const TASK_KEYS = new Set([
  "task_id",
  "title",
  "phase",
  "status",
  "dependencies",
  "read_scope",
  "write_scope",
  "fix_round",
  "active_job_id",
  "last_job_id",
  "agent",
  "model",
  "last_result",
  "error",
  "updated_at_utc",
])

const PHASES = new Set([
  "CODE",
  "TEST",
  "FIX",
  "TASK_REVIEW",
  "DONE",
  "BLOCKED",
])

const STATUSES = new Set([
  "BACKLOG",
  "READY",
  "RUNNING",
  "DONE",
  "BLOCKED",
])

const ACTIVE_PROJECT_STATUSES = new Set([
  "planning",
  "coding",
  "testing",
  "fixing",
  "reviewing",
])

const PHASE_AGENTS = {
  CODE: "bx-code",
  TEST: "bx-test",
  FIX: "bx-fix",
  TASK_REVIEW: "bx-review",
}


function exactKeys(value, expected) {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).length === expected.size &&
    Object.keys(value).every((key) => expected.has(key))
}


function stateRoot(projectRoot) {
  return path.join(projectRoot, ".biexce", "state")
}


export function schedulerStatePath(projectRoot) {
  return path.join(stateRoot(projectRoot), "AUTOPILOT_SCHEDULER.json")
}


function schedulerLockPath(projectRoot) {
  return path.join(stateRoot(projectRoot), "AUTOPILOT_SCHEDULER.lock")
}


function atomicWrite(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const temporary =
    file + "." + process.pid + "." + crypto.randomUUID() + ".tmp"
  try {
    fs.writeFileSync(temporary, value, {
      encoding: "utf8",
      mode: 0o600,
      flag: "wx",
    })
    fs.renameSync(temporary, file)
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary)
  }
}


function readRegularJson(file, label) {
  const stat = fs.lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error(label + " is not a regular file")
  }
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"))
  } catch (error) {
    throw new Error(label + " is invalid JSON: " + error.message)
  }
}


function processAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false
  try {
    process.kill(pid, 0)
    return true
  } catch (error) {
    return error?.code === "EPERM"
  }
}


function sleepSync(milliseconds) {
  const signal = new Int32Array(new SharedArrayBuffer(4))
  Atomics.wait(signal, 0, 0, milliseconds)
}


function withSchedulerLock(projectRoot, callback) {
  const file = schedulerLockPath(projectRoot)
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const token = crypto.randomUUID()
  const acquire = () => {
    const descriptor = fs.openSync(file, "wx", 0o600)
    try {
      fs.writeFileSync(descriptor, JSON.stringify({
        token,
        pid: process.pid,
        host: os.hostname(),
        acquired_at_utc: new Date().toISOString(),
      }) + "\n", "utf8")
    } finally {
      fs.closeSync(descriptor)
    }
  }
  const deadline = Date.now() + 5000
  while (true) {
    try {
      acquire()
      break
    } catch (error) {
      if (error?.code !== "EEXIST") throw error
      let stale = false
      try {
        const lock = readRegularJson(file, "BIEXCE scheduler lock")
        const age = Date.now() - Date.parse(lock.acquired_at_utc)
        stale = !Number.isFinite(age) || age > 30000 ||
          (lock.host === os.hostname() && !processAlive(lock.pid))
      } catch {
        try {
          stale = Date.now() - fs.lstatSync(file).mtimeMs > 30000
        } catch {
          stale = false
        }
      }
      if (stale) {
        try {
          fs.unlinkSync(file)
        } catch (unlinkError) {
          if (unlinkError?.code !== "ENOENT") throw unlinkError
        }
        continue
      }
      if (Date.now() >= deadline) {
        throw new Error("BIEXCE_SCHEDULER_BUSY: state lock timeout")
      }
      sleepSync(10)
    }
  }
  try {
    return callback()
  } finally {
    try {
      const current = readRegularJson(file, "BIEXCE scheduler lock")
      if (current.token === token) fs.unlinkSync(file)
    } catch {
      // A stale owner must never remove a replacement lock.
    }
  }
}


function normalizeRelative(value, label) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(label + " must be a non-empty project-relative path")
  }
  const trimmed = value.trim()
  const inlineCode = trimmed.match(/^(`+)([\s\S]*?)\1$/)
  const portable = (inlineCode ? inlineCode[2].trim() : trimmed)
    .replaceAll(String.fromCharCode(92), "/")
    .replace(/^\.\//, "")
  if (
    portable === "." ||
    path.posix.isAbsolute(portable) ||
    /^[A-Za-z]:\//.test(portable) ||
    portable.split("/").includes("..")
  ) {
    throw new Error(label + " escapes the project root: " + value)
  }
  return portable
}


function markdownField(text, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const match = text.match(new RegExp("^" + escaped + ":\\s*(.+?)\\s*$", "im"))
  return match ? match[1].trim() : null
}


function parseListField(text, name) {
  const raw = markdownField(text, name)
  if (!raw || raw.toLowerCase() === "none") return []
  return raw.split(",").map((value) => normalizeRelative(value, name))
}


function taskContract(projectRoot, taskID) {
  const file = path.join(projectRoot, ".biexce", "tasks", taskID + ".md")
  const text = fs.readFileSync(file, "utf8")
  const dependencies = (
    markdownField(text, "Depends on")?.match(/t-[0-9]{3}/g) || []
  )
  return {
    owner: markdownField(text, "Owner role"),
    dependencies: [...new Set(dependencies)],
    read_scope: [
      ".biexce/PROJECT_BRIEF.md",
      ".biexce/MASTER_PLAN.md",
      ".biexce/tasks/" + taskID + ".md",
      ...parseListField(text, "Read-only inputs"),
    ].filter((value, index, values) => values.indexOf(value) === index),
    write_scope: parseListField(text, "Writable files"),
  }
}


function isManagedReportScope(value) {
  const portable = String(value || "").replaceAll("\\", "/")
  return portable.startsWith(".biexce/reports/") &&
    !portable.split("/").includes("..")
}


function isVerificationOnlyContract(contract) {
  return contract.owner === "bx-test" &&
    contract.write_scope.every(isManagedReportScope)
}


function initialTaskPhase(contract) {
  // Verification-only stories belong to BX Test. They may be fully read-only
  // or own only runtime-managed evidence under .biexce/reports/**. They must
  // never be routed through BX Code merely to reach TEST.
  if (isVerificationOnlyContract(contract)) {
    return "TEST"
  }
  return "CODE"
}


function planWipLimit(projectRoot) {
  const text = fs.readFileSync(
    path.join(projectRoot, ".biexce", "MASTER_PLAN.md"),
    "utf8",
  )
  const value = Number(markdownField(text, "WIP limit"))
  if (!Number.isInteger(value) || value < 1 || value > 4) {
    throw new Error("MASTER_PLAN WIP limit must be between 1 and 4")
  }
  return value
}


function validateTask(task, taskID) {
  if (!exactKeys(task, TASK_KEYS) || task.task_id !== taskID) {
    throw new Error("scheduler task properties mismatch: " + taskID)
  }
  if (
    !/^t-[0-9]{3}$/.test(task.task_id) ||
    typeof task.title !== "string" || !task.title ||
    !PHASES.has(task.phase) ||
    !STATUSES.has(task.status) ||
    !Array.isArray(task.dependencies) ||
    !task.dependencies.every((value) => /^t-[0-9]{3}$/.test(value)) ||
    !Array.isArray(task.read_scope) ||
    !task.read_scope.every((value) => typeof value === "string" && value) ||
    !Array.isArray(task.write_scope) ||
    !task.write_scope.every((value) => typeof value === "string" && value) ||
    !Number.isInteger(task.fix_round) || task.fix_round < 0 ||
    !(task.active_job_id === null || typeof task.active_job_id === "string") ||
    !(task.last_job_id === null || typeof task.last_job_id === "string") ||
    !(task.agent === null || typeof task.agent === "string") ||
    !(task.model === null || typeof task.model === "string") ||
    !(task.last_result === null || typeof task.last_result === "string") ||
    !(task.error === null || typeof task.error === "string") ||
    typeof task.updated_at_utc !== "string"
  ) {
    throw new Error("scheduler task is invalid: " + taskID)
  }
  if (
    task.status === "RUNNING" &&
    (!task.active_job_id || !task.agent || !task.model)
  ) {
    throw new Error("running scheduler task lacks job ownership: " + taskID)
  }
  return task
}


function validateState(state, projectRoot) {
  if (!exactKeys(state, ROOT_KEYS)) {
    throw new Error("scheduler state properties mismatch")
  }
  if (
    state.$schema !== SCHEDULER_SCHEMA ||
    state.schema_version !== 1 ||
    path.resolve(state.project_root) !== path.resolve(projectRoot) ||
    !Number.isInteger(state.revision) || state.revision < 0 ||
    !Number.isInteger(state.wip_limit) ||
    state.wip_limit < 1 || state.wip_limit > 4 ||
    !Number.isInteger(state.local_concurrency) ||
    state.local_concurrency < 1 || state.local_concurrency > 8 ||
    !Number.isInteger(state.cloud_concurrency) ||
    state.cloud_concurrency < 1 || state.cloud_concurrency > 16 ||
    !Number.isInteger(state.read_only_concurrency) ||
    state.read_only_concurrency < 1 || state.read_only_concurrency > 16 ||
    state.tasks === null || typeof state.tasks !== "object" ||
    Array.isArray(state.tasks) ||
    typeof state.updated_at_utc !== "string"
  ) {
    throw new Error("scheduler state schema invalid")
  }
  for (const [taskID, task] of Object.entries(state.tasks)) {
    validateTask(task, taskID)
  }
  return state
}


function readProjectState(projectRoot) {
  return readRegularJson(
    path.join(projectRoot, ".biexce", "state", "PROJECT_STATE.json"),
    "BIEXCE project state",
  )
}


function initialState(projectRoot, options) {
  const project = readProjectState(projectRoot)
  if (!Array.isArray(project.tasks) || project.tasks.length < 1) {
    throw new Error("PROJECT_STATE tasks are missing")
  }
  const now = new Date().toISOString()
  const tasks = {}
  for (const source of project.tasks) {
    if (!/^t-[0-9]{3}$/.test(source.id)) {
      throw new Error("PROJECT_STATE task id is invalid")
    }
    const contract = taskContract(projectRoot, source.id)
    const done = source.status === "done"
    tasks[source.id] = {
      task_id: source.id,
      title: source.title,
      phase: done ? "DONE" : initialTaskPhase(contract),
      status: done ? "DONE" : "BACKLOG",
      dependencies: contract.dependencies,
      read_scope: contract.read_scope,
      write_scope: contract.write_scope,
      fix_round: Number.isInteger(source.round) ? source.round : 0,
      active_job_id: null,
      last_job_id: null,
      agent: null,
      model: null,
      last_result: null,
      error: null,
      updated_at_utc: now,
    }
  }
  return validateState({
    $schema: SCHEDULER_SCHEMA,
    schema_version: 1,
    project_root: fs.realpathSync(projectRoot),
    revision: 0,
    wip_limit: planWipLimit(projectRoot),
    local_concurrency: options.localConcurrency,
    cloud_concurrency: options.cloudConcurrency,
    read_only_concurrency: options.readOnlyConcurrency,
    tasks,
    updated_at_utc: now,
  }, projectRoot)
}


function loadUnlocked(projectRoot, options = null) {
  const root = fs.realpathSync(projectRoot)
  const file = schedulerStatePath(root)
  if (!fs.existsSync(file)) {
    if (!options) throw new Error("BIEXCE scheduler is not initialized")
    const state = initialState(root, options)
    atomicWrite(file, JSON.stringify(state, null, 2) + "\n")
    return state
  }
  return validateState(readRegularJson(file, "BIEXCE scheduler state"), root)
}


function saveUnlocked(projectRoot, state) {
  const root = fs.realpathSync(projectRoot)
  const next = validateState({
    ...state,
    revision: state.revision + 1,
    updated_at_utc: new Date().toISOString(),
  }, root)
  atomicWrite(
    schedulerStatePath(root),
    JSON.stringify(next, null, 2) + "\n",
  )
  return next
}


export function initializeScheduler(projectRoot, options) {
  const root = fs.realpathSync(projectRoot)
  return withSchedulerLock(root, () => loadUnlocked(root, options))
}


export function loadSchedulerState(projectRoot) {
  const root = fs.realpathSync(projectRoot)
  return loadUnlocked(root)
}


export function phaseAgent(phase) {
  const agent = PHASE_AGENTS[phase]
  if (!agent) throw new Error("scheduler phase has no agent: " + phase)
  return agent
}


function modelZone(model) {
  return model.startsWith("biexce-local/") ? "local" : "cloud"
}


function staticPrefix(pattern) {
  const wildcard = pattern.search(/[*?[]/)
  return wildcard < 0 ? pattern : pattern.slice(0, wildcard)
}


function globRegex(pattern) {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&")
  const doubleStar = "__DOUBLE_STAR__"
  return new RegExp(
    "^" +
    escaped
      .replaceAll("**", doubleStar)
      .replaceAll("*", "[^/]*")
      .replaceAll("?", "[^/]")
      .replaceAll(doubleStar, ".*") +
    "$",
  )
}


function scopeOverlap(left, right) {
  if (left === right || left === "**" || right === "**") return true
  if (!left.includes("*") && !left.includes("?") && globRegex(right).test(left)) {
    return true
  }
  if (!right.includes("*") && !right.includes("?") && globRegex(left).test(right)) {
    return true
  }
  const leftPrefix = staticPrefix(left)
  const rightPrefix = staticPrefix(right)
  if (!leftPrefix || !rightPrefix) return true
  return leftPrefix.startsWith(rightPrefix) || rightPrefix.startsWith(leftPrefix)
}


function writeScopesConflict(left, right) {
  if (left.length === 0 || right.length === 0) return false
  return left.some((one) => right.some((two) => scopeOverlap(one, two)))
}


function effectiveWriteScope(task) {
  if (["CODE", "FIX"].includes(task.phase)) return task.write_scope
  // BX Test remains read-only for product source and tests, but a
  // verification-only story may persist its assigned evidence report.
  if (task.phase === "TEST") return task.write_scope.filter(isManagedReportScope)
  return []
}


function activeTasks(state) {
  return Object.values(state.tasks).filter((task) => task.status === "RUNNING")
}


function isWorkspaceWriter(task) {
  return ["CODE", "FIX"].includes(task.phase) &&
    effectiveWriteScope(task).length > 0
}


function readiness(state, task, routing) {
  if (task.status === "RUNNING") {
    return { status: "RUNNING", reason: "task already has an active job" }
  }
  if (task.status === "DONE" || task.phase === "DONE") {
    return { status: "DONE", reason: "task is complete" }
  }
  if (task.status === "BLOCKED" || task.phase === "BLOCKED") {
    return { status: "BLOCKED", reason: task.error || "task is blocked" }
  }
  const incomplete = task.dependencies.filter(
    (dependency) => state.tasks[dependency]?.status !== "DONE",
  )
  if (incomplete.length > 0) {
    return {
      status: "WAITING_DEPENDENCY",
      reason: "waiting for " + incomplete.join(", "),
    }
  }
  const active = activeTasks(state)
  if (active.length >= state.wip_limit) {
    return { status: "QUEUED", reason: "WIP limit reached" }
  }
  const writeScope = effectiveWriteScope(task)
  const conflict = active.find((other) =>
    writeScopesConflict(writeScope, effectiveWriteScope(other)),
  )
  if (conflict) {
    return {
      status: "QUEUED",
      reason: "write scope conflicts with " + conflict.task_id,
    }
  }
  const agent = phaseAgent(task.phase)
  const model = routing?.[agent]?.primary
  if (typeof model !== "string" || !model.includes("/")) {
    return { status: "WAITING_MODEL", reason: agent + " has no primary model" }
  }
  const zone = modelZone(model)
  const sameZone = active.filter((other) =>
    typeof other.model === "string" && modelZone(other.model) === zone
  ).length
  const zoneLimit = zone === "local"
    ? state.local_concurrency
    : state.cloud_concurrency
  if (sameZone >= zoneLimit) {
    return {
      status: "WAITING_MODEL",
      reason: zone + " model concurrency reached",
    }
  }
  // Jobs currently share one physical working tree. Two source writers cannot
  // be attributed reliably from whole-workspace snapshots, even when their
  // declared write scopes are disjoint: either process may create a file after
  // the other job's baseline. Keep one writer per workspace until an isolated
  // worktree/overlay runner is available. Read-only Test/Review jobs may still
  // run concurrently with each other and with the writer.
  const activeWriter = active.find(isWorkspaceWriter)
  if (isWorkspaceWriter(task) && activeWriter) {
    return {
      status: "QUEUED",
      reason: "workspace writer is active: " + activeWriter.task_id,
    }
  }
  if (
    writeScope.length === 0 &&
    active.filter((other) => effectiveWriteScope(other).length === 0).length >=
      state.read_only_concurrency
  ) {
    return {
      status: "QUEUED",
      reason: "read-only concurrency reached",
    }
  }
  return { status: "READY", reason: "dependencies, scope and model quota pass" }
}


export function scheduledJobID(task) {
  const agent = phaseAgent(task.phase)
  return [
    "job",
    task.task_id,
    task.phase.toLowerCase(),
    agent,
    "r" + task.fix_round,
  ].join("-")
}


function projection(state, task, routing) {
  const ready = readiness(state, task, routing)
  const agent = PHASE_AGENTS[task.phase] || null
  return {
    job_id:
      task.active_job_id ||
      (agent ? scheduledJobID(task) : task.last_job_id),
    task_id: task.task_id,
    phase: task.phase,
    agent,
    model: agent ? routing?.[agent]?.primary || null : null,
    status: ready.status,
    reason: ready.reason,
    dependencies: task.dependencies,
    read_scope: task.read_scope,
    write_scope: effectiveWriteScope(task),
    fix_round: task.fix_round,
  }
}


export function listSchedulerJobs(projectRoot, routing) {
  const state = loadSchedulerState(projectRoot)
  return {
    revision: state.revision,
    wip_limit: state.wip_limit,
    local_concurrency: state.local_concurrency,
    cloud_concurrency: state.cloud_concurrency,
    jobs: Object.values(state.tasks).map((task) =>
      projection(state, task, routing)
    ),
  }
}


export function planSchedulerBatch(projectRoot, routing, maximum) {
  if (!Number.isInteger(maximum) || maximum < 1 || maximum > 4) {
    throw new Error("scheduler batch maximum must be between 1 and 4")
  }
  const state = loadSchedulerState(projectRoot)
  let simulated = state
  const jobs = []
  for (const task of Object.values(state.tasks)) {
    if (jobs.length >= maximum) break
    const candidate = simulated.tasks[task.task_id]
    const job = projection(simulated, candidate, routing)
    if (job.status !== "READY") continue
    jobs.push(job)
    simulated = {
      ...simulated,
      tasks: {
        ...simulated.tasks,
        [task.task_id]: {
          ...candidate,
          status: "RUNNING",
          active_job_id: job.job_id,
          agent: job.agent,
          model: job.model,
        },
      },
    }
  }
  return {
    scheduler_revision: state.revision,
    jobs,
  }
}


function projectStatusFor(task) {
  if (task.status === "DONE") return { status: "done", agent: null }
  if (task.status === "BLOCKED") return { status: "escalated", agent: null }
  if (task.status !== "RUNNING") return { status: "backlog", agent: null }
  const status = {
    CODE: "coding",
    TEST: "testing",
    FIX: "fixing",
    TASK_REVIEW: "reviewing",
  }[task.phase]
  return { status, agent: task.agent }
}


function saveProjectTaskUnlocked(projectRoot, schedulerTask, allDone = false) {
  const file = path.join(projectRoot, ".biexce", "state", "PROJECT_STATE.json")
  const project = readProjectState(projectRoot)
  let found = false
  project.tasks = project.tasks.map((task) => {
    if (task.id !== schedulerTask.task_id) return task
    found = true
    const mapped = projectStatusFor(schedulerTask)
    return {
      ...task,
      status: mapped.status,
      round: schedulerTask.fix_round,
      agent: mapped.agent,
    }
  })
  if (!found) throw new Error("scheduler task is missing from PROJECT_STATE")
  const active = project.tasks.filter((task) =>
    ACTIVE_PROJECT_STATUSES.has(task.status)
  ).length
  if (active > planWipLimit(projectRoot)) {
    throw new Error("PROJECT_STATE active tasks exceed plan WIP limit")
  }
  project.stage = allDone ? "B4" : "B3"
  project.updated = new Date().toISOString()
  atomicWrite(file, JSON.stringify(project, null, 2) + "\n")
}


export function claimSchedulerJob({
  projectRoot,
  taskID = null,
  requestedAgent = null,
  routing,
  options,
}) {
  const root = fs.realpathSync(projectRoot)
  return withSchedulerLock(root, () => {
    const state = loadUnlocked(root, options)
    const candidates = Object.values(state.tasks).filter((task) =>
      taskID === null || task.task_id === taskID
    )
    if (candidates.length === 0) {
      throw new Error("scheduler task is unknown: " + taskID)
    }
    let selected = null
    let selectedProjection = null
    for (const task of candidates) {
      const current = projection(state, task, routing)
      if (requestedAgent && current.agent !== requestedAgent) {
        if (taskID !== null) {
          throw new Error(
            task.task_id + " " + task.phase + " requires " +
            current.agent + ", not " + requestedAgent,
          )
        }
        continue
      }
      if (current.status === "READY") {
        selected = task
        selectedProjection = current
        break
      }
      if (taskID !== null) {
        throw new Error(
          "BIEXCE_SCHEDULER_" + current.status + ": " + current.reason,
        )
      }
    }
    if (!selected || !selectedProjection) {
      throw new Error("BIEXCE_SCHEDULER_IDLE: no runnable task")
    }
    const now = new Date().toISOString()
    const updated = {
      ...selected,
      status: "RUNNING",
      active_job_id: selectedProjection.job_id,
      last_job_id: selectedProjection.job_id,
      agent: selectedProjection.agent,
      model: selectedProjection.model,
      error: null,
      updated_at_utc: now,
    }
    const next = saveUnlocked(root, {
      ...state,
      tasks: { ...state.tasks, [selected.task_id]: updated },
    })
    saveProjectTaskUnlocked(root, updated)
    return {
      ...selectedProjection,
      status: "RUNNING",
      scheduler_revision: next.revision,
    }
  })
}


function transition(task, result) {
  if (task.phase === "CODE" && result === "SUCCEEDED") {
    return { phase: "TEST", status: "READY", round: task.fix_round }
  }
  if (task.phase === "FIX" && result === "SUCCEEDED") {
    return { phase: "TEST", status: "READY", round: task.fix_round }
  }
  if (
    ["CODE", "FIX"].includes(task.phase) &&
    result === "FAILED"
  ) {
    // A child that submits FAILED with deterministic check evidence completed
    // its protocol correctly. This is a source/contract repair input, not a
    // runtime CONTRACT error and must never requeue the identical writer job.
    if (task.fix_round >= 3) {
      return { phase: "BLOCKED", status: "BLOCKED", round: task.fix_round }
    }
    return { phase: "FIX", status: "READY", round: task.fix_round + 1 }
  }
  if (task.phase === "TEST" && result === "PASS") {
    return { phase: "TASK_REVIEW", status: "READY", round: task.fix_round }
  }
  if (task.phase === "TASK_REVIEW" &&
    ["APPROVE", "APPROVE_WITH_MINOR_NOTES"].includes(result)) {
    return { phase: "DONE", status: "DONE", round: task.fix_round }
  }
  if (
    (task.phase === "TEST" && result === "FAIL") ||
    (task.phase === "TASK_REVIEW" && result === "CHANGES_REQUIRED")
  ) {
    if (task.fix_round >= 3) {
      return { phase: "BLOCKED", status: "BLOCKED", round: task.fix_round }
    }
    return { phase: "FIX", status: "READY", round: task.fix_round + 1 }
  }
  if (task.phase === "TEST" && result === "INCONCLUSIVE") {
    if (task.last_result !== "INCONCLUSIVE") {
      return { phase: "TEST", status: "READY", round: task.fix_round }
    }
    return { phase: "BLOCKED", status: "BLOCKED", round: task.fix_round }
  }
  throw new Error(task.phase + " does not accept scheduler result " + result)
}


export function completeSchedulerJob(projectRoot, jobID, result) {
  const root = fs.realpathSync(projectRoot)
  return withSchedulerLock(root, () => {
    const state = loadUnlocked(root)
    const task = Object.values(state.tasks).find(
      (candidate) => candidate.active_job_id === jobID,
    )
    if (!task) throw new Error("scheduler job is not active: " + jobID)
    const nextStep = transition(task, result)
    const now = new Date().toISOString()
    const updated = {
      ...task,
      phase: nextStep.phase,
      status: nextStep.status,
      fix_round: nextStep.round,
      active_job_id: null,
      agent: null,
      model: null,
      last_result: result,
      error: nextStep.status === "BLOCKED"
        ? result === "INCONCLUSIVE"
          ? "Verification remained inconclusive after one automatic retry for " +
            task.task_id
          : "Fix cap blocked " + task.task_id
        : null,
      updated_at_utc: now,
    }
    const tasks = { ...state.tasks, [task.task_id]: updated }
    const allDone = Object.values(tasks).every(
      (candidate) => candidate.status === "DONE",
    )
    const hasActive = Object.values(tasks).some(
      (candidate) => candidate.status === "RUNNING",
    )
    const blockedTask = Object.values(tasks).find(
      (candidate) => candidate.status === "BLOCKED",
    )
    const next = saveUnlocked(root, { ...state, tasks })
    saveProjectTaskUnlocked(root, updated, allDone)
    return {
      task: updated,
      scheduler_revision: next.revision,
      all_done: allDone,
      blocked: updated.status === "BLOCKED",
      has_active: hasActive,
      blocked_task_id: blockedTask?.task_id || null,
    }
  })
}


export function releaseSchedulerJob(
  projectRoot,
  jobID,
  reason,
  { recoverable = true } = {},
) {
  const root = fs.realpathSync(projectRoot)
  return withSchedulerLock(root, () => {
    const state = loadUnlocked(root)
    const task = Object.values(state.tasks).find(
      (candidate) =>
        candidate.active_job_id === jobID ||
        candidate.last_job_id === jobID,
    )
    if (!task || task.active_job_id !== jobID) {
      return { changed: false, task: task || null, scheduler_revision: state.revision }
    }
    const now = new Date().toISOString()
    const updated = {
      ...task,
      status: recoverable ? "READY" : "BLOCKED",
      phase: recoverable ? task.phase : "BLOCKED",
      active_job_id: null,
      agent: null,
      model: null,
      error: reason,
      updated_at_utc: now,
    }
    const next = saveUnlocked(root, {
      ...state,
      tasks: { ...state.tasks, [task.task_id]: updated },
    })
    saveProjectTaskUnlocked(root, updated)
    return { changed: true, task: updated, scheduler_revision: next.revision }
  })
}


export function recoverStandardBlockedTask(
  projectRoot,
  taskID,
  phase,
  {
    incrementFixRound = false,
    recoveryReason = null,
    allowFixCap = false,
  } = {},
) {
  if (!["CODE", "TEST", "FIX", "TASK_REVIEW"].includes(phase)) {
    throw new Error("standard recovery phase is invalid: " + phase)
  }
  const root = fs.realpathSync(projectRoot)
  return withSchedulerLock(root, () => {
    const state = loadUnlocked(root)
    const task = state.tasks[taskID]
    if (!task) throw new Error("scheduler task is unknown: " + taskID)
    if (task.status !== "BLOCKED" || task.phase !== "BLOCKED") {
      return { changed: false, task, scheduler_revision: state.revision }
    }
    // A bounded fix loop that genuinely exhausted its budget is a source
    // problem and still needs human judgment. Operational/runtime failures are
    // re-queued without asking the user to edit scheduler state.
    if (/fix cap/i.test(task.error || "") && !allowFixCap) {
      return { changed: false, task, scheduler_revision: state.revision }
    }
    const now = new Date().toISOString()
    const updated = {
      ...task,
      phase,
      status: "READY",
      fix_round: incrementFixRound ? task.fix_round + 1 : task.fix_round,
      active_job_id: null,
      agent: null,
      model: null,
      last_result: recoveryReason
        ? "RUNTIME_RECOVERED:" + recoveryReason
        : task.last_result,
      error: null,
      updated_at_utc: now,
    }
    const next = saveUnlocked(root, {
      ...state,
      tasks: { ...state.tasks, [taskID]: updated },
    })
    saveProjectTaskUnlocked(root, updated)
    return { changed: true, task: updated, scheduler_revision: next.revision }
  })
}


function generatedRuntimeScopeError(value) {
  const paths = runtimeScopeErrorPaths(value)
  return paths.length > 0 && paths.every(generatedRuntimePath)
}


function scopeAllowsPath(scope, file) {
  return scope.some((pattern) => {
    if (pattern.endsWith("/")) return file.startsWith(pattern)
    if (pattern.includes("*") || pattern.includes("?")) {
      return globRegex(pattern).test(file)
    }
    return file === pattern
  })
}


function jobsOverlap(left, right) {
  const leftStart = Date.parse(left?.started_at_utc || "")
  const rightStart = Date.parse(right?.started_at_utc || "")
  if (!Number.isFinite(leftStart) || !Number.isFinite(rightStart)) return false
  const leftEnd = left.completed_at_utc
    ? Date.parse(left.completed_at_utc)
    : Number.POSITIVE_INFINITY
  const rightEnd = right.completed_at_utc
    ? Date.parse(right.completed_at_utc)
    : Number.POSITIVE_INFINITY
  return leftStart <= rightEnd && rightStart <= leftEnd
}


function parallelDiffRecoveryPhase({ jobBoard, task }) {
  const current = jobBoard.jobs[task.last_job_id]
  if (!current || !["CODE", "FIX"].includes(current.phase)) return null
  const paths = runtimeScopeErrorPaths(task.error)
  if (paths.length === 0) return null
  const siblings = Object.values(jobBoard.jobs).filter((job) =>
    job.task_id !== task.task_id &&
    ["CODE", "FIX"].includes(job.phase) &&
    Array.isArray(job.write_scope) &&
    jobsOverlap(current, job)
  )
  if (
    siblings.length === 0 ||
    !paths.every((file) =>
      siblings.some((job) => scopeAllowsPath(job.write_scope, file)),
    )
  ) return null
  return current.phase
}


function originWriterPhase({ jobBoard, task }) {
  const jobPhase = jobBoard.jobs[task.last_job_id]?.phase
  if (["CODE", "FIX"].includes(jobPhase)) return jobPhase
  const identity = String(task.last_job_id || "").toLowerCase()
  if (/-code-bx-code-/.test(identity)) return "CODE"
  if (/-fix-bx-fix-/.test(identity)) return "FIX"
  return null
}


function latestTaskJob(jobBoard, task) {
  const direct = jobBoard.jobs[task.last_job_id]
  if (direct) return direct
  return Object.values(jobBoard.jobs)
    .filter((job) => job.task_id === task.task_id)
    .sort((left, right) =>
      (Date.parse(right.updated_at_utc || right.completed_at_utc || "") || 0) -
      (Date.parse(left.updated_at_utc || left.completed_at_utc || "") || 0)
    )[0] || null
}


function historicalCrossTaskDiffRecoveryPhase({ jobBoard, state, task }) {
  if (task.last_result === "RUNTIME_RECOVERED:CROSS_TASK_DIFF_REBASE") return null
  const phase = originWriterPhase({ jobBoard, task })
  if (phase === null) return null
  const paths = runtimeScopeErrorPaths(task.error)
  if (paths.length === 0 || paths.some(protectedProjectPath)) return null
  const ownScope = Array.isArray(task.write_scope) ? task.write_scope : []
  const foreignScopes = Object.values(state.tasks)
    .filter((candidate) => candidate.task_id !== task.task_id)
    .flatMap((candidate) => candidate.write_scope || [])
  if (
    foreignScopes.length === 0 ||
    !paths.every((file) =>
      !scopeAllowsPath(ownScope, file) && scopeAllowsPath(foreignScopes, file)
    )
  ) return null
  // Historical runtimes used a whole-workspace baseline and may have lost the
  // precise child overlap timestamps after restart. Requeue exactly once with
  // a fresh baseline when every disputed path belongs to another task. The
  // current runtime serializes source writers, so the retry either succeeds or
  // becomes a real blocker without an infinite recovery loop.
  return phase
}


function hasPythonUnittestFile(projectRoot) {
  const testRoot = path.join(projectRoot, "tests")
  if (!fs.existsSync(testRoot)) return false
  const pending = [testRoot]
  while (pending.length > 0) {
    const directory = pending.pop()
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name)
      if (entry.isSymbolicLink()) continue
      if (entry.isDirectory()) {
        if (entry.name !== "__pycache__") pending.push(target)
        continue
      }
      if (entry.isFile() && /^test.*\.py$/i.test(entry.name)) return true
    }
  }
  return false
}


function legacyUnittestContract(projectRoot, taskID) {
  const task = fs.readFileSync(
    path.join(projectRoot, ".biexce", "tasks", taskID + ".md"),
    "utf8",
  )
  const verify = markdownField(task, "Verify") || ""
  if (!/^`?N\/?A\b/i.test(verify)) return false
  const brief = fs.readFileSync(
    path.join(projectRoot, ".biexce", "PROJECT_BRIEF.md"),
    "utf8",
  )
  return /\bunittest\b/i.test(task + "\n" + brief) &&
    hasPythonUnittestFile(projectRoot)
}


const COMPATIBILITY_RECOVERY_RULES = [
  {
    reason_code: "PARALLEL_DIFF_ATTRIBUTION",
    phase: (context) => parallelDiffRecoveryPhase(context),
    matches: (context) =>
      context.task.phase === "BLOCKED" &&
      context.task.status === "BLOCKED" &&
      parallelDiffRecoveryPhase(context) !== null,
  },
  {
    reason_code: "CROSS_TASK_DIFF_REBASE",
    phase: (context) => historicalCrossTaskDiffRecoveryPhase(context),
    matches: (context) =>
      context.task.phase === "BLOCKED" &&
      context.task.status === "BLOCKED" &&
      historicalCrossTaskDiffRecoveryPhase(context) !== null,
  },
  {
    reason_code: "ROUTING_MISMATCH",
    phase: "TEST",
    matches: ({ contract, task }) =>
      isVerificationOnlyContract(contract) &&
      !["DONE", "RUNNING"].includes(task.status) &&
      ["CODE", "BLOCKED"].includes(task.phase) &&
      (
        task.phase !== "BLOCKED" ||
        /verification-only|owner role bx-test|routing\/ownership conflict/i.test(
          task.error || "",
        ) ||
        /-code-bx-code-/i.test(task.last_job_id || "")
      ),
    updates: ({ contract }) => ({ write_scope: contract.write_scope }),
  },
  {
    reason_code: "GENERATED_ARTIFACT",
    phase: "TEST",
    matches: ({ task }) =>
      task.phase === "BLOCKED" &&
      task.status === "BLOCKED" &&
      task.last_result === "SUCCEEDED" &&
      generatedRuntimeScopeError(task.error),
  },
  {
    reason_code: "VERIFICATION_INCONCLUSIVE",
    phase: "TEST",
    matches: ({ projectRoot, taskID, task }) =>
      task.phase === "BLOCKED" &&
      task.status === "BLOCKED" &&
      task.last_result === "INCONCLUSIVE" &&
      [
        "Fix cap or inconclusive verification blocked " + taskID,
        "Verification remained inconclusive after one automatic retry for " + taskID,
      ].includes(task.error) &&
      legacyUnittestContract(projectRoot, taskID),
  },
  {
    reason_code: "MISSING_EVIDENCE",
    phase: "TEST",
    matches: ({ task }) =>
      task.phase === "BLOCKED" &&
      task.status === "BLOCKED" &&
      task.last_result === "CHANGES_REQUIRED" &&
      /required failing evidence is missing/i.test(task.error || ""),
  },
]


function recoverCompatibilityBlockers(projectRoot) {
  const root = fs.realpathSync(projectRoot)
  return withSchedulerLock(root, () => {
    const state = loadUnlocked(root)
    const jobBoard = loadJobBoard(root)
    const now = new Date().toISOString()
    const tasks = { ...state.tasks }
    const recovered = []
    const routes = {}
    const reasons = {}
    for (const [taskID, task] of Object.entries(tasks)) {
      const context = {
        projectRoot: root,
        taskID,
        task,
        contract: taskContract(root, taskID),
        jobBoard,
        state,
      }
      const rule = COMPATIBILITY_RECOVERY_RULES.find(
        (candidate) => candidate.matches(context),
      )
      if (!rule) continue
      const recoveryPhase = typeof rule.phase === "function"
        ? rule.phase(context)
        : rule.phase
      if (!recoveryPhase) continue
      tasks[taskID] = {
        ...task,
        ...(rule.updates ? rule.updates(context) : {}),
        phase: recoveryPhase,
        status: task.status === "BLOCKED" ? "READY" : task.status,
        active_job_id: null,
        agent: null,
        model: null,
        last_result:
          task.status === "BLOCKED"
            ? "RUNTIME_RECOVERED:" + rule.reason_code
            : task.last_result,
        error: null,
        updated_at_utc: now,
      }
      recovered.push(taskID)
      routes[taskID] = recoveryPhase
      reasons[taskID] = rule.reason_code
    }
    if (recovered.length === 0) {
      return {
        changed: false,
        recovered_tasks: [],
        recovered_routes: {},
        recovery_reasons: {},
        scheduler_revision: state.revision,
      }
    }
    const next = saveUnlocked(root, { ...state, tasks })
    for (const taskID of recovered) saveProjectTaskUnlocked(root, tasks[taskID])
    return {
      changed: true,
      recovered_tasks: recovered,
      recovered_routes: routes,
      recovery_reasons: reasons,
      scheduler_revision: next.revision,
    }
  })
}


const RECOVERABLE_TASK_PHASES = new Set([
  "CODE",
  "TEST",
  "FIX",
  "TASK_REVIEW",
])


export function recoverSchedulerBlockers(
  projectRoot,
  { allowStandard = false, phaseByTask = {} } = {},
) {
  const recovered = new Set()
  const routes = {}
  const reasons = {}

  const compatibility = recoverCompatibilityBlockers(projectRoot)
  for (const taskID of compatibility.recovered_tasks) {
    recovered.add(taskID)
    routes[taskID] = compatibility.recovered_routes[taskID]
    reasons[taskID] = compatibility.recovery_reasons[taskID]
  }

  if (allowStandard) {
    const state = loadSchedulerState(projectRoot)
    const jobBoard = loadJobBoard(projectRoot)
    for (const task of Object.values(state.tasks)) {
      if (task.status !== "BLOCKED" || recovered.has(task.task_id)) continue
      const originJob = latestTaskJob(jobBoard, task)
      const originPhase = phaseByTask[task.task_id] ||
        (
          ["CODE", "FIX"].includes(originJob?.phase)
            ? originJob.phase
            : originWriterPhase({ jobBoard, task })
        )
      // Legacy runtimes did not always preserve the concrete failure on the
      // scheduler task. Prefer all persisted evidence instead of requiring a
      // specific error string to survive in one state file.
      const failureEvidence = [task.error, originJob?.error]
        .filter(Boolean)
        .join("\n")
      const scope = scopeFailure(failureEvidence)
      const fixCapAdjudication = "FIX_CAP_STANDARD_ADJUDICATION"
      const alreadyAdjudicated = taskRecoveryHistory(
        projectRoot,
        task.task_id,
        50,
      ).some((event) => event.recovery_reason === fixCapAdjudication)
      const actionableFixCap =
        task.fix_round >= 3 &&
        /fix cap/i.test(task.error || "") &&
        (
          ["FAIL", "FAILED", "CHANGES_REQUIRED"].includes(task.last_result) ||
          ["FAIL", "FAILED", "CHANGES_REQUIRED"].includes(
            originJob?.result_status,
          )
        ) &&
        scope.kind !== SCOPE_FAILURES.HARD_BOUNDARY
      if (actionableFixCap && !alreadyAdjudicated) {
        // Standard mode gets one audited adjudication after the normal
        // three-round cap. This is intentionally not an unbounded fourth
        // loop: the recovery event prevents another adjudication if the
        // resulting Fix -> Test -> Review cycle still fails. Critical mode
        // never reaches this branch because allowStandard is false.
        const result = recoverStandardBlockedTask(
          projectRoot,
          task.task_id,
          "FIX",
          {
            recoveryReason: fixCapAdjudication,
            allowFixCap: true,
          },
        )
        if (!result.changed) continue
        recovered.add(task.task_id)
        routes[task.task_id] = "FIX"
        reasons[task.task_id] = fixCapAdjudication
        continue
      }
      if (!RECOVERABLE_TASK_PHASES.has(originPhase)) continue
      if (
        ["CODE", "FIX"].includes(originPhase) &&
        scope.kind === SCOPE_FAILURES.PROJECT_SCOPE_DRIFT
      ) {
        // A legacy writer may have finished useful source changes before an
        // older runtime rejected an incomplete planned write scope. Re-run BX
        // Test against the actual workspace first. PASS continues to review;
        // FAIL creates authoritative evidence for the bounded BX Fix loop.
        const result = recoverStandardBlockedTask(
          projectRoot,
          task.task_id,
          "TEST",
          { recoveryReason: "PROJECT_SCOPE_REVERIFY" },
        )
        if (!result.changed) continue
        recovered.add(task.task_id)
        routes[task.task_id] = "TEST"
        reasons[task.task_id] = "PROJECT_SCOPE_REVERIFY"
        continue
      }
      const error = new Error(failureEvidence || "scheduler task blocked")
      const policy = classifyFailure({
        error,
        // Older runtimes validated a structured FAILED result and then
        // terminal-blocked before recording the normal scheduler transition.
        // A persisted result_status=FAILED is authoritative source evidence,
        // so migrate it to the bounded FIX loop rather than replaying CODE.
        sourceFailure: originJob?.result_status === "FAILED",
        fixRound: task.fix_round,
      })
      const phase = policy.action === FAILURE_ACTIONS.FIX
        ? "FIX"
        : policy.action === FAILURE_ACTIONS.RETRY
          ? originPhase
          : null
      if (phase === null) continue
      const result = recoverStandardBlockedTask(
        projectRoot,
        task.task_id,
        phase,
        {
          incrementFixRound: policy.counts_as_fix_round,
          recoveryReason: policy.reason_code,
        },
      )
      if (!result.changed) continue
      recovered.add(task.task_id)
      routes[task.task_id] = phase
      reasons[task.task_id] = policy.reason_code
    }
  }

  return {
    changed: recovered.size > 0,
    recovered_tasks: [...recovered],
    recovered_routes: routes,
    recovery_reasons: reasons,
  }
}


export function schedulerJob(projectRoot, jobID, routing) {
  const state = loadSchedulerState(projectRoot)
  const task = Object.values(state.tasks).find(
    (candidate) =>
      candidate.active_job_id === jobID ||
      candidate.last_job_id === jobID ||
      (PHASE_AGENTS[candidate.phase] && scheduledJobID(candidate) === jobID),
  )
  if (!task) return null
  return {
    ...projection(state, task, routing),
    active_job_id: task.active_job_id,
    last_job_id: task.last_job_id,
    last_result: task.last_result,
    error: task.error,
  }
}
