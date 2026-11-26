"""FastAPI application entry point for the research skeleton."""

from fastapi import FastAPI

app = FastAPI(
    title="Intelligent Network Load Balancing Research API",
    version="0.1.0",
    description="Local research API skeleton. No experiment algorithms are implemented yet.",
)


@app.get("/api/v1/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Return process health without implying that experiments have run."""
    return {"status": "ok", "service": "research-api"}
