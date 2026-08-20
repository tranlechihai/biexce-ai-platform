import { recoverInterruptedParent } from "../runtime/recovery-core.js"


const SERVICE = "biexce-recovery"
const EVENT_DELAY = 1500
const START_DELAY = 1500
const RETRY_DELAY = 3000


async function writeLog(client, level, message, extra = {}) {
  try {
    await client.app.log({
      body: { service: SERVICE, level, message, extra },
    })
  } catch {
    // Recovery must not make OpenCode startup fail because logging is unavailable.
  }
}


export const BiexceRecoveryPlugin = async ({ client, directory }) => {
  const seen = new Set()
  let failures = 0
  let running = false
  let queued = false
  let timer

  const schedule = (delay = EVENT_DELAY) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = undefined
      void run()
    }, delay)
  }

  const run = async () => {
    if (running) {
      queued = true
      return
    }
    running = true
    try {
      const result = await recoverInterruptedParent(
        client,
        directory,
        { seen },
      )
      failures = 0
      await writeLog(client, "info", "Recovery sweep checked", result)
    } catch (error) {
      failures += 1
      await writeLog(client, "warn", "Recovery sweep failed", {
        attempt: failures,
        error: error instanceof Error ? error.message : String(error),
      })
      if (failures < 2) schedule(RETRY_DELAY)
    } finally {
      running = false
      if (queued) {
        queued = false
        schedule(250)
      }
    }
  }

  schedule(START_DELAY)
  return {
    event: async ({ event }) => {
      if (event.type === "server.connected") schedule(250)
      if (event.type === "session.idle") schedule()
      if (event.type === "session.error") schedule()
      if (event.type === "todo.updated") schedule()
      if (
        event.type === "session.status" &&
        event.properties?.status?.type === "idle"
      ) {
        schedule()
      }
    },
  }
}
