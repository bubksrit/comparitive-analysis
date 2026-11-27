"""Metric calculation from completed event records and server state intervals."""

from bisect import bisect_left
from dataclasses import dataclass

import numpy as np

from app.models.simulation import (
    FailureEvent,
    ServerSimulationMetrics,
    SimulationConfig,
    SimulationMetrics,
)
from app.simulation.state import RequestState, ServerState
from app.simulation.trace import SimulationTrace


@dataclass(frozen=True, slots=True)
class SimulationAccounting:
    offered_request_count: int
    completed_request_count: int
    queue_overflow_drop_count: int
    failure_drop_count: int
    timed_out_request_count: int
    policy_decision_wall_seconds: float
    policy_decision_count: int
    policy_decision_wall_samples: tuple[float, ...]


def _count_in_half_open_window(
    sorted_times: list[float], start: float, end: float
) -> int:
    return bisect_left(sorted_times, end) - bisect_left(sorted_times, start)


def calculate_recovery_times(
    failures: tuple[FailureEvent, ...],
    completion_times: list[float],
    *,
    warmup_seconds: float,
    simulation_end_seconds: float,
) -> tuple[list[float | None], list[float | None], list[str | None]]:
    """Apply the approved 60s baseline and three sustained 10s windows rule."""
    sorted_completions = sorted(completion_times)
    recovery_times: list[float | None] = []
    recovery_timestamps: list[float | None] = []
    reasons: list[str | None] = []
    baseline_seconds = 60.0
    recovery_window_seconds = 10.0
    required_windows = 3

    for failure in failures:
        baseline_start = failure.failure_time_seconds - baseline_seconds
        if baseline_start < warmup_seconds:
            recovery_times.append(None)
            recovery_timestamps.append(None)
            reasons.append("less than 60 seconds of post-warm-up baseline data")
            continue
        baseline_count = _count_in_half_open_window(
            sorted_completions, baseline_start, failure.failure_time_seconds
        )
        baseline_throughput = baseline_count / baseline_seconds
        if baseline_throughput <= 0:
            recovery_times.append(None)
            recovery_timestamps.append(None)
            reasons.append("pre-failure baseline throughput is zero")
            continue

        threshold = baseline_throughput * 0.9
        streak = 0
        window_start = failure.recovery_time_seconds
        recovered_at: float | None = None
        while window_start + recovery_window_seconds <= simulation_end_seconds:
            window_end = window_start + recovery_window_seconds
            count = _count_in_half_open_window(sorted_completions, window_start, window_end)
            throughput = count / recovery_window_seconds
            if throughput >= threshold:
                streak += 1
                if streak == required_windows:
                    recovered_at = window_end
                    break
            else:
                streak = 0
            window_start = window_end

        if recovered_at is None:
            recovery_times.append(None)
            recovery_timestamps.append(None)
            reasons.append("throughput did not meet the recovery threshold for 30 seconds")
        else:
            recovery_times.append(recovered_at - failure.recovery_time_seconds)
            recovery_timestamps.append(recovered_at)
            reasons.append(None)
    return recovery_times, recovery_timestamps, reasons


def calculate_metrics(
    config: SimulationConfig,
    trace: SimulationTrace,
    requests: dict[str, RequestState],
    servers: dict[str, ServerState],
    accounting: SimulationAccounting,
    *,
    simulation_end_seconds: float,
) -> tuple[SimulationMetrics, dict[str, ServerSimulationMetrics]]:
    """Calculate cohort metrics and per-server interval utilization."""
    cohort_start = config.warmup_seconds
    cohort_end = config.workload.duration_seconds
    cohort_requests = [
        requests[item.request_id]
        for item in trace.arrivals
        if cohort_start <= item.arrival_time_seconds < cohort_end
    ]
    completed = [
        request
        for request in cohort_requests
        if request.status == "completed" and request.completion_time_seconds is not None
    ]
    response_times = [
        request.completion_time_seconds - request.spec.arrival_time_seconds
        for request in completed
        if request.completion_time_seconds is not None
    ]
    response_array = np.asarray(response_times, dtype=float)
    if response_array.size:
        mean_response = float(np.mean(response_array))
        median_response = float(np.median(response_array))
        p95 = float(np.quantile(response_array, 0.95, method="linear"))
        p99 = float(np.quantile(response_array, 0.99, method="linear"))
    else:
        mean_response = median_response = p95 = p99 = None

    cohort_count = len(cohort_requests)
    queue_drops = sum(request.status == "queue_overflow_drop" for request in cohort_requests)
    failure_drops = sum(request.status == "failure_drop" for request in cohort_requests)
    timeouts = sum(request.status == "timed_out" for request in cohort_requests)
    denominator = cohort_count or 1
    completed_count = len(completed)
    measurement_seconds = cohort_end - cohort_start
    utilization_denominator = sum(
        server.healthy_available_slot_seconds for server in servers.values()
    )
    utilization_numerator = sum(server.busy_slot_seconds for server in servers.values())
    aggregate_utilization = (
        utilization_numerator / utilization_denominator if utilization_denominator else 0.0
    )

    server_metrics: dict[str, ServerSimulationMetrics] = {}
    eligible_utilizations: list[float] = []
    total_dispatched = sum(
        server.dispatched_request_count for server in servers.values()
    )
    for server_id, server in servers.items():
        available = server.healthy_available_slot_seconds
        utilization = server.busy_slot_seconds / available if available else 0.0
        if available > 0:
            eligible_utilizations.append(utilization)
        server_metrics[server_id] = ServerSimulationMetrics(
            utilization_fraction=utilization,
            simulated_cpu_proxy_fraction=utilization,
            healthy_available_seconds=(
                available / server.config.capacity_slots
                if server.config.capacity_slots
                else 0.0
            ),
            unavailable_seconds=server.unavailable_seconds,
            dispatched_request_count=server.dispatched_request_count,
            completed_request_count=server.completed_request_count,
            dispatch_share=(
                server.dispatched_request_count / total_dispatched if total_dispatched else 0.0
            ),
        )

    if not eligible_utilizations:
        imbalance: float | None = None
    else:
        mean_utilization = float(np.mean(eligible_utilizations))
        imbalance = (
            0.0
            if mean_utilization == 0
            else float(np.std(eligible_utilizations, ddof=0) / mean_utilization)
        )

    completion_times = [
        request.completion_time_seconds
        for request in requests.values()
        if request.status == "completed" and request.completion_time_seconds is not None
    ]
    recovery_times, recovery_timestamps, recovery_reasons = calculate_recovery_times(
        trace.failures,
        [float(value) for value in completion_times if value is not None],
        warmup_seconds=cohort_start,
        simulation_end_seconds=simulation_end_seconds,
    )

    metrics = SimulationMetrics(
        mean_response_time_seconds=mean_response,
        median_response_time_seconds=median_response,
        p95_latency_seconds=p95,
        p99_latency_seconds=p99,
        throughput_requests_per_second=completed_count / measurement_seconds,
        utilization_fraction=aggregate_utilization,
        simulated_cpu_proxy_fraction=aggregate_utilization,
        load_imbalance_cv=imbalance,
        offered_request_count=cohort_count,
        completed_request_count=completed_count,
        queue_overflow_drop_count=queue_drops,
        failure_drop_count=failure_drops,
        dropped_request_count=queue_drops + failure_drops,
        timed_out_request_count=timeouts,
        queue_overflow_drop_rate=queue_drops / denominator,
        failure_drop_rate=failure_drops / denominator,
        timed_out_request_rate=timeouts / denominator,
        total_request_loss_rate=(queue_drops + failure_drops + timeouts) / denominator,
        recovery_time_seconds=recovery_times,
        recovery_timestamp_seconds=recovery_timestamps,
        recovery_unavailable_reasons=recovery_reasons,
        policy_decision_count=accounting.policy_decision_count,
        policy_decision_wall_seconds=accounting.policy_decision_wall_seconds,
        mean_policy_decision_wall_seconds=(
            accounting.policy_decision_wall_seconds / accounting.policy_decision_count
            if accounting.policy_decision_count
            else 0.0
        ),
        median_policy_decision_wall_seconds=(
            float(np.median(accounting.policy_decision_wall_samples))
            if accounting.policy_decision_wall_samples
            else 0.0
        ),
        p95_policy_decision_wall_seconds=(
            float(np.quantile(accounting.policy_decision_wall_samples, 0.95, method="linear"))
            if accounting.policy_decision_wall_samples
            else 0.0
        ),
        p99_policy_decision_wall_seconds=(
            float(np.quantile(accounting.policy_decision_wall_samples, 0.99, method="linear"))
            if accounting.policy_decision_wall_samples
            else 0.0
        ),
        max_policy_decision_wall_seconds=(
            max(accounting.policy_decision_wall_samples)
            if accounting.policy_decision_wall_samples
            else 0.0
        ),
    )
    return metrics, server_metrics
