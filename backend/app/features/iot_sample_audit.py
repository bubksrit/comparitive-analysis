"""Exact duplicate audit for a prepared development sample only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_prepared_sample(
    sample_path: Path, manifest_path: Path, output_dir: Path
) -> dict[str, Any]:
    """Count exact duplicate rows in one manifested sample, without global claims.

    Identical feature vectors are counted independently of their labels so that
    the split pipeline can keep vectors with conflicting labels in one partition.
    The source CSVs are never read or changed by this function.
    """
    sample_path = sample_path.resolve()
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_hash = _sha256(sample_path)
    if actual_hash != manifest.get("sample_sha256"):
        raise ValueError("Prepared sample checksum does not match its manifest")

    frame = pd.read_csv(sample_path, low_memory=False)
    target = manifest["target_column"]
    expected_columns = manifest["columns"]
    if list(frame.columns) != expected_columns:
        raise ValueError("Prepared sample columns differ from its manifest")
    if target not in frame.columns:
        raise ValueError(f"Target column {target!r} is absent from the sample")
    feature_frame = frame.drop(columns=[target])
    report = {
        "report_title": "CIC-IoT2023 prepared development-sample duplicate audit",
        "scope": "prepared development sample only",
        "sample_path": str(sample_path),
        "sample_manifest_path": str(manifest_path),
        "sample_sha256": actual_hash,
        "sample_row_count": int(len(frame)),
        "class_counts": {
            str(label): int(count)
            for label, count in frame[target].value_counts(dropna=False).sort_index().items()
        },
        "exact_full_record_duplicate_occurrences_not_removed": int(
            frame.duplicated(keep="first").sum()
        ),
        "identical_feature_vector_duplicate_occurrences_not_removed": int(
            feature_frame.duplicated(keep="first").sum()
        ),
        "duplicate_definition": (
            "pandas exact row equality; feature-vector counts exclude the target column"
        ),
        "raw_global_duplicate_audit_status": "incomplete_no_global_count",
        "raw_global_duplicate_count": None,
        "rows_removed": 0,
        "limitations": [
            "The sample audit does not estimate or establish global raw-dataset duplicate totals.",
            "Folder-derived labels are provenance labels, not independently verified ground truth.",
            "No capture/session independence is inferred from feature equality or source-file boundaries.",
        ],
    }
    digest_prefix = actual_hash[:12]
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"cic_iot2023_sample_duplicate_audit_{digest_prefix}.json"
    markdown_path = output_dir / f"cic_iot2023_sample_duplicate_audit_{digest_prefix}.md"
    if json_path.exists() or markdown_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing sample audit: {json_path}")
    report["report_paths"] = {"json": str(json_path), "markdown": str(markdown_path)}
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(
        "\n".join(
            [
                "# CIC-IoT2023 prepared sample duplicate audit",
                "",
                f"- Scope: {report['scope']}",
                f"- Sample rows: {report['sample_row_count']:,}",
                f"- Sample SHA-256: `{actual_hash}`",
                f"- Exact full-record duplicate occurrences retained: {report['exact_full_record_duplicate_occurrences_not_removed']:,}",
                f"- Identical feature-vector duplicate occurrences retained: {report['identical_feature_vector_duplicate_occurrences_not_removed']:,}",
                "- Global raw-dataset duplicate audit: incomplete; no global count is available.",
                "- Rows removed: 0",
                "",
                "## Class counts",
                "",
                "| Label | Rows |",
                "|---|---:|",
                *[
                    f"| {label} | {count:,} |"
                    for label, count in report["class_counts"].items()
                ],
                "",
                "## Limitations",
                "",
                *[f"- {item}" for item in report["limitations"]],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return report
