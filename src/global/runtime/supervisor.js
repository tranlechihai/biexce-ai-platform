import { spawn, spawnSync } from "node:child_process"
import fs from "node:fs"
import path from "node:path"


export class SupervisorError extends Error {
  constructor(code, message) {
    super(message)
    this.name = "SupervisorError"
    this.code = code
  }
}


export function isLongLivedServerCommand(command) {
  if (typeof command !== "string") return false
  const normalized = command.toLowerCase().replace(/\s+/g, " ").trim()
  const serverPatterns = [
    /(^|\s)uvicorn(\s|$)/,
    /python(?:\.exe|3)?\s+-m\s+uvicorn(\s|$)/,
    /python(?:\.exe|3)?\s+-m\s+http\.server(\s|$)/,
    /(^|\s)flask\s+run(\s|$)/,
    /manage\.py\s+runserver(\s|$)/,
    /(^|\s)npm\s+run\s+dev(\s|$)/,
    /(^|\s)(npm|pnpm|yarn)\s+start(\s|$)/,
    /(^|\s)next\s+dev(\s|$)/,
    /(^|\s)vite(\s|$)/,
    /(^|\s)dotnet\s+run(\s|$)/,
    /(^|\s)rails\s+(server|s)(\s|$)/,
    /(^|\s)php\s+-s\s+/,
  ]
  return serverPatterns.some((pattern) => pattern.test(normalized))
}


function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}


function validateInteger(value, label, minimum, maximum) {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(
      label + " must be between " + minimum + " and " + maximum
    )
  }
  return value
}


function windowsTaskKill(pid, force) {
  const arguments_ = ["/PID", String(pid), "/T"]
  if (force) arguments_.push("/F")
  spawnSync("taskkill.exe", arguments_, {
    windowsHide: true,
    stdio: "ignore",
  })
}


function signalProcessTree(child, signal) {
  if (!child.pid) return
  try {
    if (process.platform === "win32") {
      if (signal === "SIGKILL") windowsTaskKill(child.pid, true)
      else windowsTaskKill(child.pid, false)
    } else {
      process.kill(-child.pid, signal)
    }
  } catch {
    try {
      child.kill(signal)
    } catch {
      // The process already exited.
    }
  }
}


async function terminateProcessTree(entry, graceMs) {
  if (entry.closed) return
  signalProcessTree(entry.child, "SIGTERM")
  await Promise.race([entry.closedPromise, delay(graceMs)])
  if (!entry.closed) {
    signalProcessTree(entry.child, "SIGKILL")
    await Promise.race([entry.closedPromise, delay(Math.min(graceMs, 1000))])
  }
}


function cappedCollector(limitBytes) {
  const chunks = { stdout: [], stderr: [] }
  let captured = 0
  let truncated = false
  return {
    push(stream, chunk) {
      const source = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
      const available = Math.max(0, limitBytes - captured)
      if (source.length > available) truncated = true
      if (available > 0) {
        const kept = source.subarray(0, available)
        chunks[stream].push(kept)
        captured += kept.length
      }
    },
    result() {
      return {
        stdout: Buffer.concat(chunks.stdout).toString("utf8"),
        stderr: Buffer.concat(chunks.stderr).toString("utf8"),
        truncated,
      }
    },
  }
}


export function createRuntimeSupervisor({
  client,
  logLimitBytes = 64 * 1024,
  hardKillGraceMs = 1000,
} = {}) {
  if (!client) throw new Error("supervisor requires an OpenCode client")
  validateInteger(logLimitBytes, "logLimitBytes", 32, 4 * 1024 * 1024)
  validateInteger(hardKillGraceMs, "hardKillGraceMs", 10, 30000)
  const sessions = new Map()

  function ensureSession(sessionID, directory) {
    let record = sessions.get(sessionID)
    if (!record) {
      record = {
        sessionID,
        directory,
        processes: new Map(),
        promptRejectors: new Set(),
        cancelling: null,
      }
      sessions.set(sessionID, record)
    } else if (path.resolve(record.directory) !== path.resolve(directory)) {
      throw new Error("supervised session directory mismatch")
    }
    return record
  }

  async function abortClientSession(record) {
    if (typeof client?.session?.abort !== "function") return
    const request = Promise.resolve().then(() => client.session.abort({
        path: { id: record.sessionID },
        query: { directory: record.directory },
      })).catch(() => undefined)
    await Promise.race([request, delay(hardKillGraceMs)])
  }

  async function cancelSession(sessionID, code, message) {
    const record = sessions.get(sessionID)
    if (!record) return
    if (record.cancelling) return record.cancelling
    record.cancelling = Promise.all([
      ...[...record.processes.values()].map((entry) =>
        entry.cancel(code, message)
      ),
      abortClientSession(record),
    ]).then(() => {
      for (const rejectPrompt of record.promptRejectors) {
        rejectPrompt(code, message)
      }
    })
    return record.cancelling
  }

  async function closeSession(sessionID) {
    const record = sessions.get(sessionID)
    if (!record) return
    if (record.cancelling) {
      await record.cancelling
    } else {
      await Promise.all(
        [...record.processes.values()].map((entry) =>
          entry.cancel("SESSION_CLOSED", "child session finished")
        ),
      )
    }
    sessions.delete(sessionID)
  }

  async function supervisePrompt({
    childID,
    directory,
    body,
    timeoutMs,
    signal,
    controlCheck,
    pollMs,
  }) {
    validateInteger(timeoutMs, "timeoutMs", 100, 4 * 60 * 60 * 1000)
    validateInteger(pollMs, "pollMs", 50, 10000)
    ensureSession(childID, directory)
    let timer = null
    let poll = null
    let abortListener = null
    let cancellationStarted = false
    let rejectCancellation
    const cancellation = new Promise((_, reject) => {
      rejectCancellation = reject
    })
    const rejectFromSession = (code, message) => {
      if (cancellationStarted) return
      cancellationStarted = true
      rejectCancellation(new SupervisorError(code, message))
    }
    const record = ensureSession(childID, directory)
    record.promptRejectors.add(rejectFromSession)
    const trigger = (code, message) => {
      if (cancellationStarted) return
      void cancelSession(childID, code, message).finally(() => {
        rejectFromSession(code, message)
      })
    }
    timer = setTimeout(
      () => trigger(
        "TIMEOUT",
        "child session timed out after " + timeoutMs + "ms",
      ),
      timeoutMs,
    )
    poll = setInterval(() => {
      try {
        controlCheck()
      } catch (error) {
        trigger(
          "CONTROL_STOPPED",
          "child cancelled because control stopped: " + error.message,
        )
      }
    }, pollMs)
    if (signal) {
      abortListener = () =>
        trigger("CANCELLED", "child session cancelled from OpenCode")
      if (signal.aborted) abortListener()
      else signal.addEventListener("abort", abortListener, { once: true })
    }
    const prompt = Promise.resolve().then(() => client.session.prompt({
      path: { id: childID },
      query: { directory },
      body,
    }))
    try {
      return await Promise.race([prompt, cancellation])
    } finally {
      clearTimeout(timer)
      clearInterval(poll)
      if (signal && abortListener) {
        signal.removeEventListener("abort", abortListener)
      }
      record.promptRejectors.delete(rejectFromSession)
    }
  }

  async function runCommand({
    sessionID,
    directory,
    command,
    timeoutMs,
    signal,
    environment = {},
  }) {
    if (typeof command !== "string" || !command.trim()) {
      throw new Error("managed command must be a non-empty string")
    }
    if (isLongLivedServerCommand(command)) {
      throw new SupervisorError(
        "PROCESS_DENY",
        "persistent development servers are not allowed; use TestClient or a test runner-owned webServer",
      )
    }
    validateInteger(timeoutMs, "command timeoutMs", 100, 60 * 60 * 1000)
    const resolvedDirectory = fs.realpathSync(directory)
    const record = ensureSession(sessionID, resolvedDirectory)
    if (record.cancelling) {
      throw new SupervisorError("CANCELLED", "child session is already cancelling")
    }
    const started = Date.now()
    const collector = cappedCollector(logLimitBytes)
    const child = spawn(command, {
      cwd: resolvedDirectory,
      env: { ...process.env, ...environment },
      shell: true,
      detached: process.platform !== "win32",
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    })
    const processID = String(child.pid || "pending") + "-" + started
    let closed = false
    let forcedError = null
    let resolveClosed
    const closedPromise = new Promise((resolve) => {
      resolveClosed = resolve
    })
    const entry = {
      child,
      get closed() { return closed },
      closedPromise,
      async cancel(code, message) {
        forcedError ||= new SupervisorError(code, message)
        await terminateProcessTree(entry, hardKillGraceMs)
      },
    }
    record.processes.set(processID, entry)
    child.stdout?.on("data", (chunk) => collector.push("stdout", chunk))
    child.stderr?.on("data", (chunk) => collector.push("stderr", chunk))
    let timer = null
    let abortListener = null
    const completion = new Promise((resolve, reject) => {
      child.once("error", (error) => {
        closed = true
        resolveClosed()
        reject(forcedError || error)
      })
      child.once("close", (exitCode, exitSignal) => {
        closed = true
        resolveClosed()
        if (forcedError) {
          reject(forcedError)
          return
        }
        resolve({
          exit_code: Number.isInteger(exitCode) ? exitCode : -1,
          signal: exitSignal || null,
          ...collector.result(),
          duration_ms: Date.now() - started,
        })
      })
    })
    timer = setTimeout(() => {
      void entry.cancel(
        "COMMAND_TIMEOUT",
        "managed command timed out after " + timeoutMs + "ms",
      )
    }, timeoutMs)
    if (signal) {
      abortListener = () => {
        void entry.cancel("CANCELLED", "managed command cancelled")
      }
      if (signal.aborted) abortListener()
      else signal.addEventListener("abort", abortListener, { once: true })
    }
    try {
      return await completion
    } finally {
      clearTimeout(timer)
      if (signal && abortListener) {
        signal.removeEventListener("abort", abortListener)
      }
      record.processes.delete(processID)
    }
  }

  async function shutdown(message = "runtime shutdown") {
    await Promise.all(
      [...sessions].map(([sessionID]) =>
        cancelSession(sessionID, "CANCELLED", message)
      ),
    )
    sessions.clear()
  }

  return {
    supervisePrompt,
    runCommand,
    cancelSession,
    closeSession,
    shutdown,
    activeSessionCount: () => sessions.size,
  }
}
