"""Additional data-splitting and preprocessing leakage tests (synthetic only).

These tests supplement the existing test_dataset_foundation.py with:
- Split fraction boundary verification.
- No-overlap between train / validation / test for stratified random splits.
- Explicit confirmation that preprocessing is fitted only on training data.
- Validation and test transforms never touch the fitted parameters.
- Test partition stays sealed until final_choices_frozen=True.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.features.data import load_and_audit
from app.features.preprocessing import build_preprocessor
from app.models.dataset import DatasetConfig

# ---------------------------------------------------------------------------
# Shared synthetic fixture builder
# ---------------------------------------------------------------------------


def _make_csv(tmp_path, filename: str = "split_test.csv", n_rows: int = 300) -> tuple:
    """Generate a balanced synthetic CSV suitable for stratified splitting."""
    rng = np.random.default_rng(99)
    rows = []
    for i in range(n_rows):
        label = "benign" if i % 2 == 0 else "attack"
        rows.append({
            "numeric_a": rng.normal(),
            "numeric_b": float(i),
            "category_x": "cat_a" if i % 3 == 0 else "cat_b",
            "class_label": label,
        })
    path = tmp_path / filename
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _config(csv_path, **overrides):
    base = {
        "dataset_name": "split-leakage-test-fixture",
        "data_path": csv_path,
        "target_column": "class_label",
        "split_strategy": "stratified_random",
        "train_fraction": 0.6,
        "validation_fraction": 0.2,
        "test_fraction": 0.2,
        "random_seed": 42,
        "output_dir": csv_path.parent / "reports",
        "excluded_columns": {},
    }
    base.update(overrides)
    return DatasetConfig.model_validate(base)


# ---------------------------------------------------------------------------
# Split fraction tests
# ---------------------------------------------------------------------------


class TestSplitFractions:
    def test_row_counts_approximately_match_requested_fractions(self, tmp_path):
        csv_path = _make_csv(tmp_path, n_rows=300)
        result = load_and_audit(_config(csv_path))
        total = (
            len(result.splits.train.features)
            + len(result.splits.validation.features)
            + len(result.splits.get_test_for_final_evaluation(final_choices_frozen=True).features)
        )
        assert total == 300
        train_frac = len(result.splits.train.features) / 300
        val_frac = len(result.splits.validation.features) / 300
        # Allow ±5 % tolerance for stratified rounding
        assert abs(train_frac - 0.6) < 0.05
        assert abs(val_frac - 0.2) < 0.05

    def test_split_fractions_must_sum_to_one(self, tmp_path):
        csv_path = _make_csv(tmp_path)
        with pytest.raises(ValueError, match="sum to 1"):
            _config(csv_path, train_fraction=0.6, validation_fraction=0.3, test_fraction=0.3)

    def test_partition_rows_are_non_overlapping(self, tmp_path):
        csv_path = _make_csv(tmp_path, n_rows=120)
        result = load_and_audit(_config(csv_path))
        # Reconstruct original row identity from numeric_b (unique integer index)
        train_ids = set(result.splits.train.features["numeric_b"].tolist())
        val_ids = set(result.splits.validation.features["numeric_b"].tolist())
        test_ids = set(
            result.splits.get_test_for_final_evaluation(final_choices_frozen=True)
            .features["numeric_b"].tolist()
        )
        assert train_ids.isdisjoint(val_ids), "Train and validation share rows"
        assert train_ids.isdisjoint(test_ids), "Train and test share rows"
        assert val_ids.isdisjoint(test_ids), "Validation and test share rows"


# ---------------------------------------------------------------------------
# Preprocessing leakage tests
# ---------------------------------------------------------------------------


class TestPreprocessingLeakage:
    def test_preprocessor_fitted_on_training_data_only(self, tmp_path):
        """Imputer statistics must be derived solely from training rows."""
        csv_path = _make_csv(tmp_path, n_rows=120)
        result = load_and_audit(_config(csv_path))
        train = result.splits.train.features
        preprocessor = build_preprocessor(train)
        preprocessor.fit(train)

        # Inspect the fitted median for numeric_a
        fitted_median = preprocessor.named_transformers_["numeric"].statistics_[0]  # numeric_a
        expected_median = train["numeric_a"].median()
        assert fitted_median == pytest.approx(expected_median, rel=1e-6)

    def test_validation_transform_does_not_change_fitted_parameters(self, tmp_path):
        """Transforming validation data must not alter any fitted imputer statistics."""
        csv_path = _make_csv(tmp_path, n_rows=120)
        result = load_and_audit(_config(csv_path))
        train = result.splits.train.features
        val = result.splits.validation.features.copy()

        preprocessor = build_preprocessor(train)
        preprocessor.fit(train)
        # Record statistics before transforming validation
        stats_before = preprocessor.named_transformers_["numeric"].statistics_.copy()
        preprocessor.transform(val)
        stats_after = preprocessor.named_transformers_["numeric"].statistics_.copy()

        assert (stats_before == stats_after).all(), (
            "Transforming validation data altered the imputer statistics — potential leakage"
        )

    def test_unseen_category_in_validation_handled_without_error(self, tmp_path):
        """OHE with handle_unknown='ignore' should produce zero columns for unseen cats."""
        csv_path = _make_csv(tmp_path, n_rows=120)
        result = load_and_audit(_config(csv_path))
        train = result.splits.train.features
        val = result.splits.validation.features.copy()
        # Inject an unseen category value
        val.loc[val.index[0], "category_x"] = "cat_NEVER_SEEN_IN_TRAIN"

        preprocessor = build_preprocessor(train)
        preprocessor.fit(train)
        train_transformed = preprocessor.transform(train)
        val_transformed = preprocessor.transform(val)

        # Both must produce the same number of output columns
        assert train_transformed.shape[1] == val_transformed.shape[1]

    def test_test_partition_sealed_before_freeze(self, tmp_path):
        csv_path = _make_csv(tmp_path, n_rows=120)
        result = load_and_audit(_config(csv_path))
        with pytest.raises(RuntimeError, match="sealed"):
            result.splits.get_test_for_final_evaluation()

    def test_test_partition_accessible_after_freeze(self, tmp_path):
        csv_path = _make_csv(tmp_path, n_rows=120)
        result = load_and_audit(_config(csv_path))
        test_part = result.splits.get_test_for_final_evaluation(final_choices_frozen=True)
        assert len(test_part.features) > 0
        assert len(test_part.labels) == len(test_part.features)

    def test_preprocessing_uses_training_category_set(self, tmp_path):
        """OHE categories_ must match training data, not validation or test data."""
        csv_path = _make_csv(tmp_path, n_rows=120)
        result = load_and_audit(_config(csv_path))
        train = result.splits.train.features

        preprocessor = build_preprocessor(train)
        preprocessor.fit(train)
        ohe = (
            preprocessor.named_transformers_["categorical"]
            .named_steps["encoder"]
        )
        # Categories learned from training data only
        learned_cats = set(ohe.categories_[0])
        train_cats = set(train["category_x"].dropna().unique())
        assert learned_cats == train_cats


# ---------------------------------------------------------------------------
# Class stratification tests
# ---------------------------------------------------------------------------


class TestStratification:
    def test_both_classes_appear_in_every_partition(self, tmp_path):
        csv_path = _make_csv(tmp_path, n_rows=300)
        result = load_and_audit(_config(csv_path))
        test_part = result.splits.get_test_for_final_evaluation(final_choices_frozen=True)
        for partition_name, partition in [
            ("train", result.splits.train),
            ("validation", result.splits.validation),
            ("test", test_part),
        ]:
            unique_labels = set(partition.labels.unique())
            assert "benign" in unique_labels, f"'benign' missing from {partition_name}"
            assert "attack" in unique_labels, f"'attack' missing from {partition_name}"

    def test_class_imbalance_preserved_proportionally(self, tmp_path):
        """Stratified split should maintain approximately the same class ratio."""
        csv_path = _make_csv(tmp_path, n_rows=300)  # Balanced 50/50 fixture
        result = load_and_audit(_config(csv_path))
        train_labels = result.splits.train.labels
        benign_ratio = (train_labels == "benign").sum() / len(train_labels)
        # 50/50 fixture → allow ±5 % deviation after stratification
        assert abs(benign_ratio - 0.5) < 0.05


def test_identical_feature_rows_are_kept_in_the_same_partition(tmp_path):
    rows = []
    for group_id in range(60):
        label = "benign" if group_id % 2 == 0 else "attack"
        for _ in range(2):
            rows.append({"feature_a": float(group_id), "feature_b": float(group_id % 7), "label": label})
    # Identical model inputs with conflicting folder-derived labels must also
    # remain together so the same vector cannot leak across partitions.
    rows.append({"feature_a": 0.0, "feature_b": 0.0, "label": "attack"})
    csv_path = tmp_path / "duplicate_features.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    result = load_and_audit(
        _config(
            csv_path,
            target_column="label",
            split_strategy="auto",
            group_identical_feature_rows=True,
        )
    )

    test = result.splits.get_test_for_final_evaluation(final_choices_frozen=True)
    partitions = [result.splits.train, result.splits.validation, test]
    feature_keys = [
        {tuple(row) for row in partition.features[["feature_a", "feature_b"]].to_numpy()}
        for partition in partitions
    ]
    assert feature_keys[0].isdisjoint(feature_keys[1])
    assert feature_keys[0].isdisjoint(feature_keys[2])
    assert feature_keys[1].isdisjoint(feature_keys[2])
    assert result.report["identical_eligible_feature_rows_not_removed"] == 61
    assert result.splits.split_details["actual_strategy"] == "group_aware"
    assert result.splits.split_details["identical_feature_rows_kept_together"] is True
