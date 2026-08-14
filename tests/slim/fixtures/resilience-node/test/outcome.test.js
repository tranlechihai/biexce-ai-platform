import assert from "node:assert/strict";
import test from "node:test";

import { normalizeOutcome, outcomeLabel } from "../lib/index.js";

test("canonical outcomes are normalized", () => {
  assert.equal(normalizeOutcome(" ACCEPTED "), "accepted");
  assert.equal(normalizeOutcome("rejected"), "rejected");
});

test("unknown alias is rejected", () => {
  assert.throws(() => normalizeOutcome("denied"), /unsupported outcome/);
});

test("label uses canonical outcome", () => {
  assert.equal(outcomeLabel("accepted"), "Accepted");
});
