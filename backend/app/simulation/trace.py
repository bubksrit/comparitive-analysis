"""Immutable exogenous inputs shared by policies in paired comparisons."""

from dataclasses import dataclass, field
from typing import Any

from app.models.simulation import FailureEvent


@dataclass(frozen=True, slots=True)
class ArrivalSpec:
    request_id: str
    arrival_time_seconds: float
    work_demand_units: float
    request_attributes: dict[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SimulationTrace:
    scenario_id: str
    seed: int
    arrivals: tuple[ArrivalSpec, ...]
    failures: tuple[FailureEvent, ...]
    trace_id: str

    def signature(self) -> tuple[Any, ...]:
        """Return all exogenous inputs in a stable, equality-friendly form."""
        return (
            self.scenario_id,
            self.seed,
            tuple(
                (
                    item.request_id,
                    item.arrival_time_seconds,
                    item.work_demand_units,
                    tuple(sorted(item.request_attributes.items())),
                )
                for item in self.arrivals
            ),
            tuple(
                (
                    item.server_id,
                    item.failure_time_seconds,
                    item.recovery_time_seconds,
                )
                for item in self.failures
            ),
        )
