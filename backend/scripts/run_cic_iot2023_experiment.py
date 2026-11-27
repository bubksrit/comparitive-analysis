"""Run the frozen, repeated CIC-IoT2023 Workstream A experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.features.data import load_and_audit
from app.features.experiment import run_part_a_experiment
from app.models.dataset import DatasetConfig
from app.models.experiment import PartAExperimentConfig


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
        "--output-dir", type=Path, default=Path("../outputs/cic-iot2023-final")
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        parser.error(f"Refusing to overwrite existing final-run output: {output_dir}")

    dataset_config = DatasetConfig.model_validate_json(
        args.dataset_config.read_text(encoding="utf-8")
    )
    dataset_config.output_dir = output_dir
    experiment_config = PartAExperimentConfig.model_validate_json(
        args.experiment_config.read_text(encoding="utf-8")
    )
    dataset = load_and_audit(dataset_config)
    result = run_part_a_experiment(
        dataset,
        experiment_config,
        output_dir=output_dir / "part-a-experiments",
    )
    print(json.dumps({
        "dataset": result.dataset_name,
        "study_label": result.study_label,
        "dataset_identity_verified": result.dataset_identity_verified,
        "rows": dataset.report["row_count"],
        "split": dataset.splits.split_details["row_counts"],
        "group_overlap": dataset.splits.split_details.get("group_overlap"),
        "class_counts_per_partition": {
            name: len(counts)
            for name, counts in dataset.splits.split_details["class_counts"].items()
        },
        "experiment_json": result.summary_json_path,
        "experiment_csv": result.summary_csv_path,
        "run_count": len(result.runs),
        "selector_seeds": result.selector_seeds,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
