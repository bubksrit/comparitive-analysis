"""The three approved deterministic routing policies."""

from dataclasses import dataclass
from typing import Protocol

from app.models.simulation import ServerConfig, SimulationPolicy


@dataclass(frozen=True, slots=True)
class ServerView:
    config: ServerConfig
    active_request_count: int


@dataclass(frozen=True, slots=True)
class PolicyContext:
    eligible_servers: tuple[ServerView, ...]
    server_order: tuple[str, ...]
    tie_order: tuple[str, ...]
    mean_request_demand: float
    shared_queue_depth: int


class RoutingPolicy(Protocol):
    policy_id: SimulationPolicy

    def choose_server(self, context: PolicyContext) -> str: ...


class RoundRobinPolicy:
    """Cycle through configured server order, skipping ineligible servers."""

    policy_id: SimulationPolicy = "round_robin"

    def __init__(self, server_order: tuple[str, ...]) -> None:
        self._server_order = server_order
        self._cursor = 0
        self._index = {server_id: index for index, server_id in enumerate(server_order)}

    def choose_server(self, context: PolicyContext) -> str:
        eligible_ids = {server.config.server_id for server in context.eligible_servers}
        for offset in range(len(self._server_order)):
            index = (self._cursor + offset) % len(self._server_order)
            server_id = self._server_order[index]
            if server_id in eligible_ids:
                self._cursor = (index + 1) % len(self._server_order)
                return server_id
        raise ValueError("Round Robin requires at least one eligible server")


class LeastConnectionsPolicy:
    """Choose the eligible server with the fewest active requests."""

    policy_id: SimulationPolicy = "least_connections"

    def choose_server(self, context: PolicyContext) -> str:
        tie_rank = {server_id: index for index, server_id in enumerate(context.tie_order)}
        selected = min(
            context.eligible_servers,
            key=lambda server: (
                server.active_request_count,
                tie_rank[server.config.server_id],
            ),
        )
        return selected.config.server_id


class CapacityAwareWeightedPolicy:
    """Minimize estimated active work divided by effective server capacity."""

    policy_id: SimulationPolicy = "weighted"

    def choose_server(self, context: PolicyContext) -> str:
        tie_rank = {server_id: index for index, server_id in enumerate(context.tie_order)}

        def score(server: ServerView) -> tuple[float, int]:
            config = server.config
            effective_capacity = (
                config.capacity_slots * config.service_rate_per_slot_per_second
            )
            accumulated_work = context.mean_request_demand * server.active_request_count
            return accumulated_work / effective_capacity, tie_rank[config.server_id]

        return min(context.eligible_servers, key=score).config.server_id


def make_policy(
    policy_id: SimulationPolicy, server_order: tuple[str, ...]
) -> RoutingPolicy:
    """Construct a fresh policy instance for one independent run."""
    if policy_id == "round_robin":
        return RoundRobinPolicy(server_order)
    if policy_id == "least_connections":
        return LeastConnectionsPolicy()
    if policy_id == "weighted":
        return CapacityAwareWeightedPolicy()
    raise ValueError(f"unsupported Study B policy: {policy_id}")
