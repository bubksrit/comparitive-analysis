"""Compare full-feature RF tree counts on validation only; never opens test data."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.features.data import load_and_audit
from app.features.evaluator import RandomForestEvaluator
from app.models.dataset import DatasetConfig
from app.models.features import RandomForestConfig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-config", type=Path, default=Path("config/cic-iot2023.json"))
    parser.add_argument("--tree-counts", type=int, nargs="+", default=[10, 50, 100, 200])
    parser.add_argument("--max-samples", type=float, nargs="+", default=[1.0])
    parser.add_argument(
        "--output", type=Path,
        default=Path("../outputs/cic-iot2023-pilot/rf_tree_budget_validation.json"),
    )
    args = parser.parse_args()
    output_path = args.output.resolve()
    if output_path.exists():
        parser.error(f"Refusing to overwrite existing tree-budget report: {output_path}")
    if any(count < 1 for count in args.tree_counts) or len(set(args.tree_counts)) != len(args.tree_counts):
        parser.error("tree counts must be positive and unique")
    if any(not 0 < fraction <= 1 for fraction in args.max_samples):
        parser.error("max-samples values must be in (0, 1]")

    dataset_config = DatasetConfig.model_validate_json(
        args.dataset_config.read_text(encoding="utf-8")
    )
    dataset = load_and_audit(dataset_config)
    rows = []
    for count in args.tree_counts:
        for sample_fraction in args.max_samples:
            settings = RandomForestConfig(
                n_estimators=count,
                random_state=42,
                n_jobs=1,
                class_weight="balanced_subsample",
                max_samples=sample_fraction,
            )
            result = RandomForestEvaluator(settings).evaluate_validation(
                dataset, dataset.feature_columns, persist_run=False
            )
            rows.append({
                "n_estimators": count,
                "max_samples": sample_fraction,
                "validation_macro_f1": result.metrics.macro_f1,
                "validation_accuracy": result.metrics.accuracy,
                "fit_seconds": result.fit_time_seconds,
                "prediction_seconds": result.prediction_time_seconds,
            })
    report = {
        "study_label": dataset.config.study_label,
        "dataset_name": dataset.config.dataset_name,
        "sample_sha256": dataset.report["input_files"][0]["sha256"],
        "split_index_hashes": dataset.splits.split_details["partition_row_index_sha256"],
        "evaluation_partition": "validation",
        "test_partition_accessed": False,
        "fixed_settings": {
            "criterion": "gini",
            "max_features": "sqrt",
            "bootstrap": True,
            "class_weight": "balanced_subsample",
            "random_state": 42,
            "n_jobs": 1,
            "eligible_features": dataset.feature_columns,
        },
        "results": rows,
        "created_utc": datetime.now(UTC).isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "results": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
