"""CIC-IoT2023 preparation config and dynamic study-label tests."""

import json
from pathlib import Path

import pandas as pd

from app.features.iot_loader import CIC_IOT2023_EXPECTED_COLUMNS
from app.features.iot_preparation import prepare_cic_iot2023_sample
from app.models.dataset import DatasetConfig


def test_iot2023_config_describes_raw_source_and_reproducible_sample():
    config_path = Path(__file__).parents[1] / "config" / "cic-iot2023.json"
    config = DatasetConfig.model_validate_json(config_path.read_text(encoding="utf-8"))

    assert config.dataset_name == "CIC-IoT2023"
    assert config.study_label == "CIC-IoT2023 34-class attack classification"
    assert config.raw_data_path == Path("../data/raw/cic-iot2023/CSV")
    assert config.label_strategy == "multiclass"
    assert config.sample_rows_per_folder == 5000
    assert config.sample_random_seed == 42
    assert config.random_seed == 42
    assert config.split_strategy == "auto"
    assert config.group_identical_feature_rows is True
    assert config.train_fraction == 0.6
    assert config.validation_fraction == 0.2
    assert config.test_fraction == 0.2
    assert len(config.expected_labels) == 34
    assert config.expected_labels.count("Benign") == 1
    assert config.strict_expected_columns is True
    assert config.expected_columns[-1] == "label"
    assert config.retrieval_date is None
    assert config.group_columns == []


def test_raw_folder_source_requires_label_strategy():
    payload = json.loads(
        (Path(__file__).parents[1] / "config" / "cic-iot2023.json").read_text(
            encoding="utf-8"
        )
    )
    payload["label_strategy"] = None

    try:
        DatasetConfig.model_validate(payload)
    except ValueError as exc:
        assert "requires a folder-derived label_strategy" in str(exc)
    else:
        raise AssertionError("raw_data_path without label_strategy must be rejected")


def test_sample_preparation_writes_deterministic_data_and_manifest(tmp_path):
    raw_root = tmp_path / "raw"
    for folder, label_offset in (("Benign_Final", 0), ("Attack_A", 100)):
        category = raw_root / folder
        category.mkdir(parents=True)
        frame = pd.DataFrame(
            {column: [float(label_offset + row) for row in range(4)]
             for column in CIC_IOT2023_EXPECTED_COLUMNS}
        )
        frame.to_csv(category / "capture.pcap.csv", index=False)

    prepared_path = tmp_path / "processed" / "sample.csv"
    config = DatasetConfig(
        dataset_name="CIC-IoT2023",
        study_label="CIC-IoT2023 2-class synthetic test",
        raw_data_path=raw_root,
        label_strategy="multiclass",
        sample_rows_per_folder=2,
        sample_random_seed=42,
        data_path=prepared_path,
        target_column="label",
        expected_columns=CIC_IOT2023_EXPECTED_COLUMNS + ["label"],
        strict_expected_columns=True,
        expected_labels=["Attack_A", "Benign"],
        split_strategy="stratified_random",
    )

    result = prepare_cic_iot2023_sample(config)
    saved = pd.read_csv(prepared_path)
    manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))

    assert len(saved) == 4
    assert list(saved.columns) == config.expected_columns
    assert saved["label"].value_counts().to_dict() == {"Attack_A": 2, "Benign": 2}
    assert manifest["sample_sha256"]
    assert manifest["sample_random_seed"] == 42
    assert manifest["sample_rows_per_folder"] == 2
    assert manifest["group_independence_verified"] is False
    assert "No raw or sampled rows removed" in manifest["duplicate_policy"]
    assert manifest["sample_exact_duplicate_rows_not_removed"] == 0
    assert manifest["sample_identical_feature_rows_not_removed"] == 0
    assert len(manifest["source_files"]) == 2
