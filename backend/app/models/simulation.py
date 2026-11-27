"""Validated configuration and result schemas for simulated load balancing."""

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from app.models.common import RunMetadata, StrictModel

SimulationPolicy = Literal["round_robin", "least_connections", "weighted"]


class SimulationModel(StrictModel):
    """Base schema that rejects non-finite values in simulation inputs/outputs."""

    model_config = ConfigDict(allow_inf_nan=False)


def default_servers() -> list["ServerConfig"]:
    """Return the approved heterogeneous 2/4/6-slot fleet."""
    return [
        ServerConfig(
            server_id="server-1",
            capacity_slots=2,
            service_rate_per_slot_per_second=10.0,
        ),
        ServerConfig(
            server_id="server-2",
            capacity_slots=4,
            service_rate_per_slot_per_second=10.0,
        ),
        ServerConfig(
            server_id="server-3",
            capacity_slots=6,
            service_rate_per_slot_per_second=10.0,
        ),
    ]


class ServerConfig(SimulationModel):
    server_id: str = Field(min_length=1)
    capacity_slots: int = Field(ge=1)
    service_rate_per_slot_per_second: float = Field(gt=0)
    # Retained only to ease loading old draft configs; v1 policies ignore it.
    routing_weight: float = Field(default=1.0, ge=0)


class FailureEvent(SimulationModel):
    server_id: str = Field(min_length=1)
    failure_time_seconds: float = Field(ge=0)
    recovery_time_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def recovery_follows_failure(self) -> "FailureEvent":
        if self.recovery_time_seconds <= self.failure_time_seconds:
            raise ValueError("recovery_time_seconds must follow failure_time_seconds")
        return self


class WorkloadConfig(SimulationModel):
    kind: Literal["stable", "increasing", "bursty"] = "stable"
    duration_seconds: float = Field(default=600.0, gt=0)
    stable_rate_per_second: float = Field(default=60.0, gt=0)
    increasing_start_rate_per_second: float = Field(default=30.0, gt=0)
    increasing_end_rate_per_second: float = Field(default=150.0, gt=0)
    burst_low_rate_per_second: float = Field(default=30.0, gt=0)
    burst_high_rate_per_second: float = Field(default=150.0, gt=0)
    burst_period_seconds: float = Field(default=60.0, gt=0)
    burst_high_duration_seconds: float = Field(default=15.0, gt=0)

    @model_validator(mode="after")
    def validate_burst_period(self) -> "WorkloadConfig":
        if self.burst_high_duration_seconds > self.burst_period_seconds:
            raise ValueError("burst high-rate duration cannot exceed its period")
        if (
            self.kind == "increasing"
            and self.increasing_end_rate_per_second < self.increasing_start_rate_per_second
        ):
            raise ValueError("increasing workload end rate cannot be lower than its start rate")
        return self


class SimulationConfig(SimulationModel):
    seed: int = Field(default=42, ge=0)
    scenario_id: str = Field(default="stable-default", min_length=1)
    workload: WorkloadConfig = Field(default_factory=WorkloadConfig)
    servers: list[ServerConfig] = Field(default_factory=default_servers, min_length=1)
    failure_schedule: list[FailureEvent] = Field(default_factory=list)
    warmup_seconds: float = Field(default=60.0, ge=0)
    drain_seconds: float = Field(default=60.0, ge=0)
    queue_limit_requests: int = Field(default=1000, ge=0)
    request_deadline_seconds: float = Field(default=30.0, gt=0)
    service_demand_distribution: Literal["exponential", "deterministic"] = "exponential"
    service_demand_parameters: dict[str, float] = Field(
        default_factory=lambda: {"mean_work_units": 1.0}
    )
    @model_validator(mode="after")
    def validate_simulation_contract(self) -> "SimulationConfig":
        if self.warmup_seconds >= self.workload.duration_seconds:
            raise ValueError("warmup_seconds must be less than the arrival horizon")
        if self.drain_seconds < self.request_deadline_seconds:
            raise ValueError("drain_seconds must be at least the request deadline")

        server_ids = [server.server_id for server in self.servers]
        if len(set(server_ids)) != len(server_ids):
            raise ValueError("server_id values must be unique")

        mean_demand = self.service_demand_parameters.get("mean_work_units")
        if mean_demand is None or mean_demand <= 0:
            raise ValueError("service_demand_parameters.mean_work_units must be positive")
        unexpected_parameters = set(self.service_demand_parameters) - {"mean_work_units"}
        if unexpected_parameters:
            raise ValueError(
                "unsupported service demand parameters: "
                + ", ".join(sorted(unexpected_parameters))
            )

        server_id_set = set(server_ids)
        latest_time = self.workload.duration_seconds + self.drain_seconds
        failures_by_server: dict[str, list[FailureEvent]] = {}
        for failure in self.failure_schedule:
            if failure.server_id not in server_id_set:
                raise ValueError(f"failure schedule references unknown server {failure.server_id!r}")
            if failure.recovery_time_seconds > latest_time:
                raise ValueError("failure recovery must occur by the end of the drain")
            failures_by_server.setdefault(failure.server_id, []).append(failure)

        for server_id, failures in failures_by_server.items():
            ordered = sorted(failures, key=lambda item: item.failure_time_seconds)
            for previous, following in zip(ordered, ordered[1:], strict=False):
                if following.failure_time_seconds <= previous.recovery_time_seconds:
                    raise ValueError(
                        f"failure intervals for server {server_id!r} cannot overlap or touch"
                    )
        return self


class RequestContext(SimulationModel):
    """Policy-visible state at the moment a FIFO head is dispatched."""

    request_id: str
    arrival_time_seconds: float = Field(ge=0)
    current_time_seconds: float = Field(ge=0)
    shared_queue_depth: int = Field(ge=0)
    server_health: dict[str, bool]
    active_requests_by_server: dict[str, int]
    capacity_slots_by_server: dict[str, int]
    service_rate_estimates_per_slot_per_second: dict[str, float]


class PolicyDecision(SimulationModel):
    server_id: str | None
    dropped: bool = False
    decision_wall_seconds: float = Field(ge=0)


class ServerSimulationMetrics(SimulationModel):
    utilization_fraction: float = Field(ge=0, le=1)
    simulated_cpu_proxy_fraction: float = Field(ge=0, le=1)
    healthy_available_seconds: float = Field(ge=0)
    unavailable_seconds: float = Field(ge=0)
    dispatched_request_count: int = Field(ge=0)
    completed_request_count: int = Field(ge=0)
    dispatch_share: float = Field(ge=0, le=1)


class SimulationMetrics(SimulationModel):
    mean_response_time_seconds: float | None = Field(default=None, ge=0)
    median_response_time_seconds: float | None = Field(default=None, ge=0)
    p95_latency_seconds: float | None = Field(default=None, ge=0)
    p99_latency_seconds: float | None = Field(default=None, ge=0)
    throughput_requests_per_second: float = Field(ge=0)
    utilization_fraction: float = Field(ge=0, le=1)
    simulated_cpu_proxy_fraction: float = Field(ge=0, le=1)
    load_imbalance_cv: float | None = Field(default=None, ge=0)
    offered_request_count: int = Field(ge=0)
    completed_request_count: int = Field(ge=0)
    queue_overflow_drop_count: int = Field(ge=0)
    failure_drop_count: int = Field(ge=0)
    dropped_request_count: int = Field(ge=0)
    timed_out_request_count: int = Field(ge=0)
    queue_overflow_drop_rate: float = Field(ge=0, le=1)
    failure_drop_rate: float = Field(ge=0, le=1)
    timed_out_request_rate: float = Field(ge=0, le=1)
    total_request_loss_rate: float = Field(ge=0, le=1)
    recovery_time_seconds: list[float | None] = Field(default_factory=list)
    recovery_timestamp_seconds: list[float | None] = Field(default_factory=list)
    recovery_unavailable_reasons: list[str | None] = Field(default_factory=list)
    policy_decision_count: int = Field(ge=0)
    policy_decision_wall_seconds: float = Field(ge=0)
    mean_policy_decision_wall_seconds: float = Field(ge=0)
    median_policy_decision_wall_seconds: float = Field(ge=0)
    p95_policy_decision_wall_seconds: float = Field(ge=0)
    p99_policy_decision_wall_seconds: float = Field(ge=0)
    max_policy_decision_wall_seconds: float = Field(ge=0)


class SimulationSnapshot(SimulationModel):
    time_seconds: float = Field(ge=0)
    server_health: dict[str, bool]
    active_requests_by_server: dict[str, int]
    shared_queue_depth: int = Field(ge=0)


class SimulationResult(SimulationModel):
    metadata: RunMetadata
    study_label: Literal["simulated load balancing"] = "simulated load balancing"
    policy: SimulationPolicy
    scenario_id: str
    trace_seed: int = Field(ge=0)
    configuration: SimulationConfig
    metrics: SimulationMetrics
    per_server: dict[str, ServerSimulationMetrics]
    snapshots: list[SimulationSnapshot] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
