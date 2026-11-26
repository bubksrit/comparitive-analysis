"""HTTP endpoints for the process-local simulation run lifecycle."""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.models.simulation_runs import (
    SimulationRunRequest,
    SimulationRunResultsResponse,
    SimulationRunStatusResponse,
)
from app.simulation.runs import (
    RegistryUnavailableError,
    RunLimitReachedError,
    RunNotCompletedError,
    RunNotFoundError,
    SimulationRunRegistry,
)

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])


def _registry(request: Request) -> SimulationRunRegistry:
    return request.app.state.simulation_run_registry


@router.post(
    "",
    response_model=SimulationRunStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_simulation(
    body: SimulationRunRequest,
    request: Request,
) -> SimulationRunStatusResponse:
    """Validate a run request and enqueue its paired simulation."""
    try:
        return _registry(request).submit(body)
    except RunLimitReachedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RegistryUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{run_id}", response_model=SimulationRunStatusResponse)
def get_simulation_status(run_id: str, request: Request) -> SimulationRunStatusResponse:
    """Return a thread-safe run status and replication/policy progress snapshot."""
    try:
        return _registry(request).status(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="simulation run not found") from exc


@router.get("/{run_id}/results", response_model=SimulationRunResultsResponse)
def get_simulation_results(
    run_id: str,
    request: Request,
) -> SimulationRunResultsResponse:
    """Return paired policy results only after the full run has completed."""
    try:
        return _registry(request).results(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="simulation run not found") from exc
    except RunNotCompletedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"status": exc.status, "message": str(exc)},
        ) from exc


@router.delete(
    "/{run_id}",
    response_model=SimulationRunStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def cancel_simulation(
    run_id: str, request: Request
) -> SimulationRunStatusResponse | JSONResponse:
    """Request cancellation; an active run stops at the next event boundary."""
    try:
        registry = _registry(request)
        response, was_terminal = registry.cancel(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="simulation run not found") from exc
    if was_terminal:
        # DELETE is idempotent for terminal runs and reports the terminal state.
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response.model_dump(mode="json"),
        )
    return response
