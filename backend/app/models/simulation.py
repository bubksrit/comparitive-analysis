"""Study B configuration and result schemas (no simulator or policies)."""

from typing import Literal

from pydantic import Field, model_validator

from app.models.common import RunMetadata, StrictModel


class ServerConfig(StrictModel):
    server_id: str
    capacity_slots: int = Field(ge=1)
    service_rate_per_slot_per_second: float = Field(gt=0)
    routing_weight: float = Field(default=1.0, ge=0)


class FailureEvent(StrictModel):
    server_id: str
    failure_time_seconds: float = Field(ge=0)
    recovery_time_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def recovery_follows_failure(self) -> "FailureEvent":
        if self.recovery_time_seconds <= self.failure_time_seconds:
            raise ValueError("recovery_time_seconds must follow failure_time_seconds")
        return self


class WorkloadConfig(StrictModel):
    kind: Literal["stable", "increasing", "bursty"]
    duration_seconds: float = Field(gt=0)
    stable_rate_per_second: float | None = Field(default=None, gt=0)
    increasing_start_rate_per_second: float | None = Field(default=None, gt=0)
    increasing_end_rate_per_second: float | None = Field(default=None, gt=0)
    burst_low_rate_per_second: float | None = Field(default=None, gt=0)
    burst_high_rate_per_second: float | None = Field(default=None, gt=0)
    burst_period_seconds: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def has_parameters_for_workload_kind(self) -> "WorkloadConfig":
        required_fields = {
            "stable": ("stable_rate_per_second",),
            "increasing": ("increasing_start_rate_per_second", "increasing_end_rate_per_second"),
            "bursty": ("burst_low_rate_per_second", "burst_high_rate_per_second", "burst_period_seconds"),
        }[self.kind]
        missing = [field for field in required_fields if getattr(self, field) is None]
        if missing:
            raise ValueError(f"Missing workload parameters: {', '.join(missing)}")
        return self


class OptimizationObjectiveConfig(StrictModel):
    response_time_weight: float = Field(default=1 / 3, ge=0, le=1)
    load_imbalance_weight: float = Field(default=1 / 3, ge=0, le=1)
    request_drop_weight: float = Field(default=1 / 3, ge=0, le=1)
    response_time_reference_seconds: float = Field(gt=0)
    decision_evaluation_budget: int = Field(ge=1)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "OptimizationObjectiveConfig":
        total = (
            self.response_time_weight
            + self.load_imbalance_weight
            + self.request_drop_weight
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError("Optimization objective weights must sum to 1.0")
        return self


class SimulationConfig(StrictModel):
    seed: int = Field(ge=0)
    scenario_id: str
    workload: WorkloadConfig
    servers: list[ServerConfig] = Field(min_length=1)
    failure_schedule: list[FailureEvent] = Field(default_factory=list)
    warmup_seconds: float = Field(default=0, ge=0)
    drain_seconds: float = Field(default=0, ge=0)
    queue_limit_requests: int = Field(default=0, ge=0)
    request_deadline_seconds: float | None = Field(default=None, gt=0)
    service_demand_distribution: str
    service_demand_parameters: dict[str, float]
    optimization_objective: OptimizationObjectiveConfig | None = None


class RequestContext(StrictModel):
    request_id: str
    arrival_time_seconds: float = Field(ge=0)
    request_attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)
    current_time_seconds: float = Field(ge=0)
    server_health: dict[str, bool]
    active_requests_by_server: dict[str, int]
    queued_requests_by_server: dict[str, int]
    service_rate_estimates_per_slot_per_second: dict[str, float]


class PolicyDecision(StrictModel):
    server_id: str | None
    dropped: bool = False
    fallback_used: bool = False
    decision_wall_seconds: float = Field(ge=0)
    optimizer_evaluation_count: int = Field(default=0, ge=0)


class SimulationMetrics(StrictModel):
    mean_response_time_seconds: float | None = Field(default=None, ge=0)
    p95_latency_seconds: float | None = Field(default=None, ge=0)
    p99_latency_seconds: float | None = Field(default=None, ge=0)
    throughput_requests_per_second: float = Field(ge=0)
    utilization_fraction: float = Field(ge=0, le=1)
    load_imbalance_cv: float = Field(ge=0)
    dropped_request_count: int = Field(ge=0)
    timed_out_request_count: int = Field(ge=0)
    recovery_time_seconds: list[float | None] = Field(default_factory=list)
    policy_decision_wall_seconds: float = Field(ge=0)


class SimulationResult(StrictModel):
    metadata: RunMetadata
    study_label: Literal["simulated load balancing"] = "simulated load balancing"
    policy: Literal["round_robin", "least_connections", "weighted", "random_forest", "ga", "pso", "aco"]
    scenario_id: str
    metrics: SimulationMetrics
    per_server_utilization: dict[str, float]
    assumptions: list[str] = Field(default_factory=list)
