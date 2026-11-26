"""Run the complete Part A workflow on a synthetic software-check fixture."""

import argparse
import tempfile
from pathlib import Path

from app.features.benchmark_ga import make_fixture
from app.features.data import load_and_audit
from app.features.experiment import default_synthetic_config, run_part_a_experiment
from app.models.dataset import DatasetConfig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    print("SYNTHETIC INTEGRATION BENCHMARK ONLY - NOT RESEARCH EVIDENCE")

    with tempfile.TemporaryDirectory(prefix="part-a-integration-benchmark-") as temporary:
        temporary_path = Path(temporary)
        csv_path = make_fixture(temporary_path / "synthetic_fixture.csv", args.seed)
        dataset = load_and_audit(
            DatasetConfig(
                dataset_name="Synthetic Part A integration fixture (not CIC-IDS2017)",
                data_path=csv_path,
                target_column="class_label",
                group_columns=["fixture_group"],
                excluded_columns={},
                random_seed=args.seed,
                output_dir=temporary_path / "outputs",
            )
        )
        config = default_synthetic_config([args.seed, args.seed + 1])
        result = run_part_a_experiment(dataset, config, output_dir=args.output_dir)

    print(f"Fixture: {result.dataset_name}")
    print(f"Finalized runs (baseline plus selectors): {len(result.runs)}")
    print(f"Selector seeds: {result.selector_seeds}")
    print(f"JSON summary: {result.summary_json_path}")
    print(f"CSV summary: {result.summary_csv_path}")
    print("No CIC-IDS2017 data was read and no research findings were produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
