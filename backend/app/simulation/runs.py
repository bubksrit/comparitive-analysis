"""Thread-safe, process-local registry and worker lifecycle for simulation runs."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Condition, Event, RLock
from uuid import uuid4

from pydantic import TypeAdapter

from app.models.simulation import SimulationConfig
from app.models.simulation_runs import (
    ComparisonSummaryResponse,
    SimulationRunError,
    SimulationRunProgress,
    SimulationRunRequest,
    SimulationRunResultsResponse,
    SimulationRunStatus,
    SimulationRunStatusResponse,
)
from app.simulation.comparison import PairedComparisonResult
from app.simulation.engine import SimulationCancelled, run_paired_comparison

MAX_NONTERMINAL_RUNS = 2
TERMINAL_RUN_RETENTION = 50
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

METRIC_DEFINITIONS = {
    "mean_response_time_seconds": "Mean arrival-to-completion time among completed measurement-cohort requests; null when empty.",
    "median_response_time_seconds": "Median arrival-to-completion time among completed measurement-cohort requests; null when empty.",
    "p95_latency_seconds": "95th percentile response time among completed measurement-cohort requests, using linear interpolation; null when empty.",
    "p99_latency_seconds": "99th percentile response time among completed measurement-cohort requests, using linear interpolation; null when empty.",
    "throughput_requests_per_second": "Measurement-cohort requests completed by the end of drain divided by the measurement-window duration.",
    "offered_request_count": "Number of requests arriving in the measurement cohort.",
    "completed_request_count": "Number of measurement-cohort requests completed by the end of drain.",
    "queue_overflow_drop_count": "Measurement-cohort requests rejected because the shared waiting queue was full.",
    "failure_drop_count": "Measurement-cohort in-flight requests dropped when their server failed.",
    "timed_out_request_count": "Measurement-cohort requests that did not complete by their arrival-based deadline.",
    "dropped_request_count": "Queue-overflow drops plus in-flight failure drops; excludes deadline timeouts.",
    "queue_overflow_drop_rate": "Queue-overflow drops divided by offered measurement-cohort requests; zero when no requests were offered.",
    "failure_drop_rate": "Failure drops divided by offered measurement-cohort requests; zero when no requests were offered.",
    "timed_out_request_rate": "Deadline timeouts divided by offered measurement-cohort requests; zero when no requests were offered.",
    "total_request_loss_rate": "Queue-overflow drops, failure drops and deadline timeouts divided by offered measurement-cohort requests; zero when no requests were offered.",
    "utilization_fraction": "Busy service-slot seconds divided by healthy available service-slot seconds during measurement.",
    "simulated_cpu_proxy_fraction": "Time-averaged occupied-slot fraction; a simulated proxy, not hardware CPU measurement.",
    "healthy_available_seconds": "Per-server time in healthy state during the measurement window.",
    "unavailable_seconds": "Per-server time unavailable due to scheduled failures during measurement.",
    "dispatched_request_count": "Measurement-cohort requests dispatched to the server.",
    "server_completed_request_count": "Measurement-cohort requests completed by the server by the end of drain.",
    "dispatch_share": "Server measurement-cohort dispatches divided by all measurement-cohort dispatches; zero if none were dispatched.",
    "load_imbalance_cv": "Population standard deviation divided by mean of per-server utilization among servers with positive healthy-available time; zero if the mean is zero, null if no servers qualify.",
    "recovery_time_seconds": "Elapsed simulation time from scheduled server recovery until recovery criteria are met.",
    "recovery_timestamp_seconds": "Absolute simulation timestamp when the third consecutive qualifying recovery window ends.",
    "policy_decision_count": "Number of route-selection decisions made.",
    "policy_decision_wall_seconds": "Total host wall-clock duration spent selecting routes; isolated from simulation time and outcomes.",
    "mean_policy_decision_wall_seconds": "Mean host wall-clock route-selection duration; zero if no decisions were made.",
    "median_policy_decision_wall_seconds": "Median host wall-clock route-selection duration; zero if no decisions were made.",
    "p95_policy_decision_wall_seconds": "95th percentile host wall-clock route-selection duration using linear interpolation; zero if no decisions were made.",
    "p99_policy_decision_wall_seconds": "99th percentile host wall-clock route-selection duration using linear interpolation; zero if no decisions were made.",
    "max_policy_decision_wall_seconds": "Maximum host wall-clock route-selection duration; zero if no decisions were made.",
}

_SUMMARY_ADAPTER = TypeAdapter(ComparisonSummaryResponse)


class RunNotFoundError(LookupError):
    """No active or retained run exists for the requested identifier."""


class RunNotCompletedError(RuntimeError):
    """A run does not have a complete result bundle yet."""

    def __init__(self, status: str):
        self.status = status
        super().__init__(f"run results are unavailable while status is {status!r}")


class RunLimitReachedError(RuntimeError):
    """The process already has the maximum number of nonterminal runs."""


class RegistryUnavailableError(RuntimeError):
    """The application lifespan has not started or is shutting down."""


@dataclass(slots=True)
class _RunRecord:
    run_id: str
    config: SimulationConfig
    policies: tuple[str, ...]
    replications: int
    created_at: datetime
    status: SimulationRunStatus = "queued"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    completed_replications: int = 0
    completed_policy_runs: int = 0
    error: SimulationRunError | None = None
    result: PairedComparisonResult | None = None
    cancellation_requested: Event = field(default_factory=Event)
    future: Future[None] | None = None


class SimulationRunRegistry:
    """Single-process run store with a one-thread worker and cooperative cancel."""

    def __init__(
        self,
        *,
        runner: Callable[..., PairedComparisonResult] = run_paired_comparison,
        max_nonterminal_runs: int = MAX_NONTERMINAL_RUNS,
        terminal_retention: int = TERMINAL_RUN_RETENTION,
    ) -> None:
        if max_nonterminal_runs < 1:
            raise ValueError("max_nonterminal_runs must be at least one")
        if terminal_retention < 1:
            raise ValueError("terminal_retention must be at least one")
        self._runner = runner
        self._max_nonterminal_runs = max_nonterminal_runs
        self._terminal_retention = terminal_retention
        self._lock = RLock()
        self._lifecycle = Condition(self._lock)
        self._lifecycle_state = "stopped"
        self._runs: dict[str, _RunRecord] = {}
        self._executor: ThreadPoolExecutor | None = None

    def start(self) -> None:
        """Create a fresh worker pool and run store for an application lifespan."""
        with self._lifecycle:
            while self._lifecycle_state in {"starting", "stopping"}:
                self._lifecycle.wait()
            if self._lifecycle_state == "running":
                return
            self._lifecycle_state = "starting"
            self._runs.clear()
            # One worker allows a second accepted run to remain observably queued.
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="simulation"
            )
            self._lifecycle_state = "running"
            self._lifecycle.notify_all()

    def submit(self, request: SimulationRunRequest) -> SimulationRunStatusResponse:
        with self._lock:
            if self._lifecycle_state != "running" or self._executor is None:
                raise RegistryUnavailableError("simulation registry is not accepting runs")
            active_count = sum(
                record.status not in TERMINAL_STATUSES for record in self._runs.values()
            )
            if active_count >= self._max_nonterminal_runs:
                raise RunLimitReachedError(
                    f"at most {self._max_nonterminal_runs} nonterminal simulation runs are allowed"
                )

            run_id = str(uuid4())
            record = _RunRecord(
                run_id=run_id,
                config=request.simulation_config(),
                policies=request.policies,
                replications=request.replications,
                created_at=datetime.now(UTC),
            )
            self._runs[run_id] = record
            # The worker blocks on _lock until its Future is attached and the queued
            # response snapshot has been made.
            record.future = self._executor.submit(self._execute, run_id)
            return self._status_response(record)

    def status(self, run_id: str) -> SimulationRunStatusResponse:
        with self._lock:
            record = self._get_record(run_id)
            return self._status_response(record)

    def results(self, run_id: str) -> SimulationRunResultsResponse:
        with self._lock:
            record = self._get_record(run_id)
            if record.status != "completed" or record.result is None:
                raise RunNotCompletedError(record.status)
            comparison = record.result
            summary = _SUMMARY_ADAPTER.validate_python(asdict(comparison.summary))
            return SimulationRunResultsResponse(
                run_id=record.run_id,
                status="completed",
                master_seed=comparison.master_seed,
                replication_seeds=[trace.seed for trace in comparison.traces],
                replications=comparison.replications,
                policies=comparison.policies,
                configuration=comparison.configuration,
                results=list(comparison.results),
                summary=summary,
                metric_definitions=METRIC_DEFINITIONS.copy(),
            )

    def cancel(self, run_id: str) -> tuple[SimulationRunStatusResponse, bool]:
        with self._lock:
            record = self._get_record(run_id)
            was_terminal = record.status in TERMINAL_STATUSES
            if record.status == "queued":
                record.cancellation_requested.set()
                record.status = "cancelled"
                record.finished_at = datetime.now(UTC)
                if record.future is not None:
                    record.future.cancel()
                self._trim_terminal_records()
            elif record.status == "running":
                record.cancellation_requested.set()
                record.status = "cancelling"
            return self._status_response(record), was_terminal

    def shutdown(self) -> None:
        """Request cooperative stop for active work and join the worker thread."""
        with self._lifecycle:
            while self._lifecycle_state == "starting":
                self._lifecycle.wait()
            if self._lifecycle_state == "stopped":
                return
            if self._lifecycle_state == "stopping":
                while self._lifecycle_state == "stopping":
                    self._lifecycle.wait()
                return
            self._lifecycle_state = "stopping"
            executor = self._executor
            queued_futures: list[Future[None]] = []
            for record in self._runs.values():
                if record.status == "queued":
                    record.cancellation_requested.set()
                    record.status = "cancelled"
                    record.finished_at = datetime.now(UTC)
                    if record.future is not None:
                        queued_futures.append(record.future)
                elif record.status == "running":
                    record.cancellation_requested.set()
                    record.status = "cancelling"
                elif record.status == "cancelling":
                    record.cancellation_requested.set()
            self._trim_terminal_records()
            for future in queued_futures:
                future.cancel()
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
        with self._lifecycle:
            now = datetime.now(UTC)
            for record in self._runs.values():
                if record.status in {"queued", "running", "cancelling"}:
                    record.cancellation_requested.set()
                    record.status = "cancelled"
                    record.finished_at = now
            self._trim_terminal_records()
            self._executor = None
            self._lifecycle_state = "stopped"
            self._lifecycle.notify_all()

    def _execute(self, run_id: str) -> None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None or record.status != "queued":
                return
            record.status = "running"
            record.started_at = datetime.now(UTC)

        try:
            result = self._runner(
                record.config,
                record.policies,
                record.replications,
                progress_callback=lambda completed, total, reps_done, reps_total: self._update_progress(
                    run_id, completed, total, reps_done, reps_total
                ),
                cancel_check=record.cancellation_requested.is_set,
            )
        except SimulationCancelled:
            with self._lock:
                current = self._runs.get(run_id)
                if current is not None and current.status not in TERMINAL_STATUSES:
                    current.status = "cancelled"
                    current.finished_at = datetime.now(UTC)
                    self._trim_terminal_records()
            return
        except Exception as exc:  # Keep worker exceptions inside the run lifecycle.
            with self._lock:
                current = self._runs.get(run_id)
                if current is not None and current.status not in TERMINAL_STATUSES:
                    current.status = "failed"
                    current.error = SimulationRunError(
                        code=type(exc).__name__,
                        message=str(exc)[:1000] or "simulation worker failed",
                    )
                    current.finished_at = datetime.now(UTC)
                    self._trim_terminal_records()
            return

        with self._lock:
            current = self._runs.get(run_id)
            if current is None or current.status in TERMINAL_STATUSES:
                return
            if current.cancellation_requested.is_set():
                current.status = "cancelled"
            else:
                current.result = result
                current.status = "completed"
                current.completed_policy_runs = len(result.results)
                current.completed_replications = result.replications
            current.finished_at = datetime.now(UTC)
            self._trim_terminal_records()

    def _update_progress(
        self,
        run_id: str,
        completed: int,
        total: int,
        reps_done: int,
        reps_total: int,
    ) -> None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None or record.status != "running":
                return
            expected_total = record.replications * len(record.policies)
            if (
                total != expected_total
                or reps_total != record.replications
                or not 0 <= completed <= total
                or not 0 <= reps_done <= reps_total
                or completed < record.completed_policy_runs
                or reps_done < record.completed_replications
            ):
                raise ValueError("simulation worker reported inconsistent progress")
            record.completed_policy_runs = completed
            record.completed_replications = reps_done

    def _get_record(self, run_id: str) -> _RunRecord:
        record = self._runs.get(run_id)
        if record is None:
            raise RunNotFoundError(run_id)
        return record

    @staticmethod
    def _status_response(record: _RunRecord) -> SimulationRunStatusResponse:
        return SimulationRunStatusResponse(
            run_id=record.run_id,
            status=record.status,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            progress=SimulationRunProgress(
                completed_replications=record.completed_replications,
                total_replications=record.replications,
                completed_policy_runs=record.completed_policy_runs,
                total_policy_runs=record.replications * len(record.policies),
            ),
            error=record.error,
        )

    def _trim_terminal_records(self) -> None:
        terminal_ids = sorted(
            (
                run_id
                for run_id, record in self._runs.items()
                if record.status in TERMINAL_STATUSES
            ),
            key=lambda run_id: self._runs[run_id].finished_at or datetime.min.replace(tzinfo=UTC),
        )
        for expired_id in terminal_ids[: max(0, len(terminal_ids) - self._terminal_retention)]:
            self._runs.pop(expired_id, None)
