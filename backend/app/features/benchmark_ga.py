"""Run a small synthetic software benchmark for the binary GA implementation."""

import argparse
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from app.features.data import load_and_audit
from app.features.evaluator import RandomForestEvaluator
from app.features.selection.genetic import run_genetic_algorithm
from app.models.dataset import DatasetConfig
from app.models.features import GeneticAlgorithmConfig, RandomForestConfig


def make_fixture(path: Path, seed: int) -> Path:
    """Generate test-only rows; this fixture is not CIC-IDS2017 or research evidence."""
    rng = np.random.default_rng(seed)
    rows = []
    for group in range(10):
        for row_number in range(12):
            label = "attack" if row_number % 2 else "benign"
            rows.append(
                {
                    "fixture_group": f"group-{group:02d}",
                    "signal": float(label == "attack") + rng.normal(0.0, 0.2),
                    "noise_a": rng.normal(),
                    "noise_b": rng.normal(),
                    "class_label": label,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--population-size", type=int, default=6)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--max-model-evaluations", type=int, default=20)
    args = parser.parse_args()
    print("SOFTWARE TEST BENCHMARK ONLY - SYNTHETIC FIXTURE; NOT RESEARCH EVIDENCE")

    with tempfile.TemporaryDirectory(prefix="ga-software-benchmark-") as temporary_directory:
        workdir = Path(temporary_directory)
        csv_path = make_fixture(workdir / "synthetic_fixture.csv", args.seed)
        dataset = load_and_audit(
            DatasetConfig(
                dataset_name="Synthetic GA benchmark fixture (not CIC-IDS2017)",
                data_path=csv_path,
                target_column="class_label",
                group_columns=["fixture_group"],
                excluded_columns={},
                random_seed=args.seed,
                output_dir=workdir / "outputs",
            )
        )
        config = GeneticAlgorithmConfig(
            population_size=args.population_size,
            generations=args.generations,
            max_model_evaluations=args.max_model_evaluations,
            min_features=1,
            max_features=len(dataset.feature_columns),
            seed=args.seed,
        )
        evaluator = RandomForestEvaluator(
            RandomForestConfig(n_estimators=12, random_state=42, n_jobs=1)
        )
        started = time.perf_counter()
        result = run_genetic_algorithm(dataset, config, evaluator=evaluator)
        benchmark_seconds = time.perf_counter() - started

    print(f"Fixture: {dataset.config.dataset_name}")
    print(f"Model evaluations: {result.evaluation_count}")
    print(f"Selected features: {result.selected_feature_names}")
    print(f"Best validation fitness (synthetic only): {result.best_fitness:.6f}")
    print(f"Software benchmark wall time: {benchmark_seconds:.4f} seconds")
    print("No CIC-IDS2017 data was read and no research result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
