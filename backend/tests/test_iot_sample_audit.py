"""Exact duplicate counts for manifested samples stay sample-scoped."""

import hashlib
import json
from pathlib import Path

import pandas as pd

from app.features.iot_sample_audit import audit_prepared_sample


def test_sample_audit_counts_exact_rows_and_feature_vectors_without_global_claims(tmp_path):
    sample_path = tmp_path / "sample.csv"
    manifest_path = tmp_path / "sample.manifest.json"
    output_dir = tmp_path / "reports"
    pd.DataFrame(
        {
            "feature": [1.0, 1.0, 1.0, 2.0],
            "label": ["Benign", "Benign", "Attack", "Attack"],
        }
    ).to_csv(sample_path, index=False)
    sample_hash = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(
            {
                "sample_sha256": sample_hash,
                "target_column": "label",
                "columns": ["feature", "label"],
            }
        ),
        encoding="utf-8",
    )

    report = audit_prepared_sample(sample_path, manifest_path, output_dir)

    assert report["sample_row_count"] == 4
    assert report["exact_full_record_duplicate_occurrences_not_removed"] == 1
    assert report["identical_feature_vector_duplicate_occurrences_not_removed"] == 2
    assert report["raw_global_duplicate_count"] is None
    assert report["rows_removed"] == 0
    assert json.loads(Path(report["report_paths"]["json"]).read_text())["scope"] == (
        "prepared development sample only"
    )
