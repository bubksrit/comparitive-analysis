"""Common provenance fields shared by experiment configuration and results."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model that rejects unknown fields to catch configuration typos."""

    model_config = ConfigDict(extra="forbid")


class RunMetadata(StrictModel):
    experiment_id: str = Field(default_factory=lambda: str(uuid4()))
    seed: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    code_revision: str | None = None
    software_versions: dict[str, str] = Field(default_factory=dict)
    hardware_description: str | None = None
