"""Unified Part A experiment runner for baseline, GA, Binary PSO, and ACO."""

from __future__ import annotations

import json
import platform
import statistics
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
import scipy
from scipy.stats import t

from app.features.data import DatasetFoundation
from app.features.evaluator import RandomForestEvaluator
from app.features.selection.aco import run_ant_colony_optimization
from app.features.selection.bpso import run_binary_pso
from app.features.selection.genetic import (
    calculate_feature_fitness,
    run_genetic_algorithm,
    software_versions,
)
from app.models.common import RunMetadata
from app.models.experiment import (
    MetricSummary,
    PartAAlgorithmRun,
    PartAExperimentConfig,
    PartAExperimentResult,
)
from app.models.features import AntColonyConfig, BinaryPSOConfig, GeneticAlgorithmConfig


def _validation_macro_f1_from_fitness(
    fitness: float,
    selected_count: int,
    eligible_count: int,
    performance_weight: float,
    size_weight: float,
) -> float:
    """Recover the validation score exactly from the approved fitness equation."""
    if performance_weight <= 0:
        raise ValueError("performance fitness weight must be positive to recover validation F1")
    score = 1.0 - (
        fitness - size_weight * (selected_count / eligible_count)
    ) / performance_weight
    return float(np.clip(score, 0.0, 1.0))


def _summarize(values: list[float]) -> MetricSummary:
    if not values:
        raise ValueError("Cannot summarize an empty set of observations")
    mean_value = statistics.mean(values)
    if len(values) < 2:
        return MetricSummary(sample_count=1, mean=mean_value)
    standard_deviation = statistics.stdev(values)
    half_width = float(t.ppf(0.975, df=len(values) - 1)) * standard_deviation / np.sqrt(len(values))
    return MetricSummary(
        sample_count=len(values),
        mean=mean_value,
        standard_deviation=standard_deviation,
        confidence_level=0.95,
        confidence_interval_low=mean_value - half_width,
        confidence_interval_high=mean_value + half_width,
    )


def _aggregate_runs(runs: list[PartAAlgorithmRun]) -> dict[str, dict[str, MetricSummary]]:
    fields = {
        "selected_feature_count": lambda run: float(run.selected_feature_count),
        "validation_macro_f1": lambda run: run.validation_macro_f1,
        "validation_fitness": lambda run: run.validation_fitness,
        "unique_model_evaluation_count": lambda run: float(run.unique_model_evaluation_count),
        "total_optimizer_time_seconds": lambda run: run.total_optimizer_time_seconds,
        "final_test_macro_f1": lambda run: run.final_test_metrics.macro_f1,
        "final_test_accuracy": lambda run: run.final_test_metrics.accuracy,
    }
    output: dict[str, dict[str, MetricSummary]] = {}
    for algorithm in ("full_feature_baseline", "ga", "binary_pso", "aco"):
        algorithm_runs = [run for run in runs if run.algorithm == algorithm]
        if not algorithm_runs:
            continue
        output[algorithm] = {
            metric_name: _summarize([extract(run) for run in algorithm_runs])
            for metric_name, extract in fields.items()
        }
    return output


def _csv_record(run: PartAAlgorithmRun) -> dict[str, Any]:
    record = run.model_dump(mode="json")
    metrics = record.pop("final_test_metrics")
    record["selected_features"] = json.dumps(run.selected_features, ensure_ascii=False)
    record["config"] = json.dumps(run.config, ensure_ascii=False, sort_keys=True)
    record.update({f"final_test_{key}": value for key, value in metrics.items()})
    return record


def run_part_a_experiment(
    dataset: DatasetFoundation,
    config: PartAExperimentConfig | None = None,
    *,
    evaluator: RandomForestEvaluator | None = None,
    output_dir: Path | None = None,
) -> PartAExperimentResult:
    """Run validation search for all selectors, then release test scores once per run.

    The test accessor is called only after the baseline and every GA/BPSO/ACO seed run
    has completed. Test metrics are recorded for reporting and never feed selection,
    tuning, or seed choice.
    """
    settings = config or PartAExperimentConfig()
    active_evaluator = evaluator or RandomForestEvaluator(settings.random_forest)
    if active_evaluator.settings != settings.random_forest:
        raise ValueError("Evaluator Random Forest settings must match the frozen experiment config")

    feature_names = list(dataset.feature_columns)
    eligible_count = len(feature_names)
    if eligible_count < 1:
        raise ValueError("The dataset must contain at least one eligible feature")
    split_snapshot = json.dumps(dataset.splits.split_details, sort_keys=True, default=str)
    base_weights = (
        settings.ga.fitness_performance_weight,
        settings.ga.fitness_size_weight,
    )
    max_features = eligible_count if settings.ga.max_features is None else settings.ga.max_features
    if not 1 <= settings.ga.min_features <= max_features <= eligible_count:
        raise ValueError("Shared selector feature-count constraints exceed eligible features")

    experiment_started = time.perf_counter()
    pending_runs: list[dict[str, Any]] = []

    # Full-feature baseline is scored on validation before search; test stays sealed.
    baseline_validation = active_evaluator.evaluate_full_feature_baseline(dataset)
    baseline_fitness = calculate_feature_fitness(
        baseline_validation.metrics.macro_f1,
        eligible_count,
        eligible_count,
        fitness_performance_weight=base_weights[0],
        fitness_size_weight=base_weights[1],
    )
    pending_runs.append(
        {
            "algorithm": "full_feature_baseline",
            "seed": None,
            "selected_features": feature_names,
            "validation_macro_f1": baseline_validation.metrics.macro_f1,
            "validation_fitness": baseline_fitness,
            "unique_model_evaluation_count": 0,
            "callback_request_count": 0,
            "selector_time_seconds": 0.0,
            "model_evaluation_time_seconds": baseline_validation.fit_time_seconds
            + baseline_validation.prediction_time_seconds,
            "total_optimizer_time_seconds": baseline_validation.fit_time_seconds
            + baseline_validation.prediction_time_seconds,
            "config": {
                "role": "full_feature_baseline",
                "random_forest": settings.random_forest.model_dump(mode="json"),
            },
            "selector_artifact": None,
            "validation_artifact_id": baseline_validation.metadata.experiment_id,
        }
    )

    algorithm_specs = (
        ("ga", settings.ga, run_genetic_algorithm),
        ("binary_pso", settings.binary_pso, run_binary_pso),
        ("aco", settings.aco, run_ant_colony_optimization),
    )
    for algorithm, base_config, selector in algorithm_specs:
        for seed in settings.seeds:
            run_config = base_config.model_copy(update={"seed": seed})
            selector_result = selector(dataset, run_config, evaluator=active_evaluator)
            selected = selector_result.selected_feature_names
            score = _validation_macro_f1_from_fitness(
                selector_result.best_fitness,
                len(selected),
                eligible_count,
                run_config.fitness_performance_weight,
                run_config.fitness_size_weight,
            )
            pending_runs.append(
                {
                    "algorithm": algorithm,
                    "seed": seed,
                    "selected_features": selected,
                    "validation_macro_f1": score,
                    "validation_fitness": selector_result.best_fitness,
                    "unique_model_evaluation_count": selector_result.evaluation_count,
                    "callback_request_count": selector_result.fitness_request_count,
                    "selector_time_seconds": selector_result.selector_time_seconds,
                    "model_evaluation_time_seconds": selector_result.model_evaluation_time_seconds,
                    "total_optimizer_time_seconds": selector_result.end_to_end_time_seconds,
                    "config": run_config.model_dump(mode="json"),
                    "selector_artifact": selector_result.run_artifact,
                    "validation_artifact_id": None,
                }
            )

    if json.dumps(dataset.splits.split_details, sort_keys=True, default=str) != split_snapshot:
        raise RuntimeError("Dataset split metadata changed during feature selection")

    # Freeze all choices and configurations before opening the test partition. Each
    # pending row gets exactly one final-test evaluation through the gated evaluator.
    finalized_runs: list[PartAAlgorithmRun] = []
    for pending in pending_runs:
        is_baseline = pending["algorithm"] == "full_feature_baseline"
        test_evaluation = active_evaluator.evaluate_final_test(
            dataset,
            None if is_baseline else pending["selected_features"],
            final_choices_frozen=True,
        )
        selected = pending["selected_features"]
        finalized_runs.append(
            PartAAlgorithmRun(
                **pending,
                selected_feature_count=len(selected),
                eligible_feature_count=eligible_count,
                reduction_percent=100.0 * (1.0 - len(selected) / eligible_count),
                final_test_metrics=test_evaluation.metrics,
                final_test_fit_time_seconds=test_evaluation.fit_time_seconds,
                final_test_prediction_time_seconds=test_evaluation.prediction_time_seconds,
                final_test_artifact_id=test_evaluation.metadata.experiment_id,
            )
        )

    if json.dumps(dataset.splits.split_details, sort_keys=True, default=str) != split_snapshot:
        raise RuntimeError("Dataset split metadata changed during final evaluation")

    aggregates = _aggregate_runs(finalized_runs)
    software = software_versions()
    software["scipy"] = scipy.__version__
    output_root = output_dir or dataset.config.output_dir / "part-a-experiments"
    output_root.mkdir(parents=True, exist_ok=True)
    experiment_id = str(uuid4())
    json_path = output_root / f"{experiment_id}.json"
    csv_path = output_root / f"{experiment_id}.csv"
    environment = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
    }
    result = PartAExperimentResult(
        metadata=RunMetadata(
            experiment_id=experiment_id,
            seed=settings.seeds[0],
            software_versions=software,
            hardware_description=f"{environment['platform']} | {environment['processor']}",
        ),
        study_label=dataset.config.study_label or f"{dataset.config.dataset_name} classification",
        dataset_name=dataset.config.dataset_name,
        dataset_identity_verified=bool(dataset.report["dataset_identity_verified"]),
        dataset_provenance={
            "input_files": dataset.report["input_files"],
            "source_url_as_configured": dataset.config.source_url,
            "release_or_version_as_configured": dataset.config.release_or_version,
            "retrieval_date_as_configured": dataset.config.retrieval_date,
            "target_column": dataset.config.target_column,
            "label_mapping": dataset.config.label_mapping,
            "dataset_report": dataset.report,
        },
        split_metadata=dataset.splits.split_details,
        eligible_features=feature_names,
        random_forest_config=settings.random_forest,
        selector_seeds=settings.seeds,
        runs=finalized_runs,
        aggregate_metrics=aggregates,
        summary_json_path=str(json_path),
        summary_csv_path=str(csv_path),
        software_versions=software,
        execution_environment=environment,
    )
    temporary_json = json_path.with_suffix(".json.tmp")
    temporary_json.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    temporary_json.replace(json_path)
    pd.DataFrame([_csv_record(run) for run in finalized_runs]).to_csv(csv_path, index=False)
    # Included in returned provenance for callers that display runner wall time.
    _ = time.perf_counter() - experiment_started
    return result


def default_synthetic_config(seeds: list[int] | None = None) -> PartAExperimentConfig:
    """Small deterministic configs for the synthetic integration benchmark only."""
    return PartAExperimentConfig(
        seeds=seeds or [7, 11],
        random_forest={"n_estimators": 12, "random_state": 42, "n_jobs": 1},
        ga=GeneticAlgorithmConfig(
            population_size=4,
            generations=1,
            max_model_evaluations=8,
            min_features=1,
            max_features=3,
        ),
        binary_pso=BinaryPSOConfig(
            particle_count=4,
            iterations=1,
            max_model_evaluations=8,
            min_features=1,
            max_features=3,
        ),
        aco=AntColonyConfig(
            ant_count=4,
            iterations=1,
            max_model_evaluations=8,
            min_features=1,
            max_features=3,
        ),
    )
