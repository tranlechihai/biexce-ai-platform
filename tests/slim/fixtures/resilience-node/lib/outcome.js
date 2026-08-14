export const CANONICAL_OUTCOMES = ["accepted", "rejected"];

export function normalizeOutcome(value) {
  const normalized = value.trim().toLowerCase();
  if (!CANONICAL_OUTCOMES.includes(normalized)) {
    throw new Error(`unsupported outcome: ${value}`);
  }
  return normalized;
}

export function outcomeLabel(value) {
  const normalized = normalizeOutcome(value);
  return normalized[0].toUpperCase() + normalized.slice(1);
}
