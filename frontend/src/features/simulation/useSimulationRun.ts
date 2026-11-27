import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, simulationApi } from "../../services/simulationApi";
import {
  clearActiveRunId,
  readActiveRunId,
  writeActiveRunId,
} from "./runSessionStorage.mjs";
import type {
  SimulationRunRequest,
  SimulationRunResultsResponse,
  SimulationRunStatusResponse,
} from "../../types/api";

const pollIntervalMs = 1200;

export function useSimulationRun() {
  const [run, setRun] = useState<SimulationRunStatusResponse | null>(null);
  const [results, setResults] = useState<SimulationRunResultsResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [loadingResults, setLoadingResults] = useState(false);
  const [restorationRunId, setRestorationRunId] = useState(readActiveRunId);
  const [restoring, setRestoring] = useState(() => Boolean(readActiveRunId()));
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const runRef = useRef(run);
  runRef.current = run;
  const runId = run?.run_id;
  const runStatus = run?.status;

  const start = useCallback(async (payload: SimulationRunRequest) => {
    setSubmitting(true);
    setRun(null);
    setResults(null);
    setError(null);
    clearActiveRunId();
    setRestorationRunId(null);
    setRestoring(false);
    try {
      const created = await simulationApi.start(payload);
      writeActiveRunId(created.run_id);
      setRun(created);
      return created;
    } catch (caught) {
      setError(asApiError(caught));
      return null;
    } finally {
      setSubmitting(false);
    }
  }, []);

  const retryRestore = useCallback(() => {
    if (!restorationRunId) return;
    setError(null);
    setRestoring(true);
    setRestoreAttempt((attempt) => attempt + 1);
  }, [restorationRunId]);

  const cancel = useCallback(async () => {
    const current = runRef.current;
    if (!current) return;
    setCancelling(true);
    setError(null);
    try {
      const updated = await simulationApi.cancel(current.run_id);
      setRun(updated);
    } catch (caught) {
      setError(asApiError(caught));
    } finally {
      setCancelling(false);
    }
  }, []);

  const loadResults = useCallback(async (runId: string, signal?: AbortSignal) => {
    setLoadingResults(true);
    try {
      const response = await simulationApi.results(runId, signal);
      setResults(response);
      setError(null);
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setError(asApiError(caught));
      }
    } finally {
      setLoadingResults(false);
    }
  }, []);

  useEffect(() => {
    const terminal =
      runStatus === "completed" || runStatus === "failed" || runStatus === "cancelled";
    if (!runId || terminal) return;

    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;

    const poll = async () => {
      try {
        const updated = await simulationApi.status(runId, controller.signal);
        if (disposed) return;
        if (updated.status === "completed") {
          await loadResults(runId, controller.signal);
          if (!disposed) setRun(updated);
          return;
        }
        setRun(updated);
        setError(null);
        if (updated.status === "failed" || updated.status === "cancelled") return;
        timer = setTimeout(poll, pollIntervalMs);
      } catch (caught) {
        if (disposed || (caught instanceof DOMException && caught.name === "AbortError")) return;
        const apiError = asApiError(caught);
        setError(apiError);
        if (apiError.status === 404) {
          setRun((current) =>
            current
              ? {
                  ...current,
                  status: "failed",
                  finished_at: new Date().toISOString(),
                  error: { code: "RunNotFound", message: apiError.message },
                }
              : current,
          );
          return;
        }
        timer = setTimeout(poll, 2500);
      }
    };

    timer = setTimeout(poll, 250);
    return () => {
      disposed = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [loadResults, runId, runStatus]);

  const retryResults = useCallback(() => {
    if (runRef.current?.status === "completed") {
      void loadResults(runRef.current.run_id);
    }
  }, [loadResults]);

  useEffect(() => {
    if (!restorationRunId) {
      setRestoring(false);
      return;
    }

    const controller = new AbortController();
    let disposed = false;
    setRestoring(true);

    void simulationApi.status(restorationRunId, controller.signal).then(async (restored) => {
      if (disposed) return;
      setRun(restored);
      setError(null);
      if (restored.status === "completed") {
        await loadResults(restorationRunId, controller.signal);
      }
      if (!disposed) {
        setRestorationRunId(null);
        setRestoring(false);
      }
    }).catch((caught: unknown) => {
      if (disposed || (caught instanceof DOMException && caught.name === "AbortError")) return;
      const apiError = asApiError(caught);
      if (apiError.status === 404) {
        clearActiveRunId();
        setRestorationRunId(null);
        setRun(null);
        setError(new ApiError(
          404,
          `Saved run ${restorationRunId} is unavailable. Simulation records are held in backend memory and are lost when the backend restarts or evicts the record.`,
        ));
      } else {
        setError(apiError);
      }
      setRestoring(false);
    });

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [loadResults, restoreAttempt, restorationRunId]);

  return {
    run,
    results,
    error,
    submitting,
    cancelling,
    loadingResults,
    restoring,
    restorationRunId,
    start,
    cancel,
    retryResults,
    retryRestore,
  };
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof Error) return new ApiError(0, error.message);
  return new ApiError(0, "An unexpected API error occurred.");
}
