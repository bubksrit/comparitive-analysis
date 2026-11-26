"""Synthetic-only fixtures for data-foundation tests; never CIC-IDS2017 results."""

import json

import numpy as np
import pandas as pd
import pytest

from app.features.data import _group_overlap_details, load_and_audit, write_audit_report
from app.features.preprocessing import build_preprocessor
from app.models.dataset import DatasetConfig


def _synthetic_fixture(path):
    """Generate a tiny test CSV. It is deliberately not represented as research data."""
    rows = []
    for index in range(60):
        group_number, within_group = divmod(index, 6)
        rows.append(
            {
                "flow_id": f"fixture-{index}",
                "capture_day": f"group-{group_number:02d}",
                "event_timestamp": f"2020-01-{group_number + 1:02d}T00:{within_group:02d}:00Z",
                "src_ip": f"192.0.2.{group_number + 1}",
                "dst_port": 80 + within_group,
                "amount": np.inf if index == 2 else float(index),
                "amount_copy": np.inf if index == 2 else float(index),
                "constant": 7,
                "category": "alpha" if within_group % 2 else "beta",
                "class_label": "benign" if within_group % 2 else "attack",
            }
        )
    rows.append(rows[0].copy())  # audit-only duplicate row; it is retained.
    rows[3]["amount"] = np.nan
    rows[3]["amount_copy"] = np.nan
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


@pytest.fixture
def synthetic_csv(tmp_path):
    return _synthetic_fixture(tmp_path / "tiny_test_fixture.csv")


def _config(csv_path, **overrides):
    values = {
        "dataset_name": "synthetic test fixture",
        "data_path": csv_path,
        "target_column": "class_label",
        "expected_columns": [
            "flow_id",
            "capture_day",
            "event_timestamp",
            "src_ip",
            "dst_port",
            "amount",
            "amount_copy",
            "constant",
            "category",
            "class_label",
        ],
        "strict_expected_columns": True,
        "excluded_columns": {
            "flow_id": "Synthetic fixture row identifier.",
            "src_ip": "Synthetic fixture address field.",
            "dst_port": "Synthetic fixture port field.",
        },
        "group_columns": ["capture_day"],
        "random_seed": 17,
        "output_dir": csv_path.parent / "reports",
    }
    values.update(overrides)
    return DatasetConfig.model_validate(values)


def test_audit_reports_schema_counts_and_keeps_nonconfigured_candidates(synthetic_csv):
    result = load_and_audit(_config(synthetic_csv))
    report = result.report

    assert report["dataset_identity_verified"] is False
    assert report["dataset_name_as_configured"] == "synthetic test fixture"
    assert not hasattr(result, "frame")
    assert not hasattr(result, "labels")
    assert report["row_count"] == 61
    assert report["column_count"] == 10
    assert report["eligible_feature_count"] == 5
    assert report["duplicate_row_count_not_removed"] == 1
    assert "constant" in report["constant_columns_not_removed"]
    assert report["duplicate_value_columns_not_removed"]["amount_copy"] == "amount"
    assert report["infinities_by_column_before_replacement"]["amount"] == 1
    assert report["missing_values_by_column"]["amount"] == 1
    assert report["missing_values_by_column_after_infinity_replacement"]["amount"] == 2
    assert "amount" in result.feature_columns  # Useful columns are not silently removed.
    assert "constant" in result.feature_columns  # Audit flags; it does not mutate the schema.
    assert "capture_day" not in result.feature_columns
    assert result.splits.split_details["actual_strategy"] == "group_aware"
    assert result.splits.split_details["group_overlap"] is False
    with pytest.raises(RuntimeError, match="Test partition is sealed"):
        result.splits.get_test_for_final_evaluation()
    assert len(result.splits.get_test_for_final_evaluation(final_choices_frozen=True).labels) > 0


def test_group_overlap_metadata_detects_shared_identifiers():
    groups = pd.Series(["a", "b", "b", "c", "d"])
    details = _group_overlap_details(
        groups,
        {
            "train": np.array([0, 1]),
            "validation": np.array([2, 3]),
            "test": np.array([4]),
        },
    )

    assert details["group_overlap"] is True
    assert details["group_overlap_by_partition"] == {"train__validation": ["b"]}


def test_stratified_fallback_and_audit_artifacts(synthetic_csv):
    config = _config(
        synthetic_csv,
        group_columns=[],
        excluded_columns={},
        split_strategy="stratified_random",
    )
    result = load_and_audit(config)
    outputs = write_audit_report(result)

    assert result.splits.split_details["actual_strategy"] == "stratified_random_fallback"
    assert result.report["split"]["limitations"].startswith("Stratified random split")
    assert set(outputs) == {"json", "csv", "markdown"}
    saved = json.loads((config.output_dir / "audit.json").read_text(encoding="utf-8"))
    assert saved["row_count"] == 61
    assert (config.output_dir / "columns.csv").exists()
    assert (config.output_dir / "audit.md").exists()


def test_auto_split_uses_parseable_time_metadata(synthetic_csv):
    frame = pd.read_csv(synthetic_csv).rename(columns={"capture_day": "capture_group"})
    frame.to_csv(synthetic_csv, index=False)
    expected_columns = [
        "flow_id",
        "capture_group",
        "event_timestamp",
        "src_ip",
        "dst_port",
        "amount",
        "amount_copy",
        "constant",
        "category",
        "class_label",
    ]
    config = _config(
        synthetic_csv,
        group_columns=[],
        excluded_columns={},
        expected_columns=expected_columns,
    )
    result = load_and_audit(config)

    assert result.splits.split_details["actual_strategy"] == "time_ordered"
    assert result.splits.split_details["group_or_time_columns"] == ["event_timestamp"]
    assert "event_timestamp" not in result.feature_columns
    assert result.report["auto_detected_time_column"] == "event_timestamp"


def test_preprocessor_is_created_from_training_features_only(synthetic_csv):
    result = load_and_audit(_config(synthetic_csv))
    train = result.splits.train.features
    validation = result.splits.validation.features.copy()
    validation.loc[0, "category"] = "unseen-validation-category"
    preprocessor = build_preprocessor(train)
    train_transformed = preprocessor.fit_transform(train)
    validation_transformed = preprocessor.transform(validation)

    assert train_transformed.shape[0] == len(train)
    assert validation_transformed.shape[0] == len(validation)
    assert train_transformed.shape[1] == validation_transformed.shape[1]


def test_target_and_exclusion_configuration_are_validated(synthetic_csv):
    with pytest.raises(ValueError, match="target column"):
        load_and_audit(_config(synthetic_csv, target_column="missing_label"))
    with pytest.raises(ValueError, match="non-empty rationale"):
        DatasetConfig.model_validate(
            {
                "data_path": synthetic_csv,
                "target_column": "class_label",
                "excluded_columns": {"flow_id": " "},
            }
        )
