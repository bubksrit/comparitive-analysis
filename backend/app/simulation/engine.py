"""Deterministic event engine for one policy and one immutable scenario trace."""

from __future__ import annotations

import heapq
import os
import platform
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, cast

import numpy as np
import pydantic

from app.models.common import RunMetadata
from app.models.simulation import (
    FailureEvent,
    SimulationConfig,
    SimulationPolicy,
    SimulationResult,
    SimulationSnapshot,
)
from app.simulation.comparison import PairedComparisonResult, summarize_comparison
from app.simulation.metrics import SimulationAccounting, calculate_metrics
from app.simulation.policies import PolicyContext, ServerView, make_policy
from app.simulation.state import RequestState, ServerState
from app.simulation.trace import SimulationTrace
from app.simulation.workloads import generate_trace

_COMPLETION = 0
_FAILURE_OR_RECOVERY = 1
_DEADLINE = 2
_ARRIVAL = 3
_SNAPSHOT = 4
_END = 5
_SNAPSHOT_INTERVAL_SECONDS = 10.0

Event = tuple[float, int, str, int, str, Any]


class SimulationCancelled(Exception):
    """Raised at a discrete-event boundary after cooperative cancellation."""


@dataclass(slots=True)
class _Counters:
    queue_overflow_drops: int = 0
    failure_drops: int = 0
    timed_out: int = 0
    decision_wall_seconds: float = 0.0
    decision_count: int = 0
    decision_wall_samples: list[float] = field(default_factory=list)


def _physical_memory_bytes() -> int | None:
    """Best-effort physical-memory provenance without an extra dependency."""
    if os.name == "nt":
        import ctypes

        class _MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong),
                ("available_phys", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatus()
        status.length = ctypes.sizeof(_MemoryStatus)
        kernel32 = getattr(ctypes, "windll", None)
        if kernel32 is not None and kernel32.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_phys)
    try:
        return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        return None


def _run_metadata(seed: int) -> RunMetadata:
    processor = platform.processor() or "unknown"
    memory_bytes = _physical_memory_bytes()
    memory_text = str(memory_bytes) if memory_bytes is not None else "unknown"
    return RunMetadata(
        seed=seed,
        software_versions={
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pydantic": pydantic.__version__,
        },
        hardware_description=(
            f"{platform.system()} {platform.release()}; processor={processor}; "
            f"logical_cpus={os.cpu_count()}; physical_memory_bytes={memory_text}"
        ),
    )


def _failure_signature(events: tuple[FailureEvent, ...]) -> tuple[tuple[str, float, float], ...]:
    return tuple(
        sorted(
            (
                event.server_id,
                event.failure_time_seconds,
                event.recovery_time_seconds,
            )
            for event in events
        )
    )


def _make_snapshot(
    time_seconds: float,
    servers: dict[str, ServerState],
    queue_depth: int,
) -> SimulationSnapshot:
    return SimulationSnapshot(
        time_seconds=time_seconds,
        server_health={server_id: server.healthy for server_id, server in servers.items()},
        active_requests_by_server={
            server_id: len(server.active_requests) for server_id, server in servers.items()
        },
        shared_queue_depth=queue_depth,
    )


def run_simulation(
    config: SimulationConfig,
    policy_id: SimulationPolicy,
    trace: SimulationTrace | None = None,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> SimulationResult:
    """Run one policy over one paired trace using the documented event ordering."""
    scenario_trace = trace or generate_trace(config)
    if scenario_trace.scenario_id != config.scenario_id:
        raise ValueError("trace scenario_id must match the simulation configuration")
    if _failure_signature(scenario_trace.failures) != _failure_signature(
        tuple(config.failure_schedule)
    ):
        raise ValueError("trace failure schedule must match the simulation configuration")
    server_order = tuple(server.server_id for server in config.servers)
    server_configs = {server.server_id: server for server in config.servers}
    servers = {
        server.server_id: ServerState(config=server.model_copy(deep=True))
        for server in config.servers
    }
    requests = {
        spec.request_id: RequestState(spec=spec) for spec in scenario_trace.arrivals
    }
    if len(requests) != len(scenario_trace.arrivals):
        raise ValueError("trace request IDs must be unique")
    for spec in scenario_trace.arrivals:
        if not 0 <= spec.arrival_time_seconds < config.workload.duration_seconds:
            raise ValueError("trace arrivals must fall within the half-open arrival horizon")
        if spec.work_demand_units <= 0:
            raise ValueError("request work demand must be positive")

    tie_rng = np.random.default_rng(np.random.SeedSequence(scenario_trace.seed).spawn(3)[2])
    tie_order = tuple(str(value) for value in tie_rng.permutation(server_order))
    policy = make_policy(policy_id, server_order)
    mean_request_demand = config.service_demand_parameters["mean_work_units"]
    waiting: deque[str] = deque()
    counters = _Counters()
    events: list[Event] = []
    sequence = 0

    def push(time_seconds: float, priority: int, order_key: str, kind: str, payload: Any) -> None:
        nonlocal sequence
        heapq.heappush(events, (time_seconds, priority, order_key, sequence, kind, payload))
        sequence += 1

    for spec in scenario_trace.arrivals:
        push(spec.arrival_time_seconds, _ARRIVAL, spec.request_id, "arrival", spec.request_id)
        if config.request_deadline_seconds is not None:
            deadline = spec.arrival_time_seconds + config.request_deadline_seconds
            push(deadline, _DEADLINE, spec.request_id, "deadline", spec.request_id)
    for failure in scenario_trace.failures:
        push(
            failure.failure_time_seconds,
            _FAILURE_OR_RECOVERY,
            f"{failure.server_id}:failure",
            "failure",
            failure.server_id,
        )
        push(
            failure.recovery_time_seconds,
            _FAILURE_OR_RECOVERY,
            f"{failure.server_id}:recovery",
            "recovery",
            failure.server_id,
        )

    simulation_end = config.workload.duration_seconds + config.drain_seconds
    snapshot_time = 0.0
    while snapshot_time <= simulation_end:
        push(snapshot_time, _SNAPSHOT, "snapshot", "snapshot", None)
        snapshot_time += _SNAPSHOT_INTERVAL_SECONDS
    push(simulation_end, _END, "end", "end", None)

    snapshots: list[SimulationSnapshot] = []
    measurement_start = config.warmup_seconds
    measurement_end = config.workload.duration_seconds
    last_time = 0.0

    def advance_interval(now: float) -> None:
        interval_start = max(last_time, measurement_start)
        interval_end = min(now, measurement_end)
        overlap = max(0.0, interval_end - interval_start)
        if overlap <= 0:
            return
        for server in servers.values():
            if server.healthy:
                server.healthy_available_slot_seconds += (
                    server.config.capacity_slots * overlap
                )
                server.busy_slot_seconds += len(server.active_requests) * overlap
            else:
                server.unavailable_seconds += overlap

    def eligible_server_ids() -> tuple[str, ...]:
        return tuple(
            server_id
            for server_id, server in servers.items()
            if server.healthy and server.free_slots > 0
        )

    def dispatch_one(request_id: str, queue_depth: int) -> None:
        request = requests[request_id]
        available_ids = eligible_server_ids()
        if not available_ids:
            raise RuntimeError("dispatch requires at least one eligible server")
        eligible = tuple(
            ServerView(server_configs[server_id], len(servers[server_id].active_requests))
            for server_id in available_ids
        )
        context = PolicyContext(
            eligible_servers=eligible,
            server_order=server_order,
            tie_order=tie_order,
            mean_request_demand=mean_request_demand,
            shared_queue_depth=queue_depth,
        )
        started_at = perf_counter()
        selected_id = policy.choose_server(context)
        decision_seconds = perf_counter() - started_at
        counters.decision_wall_seconds += decision_seconds
        counters.decision_count += 1
        counters.decision_wall_samples.append(decision_seconds)
        if selected_id not in available_ids:
            raise RuntimeError(f"policy {policy_id!r} selected an ineligible server")

        server = servers[selected_id]
        request.status = "in_service"
        request.server_id = selected_id
        request.dispatch_time_seconds = current_time
        server.active_requests[request_id] = None
        if measurement_start <= request.spec.arrival_time_seconds < measurement_end:
            server.dispatched_request_count += 1
        service_duration = (
            request.spec.work_demand_units
            / server.config.service_rate_per_slot_per_second
        )
        completion_time = current_time + service_duration
        if completion_time <= simulation_end:
            push(completion_time, _COMPLETION, request_id, "completion", request_id)

    def dispatch_waiting() -> None:
        while waiting and eligible_server_ids():
            request_id = waiting.popleft()
            dispatch_one(request_id, len(waiting) + 1)

    def handle_arrival(request_id: str) -> None:
        request = requests[request_id]
        request.status = "waiting"
        if not waiting and eligible_server_ids():
            dispatch_one(request_id, 1)
            return
        if len(waiting) >= config.queue_limit_requests:
            request.status = "queue_overflow_drop"
            counters.queue_overflow_drops += 1
            return
        waiting.append(request_id)
        dispatch_waiting()

    last_time = 0.0
    while events:
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("simulation cancellation requested")
        current_time = events[0][0]
        if current_time > simulation_end:
            break
        advance_interval(current_time)
        current_batch: list[Event] = []
        while events and events[0][0] == current_time:
            current_batch.append(heapq.heappop(events))
        current_batch.sort(key=lambda event: (event[1], event[2], event[3]))

        for event in current_batch:
            if event[1] != _COMPLETION:
                continue
            request_id = cast(str, event[5])
            request = requests[request_id]
            if request.status != "in_service" or request.server_id is None:
                continue
            server = servers[request.server_id]
            server.active_requests.pop(request_id, None)
            request.status = "completed"
            request.completion_time_seconds = current_time
            if measurement_start <= request.spec.arrival_time_seconds < measurement_end:
                server.completed_request_count += 1

        for event in current_batch:
            if event[1] != _FAILURE_OR_RECOVERY:
                continue
            server_id = cast(str, event[5])
            server = servers[server_id]
            if event[4] == "failure":
                if not server.healthy:
                    raise RuntimeError(f"server {server_id!r} failed while already unavailable")
                server.healthy = False
                for request_id in tuple(server.active_requests):
                    request = requests[request_id]
                    request.status = "failure_drop"
                    request.server_id = None
                    counters.failure_drops += 1
                server.active_requests.clear()
            else:
                if server.healthy:
                    raise RuntimeError(f"server {server_id!r} recovered while already healthy")
                server.healthy = True

        for event in current_batch:
            if event[1] != _DEADLINE:
                continue
            request_id = cast(str, event[5])
            request = requests[request_id]
            if request.status == "waiting":
                try:
                    waiting.remove(request_id)
                except ValueError:
                    pass
                request.status = "timed_out"
                counters.timed_out += 1
            elif request.status == "in_service" and request.server_id is not None:
                servers[request.server_id].active_requests.pop(request_id, None)
                request.server_id = None
                request.status = "timed_out"
                counters.timed_out += 1

        dispatch_waiting()
        for event in current_batch:
            if event[1] == _ARRIVAL:
                handle_arrival(cast(str, event[5]))
            elif event[1] == _SNAPSHOT:
                snapshots.append(_make_snapshot(current_time, servers, len(waiting)))
        last_time = current_time

    if cancel_check is not None and cancel_check():
        raise SimulationCancelled("simulation cancellation requested")
    advance_interval(simulation_end)
    offered = sum(
        measurement_start <= spec.arrival_time_seconds < measurement_end
        for spec in scenario_trace.arrivals
    )
    completed_count = sum(
        request.status == "completed"
        and measurement_start <= request.spec.arrival_time_seconds < measurement_end
        for request in requests.values()
    )
    accounting = SimulationAccounting(
        offered_request_count=offered,
        completed_request_count=completed_count,
        queue_overflow_drop_count=counters.queue_overflow_drops,
        failure_drop_count=counters.failure_drops,
        timed_out_request_count=counters.timed_out,
        policy_decision_wall_seconds=counters.decision_wall_seconds,
        policy_decision_count=counters.decision_count,
        policy_decision_wall_samples=tuple(counters.decision_wall_samples),
    )
    metrics, per_server = calculate_metrics(
        config,
        scenario_trace,
        requests,
        servers,
        accounting,
        simulation_end_seconds=simulation_end,
    )
    assumptions = [
        "Discrete-event simulation; all performance values are simulated.",
        "Each request occupies one service slot; service duration equals work demand divided by per-slot rate.",
        "One shared FIFO queue; failed in-flight requests are dropped and are not replayed.",
        "CPU is a simulated busy-slot proxy; physical CPU and memory are not measured.",
        "The discrete-event loop is single-threaded; policy decision wall time uses perf_counter.",
    ]
    return SimulationResult(
        metadata=_run_metadata(scenario_trace.seed),
        policy=policy_id,
        scenario_id=scenario_trace.trace_id,
        trace_seed=scenario_trace.seed,
        configuration=config,
        metrics=metrics,
        per_server=per_server,
        snapshots=snapshots,
        assumptions=assumptions,
    )


def run_paired_comparison(
    config: SimulationConfig,
    policies: tuple[SimulationPolicy, ...] = (
        "round_robin",
        "least_connections",
        "weighted",
    ),
    replications: int = 10,
    *,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> PairedComparisonResult:
    """Replay common seeded traces for every requested policy and summarize pairs."""
    replication_count = replications
    if replication_count < 1:
        raise ValueError("replications must be at least one")
    if not policies or len(set(policies)) != len(policies):
        raise ValueError("policies must be a nonempty list without duplicates")
    seed_sequences = np.random.SeedSequence(config.seed).spawn(replication_count + 1)
    traces: list[SimulationTrace] = []
    results = []
    completed_policy_runs = 0
    total_policy_runs = replication_count * len(policies)
    for seed_sequence in seed_sequences[:-1]:
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("simulation cancellation requested")
        replication_seed = int(seed_sequence.generate_state(1, dtype=np.uint32)[0])
        trace = generate_trace(config, replication_seed)
        traces.append(trace)
        for policy_id in policies:
            if cancel_check is not None and cancel_check():
                raise SimulationCancelled("simulation cancellation requested")
            results.append(run_simulation(config, policy_id, trace, cancel_check=cancel_check))
            completed_policy_runs += 1
            if progress_callback is not None:
                progress_callback(
                    completed_policy_runs,
                    total_policy_runs,
                    completed_policy_runs // len(policies),
                    replication_count,
                )
    if cancel_check is not None and cancel_check():
        raise SimulationCancelled("simulation cancellation requested")
    bootstrap_seed = int(seed_sequences[-1].generate_state(1, dtype=np.uint32)[0])
    summary = summarize_comparison(tuple(results), policies, replication_count, bootstrap_seed)
    return PairedComparisonResult(
        master_seed=config.seed,
        replications=replication_count,
        policies=policies,
        configuration=config,
        traces=tuple(traces),
        results=tuple(results),
        summary=summary,
    )
