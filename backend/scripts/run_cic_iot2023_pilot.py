"""Run a deliberately small CIC-IoT2023 Part A pipeline pilot."""

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
    parser.add_argument("--dataset-config", type=Path, default=Path("config/cic-iot2023.json"))
    parser.add_argument("--experiment-config", type=Path, default=Path("config/cic-iot2023-pilot.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("../outputs/cic-iot2023-pilot"))
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        parser.error(f"Refusing to overwrite existing pilot output: {output_dir}")

    dataset_config = DatasetConfig.model_validate_json(
        args.dataset_config.read_text(encoding="utf-8")
    )
    dataset_config.output_dir = output_dir
    experiment_config = PartAExperimentConfig.model_validate_json(
        args.experiment_config.read_text(encoding="utf-8")
    )
    dataset = load_and_audit(dataset_config)
    result = run_part_a_experiment(dataset, experiment_config, output_dir=output_dir / "part-a-experiments")
    print(json.dumps({
        "dataset": result.dataset_name,
        "rows": dataset.report["row_count"],
        "split": dataset.splits.split_details["row_counts"],
        "study_label": result.study_label,
        "dataset_identity_verified": result.dataset_identity_verified,
        "experiment_json": result.summary_json_path,
        "experiment_csv": result.summary_csv_path,
        "run_count": len(result.runs),
        "configs": experiment_config.model_dump(mode="json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
