"""Synthetic tests for exact, locator-based CIC-IoT2023 duplicate auditing."""

import csv
import json
from pathlib import Path

import pytest

import app.features.iot_duplicate_audit as duplicate_audit
from app.features.iot_duplicate_audit import GIB
from app.features.iot_loader import CIC_IOT2023_EXPECTED_COLUMNS

SIMULATED_AVAILABLE = 12 * GIB


def _write_rows(root: Path, folder: str, filename: str, rows: list[list[float | str]]) -> Path:
    destination = root / folder / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(CIC_IOT2023_EXPECTED_COLUMNS)
        writer.writerows(rows)
    return destination


def _row(value: float | str) -> list[float | str]:
    return [value] + [float(value)] * (len(CIC_IOT2023_EXPECTED_COLUMNS) - 1)


def _run(root: Path, tmp_path: Path, rows: int, **kwargs):
    scratch = tmp_path / "scratch"
    scratch.mkdir(exist_ok=True)
    return duplicate_audit.audit_dataset(
        root,
        scratch,
        tmp_path / "reports",
        expected_rows=rows,
        chunk_size=2,
        available_scratch_bytes=SIMULATED_AVAILABLE,
        **kwargs,
    )


def test_cross_file_within_file_and_conflicting_label_duplicates(tmp_path):
    root = tmp_path / "raw"
    row_a = _row(1.0)
    # The first record spans physical lines inside a quoted CSV field. Its byte
    # offset must still point to this complete logical record on candidate reread.
    row_multiline = _row("1\n")
    _write_rows(root, "Benign_Final", "a.csv", [row_multiline, row_a, _row(2.0)])
    _write_rows(root, "Benign_Final", "b.csv", [row_a, _row(3.0)])
    _write_rows(root, "DDoS-Test", "c.csv", [row_a, _row(4.0)])

    report = _run(root, tmp_path, rows=7)

    assert report["status"] == "COMPLETE"
    assert report["total_rows_scanned"] == 7
    assert report["exact_duplicate_occurrences"] == 2
    assert report["unique_duplicate_groups"] == 1
    assert report["duplicates_within_same_file_occurrences"] == 1
    assert report["duplicates_across_different_files_occurrences"] == 1
    assert report["duplicate_groups_within_same_file"] == 1
    assert report["duplicate_groups_across_different_files"] == 1
    assert report["conflicting_label_feature_groups"] == 1
    assert report["conflicting_label_feature_rows"] == 4
    assert report["per_class_duplicate_occurrences"] == {"Benign": 2}
    assert report["candidate_rows_verified"] >= 4
    assert report["full_feature_comparisons"] >= 2
    assert list((tmp_path / "scratch").iterdir()) == []
    saved = json.loads(Path(report["report_paths"]["json"]).read_text())
    assert saved["status"] == "COMPLETE"


def test_fingerprint_collision_requires_full_feature_match(tmp_path, monkeypatch):
    root = tmp_path / "raw"
    _write_rows(root, "Benign", "a.csv", [_row(1.0), _row(2.0), _row(1.0)])
    monkeypatch.setattr(
        duplicate_audit,
        "fingerprint_payload",
        lambda _payload: b"\x00" * 16,
    )

    report = _run(root, tmp_path, rows=3)

    assert report["status"] == "COMPLETE"
    assert report["exact_duplicate_occurrences"] == 1
    assert report["unique_duplicate_groups"] == 1
    assert report["fingerprint_collision_groups"] == 1
    assert report["conflicting_label_feature_groups"] == 0


def test_audit_stops_before_scan_when_preflight_fails(tmp_path):
    root = tmp_path / "raw"
    _write_rows(root, "Benign", "a.csv", [_row(1.0)])
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    report = duplicate_audit.audit_dataset(
        root,
        scratch,
        tmp_path / "reports",
        expected_rows=1,
        chunk_size=1,
        available_scratch_bytes=MINIMUM_FREE_FOR_TEST,
    )

    assert report["status"] == "INCOMPLETE"
    assert report["total_rows_scanned"] is None
    assert report["rows_processed_before_abort"] == 0
    assert report["exact_duplicate_occurrences"] is None
    assert report["scratch_preflight"]["safe_to_run"] is False
    assert list(scratch.iterdir()) == []


def test_failure_marks_incomplete_and_cleans_only_owned_temp_files(tmp_path):
    root = tmp_path / "raw"
    _write_rows(root, "Benign", "a.csv", [_row(1.0), _row(1.0)])
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    unrelated = scratch / "keep-this.txt"
    unrelated.write_text("unrelated user data")

    report = duplicate_audit.audit_dataset(
        root,
        scratch,
        tmp_path / "reports",
        expected_rows=2,
        chunk_size=1,
        available_scratch_bytes=SIMULATED_AVAILABLE,
        scratch_limit_bytes=4_096,
    )

    assert report["status"] == "INCOMPLETE"
    assert report["total_rows_scanned"] is None
    assert report["exact_duplicate_occurrences"] is None
    assert "full" in report["failure_reason"].lower() or "disk" in report["failure_reason"].lower()
    assert unrelated.read_text() == "unrelated user data"
    assert list(scratch.iterdir()) == [unrelated]
    saved = json.loads(Path(report["report_paths"]["json"]).read_text())
    assert saved["status"] == "INCOMPLETE"


MINIMUM_FREE_FOR_TEST = 10 * GIB - 1


def test_blank_numeric_field_uses_existing_csv_missing_value_canonicalization():
    blank = ["", *(["1.0"] * (len(CIC_IOT2023_EXPECTED_COLUMNS) - 1))]
    textual_nan = ["NaN", *(["1.0"] * (len(CIC_IOT2023_EXPECTED_COLUMNS) - 1))]

    assert duplicate_audit._canonical_payload(blank) == duplicate_audit._canonical_payload(textual_nan)


def test_short_csv_records_are_padded_with_trailing_missing_values():
    short = ["1.0"] * 33
    complete_with_trailing_blanks = short + [""] * 6

    assert duplicate_audit._canonical_payload(short) == duplicate_audit._canonical_payload(
        complete_with_trailing_blanks
    )
    with pytest.raises(ValueError, match="at most 39"):
        duplicate_audit._canonical_payload(["1.0"] * 40)
