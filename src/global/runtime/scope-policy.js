const GENERATED_RUNTIME_DIRECTORIES = new Set([
  "__pycache__",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache",
  ".tox",
  ".nox",
])


export const SCOPE_FAILURES = Object.freeze({
  NONE: "NONE",
  GENERATED: "GENERATED",
  MANAGED_METADATA: "MANAGED_METADATA",
  PROJECT_SCOPE_DRIFT: "PROJECT_SCOPE_DRIFT",
  HARD_BOUNDARY: "HARD_BOUNDARY",
})


export function portableProjectPath(value) {
  return String(value || "")
    .trim()
    .replaceAll(String.fromCharCode(92), "/")
    .replace(/^\.\//, "")
}


export function protectedProjectPath(value) {
  const portable = portableProjectPath(value)
  if (!portable) return true
  const parts = portable.split("/").filter(Boolean)
  const name = parts.at(-1)?.toLowerCase() || ""
  return portable.startsWith(".biexce/") ||
    portable.startsWith(".git/") ||
    portable === ".biexce" ||
    portable === ".git" ||
    parts.includes("..") ||
    /^\.env(?:\.|$)/i.test(name) ||
    /\.(?:pem|key|pfx|p12|jks|keystore|mobileprovision)$/i.test(name) ||
    /(?:credential|secret|service-account)/i.test(name) ||
    ["google-services.json", "google-service-info.plist"].includes(name)
}


export function generatedRuntimePath(value) {
  const portable = portableProjectPath(value)
  if (!portable) return false
  const parts = portable.split("/").filter(Boolean)
  const name = parts.at(-1) || ""
  return parts.some((part) => GENERATED_RUNTIME_DIRECTORIES.has(part)) ||
    name === ".coverage" ||
    name.startsWith(".coverage.") ||
    name.endsWith(".pyc") ||
    name.endsWith(".pyo")
}


export function managedPlanArtifact(value) {
  const portable = portableProjectPath(value)
  return portable === ".biexce/MASTER_PLAN.md" ||
    portable === ".biexce/reports/PREFLIGHT_REPORT.md" ||
    /^\.biexce\/tasks\/t-[0-9]{3}\.md$/.test(portable)
}


export function runtimeScopeErrorPaths(value) {
  const text = String(value || "")
  const marker = "runtime diff exceeds writable scope:"
  const index = text.toLowerCase().indexOf(marker)
  if (index < 0) return []
  return text.slice(index + marker.length)
    .split(/[\r\n]/, 1)[0]
    .split(",")
    .map(portableProjectPath)
    .filter(Boolean)
}


export function scopeFailure(value) {
  const text = String(value?.message || value || "")
  const lower = text.toLowerCase()
  if (
    /escapes (?:the )?project root|outside (?:the )?project root/.test(lower) ||
    /protected project paths changed/.test(lower) ||
    /secret exposure|exposed secret|credential leak|private key exposure/.test(lower)
  ) {
    return { kind: SCOPE_FAILURES.HARD_BOUNDARY, paths: [] }
  }

  const paths = runtimeScopeErrorPaths(text)
  if (paths.length > 0) {
    // Plan artifacts are runtime-managed and have their own bounded rebase
    // path. Classify them before the general .biexce protection rule.
    if (paths.every(managedPlanArtifact)) {
      return { kind: SCOPE_FAILURES.MANAGED_METADATA, paths }
    }
    if (paths.some(protectedProjectPath)) {
      return { kind: SCOPE_FAILURES.HARD_BOUNDARY, paths }
    }
    if (paths.every(generatedRuntimePath)) {
      return { kind: SCOPE_FAILURES.GENERATED, paths }
    }
    return { kind: SCOPE_FAILURES.PROJECT_SCOPE_DRIFT, paths }
  }

  // Older runtimes sometimes persisted only a prose contract summary and lost
  // the concrete path list. Treat a writer's non-protected scope contradiction
  // as project scope drift so Standard mode can re-verify current source rather
  // than permanently blocking the project. The caller still limits this to a
  // CODE/FIX origin and Critical mode remains fail-closed.
  if (
    /writable scope|write scope|read-only (?:input|test)|out-of-scope edit|scope conflict/.test(
      lower,
    )
  ) {
    return { kind: SCOPE_FAILURES.PROJECT_SCOPE_DRIFT, paths: [] }
  }
  return { kind: SCOPE_FAILURES.NONE, paths: [] }
}
