"""Unit and integration coverage for the Study B discrete-event simulator."""

import numpy as np
import pytest

from app.models.simulation import (
    FailureEvent,
    ServerConfig,
    SimulationConfig,
    WorkloadConfig,
)
from app.simulation.engine import run_paired_comparison, run_simulation
from app.simulation.metrics import calculate_recovery_times
from app.simulation.policies import (
    CapacityAwareWeightedPolicy,
    LeastConnectionsPolicy,
    PolicyContext,
    RoundRobinPolicy,
    ServerView,
)
from app.simulation.trace import ArrivalSpec, SimulationTrace
from app.simulation.workloads import generate_trace


def _config(**overrides) -> SimulationConfig:
    values = {
        "seed": 9,
        "scenario_id": "test-scenario",
        "workload": WorkloadConfig(
            kind="stable", duration_seconds=8, stable_rate_per_second=1
        ),
        "servers": [ServerConfig(server_id="s1", capacity_slots=1, service_rate_per_slot_per_second=1)],
        "failure_schedule": [],
        "warmup_seconds": 0,
        "drain_seconds": 5,
        "queue_limit_requests": 10,
        "request_deadline_seconds": 5,
        "service_demand_distribution": "deterministic",
        "service_demand_parameters": {"mean_work_units": 1},
    }
    values.update(overrides)
    return SimulationConfig.model_validate(values)


def _trace(config: SimulationConfig, *arrivals: tuple[str, float, float]) -> SimulationTrace:
    specs = tuple(
        ArrivalSpec(request_id, time_seconds, work_units)
        for request_id, time_seconds, work_units in arrivals
    )
    return SimulationTrace(
        scenario_id=config.scenario_id,
        seed=config.seed,
        arrivals=specs,
        failures=tuple(config.failure_schedule),
        trace_id=f"{config.scenario_id}:{config.seed}",
    )


def _policy_context(
    servers: list[tuple[str, int, float, int]],
    tie_order: tuple[str, ...] | None = None,
) -> PolicyContext:
    return PolicyContext(
        eligible_servers=tuple(
            ServerView(
                ServerConfig(
                    server_id=server_id,
                    capacity_slots=slots,
                    service_rate_per_slot_per_second=rate,
                ),
                active,
            )
            for server_id, slots, rate, active in servers
        ),
        server_order=tuple(server[0] for server in servers),
        tie_order=tie_order or tuple(server[0] for server in servers),
        mean_request_demand=1.0,
        shared_queue_depth=0,
    )


def _metric_data(result):
    data = result.model_dump()
    data.pop("metadata")
    for field in (
        "policy_decision_wall_seconds",
        "mean_policy_decision_wall_seconds",
        "median_policy_decision_wall_seconds",
        "p95_policy_decision_wall_seconds",
        "p99_policy_decision_wall_seconds",
        "max_policy_decision_wall_seconds",
    ):
        data["metrics"].pop(field)
    return data


def test_default_config_matches_approved_contract():
    config = SimulationConfig()
    assert config.seed == 42
    assert config.warmup_seconds == 60
    assert config.drain_seconds == 60
    assert config.request_deadline_seconds == 30
    assert config.queue_limit_requests == 1000
    assert config.workload.kind == "stable"
    assert config.workload.duration_seconds == 600
    assert config.workload.stable_rate_per_second == 60
    assert [server.capacity_slots for server in config.servers] == [2, 4, 6]
    assert [server.service_rate_per_slot_per_second for server in config.servers] == [10] * 3
    assert config.service_demand_distribution == "exponential"
    assert config.service_demand_parameters == {"mean_work_units": 1.0}


def test_config_rejects_invalid_burst_queue_and_failure_schedules():
    with pytest.raises(ValueError, match="cannot exceed its period"):
        WorkloadConfig(
            kind="bursty",
            burst_period_seconds=10,
            burst_high_duration_seconds=11,
        )
    with pytest.raises(ValueError, match="drain_seconds"):
        _config(drain_seconds=2, request_deadline_seconds=5)
    with pytest.raises(ValueError, match="unique"):
        _config(
            servers=[
                ServerConfig(server_id="s1", capacity_slots=1, service_rate_per_slot_per_second=1),
                ServerConfig(server_id="s1", capacity_slots=2, service_rate_per_slot_per_second=1),
            ]
        )
    with pytest.raises(ValueError, match="unknown server"):
        _config(
            failure_schedule=[
                FailureEvent(
                    server_id="missing", failure_time_seconds=1, recovery_time_seconds=2
                )
            ]
        )
    with pytest.raises(ValueError, match="overlap or touch"):
        _config(
            failure_schedule=[
                FailureEvent(server_id="s1", failure_time_seconds=1, recovery_time_seconds=3),
                FailureEvent(server_id="s1", failure_time_seconds=3, recovery_time_seconds=4),
            ]
        )


@pytest.mark.parametrize("kind", ["stable", "increasing", "bursty"])
def test_workload_trace_is_reproducible_and_inside_half_open_horizon(kind):
    config = _config(
        workload=WorkloadConfig(kind=kind, duration_seconds=600),
    )
    first = generate_trace(config, seed=321)
    second = generate_trace(config, seed=321)
    assert first.signature() == second.signature()
    assert first.arrivals
    assert all(0 <= item.arrival_time_seconds < 600 for item in first.arrivals)
    assert all(item.work_demand_units > 0 for item in first.arrivals)
    assert [item.request_id for item in first.arrivals] == [
        f"req-{index:08d}" for index in range(len(first.arrivals))
    ]


def test_increasing_traffic_has_more_late_arrivals_than_early_arrivals():
    config = _config(workload=WorkloadConfig(kind="increasing", duration_seconds=600))
    arrivals = [item.arrival_time_seconds for item in generate_trace(config, 17).arrivals]
    early = sum(time_seconds < 200 for time_seconds in arrivals)
    late = sum(time_seconds >= 400 for time_seconds in arrivals)
    assert late > early


def test_bursty_traffic_has_high_and_low_periods():
    config = _config(workload=WorkloadConfig(kind="bursty", duration_seconds=600))
    arrivals = [item.arrival_time_seconds for item in generate_trace(config, 18).arrivals]
    high_count = sum(45 <= time_seconds % 60 < 60 for time_seconds in arrivals)
    low_count = sum(time_seconds % 60 < 45 for time_seconds in arrivals)
    assert high_count > low_count


def test_round_robin_cycles_skips_ineligible_and_preserves_cursor_when_none():
    policy = RoundRobinPolicy(("a", "b", "c"))
    context = _policy_context([("a", 1, 1, 0), ("b", 1, 1, 0), ("c", 1, 1, 0)])
    assert policy.choose_server(context) == "a"
    assert policy.choose_server(context) == "b"
    context_c = _policy_context([("c", 1, 1, 0)])
    assert policy.choose_server(context_c) == "c"
    with pytest.raises(ValueError, match="eligible"):
        policy.choose_server(_policy_context([]))
    assert policy.choose_server(context) == "a"


def test_least_connections_uses_seeded_tie_order():
    context = _policy_context(
        [("a", 3, 1, 1), ("b", 3, 1, 1), ("c", 3, 1, 2)],
        tie_order=("b", "a", "c"),
    )
    assert LeastConnectionsPolicy().choose_server(context) == "b"


def test_capacity_weighted_uses_active_work_normalized_by_capacity():
    context = _policy_context(
        [("small", 1, 1, 1), ("large", 2, 2, 2), ("idle", 1, 1, 0)],
        tie_order=("small", "large", "idle"),
    )
    assert CapacityAwareWeightedPolicy().choose_server(context) == "idle"
    context = _policy_context(
        [("small", 1, 1, 1), ("large", 2, 2, 2)],
        tie_order=("small", "large"),
    )
    assert CapacityAwareWeightedPolicy().choose_server(context) == "large"


def test_shared_fifo_queue_dispatches_in_arrival_order():
    config = _config(
        queue_limit_requests=3,
        request_deadline_seconds=10,
        drain_seconds=10,
    )
    trace = _trace(config, ("r1", 0, 2), ("r2", 0.1, 3), ("r3", 0.2, 1))
    result = run_simulation(config, "round_robin", trace)
    assert result.metrics.offered_request_count == 3
    assert result.metrics.completed_request_count == 3
    assert result.metrics.queue_overflow_drop_count == 0
    assert result.metrics.mean_response_time_seconds == pytest.approx((2 + 4.9 + 5.8) / 3)
    assert result.per_server["s1"].dispatched_request_count == 3


def test_shared_fifo_dispatches_head_when_multiple_servers_become_available():
    config = _config(
        servers=[
            ServerConfig(server_id="s1", capacity_slots=1, service_rate_per_slot_per_second=1),
            ServerConfig(server_id="s2", capacity_slots=1, service_rate_per_slot_per_second=1),
        ],
        request_deadline_seconds=10,
        drain_seconds=10,
    )
    trace = _trace(
        config,
        ("r1", 0, 2),
        ("r2", 0, 2),
        ("r3", 0.1, 1),
        ("r4", 0.2, 1),
    )
    result = run_simulation(config, "round_robin", trace)
    assert result.metrics.completed_request_count == 4
    assert result.metrics.mean_response_time_seconds == pytest.approx(2.425)
    assert result.per_server["s1"].dispatched_request_count == 2
    assert result.per_server["s2"].dispatched_request_count == 2


def test_round_robin_cursor_persists_through_failure_skip_and_recovery():
    config = _config(
        servers=[
            ServerConfig(server_id="s1", capacity_slots=1, service_rate_per_slot_per_second=1),
            ServerConfig(server_id="s2", capacity_slots=1, service_rate_per_slot_per_second=1),
        ],
        failure_schedule=[
            FailureEvent(server_id="s1", failure_time_seconds=1, recovery_time_seconds=3)
        ],
        request_deadline_seconds=10,
        drain_seconds=10,
    )
    trace = _trace(
        config,
        ("r1", 0, 5),
        ("r2", 0, 1),
        ("r3", 1.5, 1),
        ("r4", 3, 1),
    )
    result = run_simulation(config, "round_robin", trace)
    assert result.metrics.failure_drop_count == 1
    assert result.per_server["s1"].dispatched_request_count == 2
    assert result.per_server["s2"].dispatched_request_count == 2
    assert result.metrics.completed_request_count == 3


def test_combined_simultaneous_events_across_multiple_servers():
    config = _config(
        workload=WorkloadConfig(kind="stable", duration_seconds=8, stable_rate_per_second=1),
        servers=[
            ServerConfig(server_id="s1", capacity_slots=1, service_rate_per_slot_per_second=1),
            ServerConfig(server_id="s2", capacity_slots=1, service_rate_per_slot_per_second=1),
            ServerConfig(server_id="s3", capacity_slots=1, service_rate_per_slot_per_second=1),
        ],
        failure_schedule=[
            FailureEvent(server_id="s2", failure_time_seconds=2, recovery_time_seconds=4),
            FailureEvent(server_id="s3", failure_time_seconds=0, recovery_time_seconds=2),
        ],
        request_deadline_seconds=2,
        drain_seconds=2,
    )
    trace = _trace(
        config,
        ("r1-completes", 0, 2),
        ("r2-fails", 0, 5),
        ("r3-deadline", 0, 5),
        ("r4-arrives", 2, 0.5),
    )
    result = run_simulation(config, "round_robin", trace)
    assert result.metrics.failure_drop_count == 1
    assert result.metrics.timed_out_request_count == 1
    assert result.metrics.completed_request_count == 2
    assert result.per_server["s1"].dispatched_request_count == 1
    assert result.per_server["s3"].dispatched_request_count == 1


def test_queue_overflow_is_a_distinct_drop_type_and_rate():
    config = _config(queue_limit_requests=1)
    trace = _trace(config, ("r1", 0, 2), ("r2", 0.1, 1), ("r3", 0.2, 1))
    result = run_simulation(config, "least_connections", trace)
    assert result.metrics.queue_overflow_drop_count == 1
    assert result.metrics.failure_drop_count == 0
    assert result.metrics.dropped_request_count == 1
    assert result.metrics.queue_overflow_drop_rate == pytest.approx(1 / 3)
    assert result.metrics.completed_request_count == 2


@pytest.mark.parametrize(("waiting_requests", "expected_overflow"), [(1000, 0), (1001, 1)])
def test_queue_limit_accepts_exactly_1000_and_drops_request_1001(
    waiting_requests, expected_overflow
):
    config = _config(
        workload=WorkloadConfig(kind="stable", duration_seconds=2, stable_rate_per_second=1),
        queue_limit_requests=1000,
        request_deadline_seconds=30,
        drain_seconds=30,
    )
    trace = _trace(
        config,
        ("active", 0, 100),
        *((f"queued-{index:04d}", 0.1, 1) for index in range(waiting_requests)),
    )
    result = run_simulation(config, "least_connections", trace)
    assert result.metrics.offered_request_count == waiting_requests + 1
    assert result.metrics.queue_overflow_drop_count == expected_overflow


def test_deadline_expires_queued_and_in_service_requests():
    config = _config(request_deadline_seconds=2, drain_seconds=2, queue_limit_requests=2)
    trace = _trace(config, ("r1", 0, 10), ("r2", 0.1, 1))
    result = run_simulation(config, "round_robin", trace)
    assert result.metrics.timed_out_request_count == 2
    assert result.metrics.completed_request_count == 0
    assert result.metrics.mean_response_time_seconds is None
    assert result.metrics.p95_latency_seconds is None
    assert result.metrics.throughput_requests_per_second == 0


def test_completion_at_exact_deadline_wins_event_tie():
    config = _config(request_deadline_seconds=2, drain_seconds=2)
    trace = _trace(config, ("r1", 0, 2))
    result = run_simulation(config, "round_robin", trace)
    assert result.metrics.completed_request_count == 1
    assert result.metrics.timed_out_request_count == 0
    assert result.metrics.mean_response_time_seconds == 2


@pytest.mark.parametrize("policy_id", ["round_robin", "least_connections", "weighted"])
def test_all_policies_share_failure_and_recovery_behaviour(policy_id):
    failure = FailureEvent(server_id="s1", failure_time_seconds=1, recovery_time_seconds=3)
    config = _config(failure_schedule=[failure], queue_limit_requests=2)
    trace = _trace(config, ("active", 0, 4), ("queued", 0.5, 1))
    result = run_simulation(config, policy_id, trace)
    assert result.metrics.failure_drop_count == 1
    assert result.metrics.completed_request_count == 1
    assert result.per_server["s1"].dispatched_request_count == 2
    snapshot_at_ten = next(item for item in result.snapshots if item.time_seconds == 10)
    assert snapshot_at_ten.server_health["s1"] is True
    assert snapshot_at_ten.shared_queue_depth == 0


def test_completion_at_exact_failure_time_is_completed_before_server_fails():
    failure = FailureEvent(server_id="s1", failure_time_seconds=2, recovery_time_seconds=4)
    config = _config(failure_schedule=[failure])
    result = run_simulation(config, "round_robin", _trace(config, ("r1", 0, 2)))
    assert result.metrics.completed_request_count == 1
    assert result.metrics.failure_drop_count == 0
    assert result.per_server["s1"].unavailable_seconds == pytest.approx(2)


def test_failure_at_arrival_time_makes_server_ineligible_until_recovery():
    failure = FailureEvent(server_id="s1", failure_time_seconds=1, recovery_time_seconds=3)
    config = _config(failure_schedule=[failure], queue_limit_requests=1)
    result = run_simulation(config, "round_robin", _trace(config, ("r1", 1, 1)))
    assert result.metrics.completed_request_count == 1
    assert result.metrics.failure_drop_count == 0
    assert result.per_server["s1"].dispatched_request_count == 1


def test_warmup_requests_affect_utilization_but_not_measured_outcomes():
    config = _config(
        workload=WorkloadConfig(kind="stable", duration_seconds=6, stable_rate_per_second=1),
        warmup_seconds=2,
    )
    trace = _trace(config, ("warmup", 0, 4), ("measured", 2, 1))
    result = run_simulation(config, "round_robin", trace)
    assert result.metrics.offered_request_count == 1
    assert result.metrics.completed_request_count == 1
    assert result.metrics.mean_response_time_seconds == 3
    assert result.metrics.utilization_fraction == pytest.approx(0.75)


def test_metrics_use_linear_quantiles_and_documented_measurement_denominators():
    config = _config(
        workload=WorkloadConfig(kind="stable", duration_seconds=5, stable_rate_per_second=1),
        servers=[ServerConfig(server_id="s1", capacity_slots=4, service_rate_per_slot_per_second=1)],
        request_deadline_seconds=5,
        drain_seconds=5,
    )
    trace = _trace(config, ("r1", 0, 1), ("r2", 0, 2), ("r3", 0, 3), ("r4", 0, 4))
    result = run_simulation(config, "least_connections", trace)
    assert result.metrics.mean_response_time_seconds == pytest.approx(2.5)
    assert result.metrics.median_response_time_seconds == pytest.approx(2.5)
    assert result.metrics.p95_latency_seconds == pytest.approx(3.85)
    assert result.metrics.p99_latency_seconds == pytest.approx(3.97)
    assert result.metrics.throughput_requests_per_second == pytest.approx(4 / 5)
    assert result.metrics.utilization_fraction == pytest.approx(0.5)
    assert result.metrics.load_imbalance_cv == 0


def test_request_distribution_server_utilization_and_imbalance_metrics():
    config = _config(
        workload=WorkloadConfig(kind="stable", duration_seconds=5, stable_rate_per_second=1),
        servers=[
            ServerConfig(server_id="s1", capacity_slots=1, service_rate_per_slot_per_second=1),
            ServerConfig(server_id="s2", capacity_slots=1, service_rate_per_slot_per_second=2),
        ],
    )
    trace = _trace(config, ("r1", 0, 1), ("r2", 0, 1))
    result = run_simulation(config, "round_robin", trace)
    assert result.per_server["s1"].dispatched_request_count == 1
    assert result.per_server["s2"].dispatched_request_count == 1
    assert result.per_server["s1"].dispatch_share == pytest.approx(0.5)
    assert result.per_server["s2"].dispatch_share == pytest.approx(0.5)
    assert result.per_server["s1"].utilization_fraction == pytest.approx(0.2)
    assert result.per_server["s2"].utilization_fraction == pytest.approx(0.1)
    assert result.metrics.utilization_fraction == pytest.approx(0.15)
    assert result.metrics.load_imbalance_cv == pytest.approx(1 / 3)


def test_recovery_requires_three_consecutive_windows_and_resets_below_threshold():
    failure = FailureEvent(server_id="s1", failure_time_seconds=100, recovery_time_seconds=120)
    # Baseline is 1 completion/s. The first post-recovery window fails; the next 30s pass.
    completions = list(np.arange(40.5, 100, 1.0))
    completions += [125.0]  # Below 0.9 completions/s in [120,130).
    completions += list(np.arange(130.0, 160.0, 1.0))
    recovery, timestamps, reasons = calculate_recovery_times(
        (failure,), completions, warmup_seconds=40, simulation_end_seconds=200
    )
    assert recovery == [40]
    assert timestamps == [160]
    assert reasons == [None]


def test_recovery_unavailable_when_baseline_is_zero_or_too_short():
    failures = (
        FailureEvent(server_id="s1", failure_time_seconds=50, recovery_time_seconds=55),
        FailureEvent(server_id="s1", failure_time_seconds=100, recovery_time_seconds=110),
    )
    values, timestamps, reasons = calculate_recovery_times(
        failures, [], warmup_seconds=40, simulation_end_seconds=200
    )
    assert values == [None, None]
    assert timestamps == [None, None]
    assert "less than 60 seconds" in reasons[0]
    assert "zero" in reasons[1]


def test_paired_comparison_reuses_same_exogenous_trace_and_reproduces_outcomes():
    config = _config(
        workload=WorkloadConfig(kind="stable", duration_seconds=20, stable_rate_per_second=2),
        warmup_seconds=2,
        drain_seconds=5,
        request_deadline_seconds=5,
        servers=[
            ServerConfig(server_id="s1", capacity_slots=1, service_rate_per_slot_per_second=1),
            ServerConfig(server_id="s2", capacity_slots=2, service_rate_per_slot_per_second=2),
        ],
        failure_schedule=[
            FailureEvent(server_id="s1", failure_time_seconds=5, recovery_time_seconds=7)
        ],
    )
    first = run_paired_comparison(config, replications=2)
    second = run_paired_comparison(config, replications=2)
    assert [trace.signature() for trace in first.traces] == [
        trace.signature() for trace in second.traces
    ]
    assert first.policies == ("round_robin", "least_connections", "weighted")
    assert len(first.results) == 6
    assert all(len(trace.failures) == 1 for trace in first.traces)
    for replication in range(2):
        group = first.results[replication * 3 : (replication + 1) * 3]
        assert {result.scenario_id for result in group} == {first.traces[replication].trace_id}
        assert len({result.metrics.offered_request_count for result in group}) == 1
    assert [_metric_data(result) for result in first.results] == [
        _metric_data(result) for result in second.results
    ]
    assert first.summary.bootstrap_resamples == 10_000
    assert "least_connections-minus-round_robin" in first.summary.paired_mean_differences


def test_arrival_immediately_before_horizon_is_in_measurement_cohort():
    config = _config(
        workload=WorkloadConfig(kind="stable", duration_seconds=600, stable_rate_per_second=1),
        warmup_seconds=60,
        request_deadline_seconds=30,
        drain_seconds=60,
    )
    result = run_simulation(
        config,
        "round_robin",
        _trace(config, ("last-arrival", np.nextafter(600.0, 0.0), 0.5)),
    )
    assert result.metrics.offered_request_count == 1
    assert result.metrics.completed_request_count == 1
    assert result.metrics.mean_response_time_seconds == pytest.approx(0.5)


def test_policy_decision_overhead_reports_count_and_distribution(monkeypatch):
    import app.simulation.engine as engine

    clock = 0.0

    def fake_perf_counter():
        nonlocal clock
        current = clock
        clock += 0.25
        return current

    monkeypatch.setattr(engine, "perf_counter", fake_perf_counter)
    config = _config()
    result = run_simulation(config, "round_robin", _trace(config, ("r1", 0, 1), ("r2", 2, 1)))
    metrics = result.metrics
    assert metrics.policy_decision_count == 2
    assert metrics.policy_decision_wall_seconds == pytest.approx(0.5)
    assert metrics.mean_policy_decision_wall_seconds == pytest.approx(0.25)
    assert metrics.median_policy_decision_wall_seconds == pytest.approx(0.25)
    assert metrics.p95_policy_decision_wall_seconds == pytest.approx(0.25)
    assert metrics.p99_policy_decision_wall_seconds == pytest.approx(0.25)
    assert metrics.max_policy_decision_wall_seconds == pytest.approx(0.25)


def test_empty_policy_decision_sample_reports_zero_aggregates():
    config = _config()
    result = run_simulation(config, "round_robin", _trace(config))
    metrics = result.metrics
    assert metrics.policy_decision_count == 0
    assert metrics.policy_decision_wall_seconds == 0
    assert metrics.mean_policy_decision_wall_seconds == 0
    assert metrics.median_policy_decision_wall_seconds == 0
    assert metrics.p95_policy_decision_wall_seconds == 0
    assert metrics.p99_policy_decision_wall_seconds == 0
    assert metrics.max_policy_decision_wall_seconds == 0


def test_policy_wall_clock_duration_does_not_change_simulated_outcomes(monkeypatch):
    import app.simulation.engine as engine

    config = _config()
    trace = _trace(config, ("r1", 0, 1), ("r2", 2, 1))

    def install_clock(step):
        clock = 0.0

        def fake_perf_counter():
            nonlocal clock
            current = clock
            clock += step
            return current

        monkeypatch.setattr(engine, "perf_counter", fake_perf_counter)

    install_clock(0.001)
    fast_timing = run_simulation(config, "round_robin", trace)
    install_clock(5.0)
    slow_timing = run_simulation(config, "round_robin", trace)
    assert fast_timing.metrics.policy_decision_wall_seconds != (
        slow_timing.metrics.policy_decision_wall_seconds
    )
    assert _metric_data(fast_timing) == _metric_data(slow_timing)


def test_paired_trace_outcomes_do_not_depend_on_policy_execution_order():
    config = _config(
        workload=WorkloadConfig(kind="stable", duration_seconds=20, stable_rate_per_second=2),
        warmup_seconds=2,
        drain_seconds=5,
        request_deadline_seconds=5,
        servers=[
            ServerConfig(server_id="s1", capacity_slots=1, service_rate_per_slot_per_second=1),
            ServerConfig(server_id="s2", capacity_slots=2, service_rate_per_slot_per_second=2),
        ],
        failure_schedule=[
            FailureEvent(server_id="s1", failure_time_seconds=5, recovery_time_seconds=7)
        ],
    )
    forward = run_paired_comparison(config, replications=2)
    reverse = run_paired_comparison(
        config,
        policies=("weighted", "least_connections", "round_robin"),
        replications=2,
    )
    assert [trace.signature() for trace in forward.traces] == [
        trace.signature() for trace in reverse.traces
    ]
    forward_results = {(item.scenario_id, item.policy): _metric_data(item) for item in forward.results}
    reverse_results = {(item.scenario_id, item.policy): _metric_data(item) for item in reverse.results}
    assert forward_results == reverse_results

