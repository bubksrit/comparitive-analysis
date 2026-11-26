import type { ApiError } from "../../services/simulationApi";
import type { SimulationRunStatusResponse } from "../../types/api";

type Props = {
  run: SimulationRunStatusResponse | null;
  error: ApiError | null;
  submitting: boolean;
  cancelling: boolean;
  loadingResults: boolean;
  onCancel: () => void;
  onRetryResults: () => void;
};

const statusCopy: Record<string, string> = {
  queued: "Waiting for the simulation worker",
  running: "Running paired policy simulations",
  cancelling: "Stopping at a simulation event boundary",
  completed: "Run completed successfully",
  failed: "Run ended with an error",
  cancelled: "Run cancelled",
};

export function RunLifecyclePanel({
  run,
  error,
  submitting,
  cancelling,
  loadingResults,
  onCancel,
  onRetryResults,
}: Props) {
  const hasRunOrActivity = Boolean(run || submitting);
  const progressPercent = run
    ? Math.min(100, (run.progress.completed_policy_runs / run.progress.total_policy_runs) * 100)
    : 0;

  return (
    <section className="panel lifecycle-panel" aria-labelledby="run-status-title">
      <div className="panel-heading compact-heading">
        <div>
          <p className="eyebrow">Run lifecycle</p>
          <h2 id="run-status-title">Simulation status</h2>
        </div>
        {run && <StatusBadge status={run.status} />}
      </div>

      {!hasRunOrActivity ? (
        <div className="empty-run-state">
          <div className="empty-icon">↗</div>
          <strong>Ready to simulate</strong>
          <p>Configure a paired experiment to start a background run.</p>
        </div>
      ) : submitting ? (
        <div className="starting-state"><span className="spinner" /><span>Submitting configuration to the simulation API…</span></div>
      ) : run ? (
        <div className="run-details">
          <div className="run-id-block">
            <span>Run ID</span>
            <code>{run.run_id}</code>
          </div>
          <div className="run-state-copy">
            <span className={`status-dot status-${run.status}`} />
            <span>{statusCopy[run.status] ?? run.status}</span>
          </div>

          <div className="progress-block">
            <div className="progress-labels">
              <span>Policy runs</span>
              <strong>{run.progress.completed_policy_runs} / {run.progress.total_policy_runs}</strong>
            </div>
            <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progressPercent)}>
              <span style={{ width: `${progressPercent}%` }} />
            </div>
            <div className="progress-labels progress-secondary">
              <span>Completed replications</span>
              <strong>{run.progress.completed_replications} / {run.progress.total_replications}</strong>
            </div>
          </div>

          <div className="timestamp-grid">
            <TimeItem label="Created" value={run.created_at} />
            <TimeItem label="Started" value={run.started_at} />
            <TimeItem label="Finished" value={run.finished_at} />
          </div>

          {run.error && (
            <div className="inline-error">
              <strong>{run.error.code}</strong>
              <span>{run.error.message}</span>
            </div>
          )}
          {run.status === "cancelled" && (
            <p className="terminal-note">No partial policy results are published for a cancelled run.</p>
          )}
          {run.status === "completed" && loadingResults && (
            <div className="results-loading"><span className="spinner" /> Retrieving completed results…</div>
          )}
          {run.status === "completed" && error && !loadingResults && (
            <button className="secondary-button retry-button" type="button" onClick={onRetryResults}>
              Retry result retrieval
            </button>
          )}

          {(run.status === "queued" || run.status === "running") && (
            <button className="danger-button" type="button" onClick={onCancel} disabled={cancelling}>
              {cancelling ? <span className="spinner" /> : <StopIcon />}
              {cancelling ? "Requesting cancellation…" : "Cancel run"}
            </button>
          )}
          {run.status === "cancelling" && <p className="terminal-note">Cancellation is cooperative; the worker will finish safely at the next event boundary.</p>}
        </div>
      ) : null}

      {error && !(run?.status === "completed" && loadingResults) && (
        <div className="api-error" role="alert">
          <div className="error-heading"><span>API error</span>{error.status > 0 && <small>HTTP {error.status}</small>}</div>
          <p>{error.message}</p>
          {error.details.length > 0 && (
            <ul>{error.details.map((detail, index) => <li key={`${detail}-${index}`}>{detail}</li>)}</ul>
          )}
        </div>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge badge-${status}`}><i />{status}</span>;
}

function TimeItem({ label, value }: { label: string; value: string | null }) {
  return (
    <div><span>{label}</span><strong>{value ? new Date(value).toLocaleTimeString() : "—"}</strong></div>
  );
}

function StopIcon() {
  return <svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor" className="button-icon"><rect x="3" y="3" width="10" height="10" rx="2" /></svg>;
}
