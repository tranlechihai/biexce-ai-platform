import { tool } from "@opencode-ai/plugin"
import { spawnSync } from "node:child_process"
import crypto from "node:crypto"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"


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
  "https://schemas.biexce.local/control-plane/autopilot-workflow-v1.schema.json"
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


function loadRunningState(directory, sessionID) {
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
    throw new Error("Autopilot is armed for another session")
  }
  return state
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


function workflowPath(projectRoot) {
  return path.join(projectRoot, ".biexce", "state", "AUTOPILOT_WORKFLOW.json")
}


function loadWorkflow(projectRoot) {
  const file = workflowPath(projectRoot)
  const realFile = fs.realpathSync(file)
  if (!realFile.startsWith(projectRoot + path.sep)) {
    throw new Error("workflow state escapes the project root")
  }
  const workflow = readJson(file, "BIEXCE Autopilot workflow state").value
  if (!exactKeys(workflow, WORKFLOW_KEYS)) {
    throw new Error("workflow state properties mismatch")
  }
  if (workflow.$schema !== WORKFLOW_SCHEMA || workflow.schema_version !== 1) {
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


function delegationLockPath(projectRoot) {
  return path.join(projectRoot, ".biexce", "state", "AUTOPILOT_DELEGATION.lock")
}


function processAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false
  try {
    process.kill(pid, 0)
    return true
  } catch (error) {
    return error.code === "EPERM"
  }
}


function acquireDelegationLock(projectRoot, context, workflow) {
  const file = delegationLockPath(projectRoot)
  const payload = `${JSON.stringify({
    pid: process.pid,
    host: os.hostname(),
    session_id: context.sessionID,
    phase: workflow.phase,
    created_at_utc: new Date().toISOString(),
  })}\n`
  for (let attempt = 0; attempt < 2; attempt += 1) {
    let descriptor = null
    try {
      descriptor = fs.openSync(file, "wx", 0o600)
      fs.writeFileSync(descriptor, payload, "utf8")
      return { descriptor, file }
    } catch (error) {
      if (descriptor !== null) {
        try {
          fs.closeSync(descriptor)
        } finally {
          if (fs.existsSync(file)) fs.unlinkSync(file)
        }
      }
      if (error.code !== "EEXIST") throw error
      const stat = fs.lstatSync(file)
      if (!stat.isFile() || stat.isSymbolicLink()) {
        throw new Error("delegation lock is not a regular file")
      }
      let owner
      try {
        owner = JSON.parse(fs.readFileSync(file, "utf8"))
      } catch {
        throw new Error("delegation lock exists and is unreadable")
      }
      if (owner.host === os.hostname() && !processAlive(owner.pid)) {
        fs.unlinkSync(file)
        continue
      }
      throw new Error(
        `BIEXCE_AUTOPILOT_DENY: WIP=1 lock is held by ${owner.host || "unknown"}/${owner.pid || "unknown"}`,
      )
    }
  }
  throw new Error("BIEXCE_AUTOPILOT_DENY: WIP=1 lock could not be acquired")
}


function releaseDelegationLock(lock) {
  if (lock === null) return
  try {
    fs.closeSync(lock.descriptor)
  } finally {
    if (fs.existsSync(lock.file)) fs.unlinkSync(lock.file)
  }
}


function taskDependencies(projectRoot, taskID) {
  const file = path.join(projectRoot, ".biexce", "tasks", `${taskID}.md`)
  const text = fs.readFileSync(file, "utf8")
  const match = text.match(/^Depends on:\s*(.+?)(?:\s*[·|]\s*Effort:|$)/im)
  if (!match || match[1].trim().toLowerCase() === "none") return []
  return match[1].match(/t-[0-9]{3}/g) || []
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


function requirePhaseInput(projectRoot, workflow) {
  if (workflow.phase === "EXPLORE") {
    requireFile(projectRoot, ".biexce/PROJECT_BRIEF.md", "PROJECT_BRIEF")
  }
  if (workflow.phase === "PLAN") {
    requireFile(projectRoot, ".biexce/CODEBASE_BRIEF.md", "CODEBASE_BRIEF")
  }
  if (workflow.phase === "PLAN_REVIEW") {
    requireFile(projectRoot, ".biexce/MASTER_PLAN.md", "MASTER_PLAN")
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


function verdict(output, allowed) {
  const lines = output.trim().split(/\r?\n/).filter((line) => line.trim())
  const finalLine = lines.at(-1)?.trim() || ""
  const match = finalLine.match(/^VERDICT:\s*(.+?)\s*$/i)
  if (!match) {
    throw new Error("agent result must end with 'VERDICT: <value>'")
  }
  const value = match[1].toUpperCase()
  if (!allowed.includes(value)) {
    throw new Error(`invalid verdict '${value}', expected ${allowed.join(" | ")}`)
  }
  return value
}


function runtimeContract(workflow) {
  if (workflow.phase === 'EXPLORE') {
    return (
      'Create or update the managed artifact at exactly ' +
      '`.biexce/CODEBASE_BRIEF.md` before returning. A green-field or empty ' +
      'repository is valid: record that fact and the planned layout instead ' +
      'of skipping the artifact. Do not return only a chat summary.'
    )
  }
  if (["PLAN_REVIEW", "TASK_REVIEW", "INTEGRATION_REVIEW"].includes(workflow.phase)) {
    return "End the response with one exact VERDICT line required by your role contract."
  }
  if (["TEST", "INTEGRATION_TEST"].includes(workflow.phase)) {
    return "End the response with exactly VERDICT: PASS, VERDICT: FAIL, or VERDICT: INCONCLUSIVE."
  }
  return "Complete the requested artifact/result and return concise evidence to BX Director."
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


function advanceWorkflow(projectRoot, workflow, agent, output) {
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
    loadProjectState(projectRoot)
    return saveWorkflow(projectRoot, workflow, {
      phase: "PLAN_REVIEW",
      last_agent: agent,
      last_result: "PLAN_READY",
      blocked_reason: null,
    })
  }
  if (workflow.phase === "PLAN_REVIEW") {
    const result = verdict(output, ["PLAN OK", "PLAN NEEDS REVISION"])
    if (result === "PLAN OK") {
      return saveWorkflow(projectRoot, workflow, {
        phase: "WAITING_GATE_1",
        last_agent: agent,
        last_result: result,
        blocked_reason: null,
      })
    }
    if (workflow.plan_revision >= 2) {
      return blockWorkflow(
        projectRoot,
        workflow,
        agent,
        result,
        "Plan revision cap reached",
      )
    }
    return saveWorkflow(projectRoot, workflow, {
      phase: "PLAN",
      plan_revision: workflow.plan_revision + 1,
      last_agent: agent,
      last_result: result,
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
    const result = verdict(output, ["PASS", "FAIL", "INCONCLUSIVE"])
    if (result === "FAIL") return routeFix(projectRoot, workflow, agent, result)
    if (result === "INCONCLUSIVE") {
      return blockWorkflow(
        projectRoot,
        workflow,
        agent,
        result,
        `Test was inconclusive for ${workflow.current_task_id}`,
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
    const result = verdict(output, [
      "APPROVE",
      "APPROVE WITH MINOR NOTES",
      "CHANGES REQUIRED",
    ])
    if (result === "CHANGES REQUIRED") {
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
    const result = verdict(output, ["PASS", "FAIL", "INCONCLUSIVE"])
    if (result !== "PASS") {
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
  if (workflow.phase === "INTEGRATION_REVIEW") {
    const result = verdict(output, [
      "APPROVE",
      "APPROVE WITH MINOR NOTES",
      "CHANGES REQUIRED",
    ])
    if (result === "CHANGES REQUIRED") {
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


function opencodeRoot() {
  if (process.env.BIEXCE_OPENCODE_CONFIG_DIR) {
    return path.resolve(process.env.BIEXCE_OPENCODE_CONFIG_DIR)
  }
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
}


function cliEntrypoint() {
  const file = process.env.BIEXCE_CLI_ENTRYPOINT
    ? path.resolve(process.env.BIEXCE_CLI_ENTRYPOINT)
    : path.join(opencodeRoot(), "biexce-cli", "scripts", "biexce.py")
  const stat = fs.lstatSync(file)
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error(`BIEXCE CLI entrypoint is not a regular file: ${file}`)
  }
  return file
}


function approveGateThroughCli(projectRoot, gate) {
  const python = process.env.BIEXCE_PYTHON ||
    (process.platform === "win32" ? "python.exe" : "python3")
  const result = spawnSync(
    python,
    [
      cliEntrypoint(),
      "autopilot",
      "approve",
      "--gate",
      String(gate),
      "--project",
      projectRoot,
      "--config-home",
      configHome(),
      "--opencode-config-dir",
      opencodeRoot(),
      "--json",
    ],
    {
      encoding: "utf8",
      env: process.env,
      timeout: 30000,
      windowsHide: true,
    },
  )
  if (result.error) throw new Error(`Gate approval process failed: ${result.error.message}`)
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || "unknown failure").trim()
    throw new Error(`Gate approval validation failed: ${detail}`)
  }
  const lines = result.stdout.trim().split(/\r?\n/).filter(Boolean)
  try {
    return JSON.parse(lines.at(-1))
  } catch {
    throw new Error("Gate approval process returned invalid JSON")
  }
}


export const BiexceControlPlugin = async ({ client }) => {
  let defaultAgent = "bx-code"
  let delegationActive = false

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
      }
      config.agent['bx-director'].permission ||= {}
      config.agent['bx-director'].permission.biexce_delegate = 'allow'
      config.agent['bx-director'].permission.biexce_gate = 'allow'
      config.agent['bx-director'].permission.biexce_gate_approval = 'ask'
    },

    "permission.ask": async (input, output) => {
      if (input.permission === "biexce_gate_approval") output.status = "ask"
    },

    "chat.message": async (input) => {
      const agent = input.agent || defaultAgent
      if (!AGENTS.includes(agent)) return
      const routing = loadAppliedRouting()
      if (!routing.agents[agent]?.primary) {
        throw new Error(`BIEXCE_MODEL_BLOCKED: ${agent} is unconfigured`)
      }
      if (!input.model) throw new Error("BIEXCE_MODEL_BLOCKED: actual model is unavailable")

    },

    tool: {
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
          const workflow = loadWorkflow(projectRoot)
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
          loadRunningState(context.directory, context.sessionID)
          const current = loadWorkflow(projectRoot)
          if (
            current.phase !== workflow.phase ||
            current.revision !== workflow.revision
          ) {
            throw new Error("BIEXCE_GATE_DENY: workflow changed while awaiting approval")
          }
          const payload = approveGateThroughCli(projectRoot, gate)
          const next = loadWorkflow(projectRoot)
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
              next_agent: PHASE_AGENTS[next.phase] || null,
              control_mode: payload.mode,
            },
          }
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
        async execute(args, context) {
          if (context.agent !== "bx-director") {
            throw new Error("BIEXCE_AUTOPILOT_DENY: only bx-director may delegate")
          }
          loadRunningState(context.directory, context.sessionID)
          const projectRoot = fs.realpathSync(context.directory)
          const workflow = loadWorkflow(projectRoot)
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
          if (delegationActive) {
            throw new Error("BIEXCE_AUTOPILOT_DENY: WIP=1 already has an active task")
          }
          delegationActive = true
          let delegationLock = null
          let projectSnapshot = null
          try {
            delegationLock = acquireDelegationLock(projectRoot, context, workflow)
            projectSnapshot = beginTaskDelegation(projectRoot, workflow)
            const routing = loadAppliedRouting()
            const binding = routing.agents[args.agent]
            if (!binding?.primary) {
              throw new Error(`BIEXCE_MODEL_BLOCKED: ${args.agent} is unconfigured`)
            }
            const created = resultData(
              await client.session.create({
                body: { parentID: context.sessionID, title: args.description },
                query: { directory: context.directory },
              }),
              "child session creation",
            )
            loadRunningState(context.directory, context.sessionID)
            const response = resultData(
              await client.session.prompt({
                path: { id: created.id },
                query: { directory: context.directory },
                body: {
                  agent: args.agent,
                  model: splitModel(binding.primary),
                  parts: [{
                    type: "text",
                    text: `${args.prompt}\n\n[BIEXCE RUNTIME CONTRACT]\n${runtimeContract(workflow)}`,
                  }],
                },
              }),
              "child session prompt",
            )
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
            const nextWorkflow = advanceWorkflow(
              projectRoot,
              workflow,
              args.agent,
              output,
            )
            projectSnapshot = null
            return {
              title: `${args.agent}: ${args.description}`,
              output: output || "Child completed without a text response.",
              metadata: {
                child_session_id: created.id,
                configured_model: binding.primary,
                fallbacks: binding.fallbacks,
                completed_phase: workflow.phase,
                next_phase: nextWorkflow.phase,
                next_agent: PHASE_AGENTS[nextWorkflow.phase] || null,
                current_task_id: nextWorkflow.current_task_id,
                fix_round: nextWorkflow.fix_round,
              },
            }
          } catch (error) {
            if (projectSnapshot !== null) {
              saveProjectState(projectRoot, projectSnapshot)
            }
            throw new Error(`BIEXCE_AUTOPILOT_ERROR: ${error.message}`)
          } finally {
            releaseDelegationLock(delegationLock)
            delegationActive = false
          }
        },
      }),
    },
  }
}
