import crypto from "node:crypto"
import fs from "node:fs"
import path from "node:path"


export const SESSION_REGISTRY_SCHEMA =
  "https://schemas.biexce.local/runtime/session-registry-v1.schema.json"

export const SESSION_STATUSES = new Set([
  "ACTIVE",
  "RETRYING",
  "COMPLETED",
  "CANCELLED",
  "FAILED",
])

const ROOT_KEYS = new Set([
  "$schema",
  "schema_version",
  "project_root",
  "revision",
  "sessions",
  "updated_at_utc",
])

const SESSION_KEYS = new Set([
  "job_id",
  "session_id",
  "parent_session_id",
  "agent",
  "model",
  "status",
  "attempt",
  "created_at_utc",
  "updated_at_utc",
  "last_error",
])


function exactKeys(value, expected) {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).length === expected.size &&
    Object.keys(value).every((key) => expected.has(key))
}


export function sessionRegistryPath(projectRoot) {
  return path.join(
    projectRoot,
    ".biexce",
    "state",
    "AUTOPILOT_SESSIONS.json",
  )
}


function atomicWrite(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const temporary = (
    file + "." + process.pid + "." + crypto.randomUUID() + ".tmp"
  )
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


function readRegularJson(file) {
  const stat = fs.lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error("BIEXCE session registry is not a regular file")
  }
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"))
  } catch (error) {
    throw new Error("BIEXCE session registry is invalid JSON: " + error.message)
  }
}


function validateRecord(record, jobID) {
  if (!exactKeys(record, SESSION_KEYS) || record.job_id !== jobID) {
    throw new Error("session registry record properties mismatch: " + jobID)
  }
  if (
    !/^job-[A-Za-z0-9._-]{1,180}$/.test(record.job_id) ||
    typeof record.session_id !== "string" || !record.session_id ||
    typeof record.parent_session_id !== "string" || !record.parent_session_id ||
    typeof record.agent !== "string" || !record.agent ||
    typeof record.model !== "string" || !record.model.includes("/") ||
    !SESSION_STATUSES.has(record.status) ||
    !Number.isInteger(record.attempt) || record.attempt < 1 ||
    typeof record.created_at_utc !== "string" ||
    typeof record.updated_at_utc !== "string" ||
    !(record.last_error === null || typeof record.last_error === "string")
  ) {
    throw new Error("session registry record is invalid: " + jobID)
  }
  return record
}


function validateRegistry(registry, projectRoot) {
  if (!exactKeys(registry, ROOT_KEYS)) {
    throw new Error("session registry properties mismatch")
  }
  if (
    registry.$schema !== SESSION_REGISTRY_SCHEMA ||
    registry.schema_version !== 1 ||
    path.resolve(registry.project_root) !== path.resolve(projectRoot) ||
    !Number.isInteger(registry.revision) || registry.revision < 0 ||
    registry.sessions === null ||
    typeof registry.sessions !== "object" ||
    Array.isArray(registry.sessions) ||
    typeof registry.updated_at_utc !== "string"
  ) {
    throw new Error("session registry schema invalid")
  }
  for (const [jobID, record] of Object.entries(registry.sessions)) {
    validateRecord(record, jobID)
  }
  return registry
}


export function loadSessionRegistry(projectRoot) {
  const root = fs.realpathSync(projectRoot)
  const file = sessionRegistryPath(root)
  if (!fs.existsSync(file)) {
    return {
      $schema: SESSION_REGISTRY_SCHEMA,
      schema_version: 1,
      project_root: root,
      revision: 0,
      sessions: {},
      updated_at_utc: new Date().toISOString(),
    }
  }
  return validateRegistry(readRegularJson(file), root)
}


export function putSessionRecord(projectRoot, input) {
  const root = fs.realpathSync(projectRoot)
  const registry = loadSessionRegistry(root)
  const previous = registry.sessions[input.job_id] || null
  const now = new Date().toISOString()
  const value = (field, fallback = null) =>
    Object.hasOwn(input, field) ? input[field] : previous?.[field] ?? fallback
  const record = validateRecord({
    job_id: input.job_id,
    session_id: value("session_id"),
    parent_session_id: value("parent_session_id"),
    agent: value("agent"),
    model: value("model"),
    status: value("status", "ACTIVE"),
    attempt: value("attempt", 1),
    created_at_utc: previous?.created_at_utc || now,
    updated_at_utc: now,
    last_error: value("last_error"),
  }, input.job_id)
  const next = validateRegistry({
    ...registry,
    revision: registry.revision + 1,
    sessions: { ...registry.sessions, [record.job_id]: record },
    updated_at_utc: now,
  }, root)
  atomicWrite(
    sessionRegistryPath(root),
    JSON.stringify(next, null, 2) + "\n",
  )
  return record
}


export function resumableSession(projectRoot, jobID, agent) {
  const record = loadSessionRegistry(projectRoot).sessions[jobID] || null
  if (
    !record ||
    record.agent !== agent ||
    !["ACTIVE", "RETRYING"].includes(record.status)
  ) {
    return null
  }
  return record
}
