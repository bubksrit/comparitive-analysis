import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, simulationApi } from "../../services/simulationApi";
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
  const runRef = useRef(run);
  runRef.current = run;
  const runId = run?.run_id;
  const runStatus = run?.status;

  const start = useCallback(async (payload: SimulationRunRequest) => {
    setSubmitting(true);
    setRun(null);
    setResults(null);
    setError(null);
    try {
      const created = await simulationApi.start(payload);
      setRun(created);
      return created;
    } catch (caught) {
      setError(asApiError(caught));
      return null;
    } finally {
      setSubmitting(false);
    }
  }, []);

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

  return {
    run,
    results,
    error,
    submitting,
    cancelling,
    loadingResults,
    start,
    cancel,
    retryResults,
  };
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof Error) return new ApiError(0, error.message);
  return new ApiError(0, "An unexpected API error occurred.");
}
