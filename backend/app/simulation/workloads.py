"""Seeded generators for the three approved exogenous traffic processes."""

from collections.abc import Iterable

import numpy as np

from app.models.simulation import SimulationConfig, WorkloadConfig
from app.simulation.trace import ArrivalSpec, SimulationTrace


def _poisson_arrivals(
    rng: np.random.Generator, start: float, end: float, rate: float
) -> Iterable[float]:
    """Generate a stationary Poisson process on the half-open interval."""
    time_seconds = start
    while True:
        time_seconds += float(rng.exponential(1.0 / rate))
        if time_seconds >= end:
            return
        yield time_seconds


def _increasing_arrivals(
    rng: np.random.Generator,
    duration: float,
    start_rate: float,
    end_rate: float,
) -> Iterable[float]:
    """Thin a homogeneous process at the maximum rate for exact NHPP sampling."""
    maximum_rate = max(start_rate, end_rate)
    time_seconds = 0.0
    while True:
        time_seconds += float(rng.exponential(1.0 / maximum_rate))
        if time_seconds >= duration:
            return
        fraction = time_seconds / duration
        current_rate = start_rate + (end_rate - start_rate) * fraction
        if rng.random() < current_rate / maximum_rate:
            yield time_seconds


def _bursty_arrivals(
    rng: np.random.Generator,
    duration: float,
    period: float,
    high_duration: float,
    low_rate: float,
    high_rate: float,
) -> Iterable[float]:
    """Generate alternating independent Poisson segments on a half-open horizon."""
    period_start = 0.0
    while period_start < duration:
        high_start = period_start + period - high_duration
        low_end = min(high_start, duration)
        if period_start < low_end:
            yield from _poisson_arrivals(rng, period_start, low_end, low_rate)
        high_end = min(period_start + period, duration)
        if high_start < high_end:
            yield from _poisson_arrivals(rng, high_start, high_end, high_rate)
        period_start += period


def generate_trace(config: SimulationConfig, seed: int | None = None) -> SimulationTrace:
    """Generate an immutable scenario trace, independent of policy behavior."""
    trace_seed = config.seed if seed is None else seed
    if trace_seed < 0:
        raise ValueError("trace seed must be nonnegative")
    arrival_sequence, demand_sequence = np.random.SeedSequence(trace_seed).spawn(2)
    arrival_rng = np.random.default_rng(arrival_sequence)
    demand_rng = np.random.default_rng(demand_sequence)
    workload: WorkloadConfig = config.workload
    duration = workload.duration_seconds

    if workload.kind == "stable":
        arrival_times = list(
            _poisson_arrivals(arrival_rng, 0.0, duration, workload.stable_rate_per_second)
        )
    elif workload.kind == "increasing":
        arrival_times = list(
            _increasing_arrivals(
                arrival_rng,
                duration,
                workload.increasing_start_rate_per_second,
                workload.increasing_end_rate_per_second,
            )
        )
    else:
        arrival_times = list(
            _bursty_arrivals(
                arrival_rng,
                duration,
                workload.burst_period_seconds,
                workload.burst_high_duration_seconds,
                workload.burst_low_rate_per_second,
                workload.burst_high_rate_per_second,
            )
        )

    arrival_times.sort()
    mean_work = config.service_demand_parameters["mean_work_units"]
    if config.service_demand_distribution == "exponential":
        demands = demand_rng.exponential(mean_work, size=len(arrival_times))
        demands = np.maximum(demands, np.finfo(float).tiny)
    else:
        demands = np.full(len(arrival_times), mean_work, dtype=float)

    arrivals = tuple(
        ArrivalSpec(
            request_id=f"req-{index:08d}",
            arrival_time_seconds=arrival_time,
            work_demand_units=float(demands[index]),
        )
        for index, arrival_time in enumerate(arrival_times)
    )
    failures = tuple(
        sorted(
            (event.model_copy(deep=True) for event in config.failure_schedule),
            key=lambda event: (event.failure_time_seconds, event.server_id),
        )
    )
    return SimulationTrace(
        scenario_id=config.scenario_id,
        seed=trace_seed,
        arrivals=arrivals,
        failures=failures,
        trace_id=f"{config.scenario_id}:{trace_seed}",
    )
