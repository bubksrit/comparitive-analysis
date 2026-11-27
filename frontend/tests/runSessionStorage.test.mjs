import assert from "node:assert/strict";
import test from "node:test";
import {
  clearActiveRunId,
  readActiveRunId,
  writeActiveRunId,
} from "../src/features/simulation/runSessionStorage.mjs";

function createStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

test("stores, restores, and clears the active simulation run ID", () => {
  const storage = createStorage();
  assert.equal(readActiveRunId(storage), null);

  writeActiveRunId("run-123", storage);
  assert.equal(readActiveRunId(storage), "run-123");

  clearActiveRunId(storage);
  assert.equal(readActiveRunId(storage), null);
});

test("storage errors do not prevent the dashboard from loading", () => {
  const unavailableStorage = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
    removeItem() { throw new Error("blocked"); },
  };

  assert.doesNotThrow(() => writeActiveRunId("run-123", unavailableStorage));
  assert.equal(readActiveRunId(unavailableStorage), null);
  assert.doesNotThrow(() => clearActiveRunId(unavailableStorage));
});
