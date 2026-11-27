import assert from "node:assert/strict";
import test from "node:test";
import { formatPolicyTimingMilliseconds } from "../src/features/simulation/policyTimingFormat.mjs";

test("formats total and distribution timings in milliseconds without hiding small values", () => {
  const secondsByStatistic = {
    total: 0.091,
    mean: 0.000136,
    median: 0.000087,
    p95: 0.000211,
    p99: 0.000412,
    maximum: 0.0009,
  };
  const formatted = Object.values(secondsByStatistic).map(
    formatPolicyTimingMilliseconds,
  );

  assert.match(formatted[0], /^91(?:\.0+)? ms$/);
  assert.match(formatted[1], /^0[.,]136 ms$/);
  assert.match(formatted[2], /^0[.,]087 ms$/);
  assert.match(formatted[3], /^0[.,]211 ms$/);
  assert.match(formatted[4], /^0[.,]412 ms$/);
  assert.match(formatted[5], /^0[.,]9 ms$/);
  assert.ok(formatted.every((value) => value.endsWith(" ms")));
});

test("displays genuine zero as zero and marks values below display resolution", () => {
  assert.equal(formatPolicyTimingMilliseconds(0), "0 ms");
  assert.equal(formatPolicyTimingMilliseconds(1e-12), "<0.000001 ms");
  assert.equal(formatPolicyTimingMilliseconds(null), "Unavailable");
});
