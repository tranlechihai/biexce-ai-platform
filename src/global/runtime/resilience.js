export const ERROR_KINDS = new Set([
  "TRANSPORT",
  "RATE_LIMIT",
  "OVERLOADED",
  "MODEL_UNAVAILABLE",
  "CONTEXT_OVERFLOW",
  "AUTH",
  "PERMISSION",
  "INVALID_REQUEST",
  "CONTRACT",
  "TIMEOUT",
  "CANCELLED",
  "UNKNOWN",
])


function errorText(error) {
  const fields = [
    error?.code,
    error?.name,
    error?.message,
    error?.status,
    error?.statusCode,
  ]
  try {
    fields.push(JSON.stringify(error?.data || error?.cause || null))
  } catch {
    // Ignore non-serializable SDK error details.
  }
  return fields.filter(Boolean).join(" ").toLowerCase()
}


export function classifyRuntimeError(error) {
  if (error?.code === "CANCELLED" || error?.code === "CONTROL_STOPPED") {
    return "CANCELLED"
  }
  if (error?.code === "TIMEOUT" || error?.code === "COMMAND_TIMEOUT") {
    return "TIMEOUT"
  }
  const text = errorText(error)
  if (
    /\babort(?:ed|ing)?\b|\bcancel(?:led|ing|lation)?\b|operation was canceled/.test(text)
  ) return "CANCELLED"
  if (
    /context.{0,20}(length|window|limit)|too many tokens|token.{0,20}limit/.test(text)
  ) return "CONTEXT_OVERFLOW"
  if (/rate.?limit|\b429\b|too many requests/.test(text)) return "RATE_LIMIT"
  if (/overload|capacity|temporarily unavailable|\b503\b/.test(text)) {
    return "OVERLOADED"
  }
  if (
    /model.{0,30}(not found|unavailable|does not exist)|no route for model/.test(text)
  ) return "MODEL_UNAVAILABLE"
  if (/unauthorized|authentication|invalid api key|\b401\b/.test(text)) {
    return "AUTH"
  }
  if (/forbidden|permission denied|\b403\b/.test(text)) return "PERMISSION"
  if (/bad request|invalid request|\b400\b|validation error/.test(text)) {
    return "INVALID_REQUEST"
  }
  if (
    /agent result|result_json|biexce_submit_result|changed_files/.test(text) ||
    /declared artifact|writable scope|runtime diff/.test(text) ||
    /\b(?:pass|fail|inconclusive) requires\b/.test(text)
  ) return "CONTRACT"
  if (
    /econnreset|econnrefused|enetunreach|ehostunreach|fetch failed|network|socket|gateway|\b502\b|\b504\b|unexpected server error/.test(text)
  ) return "TRANSPORT"
  return "UNKNOWN"
}


export function isRetryableKind(kind) {
  return ["TRANSPORT", "RATE_LIMIT", "OVERLOADED"].includes(kind)
}


export function isFallbackKind(kind) {
  return [
    "TRANSPORT",
    "RATE_LIMIT",
    "OVERLOADED",
    "MODEL_UNAVAILABLE",
    "CONTEXT_OVERFLOW",
  ].includes(kind)
}


export function modelZone(model) {
  return model.startsWith("biexce-local/") ? "local" : "cloud"
}


export function runtimeModels(binding) {
  const primaryZone = modelZone(binding.primary)
  const models = [{
    model: binding.primary,
    zone: primaryZone,
    fallback: false,
  }]
  for (const fallback of binding.fallbacks) {
    const zone = modelZone(fallback)
    if (
      zone !== primaryZone &&
      !binding.confirmed_cross_zone_fallbacks.includes(fallback)
    ) {
      continue
    }
    models.push({ model: fallback, zone, fallback: true })
  }
  return models
}


function delay(milliseconds) {
  if (milliseconds <= 0) return Promise.resolve()
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}


export async function executeWithRetry({
  candidates,
  retriesPerModel,
  backoffMs,
  execute,
  onRetry,
  onFallback,
}) {
  if (!Array.isArray(candidates) || candidates.length === 0) {
    throw new Error("retry policy requires at least one model candidate")
  }
  let attempt = 0
  let lastError = null
  for (let modelIndex = 0; modelIndex < candidates.length; modelIndex += 1) {
    const candidate = candidates[modelIndex]
    for (let retry = 0; retry <= retriesPerModel; retry += 1) {
      attempt += 1
      try {
        const value = await execute({ ...candidate, attempt })
        return { value, ...candidate, attempt }
      } catch (error) {
        lastError = error
        const kind = classifyRuntimeError(error)
        const retrySameModel =
          retry < retriesPerModel && isRetryableKind(kind)
        const fallbackAvailable =
          modelIndex + 1 < candidates.length && isFallbackKind(kind)
        if (retrySameModel) {
          await onRetry?.({ ...candidate, attempt, kind, error })
          await delay(backoffMs * attempt)
          continue
        }
        if (fallbackAvailable) {
          await onFallback?.({
            from: candidate,
            to: candidates[modelIndex + 1],
            attempt,
            kind,
            error,
          })
          break
        }
        error.biexceKind = kind
        error.biexceAttempt = attempt
        error.biexceModel = candidate.model
        throw error
      }
    }
  }
  throw lastError || new Error("retry policy exhausted without an error")
}
