"""API integration tests for simulation run lifecycle and concurrency behavior."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.models.simulation import SimulationConfig
from app.simulation.engine import SimulationCancelled, run_paired_comparison, run_simulation
from app.simulation.runs import SimulationRunRegistry
from app.simulation.trace import SimulationTrace


def _payload(**overrides):
    payload = {
        "seed": 7,
        "scenario_id": "api-test",
        "workload": {
            "kind": "stable",
            "duration_seconds": 2,
            "stable_rate_per_second": 1,
        },
        "servers": [
            {
                "server_id": "api-server",
                "capacity_slots": 1,
                "service_rate_per_slot_per_second": 1,
            }
        ],
        "warmup_seconds": 0,
        "drain_seconds": 30,
        "request_deadline_seconds": 30,
        "queue_limit_requests": 10,
        "service_demand_distribution": "deterministic",
        "service_demand_parameters": {"mean_work_units": 1},
        "policies": ["round_robin", "least_connections", "weighted"],
        "replications": 1,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def make_client():
    clients: list[TestClient] = []

    def factory(runner=run_paired_comparison):
        registry = SimulationRunRegistry(runner=runner)
        client = TestClient(create_app(registry))
        client.__enter__()
        clients.append(client)
        return client, registry

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def _wait_for(client: TestClient, run_id: str, expected_status: str) -> dict:
    deadline = monotonic() + 5
    latest = None
    while monotonic() < deadline:
        response = client.get(f"/api/v1/simulations/{run_id}")
        assert response.status_code == 200
        latest = response.json()
        if latest["status"] == expected_status:
            return latest
        sleep(0.01)
    raise AssertionError(f"run did not reach {expected_status!r}; last status was {latest}")


def test_post_starts_valid_run_and_returns_queued_status(make_client):
    client, _ = make_client()
    response = client.post("/api/v1/simulations", json=_payload())
    assert response.status_code == 202
    data = response.json()
    assert data["run_id"]
    assert data["status"] == "queued"
    assert data["created_at"]
    assert data["progress"] == {
        "completed_replications": 0,
        "total_replications": 1,
        "completed_policy_runs": 0,
        "total_policy_runs": 3,
    }


def test_invalid_configuration_returns_useful_validation_errors(make_client):
    client, _ = make_client()
    payload = _payload(servers=[])
    response = client.post("/api/v1/simulations", json=payload)
    assert response.status_code == 422
    assert "servers" in response.text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policies", ["random_forest"]),
        ("replications", 0),
        ("replications", -1),
        (
            "workload",
            {
                "kind": "increasing",
                "duration_seconds": 600,
                "increasing_start_rate_per_second": 150,
                "increasing_end_rate_per_second": 30,
            },
        ),
    ],
)
def test_invalid_policy_replication_and_increasing_workload_return_422(
    make_client, field, value
):
    client, _ = make_client()
    payload = _payload(**{field: value})
    response = client.post("/api/v1/simulations", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_service_demand_returns_422(make_client, value):
    client, _ = make_client()
    payload = _payload(service_demand_parameters={"mean_work_units": value})
    response = client.post(
        "/api/v1/simulations",
        content=json.dumps(payload, allow_nan=True),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "path",
    [
        ("servers", 0, "service_rate_per_slot_per_second"),
        ("servers", 0, "routing_weight"),
        ("failure_schedule", 0, "failure_time_seconds"),
        ("failure_schedule", 0, "recovery_time_seconds"),
        ("workload", "duration_seconds"),
        ("workload", "stable_rate_per_second"),
        ("workload", "increasing_start_rate_per_second"),
        ("workload", "increasing_end_rate_per_second"),
        ("workload", "burst_low_rate_per_second"),
        ("workload", "burst_high_rate_per_second"),
        ("workload", "burst_period_seconds"),
        ("workload", "burst_high_duration_seconds"),
        ("warmup_seconds",),
        ("drain_seconds",),
        ("request_deadline_seconds",),
        ("service_demand_parameters", "mean_work_units"),
    ],
)
def test_all_float_configuration_fields_reject_nonfinite_values(path, value):
    payload = _payload()
    payload["failure_schedule"] = [
        {"server_id": "api-server", "failure_time_seconds": 1, "recovery_time_seconds": 2}
    ]
    current = payload
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    payload.pop("policies")
    payload.pop("replications")
    with pytest.raises(ValidationError):
        SimulationConfig.model_validate(payload)


def test_status_progress_and_timestamps_update_while_running(make_client):
    entered = Event()
    release = Event()

    def gated_runner(config, policies, replications, *, progress_callback, cancel_check):
        progress_callback(1, 2, 0, 2)
        entered.set()
        assert release.wait(5)
        if cancel_check():
            raise SimulationCancelled
        progress_callback(2, 2, 2, 2)
        return run_paired_comparison(config, policies, replications)

    client, _ = make_client(gated_runner)
    posted = client.post(
        "/api/v1/simulations",
        json=_payload(policies=["round_robin"], replications=2),
    ).json()
    assert entered.wait(3)
    status = client.get(f"/api/v1/simulations/{posted['run_id']}").json()
    assert status["status"] == "running"
    assert status["started_at"]
    assert status["finished_at"] is None
    assert status["progress"]["completed_policy_runs"] == 1
    assert status["progress"]["total_policy_runs"] == 2
    release.set()
    completed = _wait_for(client, posted["run_id"], "completed")
    assert completed["finished_at"]
    assert completed["progress"]["completed_replications"] == 2


def test_completed_run_returns_paired_results_and_aggregate_metrics(make_client):
    client, _ = make_client()
    started = client.post("/api/v1/simulations", json=_payload()).json()
    _wait_for(client, started["run_id"], "completed")
    response = client.get(f"/api/v1/simulations/{started['run_id']}/results")
    assert response.status_code == 200
    results = response.json()
    assert results["status"] == "completed"
    assert results["master_seed"] == 7
    assert len(results["replication_seeds"]) == 1
    assert len(results["results"]) == 3
    assert set(results["summary"]["by_policy"]) == {
        "round_robin",
        "least_connections",
        "weighted",
    }
    assert "mean_response_time_seconds" in results["metric_definitions"]


@pytest.mark.parametrize("suffix", ["", "/results"])
def test_unknown_run_ids_return_404(make_client, suffix):
    client, _ = make_client()
    response = client.get(f"/api/v1/simulations/missing{suffix}")
    assert response.status_code == 404


def test_delete_unknown_run_id_returns_404(make_client):
    client, _ = make_client()
    response = client.delete("/api/v1/simulations/missing")
    assert response.status_code == 404


def test_results_requested_before_completion_return_409(make_client):
    entered = Event()
    release = Event()

    def gated_runner(config, policies, replications, *, progress_callback, cancel_check):
        entered.set()
        release.wait(5)
        if cancel_check():
            raise SimulationCancelled
        return run_paired_comparison(config, policies, replications)

    client, _ = make_client(gated_runner)
    started = client.post("/api/v1/simulations", json=_payload()).json()
    assert entered.wait(3)
    response = client.get(f"/api/v1/simulations/{started['run_id']}/results")
    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "running"
    release.set()
    _wait_for(client, started["run_id"], "completed")


def test_queued_run_can_be_cancelled_without_starting(make_client):
    entered = Event()

    def blocking_runner(config, policies, replications, *, progress_callback, cancel_check):
        entered.set()
        while not cancel_check():
            sleep(0.005)
        raise SimulationCancelled

    client, _ = make_client(blocking_runner)
    first = client.post("/api/v1/simulations", json=_payload()).json()
    assert entered.wait(3)
    second = client.post("/api/v1/simulations", json=_payload()).json()
    assert second["status"] == "queued"
    cancelled = client.delete(f"/api/v1/simulations/{second['run_id']}")
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "cancelled"
    assert client.get(f"/api/v1/simulations/{second['run_id']}").json()["started_at"] is None
    client.delete(f"/api/v1/simulations/{first['run_id']}")
    _wait_for(client, first["run_id"], "cancelled")


def test_running_run_is_cooperatively_cancelled(make_client):
    entered = Event()

    def cancellable_runner(config, policies, replications, *, progress_callback, cancel_check):
        entered.set()
        while not cancel_check():
            sleep(0.005)
        raise SimulationCancelled

    client, _ = make_client(cancellable_runner)
    started = client.post("/api/v1/simulations", json=_payload()).json()
    assert entered.wait(3)
    response = client.delete(f"/api/v1/simulations/{started['run_id']}")
    assert response.status_code == 202
    assert response.json()["status"] == "cancelling"
    assert _wait_for(client, started["run_id"], "cancelled")["finished_at"]


def test_cancellation_after_completion_is_idempotent(make_client):
    client, _ = make_client()
    started = client.post("/api/v1/simulations", json=_payload()).json()
    _wait_for(client, started["run_id"], "completed")
    response = client.delete(f"/api/v1/simulations/{started['run_id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_worker_exception_is_reported_as_failed_run(make_client):
    def raising_runner(*args, **kwargs):
        raise RuntimeError("controlled worker failure")

    client, _ = make_client(raising_runner)
    started = client.post("/api/v1/simulations", json=_payload()).json()
    failed = _wait_for(client, started["run_id"], "failed")
    assert failed["finished_at"]
    assert failed["error"] == {
        "code": "RuntimeError",
        "message": "controlled worker failure",
    }
    results = client.get(f"/api/v1/simulations/{started['run_id']}/results")
    assert results.status_code == 409
    assert results.json()["detail"]["status"] == "failed"
    cancelled = client.delete(f"/api/v1/simulations/{started['run_id']}")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "failed"


def test_two_nonterminal_run_limit_returns_429(make_client):
    entered = Event()

    def blocking_runner(config, policies, replications, *, progress_callback, cancel_check):
        entered.set()
        while not cancel_check():
            sleep(0.005)
        raise SimulationCancelled

    client, _ = make_client(blocking_runner)
    first = client.post("/api/v1/simulations", json=_payload()).json()
    assert entered.wait(3)
    second = client.post("/api/v1/simulations", json=_payload()).json()
    assert second["status"] == "queued"
    rejected = client.post("/api/v1/simulations", json=_payload())
    assert rejected.status_code == 429
    client.delete(f"/api/v1/simulations/{first['run_id']}")
    client.delete(f"/api/v1/simulations/{second['run_id']}")
    _wait_for(client, first["run_id"], "cancelled")


def test_status_transitions_are_thread_safe_under_concurrent_requests(make_client):
    entered = Event()

    def blocking_runner(config, policies, replications, *, progress_callback, cancel_check):
        entered.set()
        while not cancel_check():
            sleep(0.005)
        raise SimulationCancelled

    client, _ = make_client(blocking_runner)
    started = client.post("/api/v1/simulations", json=_payload()).json()
    assert entered.wait(3)
    run_id = started["run_id"]

    def read_status():
        return client.get(f"/api/v1/simulations/{run_id}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        reads = [pool.submit(read_status) for _ in range(12)]
        delete = pool.submit(client.delete, f"/api/v1/simulations/{run_id}")
        responses = [future.result() for future in reads]
        delete_response = delete.result()
    assert all(response.status_code == 200 for response in responses)
    assert all(
        response.json()["status"] in {"running", "cancelling", "cancelled"}
        for response in responses
    )
    assert delete_response.status_code == 202
    assert _wait_for(client, run_id, "cancelled")["status"] == "cancelled"


def test_concurrent_post_requests_never_exceed_registry_limit(make_client):
    entered = Event()
    release = Event()

    def blocked_runner(config, policies, replications, *, progress_callback, cancel_check):
        entered.set()
        assert release.wait(5)
        if cancel_check():
            raise SimulationCancelled
        return SimpleNamespace(results=[object()], replications=replications)

    client, _ = make_client(blocked_runner)
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(
            pool.map(
                lambda _: client.post("/api/v1/simulations", json=_payload()),
                range(8),
            )
        )
    accepted = [response for response in responses if response.status_code == 202]
    rejected = [response for response in responses if response.status_code == 429]
    assert len(accepted) == 2
    assert len(rejected) == 6
    assert entered.wait(3)
    for response in accepted:
        client.delete(f"/api/v1/simulations/{response.json()['run_id']}")
    release.set()
    for response in accepted:
        _wait_for(client, response.json()["run_id"], "cancelled")


def test_queued_run_starts_after_preceding_run_completes(make_client):
    first_entered = Event()
    release_first = Event()
    second_entered = Event()
    invocation = 0

    def sequenced_runner(config, policies, replications, *, progress_callback, cancel_check):
        nonlocal invocation
        invocation += 1
        if invocation == 1:
            first_entered.set()
            assert release_first.wait(5)
        else:
            second_entered.set()
        return SimpleNamespace(results=[object()], replications=replications)

    client, _ = make_client(sequenced_runner)
    first = client.post("/api/v1/simulations", json=_payload()).json()
    assert first_entered.wait(3)
    second = client.post("/api/v1/simulations", json=_payload()).json()
    assert second["status"] == "queued"
    release_first.set()
    assert second_entered.wait(3)
    assert _wait_for(client, first["run_id"], "completed")["status"] == "completed"
    assert _wait_for(client, second["run_id"], "completed")["status"] == "completed"


def test_queued_run_starts_after_preceding_run_fails(make_client):
    first_entered = Event()
    fail_first = Event()
    second_entered = Event()
    invocation = 0

    def sequenced_runner(config, policies, replications, *, progress_callback, cancel_check):
        nonlocal invocation
        invocation += 1
        if invocation == 1:
            first_entered.set()
            assert fail_first.wait(5)
            raise RuntimeError("first run fails")
        second_entered.set()
        return SimpleNamespace(results=[object()], replications=replications)

    client, _ = make_client(sequenced_runner)
    first = client.post("/api/v1/simulations", json=_payload()).json()
    assert first_entered.wait(3)
    second = client.post("/api/v1/simulations", json=_payload()).json()
    assert second["status"] == "queued"
    fail_first.set()
    assert second_entered.wait(3)
    assert _wait_for(client, first["run_id"], "failed")["status"] == "failed"
    assert _wait_for(client, second["run_id"], "completed")["status"] == "completed"


def test_cancel_at_final_engine_event_boundary_returns_cancelled(make_client):
    final_boundary = Event()
    release_boundary = Event()

    def final_boundary_runner(config, policies, replications, *, progress_callback, cancel_check):
        checks = 0

        def synchronized_check():
            nonlocal checks
            checks += 1
            # The empty-trace run has five timestamp batches (0, 10, 20, 30, 32),
            # then one final check after the last event batch.
            if checks == 6:
                final_boundary.set()
                assert release_boundary.wait(5)
            return cancel_check()

        trace = SimulationTrace(
            scenario_id=config.scenario_id,
            seed=config.seed,
            arrivals=(),
            failures=tuple(config.failure_schedule),
            trace_id="final-boundary-trace",
        )
        run_simulation(config, policies[0], trace, cancel_check=synchronized_check)
        raise AssertionError("cancellation should stop the final event boundary")

    client, _ = make_client(final_boundary_runner)
    started = client.post(
        "/api/v1/simulations", json=_payload(policies=["round_robin"])
    ).json()
    assert final_boundary.wait(3)
    response = client.delete(f"/api/v1/simulations/{started['run_id']}")
    assert response.status_code == 202
    release_boundary.set()
    cancelled = _wait_for(client, started["run_id"], "cancelled")
    assert cancelled["progress"]["completed_policy_runs"] == 0


def test_cancellation_immediately_before_result_publication_discards_result(make_client):
    computed = Event()
    release_publication = Event()

    def computed_but_gated_runner(
        config, policies, replications, *, progress_callback, cancel_check
    ):
        result = run_paired_comparison(config, policies, replications)
        computed.set()
        assert release_publication.wait(5)
        return result

    client, _ = make_client(computed_but_gated_runner)
    started = client.post(
        "/api/v1/simulations", json=_payload(policies=["round_robin"])
    ).json()
    assert computed.wait(3)
    response = client.delete(f"/api/v1/simulations/{started['run_id']}")
    assert response.status_code == 202
    release_publication.set()
    assert _wait_for(client, started["run_id"], "cancelled")["status"] == "cancelled"
    assert client.get(f"/api/v1/simulations/{started['run_id']}/results").status_code == 409


@pytest.mark.parametrize("outcome", ["cancelled", "failed"])
def test_partial_progress_is_retained_after_cancel_or_failure(make_client, outcome):
    reported = Event()
    release = Event()

    def partial_runner(config, policies, replications, *, progress_callback, cancel_check):
        progress_callback(1, 2, 0, 2)
        reported.set()
        assert release.wait(5)
        if outcome == "cancelled" or cancel_check():
            raise SimulationCancelled
        raise RuntimeError("failure after one policy run")

    client, _ = make_client(partial_runner)
    started = client.post(
        "/api/v1/simulations",
        json=_payload(policies=["round_robin"], replications=2),
    ).json()
    assert reported.wait(3)
    if outcome == "cancelled":
        response = client.delete(f"/api/v1/simulations/{started['run_id']}")
        assert response.status_code == 202
    release.set()
    final = _wait_for(client, started["run_id"], outcome)
    assert final["progress"] == {
        "completed_replications": 0,
        "total_replications": 2,
        "completed_policy_runs": 1,
        "total_policy_runs": 2,
    }


def test_latest_50_terminal_runs_retained_without_evicting_active_run(make_client):
    entered_active = Event()
    invocation = 0

    def retention_runner(config, policies, replications, *, progress_callback, cancel_check):
        nonlocal invocation
        invocation += 1
        if invocation == 51:
            entered_active.set()
            while not cancel_check():
                sleep(0.005)
            raise SimulationCancelled
        return SimpleNamespace(results=[object()], replications=replications)

    client, _ = make_client(retention_runner)
    completed_ids = []
    for _ in range(50):
        run = client.post(
            "/api/v1/simulations", json=_payload(policies=["round_robin"])
        ).json()
        completed_ids.append(run["run_id"])
        _wait_for(client, run["run_id"], "completed")

    active = client.post(
        "/api/v1/simulations", json=_payload(policies=["round_robin"])
    ).json()
    assert entered_active.wait(3)
    queued = client.post(
        "/api/v1/simulations", json=_payload(policies=["round_robin"])
    ).json()
    client.delete(f"/api/v1/simulations/{queued['run_id']}")
    assert client.get(f"/api/v1/simulations/{completed_ids[0]}").status_code == 404
    assert client.get(f"/api/v1/simulations/{completed_ids[-1]}").status_code == 200
    assert client.get(f"/api/v1/simulations/{queued['run_id']}").status_code == 200
    assert client.get(f"/api/v1/simulations/{active['run_id']}").json()["status"] == "running"
    client.delete(f"/api/v1/simulations/{active['run_id']}")


def test_shutdown_cancels_queued_and_running_runs_and_restarts_same_app():
    entered = Event()
    invocation = 0

    def blocking_runner(config, policies, replications, *, progress_callback, cancel_check):
        nonlocal invocation
        invocation += 1
        if invocation == 1:
            entered.set()
            while not cancel_check():
                sleep(0.005)
            raise SimulationCancelled
        return SimpleNamespace(results=[object()], replications=replications)

    registry = SimulationRunRegistry(runner=blocking_runner)
    app = create_app(registry)
    with TestClient(app) as client:
        active = client.post(
            "/api/v1/simulations", json=_payload(policies=["round_robin"])
        ).json()
        assert entered.wait(3)
        queued = client.post(
            "/api/v1/simulations", json=_payload(policies=["round_robin"])
        ).json()
        assert queued["status"] == "queued"

    for run in (active, queued):
        final = registry.status(run["run_id"])
        assert final.status == "cancelled"
        assert final.finished_at is not None
    assert registry._runs[active["run_id"]].future.done()
    assert registry._runs[queued["run_id"]].future.cancelled()

    with TestClient(app) as restarted_client:
        assert restarted_client.get(f"/api/v1/simulations/{active['run_id']}").status_code == 404
        accepted = restarted_client.post(
            "/api/v1/simulations",
            json=_payload(policies=["round_robin"]),
        )
        assert accepted.status_code == 202
        assert _wait_for(restarted_client, accepted.json()["run_id"], "completed")["status"] == "completed"
