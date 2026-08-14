import { recoverInterruptedParent } from "../runtime/recovery-core.js"


const SERVICE = "biexce-recovery"


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
  let attempts = 0
  let completed = false
  let running = false

  const run = async () => {
    if (completed || running) return
    running = true
    attempts += 1
    try {
      const result = await recoverInterruptedParent(client, directory)
      completed = result.status !== "unsupported"
      await writeLog(client, "info", "Restart recovery checked", result)
    } catch (error) {
      await writeLog(client, "warn", "Restart recovery failed", {
        attempt: attempts,
        error: error instanceof Error ? error.message : String(error),
      })
    } finally {
      running = false
      if (!completed && attempts < 2) setTimeout(run, 3000)
    }
  }

  setTimeout(run, 1500)
  return {
    event: async ({ event }) => {
      if (event.type === "server.connected") setTimeout(run, 250)
    },
  }
}
