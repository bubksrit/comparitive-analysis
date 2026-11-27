"""Repeat only the frozen full-feature RF baseline for the selector seed labels.

The Random Forest configuration stays exactly as recorded in the original
experiment (including its fixed random_state). The three values 42/43/44 are
comparison-replicate labels matching the GA/BPSO/ACO optimizer seeds; they do
not change estimator randomness. This makes the baseline deterministic and its
zero observed standard deviation must not be interpreted as an inferential CI.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from scipy.stats import t

from app.features.data import load_and_audit
from app.features.evaluator import RandomForestEvaluator
from app.features.experiment import _aggregate_runs, _csv_record
from app.features.selection.genetic import calculate_feature_fitness
from app.models.common import RunMetadata
from app.models.dataset import DatasetConfig
from app.models.experiment import (
    PartAAlgorithmRun,
    PartAExperimentConfig,
    PartAExperimentResult,
)
from app.models.features import RandomForestConfig


def _build_baseline_run(seed: int, dataset, evaluator: RandomForestEvaluator) -> PartAAlgorithmRun:
    validation = evaluator.evaluate_full_feature_baseline(dataset)
    test = evaluator.evaluate_final_test(
        dataset, selected_features=None, final_choices_frozen=True
    )
    features = list(dataset.feature_columns)
    settings = evaluator.settings
    fitness = calculate_feature_fitness(
        validation.metrics.macro_f1,
        len(features),
        len(features),
        fitness_performance_weight=0.8,
        fitness_size_weight=0.2,
    )
    evaluation_seconds = validation.fit_time_seconds + validation.prediction_time_seconds
    return PartAAlgorithmRun(
        algorithm="full_feature_baseline",
        seed=seed,
        selected_features=features,
        selected_feature_count=len(features),
        eligible_feature_count=len(features),
        reduction_percent=0.0,
        validation_macro_f1=validation.metrics.macro_f1,
        validation_fitness=fitness,
        unique_model_evaluation_count=0,
        callback_request_count=0,
        selector_time_seconds=0.0,
        model_evaluation_time_seconds=evaluation_seconds,
        total_optimizer_time_seconds=evaluation_seconds,
        final_test_metrics=test.metrics,
        final_test_fit_time_seconds=test.fit_time_seconds,
        final_test_prediction_time_seconds=test.prediction_time_seconds,
        config={
            "role": "full_feature_baseline",
            "random_forest": settings.model_dump(mode="json"),
            "comparison_seed": seed,
            "comparison_seed_role": "replicate label only; estimator random_state remains fixed",
        },
        selector_artifact=None,
        validation_artifact_id=validation.metadata.experiment_id,
        final_test_artifact_id=test.metadata.experiment_id,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-config", type=Path, default=Path("config/cic-iot2023-final.json")
    )
    parser.add_argument(
        "--experiment-config",
        type=Path,
        default=Path("config/cic-iot2023-final-experiment.json"),
    )
    parser.add_argument(
        "--source-result",
        type=Path,
        default=Path(
            "../outputs/cic-iot2023-final/part-a-experiments/"
            "e19b2696-bfb4-4ed1-85eb-bd990556173e.json"
        ),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("../outputs/cic-iot2023-baseline-repeats")
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        parser.error(f"Refusing to overwrite existing baseline-repeat output: {output_dir}")

    source = PartAExperimentResult.model_validate_json(
        args.source_result.read_text(encoding="utf-8")
    )
    config = PartAExperimentConfig.model_validate_json(
        args.experiment_config.read_text(encoding="utf-8")
    )
    if source.selector_seeds != config.seeds:
        parser.error("Experiment seeds differ from the saved selector seeds")
    source_rf = source.random_forest_config
    if source_rf != config.random_forest:
        parser.error("Experiment RF settings differ from the saved source result")

    dataset_config = DatasetConfig.model_validate_json(
        args.dataset_config.read_text(encoding="utf-8")
    )
    dataset_config.output_dir = output_dir
    dataset = load_and_audit(dataset_config)
    if dataset.feature_columns != source.eligible_features:
        parser.error("Reloaded eligible feature order differs from the saved source result")
    saved_hash = source.dataset_provenance["input_files"][0]["sha256"]
    if dataset.report["input_files"][0]["sha256"] != saved_hash:
        parser.error("Reloaded sample checksum differs from the saved source result")
    if dataset.splits.split_details != source.split_metadata:
        parser.error("Reloaded split metadata differs from the saved source result")

    evaluator = RandomForestEvaluator(RandomForestConfig.model_validate(source_rf.model_dump()))
    baselines = [
        _build_baseline_run(seed, dataset, evaluator) for seed in config.seeds
    ]
    baseline_metrics = [
        (run.validation_macro_f1, run.final_test_metrics.model_dump(mode="json"))
        for run in baselines
    ]
    if any(metrics != baseline_metrics[0] for metrics in baseline_metrics[1:]):
        raise RuntimeError(
            "Fixed-settings baseline repetitions were not deterministic; inspect estimator/runtime"
        )

    original_runs = [run for run in source.runs if run.algorithm != "full_feature_baseline"]
    all_runs = baselines + original_runs
    aggregates = _aggregate_runs(all_runs)
    # Identical fixed-RNG repeats are useful for seed-aligned presentation, but
    # are not independent observations and therefore receive no confidence interval.
    for summary in aggregates["full_feature_baseline"].values():
        summary.confidence_interval_low = None
        summary.confidence_interval_high = None

    experiment_id = str(uuid4())
    summary_dir = output_dir / "part-a-experiments"
    summary_dir.mkdir(parents=True, exist_ok=False)
    json_path = summary_dir / f"{experiment_id}.json"
    csv_path = summary_dir / f"{experiment_id}.csv"
    comparison = source.model_copy(
        update={
            "metadata": RunMetadata(
                experiment_id=experiment_id,
                seed=config.seeds[0],
                software_versions=source.software_versions,
                hardware_description=source.metadata.hardware_description,
            ),
            "runs": all_runs,
            "aggregate_metrics": aggregates,
            "summary_json_path": str(json_path),
            "summary_csv_path": str(csv_path),
        }
    )
    temporary = json_path.with_suffix(".json.tmp")
    temporary.write_text(comparison.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(json_path)
    pd.DataFrame([_csv_record(run) for run in all_runs]).to_csv(csv_path, index=False)

    run_manifest = {
        "source_experiment_json": str(args.source_result.resolve()),
        "comparison_result_json": str(json_path),
        "sample_sha256": saved_hash,
        "split_metadata": dataset.splits.split_details,
        "replicate_labels": config.seeds,
        "random_forest_config_unchanged": source_rf.model_dump(mode="json"),
        "estimator_random_state_policy": (
            "Fixed random_state=42 for all three repetitions, matching the original selector runs. "
            "The 42/43/44 values label comparison repetitions only."
        ),
        "baseline_metrics_identical_across_repetitions": True,
        "baseline_confidence_interval": (
            "Not estimated: repeated metric values are deterministic duplicates, not independent runs."
        ),
        "paired_differences_vs_baseline": {},
        "baseline_runs": [run.model_dump(mode="json") for run in baselines],
    }
    baseline_by_seed = {
        run.seed: run.final_test_metrics for run in baselines
    }
    for algorithm in ("ga", "binary_pso", "aco"):
        algorithm_runs = [run for run in original_runs if run.algorithm == algorithm]
        deltas_by_metric: dict[str, Any] = {}
        for metric in ("macro_f1", "accuracy"):
            deltas = [
                float(getattr(run.final_test_metrics, metric))
                - float(getattr(baseline_by_seed[run.seed], metric))
                for run in algorithm_runs
            ]
            mean = statistics.mean(deltas)
            standard_deviation = statistics.stdev(deltas)
            half_width = float(t.ppf(0.975, df=len(deltas) - 1)) * standard_deviation / (
                len(deltas) ** 0.5
            )
            deltas_by_metric[metric] = {
                "seed_level_differences": deltas,
                "sample_count": len(deltas),
                "mean_difference": mean,
                "standard_deviation": standard_deviation,
                "confidence_level": 0.95,
                "confidence_interval_low": mean - half_width,
                "confidence_interval_high": mean + half_width,
            }
        run_manifest["paired_differences_vs_baseline"][algorithm] = deltas_by_metric
    (output_dir / "baseline_repeats_manifest.json").write_text(
        json.dumps(run_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({
        "comparison_json": str(json_path),
        "comparison_csv": str(csv_path),
        "output_dir": str(output_dir),
        "baseline_replications": len(baselines),
        "baseline_validation_macro_f1": baselines[0].validation_macro_f1,
        "baseline_test_macro_f1": baselines[0].final_test_metrics.macro_f1,
        "baseline_test_accuracy": baselines[0].final_test_metrics.accuracy,
        "all_three_metrics_identical": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
