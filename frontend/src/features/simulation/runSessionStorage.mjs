const activeRunKey = "study-b-active-simulation-run-id";

export function readActiveRunId(storage) {
  try {
    const target = storage ?? globalThis.sessionStorage;
    return target?.getItem(activeRunKey) || null;
  } catch {
    return null;
  }
}

export function writeActiveRunId(runId, storage) {
  try {
    const target = storage ?? globalThis.sessionStorage;
    target?.setItem(activeRunKey, runId);
  } catch {
    // The dashboard remains usable when browser storage is unavailable.
  }
}

export function clearActiveRunId(storage) {
  try {
    const target = storage ?? globalThis.sessionStorage;
    target?.removeItem(activeRunKey);
  } catch {
    // The dashboard remains usable when browser storage is unavailable.
  }
}
