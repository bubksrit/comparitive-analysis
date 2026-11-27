"""Study A configuration and result schemas (no feature-selection code)."""

from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator

from app.models.common import RunMetadata, StrictModel


class ExcludedColumn(StrictModel):
    name: str
    reason: str


class DatasetManifest(StrictModel):
    source_name: str = "CIC-IDS2017"
    source_url: str | None = None
    release_or_version: str | None = None
    retrieval_date: str | None = None
    input_files: list[str] = Field(default_factory=list)
    checksums_sha256: dict[str, str] = Field(default_factory=dict)
    target_column: str | None = None
    label_mapping: dict[str, str] = Field(default_factory=dict)
    eligible_feature_columns: list[str] = Field(default_factory=list)
    excluded_columns: list[ExcludedColumn] = Field(default_factory=list)
    audit_summary: dict[str, int | float | str] = Field(default_factory=dict)


class DatasetSplitConfig(StrictModel):
    strategy: Literal["group_aware", "stratified_random_fallback"]
    train_fraction: float = Field(default=0.6, gt=0, lt=1)
    validation_fraction: float = Field(default=0.2, gt=0, lt=1)
    test_fraction: float = Field(default=0.2, gt=0, lt=1)
    group_columns: list[str] = Field(default_factory=list)
    seed: int = Field(ge=0)

    @model_validator(mode="after")
    def fractions_sum_to_one(self) -> "DatasetSplitConfig":
        if abs(self.train_fraction + self.validation_fraction + self.test_fraction - 1.0) > 1e-9:
            raise ValueError("Train, validation, and test fractions must sum to 1.0")
        if self.strategy == "group_aware" and not self.group_columns:
            raise ValueError("group_aware split requires verified group columns")
        return self


class RandomForestConfig(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    n_estimators: int = Field(default=200, ge=1)
    criterion: Literal["gini", "entropy", "log_loss"] = "gini"
    max_depth: int | None = Field(default=None, ge=1)
    min_samples_split: int = Field(default=2, ge=2)
    min_samples_leaf: int = Field(default=1, ge=1)
    min_weight_fraction_leaf: float = Field(default=0.0, ge=0, lt=0.5)
    max_features: Literal["sqrt", "log2"] = "sqrt"
    max_leaf_nodes: int | None = Field(default=None, ge=2)
    min_impurity_decrease: float = Field(default=0.0, ge=0)
    bootstrap: bool = True
    class_weight: Literal["balanced", "balanced_subsample"] | None = "balanced_subsample"
    oob_score: bool = False
    random_state: int = Field(default=42, ge=0)
    n_jobs: int = Field(default=1)
    verbose: int = Field(default=0, ge=0)
    warm_start: bool = False
    ccp_alpha: float = Field(default=0.0, ge=0)
    max_samples: float | None = Field(default=None, gt=0, le=1)


class FeatureSelectionConfig(StrictModel):
    algorithm: Literal["ga", "binary_pso", "aco"]
    seed: int = Field(ge=0)
    population_size: int = Field(ge=2)
    max_model_evaluations: int = Field(ge=1)
    max_iterations: int = Field(ge=1)
    min_features: int = Field(default=1, ge=1)
    max_features: int | None = Field(default=None, ge=1)
    fitness_performance_weight: float = Field(default=0.8, ge=0, le=1)
    fitness_size_weight: float = Field(default=0.2, ge=0, le=1)
    repeats: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "FeatureSelectionConfig":
        if abs(self.fitness_performance_weight + self.fitness_size_weight - 1.0) > 1e-9:
            raise ValueError("Feature fitness weights must sum to 1.0")
        if self.max_features is not None and self.min_features > self.max_features:
            raise ValueError("min_features cannot exceed max_features")
        return self


class GeneticAlgorithmConfig(StrictModel):
    """Configurable binary-mask GA. Evaluation budget counts unique RF fitness fits."""

    population_size: int = Field(default=20, ge=2)
    generations: int = Field(default=20, ge=0)
    selection_method: Literal["tournament", "roulette"] = "tournament"
    tournament_size: int = Field(default=3, ge=2)
    crossover_probability: float = Field(default=0.8, ge=0, le=1)
    mutation_probability: float = Field(default=0.02, ge=0, le=1)
    elitism_count: int = Field(default=1, ge=0)
    min_features: int = Field(default=1, ge=1)
    max_features: int | None = Field(default=None, ge=1)
    max_model_evaluations: int = Field(default=200, ge=2)
    fitness_performance_weight: float = Field(default=0.8, ge=0, le=1)
    fitness_size_weight: float = Field(default=0.2, ge=0, le=1)
    seed: int = Field(default=42, ge=0)

    @model_validator(mode="after")
    def validate_ga_parameters(self) -> "GeneticAlgorithmConfig":
        if self.max_model_evaluations < self.population_size:
            raise ValueError("max_model_evaluations must be at least population_size")
        if self.elitism_count >= self.population_size:
            raise ValueError("elitism_count must be less than population_size")
        if abs(self.fitness_performance_weight + self.fitness_size_weight - 1.0) > 1e-9:
            raise ValueError("Feature fitness weights must sum to 1.0")
        if self.max_features is not None and self.min_features > self.max_features:
            raise ValueError("min_features cannot exceed max_features")
        if self.selection_method == "tournament" and self.tournament_size > self.population_size:
            raise ValueError("tournament_size cannot exceed population_size")
        return self


class GeneticAlgorithmResult(StrictModel):
    algorithm: Literal["ga"] = "ga"
    selected_mask: list[int]
    selected_feature_names: list[str]
    best_fitness: float = Field(ge=0, le=1)
    best_fitness_trace: list[float]
    evaluation_count: int = Field(ge=0)
    fitness_request_count: int = Field(ge=0)
    selector_time_seconds: float = Field(ge=0)
    model_evaluation_time_seconds: float = Field(ge=0)
    end_to_end_time_seconds: float = Field(ge=0)
    seed: int = Field(ge=0)
    config: GeneticAlgorithmConfig
    stop_reason: Literal["generations_complete", "evaluation_budget"]
    fitness_formula: str = (
        "0.8 * (1 - validation_macro_f1) + 0.2 * (selected_feature_count / eligible_feature_count)"
    )
    dataset_name: str
    dataset_provenance: dict[str, Any]
    split_metadata: dict[str, Any]
    software_versions: dict[str, str]
    run_artifact: str


class BinaryPSOConfig(StrictModel):
    """Configurable binary PSO; model-evaluation budget counts unique masks."""

    particle_count: int = Field(default=20, ge=2)
    iterations: int = Field(default=20, ge=0)
    inertia_start: float = Field(default=0.9, ge=0, le=1)
    inertia_end: float = Field(default=0.4, ge=0, le=1)
    cognitive_coefficient: float = Field(default=2.0, gt=0)
    social_coefficient: float = Field(default=2.0, gt=0)
    velocity_min: float = -4.0
    velocity_max: float = 4.0
    transfer_function: Literal["sigmoid"] = "sigmoid"
    min_features: int = Field(default=1, ge=1)
    max_features: int | None = Field(default=None, ge=1)
    max_model_evaluations: int = Field(default=200, ge=2)
    fitness_performance_weight: float = Field(default=0.8, ge=0, le=1)
    fitness_size_weight: float = Field(default=0.2, ge=0, le=1)
    seed: int = Field(default=42, ge=0)

    @model_validator(mode="after")
    def validate_bpso_parameters(self) -> "BinaryPSOConfig":
        if self.max_model_evaluations < self.particle_count:
            raise ValueError("max_model_evaluations must be at least particle_count")
        if self.velocity_min >= self.velocity_max:
            raise ValueError("velocity_min must be less than velocity_max")
        if abs(self.fitness_performance_weight + self.fitness_size_weight - 1.0) > 1e-9:
            raise ValueError("Feature fitness weights must sum to 1.0")
        if self.max_features is not None and self.min_features > self.max_features:
            raise ValueError("min_features cannot exceed max_features")
        return self


class BinaryPSOResult(StrictModel):
    algorithm: Literal["binary_pso"] = "binary_pso"
    selected_mask: list[int]
    selected_feature_names: list[str]
    best_fitness: float = Field(ge=0, le=1)
    global_best_fitness_trace: list[float]
    evaluation_count: int = Field(ge=0)
    fitness_request_count: int = Field(ge=0)
    iterations_completed: int = Field(ge=0)
    selector_time_seconds: float = Field(ge=0)
    model_evaluation_time_seconds: float = Field(ge=0)
    end_to_end_time_seconds: float = Field(ge=0)
    seed: int = Field(ge=0)
    config: BinaryPSOConfig
    stop_reason: Literal["iterations_complete", "evaluation_budget"]
    fitness_formula: str = (
        "0.8 * (1 - validation_macro_f1) + 0.2 * (selected_feature_count / eligible_feature_count)"
    )
    dataset_name: str
    dataset_provenance: dict[str, Any]
    split_metadata: dict[str, Any]
    software_versions: dict[str, str]
    run_artifact: str


class AntColonyConfig(StrictModel):
    """ACO subset-search settings; budget counts unique RF evaluations."""

    ant_count: int = Field(default=20, ge=2)
    iterations: int = Field(default=20, ge=1)
    pheromone_alpha: float = Field(default=1.0, ge=0)
    heuristic_beta: float = Field(default=0.0, ge=0)
    initial_pheromone: float = Field(default=1.0, gt=0)
    evaporation_rate: float = Field(default=0.2, ge=0, lt=1)
    deposit_scale: float = Field(default=1.0, gt=0)
    pheromone_min: float = Field(default=0.01, gt=0)
    pheromone_max: float = Field(default=10.0, gt=0)
    min_features: int = Field(default=1, ge=1)
    max_features: int | None = Field(default=None, ge=1)
    max_model_evaluations: int = Field(default=200, ge=2)
    fitness_performance_weight: float = Field(default=0.8, ge=0, le=1)
    fitness_size_weight: float = Field(default=0.2, ge=0, le=1)
    seed: int = Field(default=42, ge=0)

    @model_validator(mode="after")
    def validate_aco_parameters(self) -> "AntColonyConfig":
        if self.max_model_evaluations < self.ant_count:
            raise ValueError("max_model_evaluations must be at least ant_count")
        if self.pheromone_min >= self.pheromone_max:
            raise ValueError("pheromone_min must be less than pheromone_max")
        if not self.pheromone_min <= self.initial_pheromone <= self.pheromone_max:
            raise ValueError("initial_pheromone must be within pheromone bounds")
        if abs(self.fitness_performance_weight + self.fitness_size_weight - 1.0) > 1e-9:
            raise ValueError("Feature fitness weights must sum to 1.0")
        if self.max_features is not None and self.min_features > self.max_features:
            raise ValueError("min_features cannot exceed max_features")
        return self


class AntColonyResult(StrictModel):
    algorithm: Literal["aco"] = "aco"
    selected_mask: list[int]
    selected_feature_names: list[str]
    best_fitness: float = Field(ge=0, le=1)
    best_fitness_trace: list[float]
    evaluation_count: int = Field(ge=0)
    fitness_request_count: int = Field(ge=0)
    iterations_completed: int = Field(ge=0)
    selector_time_seconds: float = Field(ge=0)
    model_evaluation_time_seconds: float = Field(ge=0)
    end_to_end_time_seconds: float = Field(ge=0)
    seed: int = Field(ge=0)
    config: AntColonyConfig
    stop_reason: Literal["iterations_complete", "evaluation_budget"]
    fitness_formula: str = (
        "0.8 * (1 - validation_macro_f1) + 0.2 * (selected_feature_count / eligible_feature_count)"
    )
    dataset_name: str
    dataset_provenance: dict[str, Any]
    split_metadata: dict[str, Any]
    software_versions: dict[str, str]
    run_artifact: str


class ClassificationMetrics(StrictModel):
    accuracy: float = Field(ge=0, le=1)
    macro_precision: float = Field(ge=0, le=1)
    macro_recall: float = Field(ge=0, le=1)
    macro_f1: float = Field(ge=0, le=1)
    weighted_precision: float = Field(ge=0, le=1)
    weighted_recall: float = Field(ge=0, le=1)
    weighted_f1: float = Field(ge=0, le=1)
    confusion_matrix: list[list[int]]
    label_order: list[str]
    class_support: dict[str, int]
    sample_count: int = Field(ge=0)


class FeatureSelectionResult(StrictModel):
    metadata: RunMetadata
    study_label: str = "CIC-IDS2017 classification"
    algorithm: Literal["full_feature_baseline", "ga", "binary_pso", "aco"]
    selected_features: list[str]
    eligible_feature_count: int = Field(ge=1)
    selected_feature_count: int = Field(ge=1)
    reduction_percent: float = Field(ge=0, le=100)
    validation_fitness: float | None = None
    held_out_metrics: ClassificationMetrics | None = None
    optimizer_seconds: float = Field(default=0, ge=0)
    rf_fit_evaluation_seconds: float = Field(default=0, ge=0)
    preprocessing_seconds: float = Field(default=0, ge=0)
    end_to_end_seconds: float = Field(default=0, ge=0)
    model_evaluation_count: int = Field(default=0, ge=0)
    split_description: str


class FeatureSubsetEvaluationResult(StrictModel):
    metadata: RunMetadata
    evaluation_partition: Literal["validation", "test"]
    evaluation_role: Literal["full_feature_baseline", "feature_subset"]
    dataset_name: str
    study_label: str = "CIC-IDS2017 classification"
    dataset_identity_verified: bool = False
    target_column: str
    label_mapping: dict[str, str]
    selected_features: list[str]
    selected_feature_count: int = Field(ge=1)
    random_forest_config: RandomForestConfig
    training_class_counts: dict[str, int]
    metrics: ClassificationMetrics
    primary_metric_name: Literal["macro_f1"] = "macro_f1"
    primary_score: float = Field(ge=0, le=1)
    fit_time_seconds: float = Field(ge=0)
    prediction_time_seconds: float = Field(ge=0)
    split_metadata: dict[str, Any]
    dataset_provenance: dict[str, Any]
    software_versions: dict[str, str]
