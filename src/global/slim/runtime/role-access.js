const DIRECTOR_ID = "orchestrator"
const LEGACY_DIRECTOR_ALIAS = "bx-director"

export const SPECIALIST_IDS = Object.freeze([
  "bx-plan",
  "bx-explore",
  "bx-code",
  "bx-fix",
  "bx-test",
  "bx-review",
])


export function exposeUserFacingRoles(config) {
  const agents = config?.agent
  if (!agents || typeof agents !== "object") {
    return { ok: false, missing: [DIRECTOR_ID, ...SPECIALIST_IDS] }
  }

  const missing = []
  delete agents[LEGACY_DIRECTOR_ALIAS]

  const director = agents[DIRECTOR_ID]
  if (director && typeof director === "object") {
    director.mode = "primary"
    delete director.hidden
  } else {
    missing.push(DIRECTOR_ID)
  }

  for (const id of SPECIALIST_IDS) {
    const specialist = agents[id]
    if (specialist && typeof specialist === "object") {
      specialist.mode = "all"
      delete specialist.hidden
    } else {
      missing.push(id)
    }
  }

  return { ok: missing.length === 0, missing }
}
