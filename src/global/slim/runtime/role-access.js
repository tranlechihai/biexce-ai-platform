const DIRECTOR_ID = "orchestrator"
const DIRECTOR_ALIAS = "bx-director"

export const SPECIALIST_IDS = Object.freeze([
  "bx-plan",
  "bx-explore",
  "bx-code",
  "bx-fix",
  "bx-test",
  "bx-review",
])

function matchingKeys(agents, expected) {
  const normalized = expected.toLowerCase()
  return Object.keys(agents).filter(
    (key) => key.toLowerCase() === normalized,
  )
}

function keepCanonicalKey(agents, expected) {
  const keys = matchingKeys(agents, expected)
  let canonical = keys.find((key) => key === expected)
  if (!canonical && keys.length > 0) {
    canonical = expected
    agents[canonical] = agents[keys[0]]
  }
  for (const key of keys) {
    if (key !== canonical) delete agents[key]
  }
  return canonical
}

export function exposeUserFacingRoles(config) {
  const agents = config?.agent
  if (!agents || typeof agents !== "object") {
    return { ok: false, missing: [DIRECTOR_ID, ...SPECIALIST_IDS] }
  }

  const missing = []
  const internalDirector = agents[DIRECTOR_ID]
  const directorKey = keepCanonicalKey(agents, DIRECTOR_ALIAS)
  const director = directorKey ? agents[directorKey] : undefined

  if (!internalDirector || typeof internalDirector !== "object") {
    missing.push(DIRECTOR_ID)
  }
  if (director && typeof director === "object") {
    director.mode = "primary"
    delete director.hidden
    config.default_agent = directorKey
  } else {
    missing.push(DIRECTOR_ALIAS)
  }

  if (internalDirector && typeof internalDirector === "object") {
    internalDirector.mode = "subagent"
    internalDirector.hidden = true
  }

  for (const id of SPECIALIST_IDS) {
    const specialistKey = keepCanonicalKey(agents, id)
    const specialist = specialistKey ? agents[specialistKey] : undefined
    if (specialist && typeof specialist === "object") {
      specialist.mode = "all"
      delete specialist.hidden
    } else {
      missing.push(id)
    }
  }

  return { ok: missing.length === 0, missing }
}
