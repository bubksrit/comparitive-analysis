"""Run a small synthetic software benchmark for ACO feature selection."""

import argparse
import tempfile
import time
from pathlib import Path

from app.features.benchmark_ga import make_fixture
from app.features.data import load_and_audit
from app.features.evaluator import RandomForestEvaluator
from app.features.selection.aco import run_ant_colony_optimization
from app.models.dataset import DatasetConfig
from app.models.features import AntColonyConfig, RandomForestConfig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--ant-count", type=int, default=6)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--max-model-evaluations", type=int, default=20)
    args = parser.parse_args()
    print("SOFTWARE TEST BENCHMARK ONLY - SYNTHETIC FIXTURE; NOT RESEARCH EVIDENCE")

    with tempfile.TemporaryDirectory(prefix="aco-software-benchmark-") as temporary_directory:
        workdir = Path(temporary_directory)
        csv_path = make_fixture(workdir / "synthetic_fixture.csv", args.seed)
        dataset = load_and_audit(
            DatasetConfig(
                dataset_name="Synthetic ACO benchmark fixture (not CIC-IDS2017)",
                data_path=csv_path,
                target_column="class_label",
                group_columns=["fixture_group"],
                excluded_columns={},
                random_seed=args.seed,
                output_dir=workdir / "outputs",
            )
        )
        config = AntColonyConfig(
            ant_count=args.ant_count,
            iterations=args.iterations,
            max_model_evaluations=args.max_model_evaluations,
            min_features=1,
            max_features=len(dataset.feature_columns),
            seed=args.seed,
        )
        evaluator = RandomForestEvaluator(
            RandomForestConfig(n_estimators=12, random_state=42, n_jobs=1)
        )
        started = time.perf_counter()
        result = run_ant_colony_optimization(dataset, config, evaluator=evaluator)
        benchmark_seconds = time.perf_counter() - started

    print(f"Fixture: {dataset.config.dataset_name}")
    print(f"Unique model evaluations: {result.evaluation_count}")
    print(f"Callback requests: {result.fitness_request_count}")
    print(f"Selected features: {result.selected_feature_names}")
    print(f"Best validation fitness (synthetic only): {result.best_fitness:.6f}")
    print(f"Software benchmark wall time: {benchmark_seconds:.4f} seconds")
    print("No CIC-IDS2017 data was read and no research result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
