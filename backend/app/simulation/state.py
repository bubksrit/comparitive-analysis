"""Small mutable runtime records owned by a single simulation run."""

from dataclasses import dataclass, field

from app.models.simulation import ServerConfig
from app.simulation.trace import ArrivalSpec


@dataclass(slots=True)
class RequestState:
    spec: ArrivalSpec
    status: str = "not_arrived"
    server_id: str | None = None
    dispatch_time_seconds: float | None = None
    completion_time_seconds: float | None = None


@dataclass(slots=True)
class ServerState:
    config: ServerConfig
    healthy: bool = True
    active_requests: dict[str, None] = field(default_factory=dict)
    busy_slot_seconds: float = 0.0
    healthy_available_slot_seconds: float = 0.0
    unavailable_seconds: float = 0.0
    dispatched_request_count: int = 0
    completed_request_count: int = 0

    @property
    def free_slots(self) -> int:
        return self.config.capacity_slots - len(self.active_requests)
