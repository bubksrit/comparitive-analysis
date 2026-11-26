"""BPSO tests on synthetic-only fixtures; not CIC-IDS2017 research results."""

import numpy as np
import pytest

from app.features.benchmark_ga import make_fixture
from app.features.data import load_and_audit
from app.features.evaluator import RandomForestEvaluator
from app.features.selection.bpso import _sigmoid, run_binary_pso
from app.features.selection.genetic import calculate_feature_fitness
from app.models.dataset import DatasetConfig
from app.models.features import BinaryPSOConfig, RandomForestConfig


def _synthetic_dataset(tmp_path):
    csv_path = make_fixture(tmp_path / "synthetic_bpso_test_fixture.csv", seed=123)
    return load_and_audit(
        DatasetConfig(
            dataset_name="Synthetic BPSO test fixture (not CIC-IDS2017)",
            data_path=csv_path,
            target_column="class_label",
            group_columns=["fixture_group"],
            excluded_columns={},
            random_seed=15,
            output_dir=tmp_path / "outputs",
        )
    )


def _bpso_config(seed=21):
    return BinaryPSOConfig(
        particle_count=4,
        iterations=4,
        inertia_start=0.9,
        inertia_end=0.4,
        cognitive_coefficient=2.0,
        social_coefficient=2.0,
        velocity_min=-4.0,
        velocity_max=4.0,
        min_features=1,
        max_features=2,
        max_model_evaluations=10,
        seed=seed,
    )


def _evaluator():
    return RandomForestEvaluator(RandomForestConfig(n_estimators=8, random_state=42, n_jobs=1))


def test_sigmoid_transfer_maps_velocity_to_selection_probability():
    probabilities = _sigmoid(np.array([-4.0, 0.0, 4.0]))
    assert probabilities[0] == pytest.approx(1 / (1 + np.exp(4)))
    assert probabilities[1] == pytest.approx(0.5)
    assert probabilities[2] == pytest.approx(1 / (1 + np.exp(-4)))


def test_bpso_uses_approved_fitness_formula():
    fitness = calculate_feature_fitness(0.75, 2, 5)
    assert fitness == pytest.approx(0.8 * (1 - 0.75) + 0.2 * (2 / 5))


def test_bpso_positions_are_binary_and_feature_constraints_are_enforced(tmp_path):
    dataset = _synthetic_dataset(tmp_path)
    result = run_binary_pso(dataset, _bpso_config(), evaluator=_evaluator())

    assert len(result.selected_mask) == len(dataset.feature_columns)
    assert set(result.selected_mask) <= {0, 1}
    assert result.config.min_features <= sum(result.selected_mask) <= result.config.max_features
    assert result.selected_feature_names == [
        name
        for bit, name in zip(result.selected_mask, dataset.feature_columns, strict=True)
        if bit
    ]
    assert result.evaluation_count <= result.config.max_model_evaluations
    assert result.fitness_request_count >= result.evaluation_count
    assert result.global_best_fitness_trace[0] >= result.global_best_fitness_trace[-1]
    assert result.best_fitness == result.global_best_fitness_trace[-1]
    assert result.iterations_completed == len(result.global_best_fitness_trace) - 1
    assert result.config.velocity_min == -4.0
    assert result.config.velocity_max == 4.0
    assert result.config.transfer_function == "sigmoid"
    assert result.selector_time_seconds >= 0
    assert result.model_evaluation_time_seconds >= 0
    assert result.seed == result.config.seed
    assert result.run_artifact


def test_bpso_is_reproducible_for_fixed_config_and_seed(tmp_path):
    dataset = _synthetic_dataset(tmp_path)
    settings = _bpso_config(seed=43)
    evaluator = _evaluator()

    first = run_binary_pso(dataset, settings, evaluator=evaluator)
    second = run_binary_pso(dataset, settings, evaluator=evaluator)

    assert first.selected_mask == second.selected_mask
    assert first.selected_feature_names == second.selected_feature_names
    assert first.best_fitness == second.best_fitness
    assert first.global_best_fitness_trace == second.global_best_fitness_trace
    assert first.evaluation_count == second.evaluation_count


def test_bpso_fitness_callback_never_opens_the_held_out_test_partition(
    tmp_path, monkeypatch
):
    dataset = _synthetic_dataset(tmp_path)

    def fail_if_test_opened(*args, **kwargs):
        raise AssertionError("BPSO fitness attempted to access the held-out test partition")

    monkeypatch.setattr(dataset.splits, "get_test_for_final_evaluation", fail_if_test_opened)
    result = run_binary_pso(dataset, _bpso_config(seed=8), evaluator=_evaluator())

    assert result.evaluation_count > 0
    assert result.split_metadata["test_partition_sealed"] is True
