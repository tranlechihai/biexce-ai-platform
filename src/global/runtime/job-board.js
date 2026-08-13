import crypto from "node:crypto"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"


export const JOB_BOARD_SCHEMA =
  "https://schemas.biexce.local/runtime/job-board-v1.schema.json"

export const JOB_STATUSES = new Set([
  "QUEUED",
  "RUNNING",
  "WAITING_DEPENDENCY",
  "WAITING_MODEL",
  "WAITING_HUMAN",
  "RETRYING",
  "FALLBACK",
  "BLOCKED",
  "FAILED",
  "TIMED_OUT",
  "CANCELLED",
  "COMPLETED",
])

const BOARD_KEYS = new Set([
  "$schema",
  "schema_version",
  "project_root",
  "revision",
  "jobs",
  "updated_at_utc",
])

const JOB_KEYS = new Set([
  "job_id",
  "trace_id",
  "task_id",
  "agent",
  "session_id",
  "phase",
  "status",
  "dependencies",
  "read_scope",
  "write_scope",
  "model",
  "attempt",
  "recovery_count",
  "created_at_utc",
  "started_at_utc",
  "deadline_at_utc",
  "completed_at_utc",
  "updated_at_utc",
  "result_status",
  "error",
])

const LEASE_KEYS = new Set([
  "schema_version",
  "job_id",
  "token",
  "pid",
  "host",
  "owner_session_id",
  "acquired_at_utc",
  "deadline_at_utc",
])


function exactKeys(value, expected) {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).length === expected.size &&
    Object.keys(value).every((key) => expected.has(key))
}


function stateRoot(projectRoot) {
  return path.join(projectRoot, ".biexce", "state")
}


export function jobBoardPath(projectRoot) {
  return path.join(stateRoot(projectRoot), "AUTOPILOT_JOBS.json")
}


export function jobEventPath(projectRoot) {
  return path.join(stateRoot(projectRoot), "AUTOPILOT_EVENTS.jsonl")
}


export function jobLeasePath(projectRoot, jobID) {
  if (!/^job-[A-Za-z0-9._-]{1,180}$/.test(jobID)) {
    throw new Error(`invalid job id: ${jobID}`)
  }
  return path.join(stateRoot(projectRoot), "leases", `${jobID}.json`)
}


function atomicWrite(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const temporary = `${file}.${process.pid}.${crypto.randomUUID()}.tmp`
  try {
    fs.writeFileSync(temporary, value, { encoding: "utf8", mode: 0o600, flag: "wx" })
    fs.renameSync(temporary, file)
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary)
  }
}


function readRegularJson(file, label) {
  const stat = fs.lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error(`${label} is not a regular file`)
  }
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"))
  } catch (error) {
    throw new Error(`${label} is invalid JSON: ${error.message}`)
  }
}


function validateStringArray(value, label) {
  if (
    !Array.isArray(value) ||
    value.some((entry) => typeof entry !== "string" || !entry.trim()) ||
    new Set(value).size !== value.length
  ) {
    throw new Error(`${label} must be an array of unique non-empty strings`)
  }
}


function validateJob(job, key) {
  if (!exactKeys(job, JOB_KEYS) || job.job_id !== key) {
    throw new Error(`job record properties mismatch: ${key}`)
  }
  if (
    !/^job-[A-Za-z0-9._-]{1,180}$/.test(job.job_id) ||
    typeof job.trace_id !== "string" || !job.trace_id ||
    !(job.task_id === null || /^t-[0-9]{3}$/.test(job.task_id)) ||
    typeof job.agent !== "string" || !job.agent ||
    !(job.session_id === null || typeof job.session_id === "string") ||
    typeof job.phase !== "string" || !job.phase ||
    !JOB_STATUSES.has(job.status) ||
    !(job.model === null || typeof job.model === "string") ||
    !Number.isInteger(job.attempt) || job.attempt < 1 ||
    !Number.isInteger(job.recovery_count) || job.recovery_count < 0
  ) {
    throw new Error(`job record is invalid: ${key}`)
  }
  validateStringArray(job.dependencies, `${key}.dependencies`)
  validateStringArray(job.read_scope, `${key}.read_scope`)
  validateStringArray(job.write_scope, `${key}.write_scope`)
  for (const field of [
    "created_at_utc", "started_at_utc", "deadline_at_utc",
    "completed_at_utc", "updated_at_utc",
  ]) {
    if (!(job[field] === null || typeof job[field] === "string")) {
      throw new Error(`${key}.${field} is invalid`)
    }
  }
  for (const field of ["result_status", "error"]) {
    if (!(job[field] === null || typeof job[field] === "string")) {
      throw new Error(`${key}.${field} is invalid`)
    }
  }
  return job
}


function validateBoard(board, projectRoot) {
  if (!exactKeys(board, BOARD_KEYS)) throw new Error("job board properties mismatch")
  if (
    board.$schema !== JOB_BOARD_SCHEMA ||
    board.schema_version !== 1 ||
    path.resolve(board.project_root) !== path.resolve(projectRoot) ||
    !Number.isInteger(board.revision) || board.revision < 0 ||
    board.jobs === null || typeof board.jobs !== "object" || Array.isArray(board.jobs) ||
    typeof board.updated_at_utc !== "string"
  ) {
    throw new Error("job board schema invalid")
  }
  for (const [key, job] of Object.entries(board.jobs)) validateJob(job, key)
  return board
}


export function loadJobBoard(projectRoot) {
  const root = fs.realpathSync(projectRoot)
  const file = jobBoardPath(root)
  if (!fs.existsSync(file)) {
    return {
      $schema: JOB_BOARD_SCHEMA,
      schema_version: 1,
      project_root: root,
      revision: 0,
      jobs: {},
      updated_at_utc: new Date().toISOString(),
    }
  }
  return validateBoard(readRegularJson(file, "BIEXCE job board"), root)
}


function saveJobBoard(projectRoot, board) {
  const next = validateBoard({
    ...board,
    project_root: fs.realpathSync(projectRoot),
    revision: board.revision + 1,
    updated_at_utc: new Date().toISOString(),
  }, fs.realpathSync(projectRoot))
  atomicWrite(jobBoardPath(projectRoot), `${JSON.stringify(next, null, 2)}\n`)
  return next
}


export function appendJobEvent(projectRoot, event) {
  const file = jobEventPath(projectRoot)
  let existing = ""
  if (fs.existsSync(file)) {
    const stat = fs.lstatSync(file)
    if (!stat.isFile() || stat.isSymbolicLink()) throw new Error("job event log is invalid")
    existing = fs.readFileSync(file, "utf8")
    for (const line of existing.split(/\r?\n/).filter((entry) => entry.trim())) {
      JSON.parse(line)
    }
  }
  const record = {
    schema_version: 1,
    event_id: crypto.randomUUID(),
    timestamp_utc: new Date().toISOString(),
    ...event,
  }
  const separator = existing && !existing.endsWith("\n") ? "\n" : ""
  atomicWrite(file, `${existing}${separator}${JSON.stringify(record)}\n`)
  return record
}


function readJobEvents(projectRoot) {
  const file = jobEventPath(projectRoot)
  if (!fs.existsSync(file)) return []
  const stat = fs.lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error("job event log is invalid")
  }
  return fs.readFileSync(file, "utf8")
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line))
}


export function recordJobResult(projectRoot, jobID, result, resultSource) {
  const job = loadJobBoard(projectRoot).jobs[jobID]
  if (!job) throw new Error(`job is not registered: ${jobID}`)
  if (
    result === null || typeof result !== "object" || Array.isArray(result) ||
    typeof result.status !== "string" || !result.status ||
    typeof result.summary !== "string" || !result.summary.trim() ||
    !Array.isArray(result.changed_files) ||
    !Array.isArray(result.checks) ||
    !Array.isArray(result.artifacts) ||
    typeof resultSource !== "string" || !resultSource
  ) {
    throw new Error(`job result is invalid: ${jobID}`)
  }
  return appendJobEvent(projectRoot, {
    event: "JOB_RESULT_RECORDED",
    job_id: jobID,
    task_id: job.task_id,
    phase: job.phase,
    agent: job.agent,
    result_source: resultSource,
    result,
  })
}


export function taskResultHistory(projectRoot, taskID, limit = 12) {
  if (!/^t-[0-9]{3}$/.test(taskID)) {
    throw new Error(`task result history id is invalid: ${taskID}`)
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
    throw new Error("task result history limit must be between 1 and 50")
  }
  return readJobEvents(projectRoot)
    .filter((event) =>
      event.event === "JOB_RESULT_RECORDED" && event.task_id === taskID
    )
    .slice(-limit)
}


export function taskRecoveryHistory(projectRoot, taskID, limit = 12) {
  if (!/^t-[0-9]{3}$/.test(taskID)) {
    throw new Error(`task recovery history id is invalid: ${taskID}`)
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
    throw new Error("task recovery history limit must be between 1 and 50")
  }
  return readJobEvents(projectRoot)
    .filter((event) =>
      event.event === "RUNTIME_TASK_RECOVERED" && event.task_id === taskID
    )
    .slice(-limit)
}


export function workflowResultHistory(projectRoot, limit = 12) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
    throw new Error("workflow result history limit must be between 1 and 50")
  }
  return readJobEvents(projectRoot)
    .filter((event) =>
      event.event === "JOB_RESULT_RECORDED" && event.task_id === null
    )
    .slice(-limit)
}


export function putJob(projectRoot, input) {
  const board = loadJobBoard(projectRoot)
  const previous = board.jobs[input.job_id] || null
  const now = new Date().toISOString()
  const value = (field, fallback = null) =>
    Object.hasOwn(input, field) ? input[field] : previous?.[field] ?? fallback
  const job = validateJob({
    job_id: input.job_id,
    trace_id: value("trace_id"),
    task_id: value("task_id"),
    agent: value("agent"),
    session_id: value("session_id"),
    phase: value("phase"),
    status: value("status", "QUEUED"),
    dependencies: value("dependencies", []),
    read_scope: value("read_scope", []),
    write_scope: value("write_scope", []),
    model: value("model"),
    attempt: value("attempt", 1),
    recovery_count: value("recovery_count", 0),
    created_at_utc: previous?.created_at_utc || now,
    started_at_utc: value("started_at_utc"),
    deadline_at_utc: value("deadline_at_utc"),
    completed_at_utc: value("completed_at_utc"),
    updated_at_utc: now,
    result_status: value("result_status"),
    error: value("error"),
  }, input.job_id)
  const next = saveJobBoard(projectRoot, {
    ...board,
    jobs: { ...board.jobs, [job.job_id]: job },
  })
  appendJobEvent(projectRoot, {
    event: previous ? "JOB_UPDATED" : "JOB_CREATED",
    job_id: job.job_id,
    status: job.status,
    board_revision: next.revision,
  })
  return job
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


function leaseExpired(lease) {
  const deadline = Date.parse(lease.deadline_at_utc)
  return Number.isFinite(deadline) && deadline <= Date.now()
}


function validateLease(lease, jobID) {
  if (
    !exactKeys(lease, LEASE_KEYS) ||
    lease.schema_version !== 1 ||
    lease.job_id !== jobID ||
    typeof lease.token !== "string" || !lease.token ||
    !Number.isInteger(lease.pid) ||
    typeof lease.host !== "string" ||
    typeof lease.owner_session_id !== "string" ||
    typeof lease.acquired_at_utc !== "string" ||
    typeof lease.deadline_at_utc !== "string"
  ) {
    throw new Error(`job lease is invalid: ${jobID}`)
  }
  return lease
}


function removeLeaseOwnedBy(file, token) {
  if (!fs.existsSync(file)) return false
  const current = readRegularJson(file, "BIEXCE job lease")
  if (current.token !== token) return false
  fs.unlinkSync(file)
  return true
}


export function acquireJobLease(projectRoot, jobID, ownerSessionID, timeoutMs) {
  const board = loadJobBoard(projectRoot)
  if (!board.jobs[jobID]) throw new Error(`job is not registered: ${jobID}`)
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1000) {
    throw new Error("job lease timeout must be at least 1000ms")
  }
  const file = jobLeasePath(projectRoot, jobID)
  fs.mkdirSync(path.dirname(file), { recursive: true })
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const now = new Date()
    const lease = {
      schema_version: 1,
      job_id: jobID,
      token: crypto.randomUUID(),
      pid: process.pid,
      host: os.hostname(),
      owner_session_id: ownerSessionID,
      acquired_at_utc: now.toISOString(),
      deadline_at_utc: new Date(now.getTime() + timeoutMs).toISOString(),
    }
    try {
      fs.writeFileSync(file, `${JSON.stringify(lease, null, 2)}\n`, {
        encoding: "utf8", mode: 0o600, flag: "wx",
      })
      appendJobEvent(projectRoot, { event: "JOB_LEASE_ACQUIRED", job_id: jobID })
      return lease
    } catch (error) {
      if (error?.code !== "EEXIST") throw error
      const current = validateLease(readRegularJson(file, "BIEXCE job lease"), jobID)
      if (
        leaseExpired(current) ||
        (current.host === os.hostname() && !processAlive(current.pid))
      ) {
        removeLeaseOwnedBy(file, current.token)
        continue
      }
      throw new Error(`job lease is already active: ${jobID}`)
    }
  }
  throw new Error(`job lease could not be acquired: ${jobID}`)
}


export function releaseJobLease(projectRoot, lease) {
  const removed = removeLeaseOwnedBy(
    jobLeasePath(projectRoot, lease.job_id),
    lease.token,
  )
  if (removed) appendJobEvent(projectRoot, {
    event: "JOB_LEASE_RELEASED",
    job_id: lease.job_id,
  })
  return removed
}


export function hasActiveJobLeases(projectRoot) {
  const directory = path.join(stateRoot(projectRoot), "leases")
  if (!fs.existsSync(directory)) return false
  for (const name of fs.readdirSync(directory)) {
    if (!name.endsWith(".json")) continue
    const jobID = name.slice(0, -5)
    const lease = validateLease(
      readRegularJson(path.join(directory, name), "BIEXCE job lease"),
      jobID,
    )
    if (!leaseExpired(lease)) return true
  }
  return false
}


export function reconcileJobBoard(projectRoot) {
  let board = loadJobBoard(projectRoot)
  const recovered = []
  for (const job of Object.values(board.jobs)) {
    if (job.status !== "RUNNING") continue
    const file = jobLeasePath(projectRoot, job.job_id)
    let orphaned = !fs.existsSync(file)
    let lease = null
    if (!orphaned) {
      lease = validateLease(readRegularJson(file, "BIEXCE job lease"), job.job_id)
      orphaned = leaseExpired(lease) ||
        (lease.host === os.hostname() && !processAlive(lease.pid))
    }
    if (!orphaned) continue
    if (lease) removeLeaseOwnedBy(file, lease.token)
    const now = new Date().toISOString()
    board = saveJobBoard(projectRoot, {
      ...board,
      jobs: {
        ...board.jobs,
        [job.job_id]: {
          ...job,
          status: "QUEUED",
          session_id: null,
          started_at_utc: null,
          deadline_at_utc: null,
          updated_at_utc: now,
          recovery_count: job.recovery_count + 1,
          error: "Recovered orphaned RUNNING job after restart",
        },
      },
    })
    appendJobEvent(projectRoot, {
      event: "JOB_REQUEUED_AFTER_RESTART",
      job_id: job.job_id,
      board_revision: board.revision,
    })
    recovered.push(job.job_id)
  }
  return { board, recovered }
}
