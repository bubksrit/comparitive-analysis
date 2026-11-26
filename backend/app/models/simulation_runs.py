"""HTTP request and response schemas for simulation run lifecycle endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.models.common import StrictModel
from app.models.simulation import (
    SimulationConfig,
    SimulationPolicy,
    SimulationResult,
)

SimulationRunStatus = Literal[
    "queued", "running", "completed", "failed", "cancelling", "cancelled"
]


class SimulationRunRequest(SimulationConfig):
    """Simulation configuration plus policy and replication controls."""

    policies: tuple[SimulationPolicy, ...] = (
        "round_robin",
        "least_connections",
        "weighted",
    )
    replications: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def validate_policies(self) -> "SimulationRunRequest":
        if not self.policies:
            raise ValueError("policies must contain at least one policy")
        if len(set(self.policies)) != len(self.policies):
            raise ValueError("policies must not contain duplicates")
        return self

    def simulation_config(self) -> SimulationConfig:
        return SimulationConfig.model_validate(
            self.model_dump(exclude={"policies", "replications"})
        )


class SimulationRunProgress(StrictModel):
    completed_replications: int = Field(ge=0)
    total_replications: int = Field(ge=1)
    completed_policy_runs: int = Field(ge=0)
    total_policy_runs: int = Field(ge=1)


class SimulationRunError(StrictModel):
    code: str
    message: str


class SimulationRunStatusResponse(StrictModel):
    run_id: str
    status: SimulationRunStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: SimulationRunProgress
    error: SimulationRunError | None = None


class MetricEstimateResponse(StrictModel):
    mean: float | None
    standard_deviation: float | None
    confidence_interval_95: tuple[float, float] | None
    sample_count: int = Field(ge=0)


class ComparisonSummaryResponse(StrictModel):
    by_policy: dict[str, dict[str, MetricEstimateResponse]]
    paired_mean_differences: dict[str, dict[str, MetricEstimateResponse]]
    bootstrap_resamples: int = Field(ge=1)
    bootstrap_seed: int = Field(ge=0)


class SimulationRunResultsResponse(StrictModel):
    run_id: str
    status: Literal["completed"]
    master_seed: int = Field(ge=0)
    replication_seeds: list[int]
    replications: int = Field(ge=1)
    policies: tuple[SimulationPolicy, ...]
    configuration: SimulationConfig
    results: list[SimulationResult]
    summary: ComparisonSummaryResponse
    metric_definitions: dict[str, str]
