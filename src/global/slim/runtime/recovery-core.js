const RECOVERY_TAG = "biexce.restart-recovery.v1"
const INCOMPLETE = new Set(["pending", "in_progress"])


function responseData(response) {
  return response?.data
}


function isActive(status, sessionID) {
  const type = status?.[sessionID]?.type
  return type === "busy" || type === "retry"
}


function lastOrchestratorMessage(messages) {
  return [...messages].reverse().find(
    (entry) =>
      entry?.info?.role === "user" &&
      entry.info.agent === "orchestrator",
  )
}


function incompleteTodos(todos) {
  return todos.filter((todo) => INCOMPLETE.has(todo?.status))
}


function childSnapshot(children, status) {
  if (children.length === 0) return "- no child sessions"
  return children
    .map((child) => {
      const state = status?.[child.id]?.type ?? "idle-or-stopped"
      return `- ${child.id} | ${state} | ${child.title ?? "untitled"}`
    })
    .join("\n")
}


export function buildRecoveryPrompt(todos, children, status) {
  const todoLines = todos
    .map((todo) => `- ${todo.id ?? "todo"} | ${todo.status} | ${todo.content}`)
    .join("\n")
  return `<system-reminder data-biexce-recovery="${RECOVERY_TAG}">
OpenCode restarted while this BIEXCE workflow had incomplete work.

Incomplete native TODOs:
${todoLines}

Native child sessions:
${childSnapshot(children, status)}

Resume autonomously from the current workspace and native session evidence.
Inspect existing artifacts before dispatching. If a child is active, monitor it;
if a terminal result exists, reconcile it; if a child stopped without a result,
inspect partial changes and re-dispatch only the unfinished lane with the same
role and ownership. Never redo verified completed work.
Do not recreate an existing Brief or Plan. Do not create a BIEXCE scheduler,
lock, WIP file, or custom workflow state. Ask the user only for a genuine
safety, access, destructive, production, or product decision.
Do not respond to this reminder with status only; continue the workflow.
</system-reminder>`
}


async function readCandidate(sessionApi, session, directory, status) {
  const [todoResponse, childResponse, messageResponse] = await Promise.all([
    sessionApi.todo(
      {
        path: { id: session.id },
        query: { directory },
        throwOnError: true,
      },
    ),
    sessionApi.children(
      {
        path: { id: session.id },
        query: { directory },
        throwOnError: true,
      },
    ),
    sessionApi.messages(
      {
        path: { id: session.id },
        query: { directory, limit: 30 },
        throwOnError: true,
      },
    ),
  ])
  const todos = responseData(todoResponse)
  const children = responseData(childResponse)
  const messages = responseData(messageResponse)
  if (!Array.isArray(todos) || !Array.isArray(children) || !Array.isArray(messages)) {
    return undefined
  }
  const pending = incompleteTodos(todos)
  const initiator = lastOrchestratorMessage(messages)
  if (pending.length === 0 || !initiator || isActive(status, session.id)) {
    return undefined
  }
  return { session, todos: pending, children, initiator }
}


export async function recoverInterruptedParent(client, directory) {
  const sessionApi = client?.session
  if (!sessionApi) return { status: "unsupported" }
  const [listResponse, statusResponse] = await Promise.all([
    sessionApi.list({ query: { directory }, throwOnError: true }),
    sessionApi.status({ query: { directory }, throwOnError: true }),
  ])
  const sessions = responseData(listResponse)
  const status = responseData(statusResponse)
  if (!Array.isArray(sessions) || !status || typeof status !== "object") {
    return { status: "unsupported" }
  }
  const roots = sessions
    .filter((session) => !session.parentID && session.directory === directory)
    .sort((left, right) => (right.time?.created ?? 0) - (left.time?.created ?? 0))
  for (const session of roots) {
    const candidate = await readCandidate(sessionApi, session, directory, status)
    if (!candidate) continue
    const model = candidate.initiator.info.model
    await sessionApi.promptAsync(
      {
        path: { id: session.id },
        query: { directory },
        body: {
          agent: "orchestrator",
          ...(model ? { model } : {}),
          parts: [{
            type: "text",
            text: buildRecoveryPrompt(candidate.todos, candidate.children, status),
            synthetic: true,
            metadata: { "biexce.restartRecovery": RECOVERY_TAG },
          }],
        },
        throwOnError: true,
      },
    )
    return { status: "woken", sessionID: session.id }
  }
  return { status: "nothing-to-recover" }
}
