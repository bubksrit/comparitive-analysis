"""GA selector tests on synthetic-only fixtures; not CIC-IDS2017 research results."""

import numpy as np
import pandas as pd
import pytest

from app.features.data import load_and_audit
from app.features.evaluator import RandomForestEvaluator
from app.features.selection.genetic import (
    calculate_feature_fitness,
    repair_mask,
    run_genetic_algorithm,
)
from app.models.dataset import DatasetConfig
from app.models.features import GeneticAlgorithmConfig, RandomForestConfig


def _synthetic_dataset(tmp_path):
    rng = np.random.default_rng(123)
    rows = []
    for group in range(10):
        for within_group in range(12):
            label = "attack" if within_group % 2 else "benign"
            rows.append(
                {
                    "fixture_group": f"group-{group:02d}",
                    "signal": float(label == "attack") + rng.normal(0, 0.2),
                    "noise_a": rng.normal(),
                    "noise_b": rng.normal(),
                    "class_label": label,
                }
            )
    csv_path = tmp_path / "ga_synthetic_test_fixture.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    config = DatasetConfig(
        dataset_name="Synthetic GA test fixture (not CIC-IDS2017)",
        data_path=csv_path,
        target_column="class_label",
        group_columns=["fixture_group"],
        excluded_columns={},
        random_seed=9,
        output_dir=tmp_path / "outputs",
    )
    return load_and_audit(config)


def _ga_config(seed=19):
    return GeneticAlgorithmConfig(
        population_size=4,
        generations=4,
        selection_method="tournament",
        tournament_size=2,
        crossover_probability=0.8,
        mutation_probability=0.1,
        elitism_count=1,
        min_features=1,
        max_features=2,
        max_model_evaluations=10,
        seed=seed,
    )


def _evaluator():
    return RandomForestEvaluator(
        RandomForestConfig(n_estimators=8, random_state=42, n_jobs=1)
    )


def test_fitness_matches_approved_formula():
    fitness = calculate_feature_fitness(
        validation_macro_f1=0.75,
        selected_feature_count=2,
        eligible_feature_count=5,
    )
    assert fitness == pytest.approx(0.8 * (1 - 0.75) + 0.2 * (2 / 5))


def test_repair_enforces_nonempty_and_feature_count_constraints():
    rng = np.random.default_rng(4)
    repaired_empty = repair_mask([0, 0, 0, 0, 0], 5, 2, 3, rng)
    repaired_oversized = repair_mask([1, 1, 1, 1, 1], 5, 2, 3, rng)

    assert len(repaired_empty) == 5
    assert int(repaired_empty.sum()) == 2
    assert 2 <= int(repaired_oversized.sum()) <= 3
    with pytest.raises(ValueError, match="length 5"):
        repair_mask([1, 0], 5, 1, 5, rng)
    with pytest.raises(ValueError, match="binary"):
        repair_mask([0, 0, 2, 0, 0], 5, 1, 5, rng)


def test_ga_returns_feasible_binary_mask_and_respects_evaluation_budget(tmp_path):
    dataset = _synthetic_dataset(tmp_path)
    result = run_genetic_algorithm(dataset, _ga_config(), evaluator=_evaluator())

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
    assert result.best_fitness_trace[0] >= result.best_fitness_trace[-1]
    assert result.best_fitness == result.best_fitness_trace[-1]
    assert result.selector_time_seconds >= 0
    assert result.model_evaluation_time_seconds >= 0
    assert result.seed == result.config.seed
    assert result.config.selection_method == "tournament"
    assert result.run_artifact


def test_ga_is_reproducible_for_fixed_config_and_seed(tmp_path):
    dataset = _synthetic_dataset(tmp_path)
    settings = _ga_config(seed=32)
    evaluator = _evaluator()

    first = run_genetic_algorithm(dataset, settings, evaluator=evaluator)
    second = run_genetic_algorithm(dataset, settings, evaluator=evaluator)

    assert first.selected_mask == second.selected_mask
    assert first.selected_feature_names == second.selected_feature_names
    assert first.best_fitness == second.best_fitness
    assert first.best_fitness_trace == second.best_fitness_trace
    assert first.evaluation_count == second.evaluation_count


def test_fitness_callback_never_opens_the_held_out_test_partition(tmp_path, monkeypatch):
    dataset = _synthetic_dataset(tmp_path)

    def fail_if_test_opened(*args, **kwargs):
        raise AssertionError("GA fitness attempted to access the held-out test partition")

    monkeypatch.setattr(dataset.splits, "get_test_for_final_evaluation", fail_if_test_opened)
    result = run_genetic_algorithm(dataset, _ga_config(seed=5), evaluator=_evaluator())

    assert result.evaluation_count > 0
    assert result.split_metadata["test_partition_sealed"] is True

