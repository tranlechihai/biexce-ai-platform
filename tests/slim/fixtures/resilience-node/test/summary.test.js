import assert from "node:assert/strict";
import test from "node:test";

import { countOutcomes } from "../lib/index.js";

test("counts canonical outcomes", () => {
  assert.deepEqual(countOutcomes(["accepted", "rejected", " ACCEPTED "]), {
    accepted: 2,
    rejected: 1,
  });
});
