"""Unified-runner integration tests on synthetic-only data, not CIC-IDS2017 results."""

import json
from pathlib import Path

import pandas as pd
import pytest

import app.features.experiment as experiment_module
from app.features.benchmark_ga import make_fixture
from app.features.data import load_and_audit
from app.features.experiment import default_synthetic_config, run_part_a_experiment
from app.models.dataset import DatasetConfig


def _synthetic_dataset(tmp_path):
    csv_path = make_fixture(tmp_path / "synthetic_runner_fixture.csv", seed=123)
    return load_and_audit(
        DatasetConfig(
            dataset_name="Synthetic unified-runner fixture (not CIC-IDS2017)",
            data_path=csv_path,
            target_column="class_label",
            group_columns=["fixture_group"],
            excluded_columns={},
            random_seed=15,
            output_dir=tmp_path / "dataset_outputs",
        )
    )


def test_runner_reproducibility_split_integrity_and_final_test_isolation(
    tmp_path, monkeypatch
):
    dataset = _synthetic_dataset(tmp_path)
    original_split_metadata = dict(dataset.splits.split_details)
    selector_count = 0
    test_access_count = 0

    def track_selector(function):
        def wrapped(*args, **kwargs):
            nonlocal selector_count
            result = function(*args, **kwargs)
            selector_count += 1
            return result

        return wrapped

    monkeypatch.setattr(
        experiment_module,
        "run_genetic_algorithm",
        track_selector(experiment_module.run_genetic_algorithm),
    )
    monkeypatch.setattr(
        experiment_module,
        "run_binary_pso",
        track_selector(experiment_module.run_binary_pso),
    )
    monkeypatch.setattr(
        experiment_module,
        "run_ant_colony_optimization",
        track_selector(experiment_module.run_ant_colony_optimization),
    )
    original_test_accessor = dataset.splits.get_test_for_final_evaluation

    def observe_test_access(*, final_choices_frozen=False):
        nonlocal test_access_count
        expected_completed_selectors = ((test_access_count // 7) + 1) * 6
        assert selector_count == expected_completed_selectors
        test_access_count += 1
        return original_test_accessor(final_choices_frozen=final_choices_frozen)

    monkeypatch.setattr(dataset.splits, "get_test_for_final_evaluation", observe_test_access)
    config = default_synthetic_config([7, 11])
    first = run_part_a_experiment(dataset, config, output_dir=tmp_path / "experiment_one")
    assert test_access_count == 7
    assert selector_count == 6

    # New invocation repeats the same frozen protocol, and each run gets one test read.
    second = run_part_a_experiment(dataset, config, output_dir=tmp_path / "experiment_two")
    assert test_access_count == 14
    assert selector_count == 12

    assert first.split_metadata == second.split_metadata == original_split_metadata
    assert len(first.runs) == 1 + 3 * len(config.seeds)
    assert [run.algorithm for run in first.runs] == [
        "full_feature_baseline",
        "ga",
        "ga",
        "binary_pso",
        "binary_pso",
        "aco",
        "aco",
    ]
    assert all(run.final_test_metrics.sample_count > 0 for run in first.runs)
    assert all(run.validation_macro_f1 >= 0 for run in first.runs)
    assert all(
        run.selected_feature_count <= run.eligible_feature_count for run in first.runs
    )
    assert all(
        run.unique_model_evaluation_count <= config.ga.max_model_evaluations
        for run in first.runs
    )

    first_reproducible_fields = [
        (run.algorithm, run.seed, run.selected_features, run.validation_fitness)
        for run in first.runs
    ]
    second_reproducible_fields = [
        (run.algorithm, run.seed, run.selected_features, run.validation_fitness)
        for run in second.runs
    ]
    assert first_reproducible_fields == second_reproducible_fields
    assert first.aggregate_metrics["ga"]["validation_macro_f1"].sample_count == 2
    assert first.aggregate_metrics["ga"]["validation_macro_f1"].standard_deviation is not None
    assert first.aggregate_metrics["ga"]["validation_macro_f1"].confidence_interval_low is not None

    json_summary = json.loads(Path(first.summary_json_path).read_text(encoding="utf-8"))
    csv_summary = pd.read_csv(first.summary_csv_path)
    assert len(json_summary["runs"]) == 7
    assert len(csv_summary) == 7
    assert "validation_macro_f1" in csv_summary.columns
    assert "final_test_macro_f1" in csv_summary.columns
    assert json_summary["dataset_identity_verified"] is False


def test_runner_requires_matching_selector_fitness_and_evaluation_protocol():
    config = default_synthetic_config([3])
    bad_ga = config.ga.model_copy(
        update={"fitness_performance_weight": 0.7, "fitness_size_weight": 0.3}
    )
    bad_bpso = config.binary_pso.model_copy(
        update={"fitness_performance_weight": 0.7, "fitness_size_weight": 0.3}
    )
    with pytest.raises(ValueError, match="identical feature-fitness weights"):
        type(config)(
            seeds=config.seeds,
            random_forest=config.random_forest,
            ga=bad_ga,
            binary_pso=bad_bpso,
            aco=config.aco,
        )
