"""Paired multi-policy summaries with deterministic scenario-level bootstrap CIs."""

from dataclasses import dataclass

import numpy as np

from app.models.simulation import SimulationConfig, SimulationPolicy, SimulationResult
from app.simulation.trace import SimulationTrace

BOOTSTRAP_RESAMPLES = 10_000
SUMMARY_METRICS = (
    "mean_response_time_seconds",
    "median_response_time_seconds",
    "p95_latency_seconds",
    "p99_latency_seconds",
    "throughput_requests_per_second",
    "utilization_fraction",
    "simulated_cpu_proxy_fraction",
    "load_imbalance_cv",
    "queue_overflow_drop_rate",
    "failure_drop_rate",
    "timed_out_request_rate",
    "total_request_loss_rate",
    "policy_decision_count",
    "policy_decision_wall_seconds",
    "mean_policy_decision_wall_seconds",
    "median_policy_decision_wall_seconds",
    "p95_policy_decision_wall_seconds",
    "p99_policy_decision_wall_seconds",
    "max_policy_decision_wall_seconds",
)


@dataclass(frozen=True, slots=True)
class MetricEstimate:
    mean: float | None
    standard_deviation: float | None
    confidence_interval_95: tuple[float, float] | None
    sample_count: int


@dataclass(frozen=True, slots=True)
class ComparisonSummary:
    by_policy: dict[str, dict[str, MetricEstimate]]
    paired_mean_differences: dict[str, dict[str, MetricEstimate]]
    bootstrap_resamples: int
    bootstrap_seed: int


@dataclass(frozen=True, slots=True)
class PairedComparisonResult:
    master_seed: int
    replications: int
    policies: tuple[SimulationPolicy, ...]
    configuration: SimulationConfig
    traces: tuple[SimulationTrace, ...]
    results: tuple[SimulationResult, ...]
    summary: ComparisonSummary


def _estimate(values: list[float], rng: np.random.Generator) -> MetricEstimate:
    if not values:
        return MetricEstimate(None, None, None, 0)
    value_array = np.asarray(values, dtype=float)
    mean = float(np.mean(value_array))
    std = float(np.std(value_array, ddof=1)) if len(values) > 1 else 0.0
    sample_count = len(values)
    indices = rng.integers(0, sample_count, size=(BOOTSTRAP_RESAMPLES, sample_count))
    bootstrap_means = np.mean(value_array[indices], axis=1)
    low, high = np.quantile(bootstrap_means, (0.025, 0.975), method="linear")
    return MetricEstimate(mean, std, (float(low), float(high)), sample_count)


def summarize_comparison(
    results: tuple[SimulationResult, ...],
    policies: tuple[SimulationPolicy, ...],
    replications: int,
    bootstrap_seed: int,
) -> ComparisonSummary:
    """Summarize results in replication-major order and paired differences."""
    if len(results) != len(policies) * replications:
        raise ValueError("expected exactly one result per policy and replication")
    result_by_rep_and_policy = {
        (replication, result.policy): result
        for replication in range(replications)
        for result in results[replication * len(policies) : (replication + 1) * len(policies)]
    }
    if len(result_by_rep_and_policy) != len(results):
        raise ValueError("comparison results contain duplicate replication/policy pairs")

    rng = np.random.default_rng(bootstrap_seed)
    by_policy: dict[str, dict[str, MetricEstimate]] = {}
    values: dict[str, dict[str, list[float | None]]] = {}
    for policy in policies:
        policy_results = [
            result_by_rep_and_policy[(replication, policy)]
            for replication in range(replications)
        ]
        values[policy] = {
            metric_name: [getattr(result.metrics, metric_name) for result in policy_results]
            for metric_name in SUMMARY_METRICS
        }
        by_policy[policy] = {
            metric_name: _estimate(
                [float(value) for value in metric_values if value is not None], rng
            )
            for metric_name, metric_values in values[policy].items()
        }

    reference_policy = policies[0]
    paired_differences: dict[str, dict[str, MetricEstimate]] = {}
    for policy in policies[1:]:
        paired_differences[f"{policy}-minus-{reference_policy}"] = {}
        for metric_name in SUMMARY_METRICS:
            differences = [
                float(policy_value) - float(reference_value)
                for policy_value, reference_value in zip(
                    values[policy][metric_name],
                    values[reference_policy][metric_name],
                    strict=True,
                )
                if policy_value is not None and reference_value is not None
            ]
            paired_differences[f"{policy}-minus-{reference_policy}"][metric_name] = _estimate(
                differences, rng
            )

    return ComparisonSummary(
        by_policy=by_policy,
        paired_mean_differences=paired_differences,
        bootstrap_resamples=BOOTSTRAP_RESAMPLES,
        bootstrap_seed=bootstrap_seed,
    )
