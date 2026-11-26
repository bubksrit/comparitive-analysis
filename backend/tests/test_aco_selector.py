"""ACO tests use synthetic-only fixtures; they are not CIC-IDS2017 research results."""

import numpy as np
import pytest

from app.features.benchmark_ga import make_fixture
from app.features.data import load_and_audit
from app.features.evaluator import RandomForestEvaluator
from app.features.selection.aco import (
    construct_binary_subset,
    run_ant_colony_optimization,
    update_pheromones,
)
from app.features.selection.genetic import calculate_feature_fitness
from app.models.dataset import DatasetConfig
from app.models.features import AntColonyConfig, RandomForestConfig


def _synthetic_dataset(tmp_path):
    csv_path = make_fixture(tmp_path / "synthetic_aco_test_fixture.csv", seed=123)
    return load_and_audit(
        DatasetConfig(
            dataset_name="Synthetic ACO test fixture (not CIC-IDS2017)",
            data_path=csv_path,
            target_column="class_label",
            group_columns=["fixture_group"],
            excluded_columns={},
            random_seed=15,
            output_dir=tmp_path / "outputs",
        )
    )


def _aco_config(seed=21, budget=12):
    return AntColonyConfig(
        ant_count=4,
        iterations=4,
        pheromone_alpha=1.0,
        heuristic_beta=0.0,
        initial_pheromone=1.0,
        evaporation_rate=0.2,
        deposit_scale=1.0,
        pheromone_min=0.01,
        pheromone_max=10.0,
        min_features=1,
        max_features=2,
        max_model_evaluations=budget,
        seed=seed,
    )


def _evaluator():
    return RandomForestEvaluator(RandomForestConfig(n_estimators=8, random_state=42, n_jobs=1))


def test_pheromone_update_evaporates_and_reinforces_selected_features():
    updated = update_pheromones(
        np.array([1.0, 1.0, 1.0]),
        np.array([1, 0, 1]),
        0.5,
        evaporation_rate=0.2,
        deposit_scale=1.0,
        pheromone_min=0.01,
        pheromone_max=10.0,
    )
    assert updated == pytest.approx([0.8 + 1 / 1.5, 0.8, 0.8 + 1 / 1.5])


def test_pheromone_update_clips_to_configured_bounds():
    updated = update_pheromones(
        np.array([100.0, 0.001]),
        np.array([0, 0]),
        0.5,
        evaporation_rate=0.0,
        deposit_scale=1.0,
        pheromone_min=0.01,
        pheromone_max=10.0,
    )
    assert updated == pytest.approx([10.0, 0.01])


def test_constructed_masks_are_binary_and_within_feature_bounds():
    config = _aco_config()
    rng = np.random.default_rng(10)
    for _ in range(20):
        mask = construct_binary_subset(np.ones(5), config, rng)
        assert mask.shape == (5,)
        assert set(mask.tolist()) <= {0, 1}
        assert config.min_features <= int(mask.sum()) <= config.max_features


def test_aco_uses_approved_shared_fitness_formula():
    assert calculate_feature_fitness(0.75, 2, 5) == pytest.approx(
        0.8 * (1 - 0.75) + 0.2 * (2 / 5)
    )


def test_aco_respects_unique_evaluation_budget_and_records_callback_requests(tmp_path):
    dataset = _synthetic_dataset(tmp_path)
    result = run_ant_colony_optimization(
        dataset, _aco_config(budget=5), evaluator=_evaluator()
    )
    assert 0 < result.evaluation_count <= 5
    assert result.fitness_request_count >= result.evaluation_count
    assert result.iterations_completed == len(result.best_fitness_trace)
    assert result.best_fitness_trace[-1] == result.best_fitness
    assert all(
        a >= b
        for a, b in zip(result.best_fitness_trace, result.best_fitness_trace[1:], strict=False)
    )
    assert result.evaluation_count <= result.config.max_model_evaluations


def test_aco_is_reproducible_for_fixed_config_and_seed(tmp_path):
    dataset = _synthetic_dataset(tmp_path)
    settings = _aco_config(seed=43)
    evaluator = _evaluator()
    first = run_ant_colony_optimization(dataset, settings, evaluator=evaluator)
    second = run_ant_colony_optimization(dataset, settings, evaluator=evaluator)
    assert first.selected_mask == second.selected_mask
    assert first.best_fitness == second.best_fitness
    assert first.best_fitness_trace == second.best_fitness_trace
    assert first.evaluation_count == second.evaluation_count


def test_aco_fitness_never_opens_held_out_test_partition(tmp_path, monkeypatch):
    dataset = _synthetic_dataset(tmp_path)

    def fail_if_test_opened(*args, **kwargs):
        raise AssertionError("ACO fitness attempted to access the held-out test partition")

    monkeypatch.setattr(dataset.splits, "get_test_for_final_evaluation", fail_if_test_opened)
    result = run_ant_colony_optimization(dataset, _aco_config(seed=8), evaluator=_evaluator())
    assert result.evaluation_count > 0
    assert result.split_metadata["test_partition_sealed"] is True


def test_aco_rejects_feature_bounds_outside_dataset(tmp_path):
    dataset = _synthetic_dataset(tmp_path)
    config = AntColonyConfig(
        ant_count=4,
        iterations=1,
        min_features=1,
        max_features=len(dataset.feature_columns) + 1,
        max_model_evaluations=4,
    )
    with pytest.raises(ValueError, match="feature constraints"):
        run_ant_colony_optimization(dataset, config, evaluator=_evaluator())
