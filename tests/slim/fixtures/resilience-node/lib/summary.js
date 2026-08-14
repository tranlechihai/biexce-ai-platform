import { CANONICAL_OUTCOMES, normalizeOutcome } from "./outcome.js";

export function countOutcomes(values) {
  const counts = Object.fromEntries(
    CANONICAL_OUTCOMES.map((outcome) => [outcome, 0]),
  );
  for (const value of values) {
    counts[normalizeOutcome(value)] += 1;
  }
  return counts;
}
