"""Prepare a deterministic, labeled CIC-IoT2023 sample for the shared pipeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.features.iot_loader import load_cic_iot2023
from app.models.dataset import DatasetConfig


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_cic_iot2023_sample(config: DatasetConfig) -> dict[str, Any]:
    """Materialize the configured development sample and its reproducibility manifest.

    This prepares data only. It does not split data, fit a model, or run feature
    selection. The raw source directory is read without modification.
    """
    if config.raw_data_path is None:
        raise ValueError("raw_data_path is required for CIC-IoT2023 sample preparation")
    if config.label_strategy is None:
        raise ValueError("label_strategy is required for folder-derived labels")
    if config.sample_rows_per_folder is None:
        raise ValueError("sample_rows_per_folder is required for a bounded sample")
    raw_root = config.raw_data_path.resolve()
    output_path = config.data_path.resolve()
    if output_path == raw_root or raw_root in output_path.parents:
        raise ValueError("prepared sample path must be outside the raw data directory")
    manifest_path = config.data_path.with_suffix(config.data_path.suffix + ".manifest.json")
    if config.data_path.exists() or manifest_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite an existing sample or manifest at {config.data_path}"
        )

    foundation = load_cic_iot2023(
        config.raw_data_path,
        label_strategy=config.label_strategy,
        max_rows_per_folder=config.sample_rows_per_folder,
        random_seed=config.sample_random_seed,
        compute_checksums=True,
    )
    sample = foundation.features.copy()
    sample[config.target_column] = foundation.labels.to_numpy()
    if config.expected_columns and list(sample.columns) != config.expected_columns:
        raise ValueError(
            "Prepared sample schema differs from configured expected_columns: "
            f"observed={list(sample.columns)}"
        )
    if config.expected_labels:
        observed_labels = sorted(sample[config.target_column].astype(str).unique())
        if observed_labels != sorted(config.expected_labels):
            raise ValueError(
                "Prepared sample labels differ from expected_labels: "
                f"observed={observed_labels}"
            )

    config.data_path.parent.mkdir(parents=True, exist_ok=True)
    sample_tmp = config.data_path.with_name(config.data_path.name + ".tmp")
    sample.to_csv(sample_tmp, index=False)
    sample_tmp.replace(config.data_path)

    source_files = []
    for folder in foundation.provenance["folder_manifests"]:
        for file_path, checksum in sorted(folder["sha256_by_file"].items()):
            source_files.append(
                {
                    "path": file_path,
                    "sha256": checksum,
                    "folder": folder["folder_name"],
                    "derived_label": (
                        folder["label_multiclass"]
                        if config.label_strategy == "multiclass"
                        else folder["label_binary"]
                    ),
                }
            )
    manifest = {
        "dataset_name": config.dataset_name,
        "study_label": config.study_label
        or f"{config.dataset_name} classification",
        "source_url": config.source_url,
        "release_or_version": config.release_or_version,
        "retrieval_date": config.retrieval_date,
        "dataset_identity_verified": False,
        "group_independence_verified": False,
        "raw_data_path": str(config.raw_data_path),
        "prepared_data_path": str(config.data_path),
        "target_column": config.target_column,
        "label_strategy": config.label_strategy,
        "label_derivation": "Immediate parent folder; Benign_Final maps to Benign.",
        "sample_rows_per_folder": config.sample_rows_per_folder,
        "sample_random_seed": config.sample_random_seed,
        "sampling_algorithm": "Seeded random-priority sampling over sorted files in 100000-row chunks.",
        "sample_row_count": len(sample),
        "sample_class_counts": {
            str(label): int(count)
            for label, count in sample[config.target_column].value_counts().sort_index().items()
        },
        "columns": list(sample.columns),
        "sample_sha256": _sha256(config.data_path),
        "duplicate_policy": (
            "No raw or sampled rows removed. Exact global raw duplicate audit is incomplete; "
            "the experiment split groups identical eligible feature vectors together."
        ),
        "sample_exact_duplicate_rows_not_removed": int(sample.duplicated(keep="first").sum()),
        "sample_identical_feature_rows_not_removed": int(
            sample.drop(columns=[config.target_column]).duplicated(keep="first").sum()
        ),
        "source_files": source_files,
    }
    manifest_tmp = manifest_path.with_name(manifest_path.name + ".tmp")
    manifest_tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest_tmp.replace(manifest_path)
    return {"sample": config.data_path, "manifest": manifest_path, "metadata": manifest}
