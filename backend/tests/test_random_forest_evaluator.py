"""Synthetic-only metric/pipeline tests; these are not CIC-IDS2017 results."""

import json

import pandas as pd
import pytest

from app.features.data import load_and_audit
from app.features.evaluator import (
    RandomForestEvaluator,
    build_rf_pipeline,
    calculate_classification_metrics,
)
from app.models.dataset import DatasetConfig
from app.models.features import RandomForestConfig


def _synthetic_dataset(tmp_path):
    rows = []
    for index in range(120):
        group, within = divmod(index, 6)
        label = "benign" if within % 2 else "attack"
        rows.append(
            {
                "group_day": f"group-{group:02d}",
                "numeric_signal": float(index % 13),
                "category": "ordinary" if within < 3 else "rare-in-train",
                "class_label": label,
            }
        )
    path = tmp_path / "synthetic_evaluator_fixture.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    config = DatasetConfig(
        dataset_name="synthetic test fixture",
        data_path=path,
        target_column="class_label",
        group_columns=["group_day"],
        excluded_columns={},
        random_seed=23,
        output_dir=tmp_path / "reports",
    )
    return load_and_audit(config)


def test_metric_calculations_and_support_counts():
    metrics = calculate_classification_metrics(
        ["a", "a", "b", "b"],
        ["a", "b", "b", "b"],
        class_order=["a", "b"],
    )

    assert metrics.accuracy == pytest.approx(0.75)
    assert metrics.macro_precision == pytest.approx(5 / 6)
    assert metrics.macro_recall == pytest.approx(0.75)
    assert metrics.macro_f1 == pytest.approx((2 / 3 + 0.8) / 2)
    assert metrics.weighted_precision == pytest.approx(5 / 6)
    assert metrics.weighted_recall == pytest.approx(0.75)
    assert metrics.weighted_f1 == pytest.approx((2 / 3 + 0.8) / 2)
    assert metrics.confusion_matrix == [[1, 1], [0, 2]]
    assert metrics.class_support == {"a": 2, "b": 2}
    assert metrics.sample_count == 4


def test_validation_evaluator_uses_common_pipeline_and_records_run(tmp_path):
    dataset = _synthetic_dataset(tmp_path)
    evaluator = RandomForestEvaluator()
    subset_result = evaluator.evaluate_validation(dataset, ["numeric_signal"])
    baseline = evaluator.evaluate_full_feature_baseline(dataset)

    assert subset_result.evaluation_partition == "validation"
    assert subset_result.evaluation_role == "feature_subset"
    assert subset_result.selected_features == ["numeric_signal"]
    assert subset_result.primary_metric_name == "macro_f1"
    assert subset_result.primary_score == subset_result.metrics.macro_f1
    assert subset_result.metrics.sample_count == len(dataset.splits.validation.labels)
    assert sum(subset_result.metrics.class_support.values()) == len(
        dataset.splits.validation.labels
    )
    assert baseline.evaluation_role == "full_feature_baseline"
    assert baseline.selected_features == dataset.feature_columns
    assert subset_result.random_forest_config == RandomForestConfig()
    assert subset_result.metadata.seed == dataset.config.random_seed
    assert subset_result.software_versions["scikit_learn"]
    assert subset_result.fit_time_seconds >= 0
    assert subset_result.prediction_time_seconds >= 0

    saved_runs = list((dataset.config.output_dir / "rf-evaluations").glob("*.json"))
    assert len(saved_runs) == 2
    saved = json.loads(saved_runs[0].read_text(encoding="utf-8"))
    assert saved["random_forest_config"]["random_state"] == 42
    assert saved["split_metadata"]["actual_strategy"] == "group_aware"
    assert saved["dataset_name"] == "synthetic test fixture"


def test_final_test_requires_frozen_choices_and_does_not_fit_preprocessing_on_validation(
    tmp_path,
):
    dataset = _synthetic_dataset(tmp_path)
    train = dataset.splits.train.features
    validation = dataset.splits.validation.features.copy()
    validation.loc[:, "category"] = "validation-only-category"
    pipeline = build_rf_pipeline(train, ["category"], RandomForestConfig())
    pipeline.fit(train[["category"]], dataset.splits.train.labels)
    encoder = (
        pipeline.named_steps["preprocessor"]
        .named_transformers_["categorical"]
        .named_steps["encoder"]
    )
    assert "validation-only-category" not in encoder.categories_[0]

    evaluator = RandomForestEvaluator()
    with pytest.raises(RuntimeError, match="choices are frozen"):
        evaluator.evaluate_final_test(dataset)
    result = evaluator.evaluate_final_test(dataset, final_choices_frozen=True)
    assert result.evaluation_partition == "test"
    assert result.metrics.sample_count == len(
        dataset.splits.get_test_for_final_evaluation(final_choices_frozen=True).labels
    )
    assert result.fit_time_seconds >= 0


def test_empty_or_ineligible_feature_subsets_are_rejected(tmp_path):
    dataset = _synthetic_dataset(tmp_path)
    evaluator = RandomForestEvaluator()
    with pytest.raises(ValueError, match="Feature subset cannot be empty"):
        evaluator.evaluate_validation(dataset, [])
    with pytest.raises(ValueError, match="ineligible or unknown"):
        evaluator.evaluate_validation(dataset, ["class_label"])



def test_evaluation_result_uses_configured_study_label(tmp_path):
    dataset = _synthetic_dataset(tmp_path)
    dataset.config.study_label = "CIC-IoT2023 34-class attack classification"

    result = RandomForestEvaluator().evaluate_validation(
        dataset, ["numeric_signal"], persist_run=False
    )

    assert result.study_label == "CIC-IoT2023 34-class attack classification"
