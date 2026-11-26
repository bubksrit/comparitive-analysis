"""Models for a unified, leakage-safe Part A experiment workflow."""

from typing import Any, Literal

from pydantic import Field, model_validator

from app.models.common import RunMetadata, StrictModel
from app.models.features import (
    AntColonyConfig,
    BinaryPSOConfig,
    ClassificationMetrics,
    GeneticAlgorithmConfig,
    RandomForestConfig,
)


class PartAExperimentConfig(StrictModel):
    """Frozen shared model/evaluation settings and repeated selector seeds."""

    seeds: list[int] = Field(default_factory=lambda: [42, 43, 44], min_length=1)
    random_forest: RandomForestConfig = Field(default_factory=RandomForestConfig)
    ga: GeneticAlgorithmConfig = Field(default_factory=GeneticAlgorithmConfig)
    binary_pso: BinaryPSOConfig = Field(default_factory=BinaryPSOConfig)
    aco: AntColonyConfig = Field(default_factory=AntColonyConfig)

    @model_validator(mode="after")
    def validate_common_selector_protocol(self) -> "PartAExperimentConfig":
        if any(seed < 0 for seed in self.seeds):
            raise ValueError("All experiment seeds must be non-negative")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("Experiment seeds must be unique")
        selectors = [self.ga, self.binary_pso, self.aco]
        fitness_weights = {
            (selector.fitness_performance_weight, selector.fitness_size_weight)
            for selector in selectors
        }
        feature_bounds = {(selector.min_features, selector.max_features) for selector in selectors}
        evaluation_budgets = {selector.max_model_evaluations for selector in selectors}
        if len(fitness_weights) != 1:
            raise ValueError("GA, BPSO, and ACO must use identical feature-fitness weights")
        if len(feature_bounds) != 1:
            raise ValueError("GA, BPSO, and ACO must use identical feature-count constraints")
        if len(evaluation_budgets) != 1:
            raise ValueError("GA, BPSO, and ACO must use the same unique-evaluation budget")
        return self


class PartAAlgorithmRun(StrictModel):
    algorithm: Literal["full_feature_baseline", "ga", "binary_pso", "aco"]
    seed: int | None = None
    selected_features: list[str]
    selected_feature_count: int = Field(ge=1)
    eligible_feature_count: int = Field(ge=1)
    reduction_percent: float = Field(ge=0, le=100)
    validation_macro_f1: float = Field(ge=0, le=1)
    validation_fitness: float = Field(ge=0, le=1)
    unique_model_evaluation_count: int = Field(ge=0)
    callback_request_count: int = Field(ge=0)
    selector_time_seconds: float = Field(ge=0)
    model_evaluation_time_seconds: float = Field(ge=0)
    total_optimizer_time_seconds: float = Field(ge=0)
    final_test_metrics: ClassificationMetrics
    final_test_fit_time_seconds: float = Field(ge=0)
    final_test_prediction_time_seconds: float = Field(ge=0)
    config: dict[str, Any]
    selector_artifact: str | None = None
    validation_artifact_id: str | None = None
    final_test_artifact_id: str


class MetricSummary(StrictModel):
    sample_count: int = Field(ge=1)
    mean: float
    standard_deviation: float | None = None
    confidence_level: float = 0.95
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None


class PartAExperimentResult(StrictModel):
    metadata: RunMetadata
    study_label: Literal["CIC-IDS2017 classification"] = "CIC-IDS2017 classification"
    dataset_name: str
    dataset_identity_verified: bool
    dataset_provenance: dict[str, Any]
    split_metadata: dict[str, Any]
    eligible_features: list[str]
    random_forest_config: RandomForestConfig
    selector_seeds: list[int]
    runs: list[PartAAlgorithmRun]
    aggregate_metrics: dict[str, dict[str, MetricSummary]]
    summary_json_path: str
    summary_csv_path: str
    software_versions: dict[str, str]
    execution_environment: dict[str, str]
