const STATUSES = new Set([
  "QUEUED",
  "RUNNING",
  "RETRYING",
  "FALLBACK",
  "DONE",
  "ERROR",
  "CANCELLED",
  "TIMED_OUT",
])


function text(value, fallback = null) {
  return typeof value === "string" && value.trim() ? value.trim() : fallback
}


function finite(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null
}


export function childSessionTitle({ agent, phase, taskId = null }) {
  const cleanAgent = text(agent, "bx-agent")
  const cleanPhase = text(phase, "WORK").toUpperCase()
  const subject = text(taskId, "project")
  return `[BX][${subject}][${cleanPhase}] ${cleanAgent}`
}


export function responseUsage(response) {
  const source = response?.info || response
  const tokens = source?.tokens
  const durationMs =
    finite(source?.time?.created) !== null &&
    finite(source?.time?.completed) !== null &&
    source.time.completed >= source.time.created
      ? source.time.completed - source.time.created
      : null
  if ((!tokens || typeof tokens !== "object") && durationMs === null) return null
  const usage = {
    inputTokens: finite(tokens?.input),
    outputTokens: finite(tokens?.output),
    reasoningTokens: finite(tokens?.reasoning),
    cacheReadTokens: finite(tokens?.cache?.read),
    cacheWriteTokens: finite(tokens?.cache?.write),
    cost: finite(source?.cost),
    durationMs,
  }
  if (Object.values(usage).every((value) => value === null)) return null
  return Object.fromEntries(
    Object.entries(usage).filter(([, value]) => value !== null),
  )
}


export function observabilityUpdate({
  parentSessionId,
  sessionId = null,
  jobId = null,
  traceId = null,
  agent,
  phase,
  taskId = null,
  status,
  configuredModel = null,
  actualModel = null,
  modelZone = null,
  attempt = 1,
  fallbackUsed = false,
  sessionResumed = false,
  schedulerRevision = null,
  dependencies = [],
  nextPhase = null,
  nextAgent = null,
  resultStatus = null,
  errorCode = null,
  errorKind = null,
  usage = null,
  evidence = [],
} = {}) {
  const cleanAgent = text(agent, "bx-agent")
  const cleanPhase = text(phase, "WORK").toUpperCase()
  const cleanStatus = text(status, "RUNNING").toUpperCase()
  if (!STATUSES.has(cleanStatus)) {
    throw new Error(`unsupported observability status: ${cleanStatus}`)
  }
  const cleanTask = text(taskId, null)
  const cleanAttempt = Number.isInteger(attempt) && attempt > 0 ? attempt : 1
  const titleParts = [
    cleanAgent,
    cleanStatus,
    cleanTask || cleanPhase,
    cleanPhase,
  ]
  if (["RETRYING", "FALLBACK"].includes(cleanStatus)) {
    titleParts.push(`attempt ${cleanAttempt}`)
  }
  const metadata = {
    contract: "biexce-observability-v1",
    transport: "opencode-session",
    parentSessionId: text(parentSessionId, null),
    sessionId: text(sessionId, null),
    jobId: text(jobId, null),
    traceId: text(traceId, null),
    agent: cleanAgent,
    phase: cleanPhase,
    taskId: cleanTask,
    runtimeStatus: cleanStatus,
    configuredModel: text(configuredModel, null),
    actualModel: text(actualModel, null),
    modelZone: text(modelZone, null),
    attempt: cleanAttempt,
    fallbackUsed: Boolean(fallbackUsed),
    sessionResumed: Boolean(sessionResumed),
    schedulerRevision:
      Number.isInteger(schedulerRevision) ? schedulerRevision : null,
    dependencies: Array.isArray(dependencies)
      ? dependencies.filter((value) => typeof value === "string")
      : [],
    nextPhase: text(nextPhase, null),
    nextAgent: text(nextAgent, null),
    resultStatus: text(resultStatus, null),
    errorCode: text(errorCode, null),
    errorKind: text(errorKind, null),
    usage: usage && typeof usage === "object" ? usage : null,
    evidence: Array.isArray(evidence)
      ? evidence.filter((value) => typeof value === "string")
      : [],
  }
  return { title: titleParts.join(" | "), metadata }
}
