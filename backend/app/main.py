"""FastAPI application entry point for the research API."""

import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.simulations import router as simulation_router
from app.simulation.runs import SimulationRunRegistry


def _safe_validation_value(value: Any) -> Any:
    """Keep rejected NaN/Infinity inputs representable in JSON error responses."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _safe_validation_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_validation_value(item) for item in value]
    return value


def create_app(
    simulation_run_registry: SimulationRunRegistry | None = None,
) -> FastAPI:
    """Build an app with an isolated, process-local simulation registry."""
    registry = simulation_run_registry or SimulationRunRegistry()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        registry.start()
        application.state.simulation_run_registry = registry
        try:
            yield
        finally:
            registry.shutdown()

    application = FastAPI(
        title="Intelligent Network Load Balancing Research API",
        version="0.1.0",
        description=(
            "Local research API for Study A classification utilities and Study B "
            "simulated load-balancing experiments."
        ),
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(_safe_validation_value(exc.errors()))},
        )

    application.state.simulation_run_registry = registry
    application.include_router(simulation_router)

    @application.get("/api/v1/health", tags=["health"])
    def health_check() -> dict[str, str]:
        """Return process health without implying that experiments have run."""
        return {"status": "ok", "service": "research-api"}

    return application


app = create_app()
