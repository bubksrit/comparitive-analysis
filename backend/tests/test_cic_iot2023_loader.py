"""Tests for the CIC-IoT2023 recursive loader (synthetic fixtures only).

These tests use small synthetic CSV files that mimic the CIC-IoT2023 folder
structure and 39-column schema.  They never load, claim, or fabricate
real CIC-IoT2023 research results.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.features.iot_loader import (
    CIC_IOT2023_EXPECTED_COLUMNS,
    CICIoT2023LoaderError,
    _binary_label,
    _derive_label,
    _is_benign_folder,
    _multiclass_label,
    discover_folder_manifests,
    load_cic_iot2023,
    load_manifest_frames,
    write_cic_iot2023_audit,
)

# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------


def _make_synthetic_folder(root, folder_name: str, n_rows: int = 20, n_files: int = 1):
    """Create <root>/<folder_name>/<i>.csv with the canonical 39-column schema."""
    folder = root / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    for file_index in range(n_files):
        df = pd.DataFrame(
            {col: [float(i + file_index * n_rows) for i in range(n_rows)]
             for col in CIC_IOT2023_EXPECTED_COLUMNS}
        )
        df.to_csv(folder / f"part_{file_index}.csv", index=False)
    return folder


def _make_synthetic_root(tmp_path, folders: dict[str, int] | None = None):
    """Create a minimal CIC-IoT2023 root with synthetic category folders."""
    if folders is None:
        folders = {"Benign": 30, "DDoS-ICMP_Flood": 20, "Port_Scan": 15}
    root = tmp_path / "cic_iot2023_synthetic"
    root.mkdir()
    for folder_name, n_rows in folders.items():
        _make_synthetic_folder(root, folder_name, n_rows=n_rows)
    return root


def test_expected_schema_matches_observed_cic_iot2023_header():
    assert CIC_IOT2023_EXPECTED_COLUMNS == [
        "Header_Length",
        "Protocol Type",
        "Time_To_Live",
        "Rate",
        "fin_flag_number",
        "syn_flag_number",
        "rst_flag_number",
        "psh_flag_number",
        "ack_flag_number",
        "ece_flag_number",
        "cwr_flag_number",
        "ack_count",
        "syn_count",
        "fin_count",
        "rst_count",
        "HTTP",
        "HTTPS",
        "DNS",
        "Telnet",
        "SMTP",
        "SSH",
        "IRC",
        "TCP",
        "UDP",
        "DHCP",
        "ARP",
        "ICMP",
        "IGMP",
        "IPv",
        "LLC",
        "Tot sum",
        "Min",
        "Max",
        "AVG",
        "Std",
        "Tot size",
        "IAT",
        "Number",
        "Variance",
    ]

# ---------------------------------------------------------------------------
# Label utility tests
# ---------------------------------------------------------------------------


def test_is_benign_folder_identifies_benign_tokens():
    assert _is_benign_folder("Benign") is True
    assert _is_benign_folder("BENIGN") is True
    assert _is_benign_folder("benign_traffic") is True
    assert _is_benign_folder("Normal") is True
    assert _is_benign_folder("DDoS-ICMP_Flood") is False
    assert _is_benign_folder("Port_Scan") is False
    assert _is_benign_folder("Mirai-greeth_flood") is False


def test_binary_label_returns_two_classes():
    assert _binary_label("Benign") == "Benign"
    assert _binary_label("Normal") == "Benign"
    assert _binary_label("DDoS-ICMP_Flood") == "Attack"
    assert _binary_label("Recon-OSScan") == "Attack"


def test_multiclass_label_preserves_folder_name():
    assert _multiclass_label("Benign") == "Benign"
    assert _multiclass_label("Normal") == "Benign"
    assert _multiclass_label("DDoS-ICMP_Flood") == "DDoS-ICMP_Flood"
    assert _multiclass_label("Recon-OSScan") == "Recon-OSScan"


def test_derive_label_dispatches_correctly():
    assert _derive_label("Benign", "binary") == "Benign"
    assert _derive_label("DDoS-ICMP_Flood", "binary") == "Attack"
    assert _derive_label("DDoS-ICMP_Flood", "multiclass") == "DDoS-ICMP_Flood"
    assert _derive_label("Benign", "multiclass") == "Benign"


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


def test_discover_finds_all_category_folders(tmp_path):
    root = _make_synthetic_root(tmp_path, {"Benign": 10, "DDoS-ICMP_Flood": 10, "Port_Scan": 10})
    manifests = discover_folder_manifests(root, compute_checksums=False)
    folder_names = {m.folder_name for m in manifests}
    assert folder_names == {"Benign", "DDoS-ICMP_Flood", "Port_Scan"}


def test_discover_raises_for_missing_root(tmp_path):
    with pytest.raises(CICIoT2023LoaderError, match="does not exist"):
        discover_folder_manifests(tmp_path / "nonexistent", compute_checksums=False)


def test_discover_raises_for_no_csv_folders(tmp_path):
    root = tmp_path / "empty_root"
    root.mkdir()
    (root / "just_a_folder_no_csv").mkdir()
    with pytest.raises(CICIoT2023LoaderError, match="No category folders"):
        discover_folder_manifests(root, compute_checksums=False)


def test_discover_validates_column_schema(tmp_path):
    root = tmp_path / "bad_schema"
    root.mkdir()
    bad_folder = root / "Benign"
    bad_folder.mkdir()
    # Write CSV with wrong columns
    pd.DataFrame({"col_a": [1, 2], "col_b": [3, 4]}).to_csv(bad_folder / "bad.csv", index=False)
    with pytest.raises(CICIoT2023LoaderError, match="column mismatch"):
        discover_folder_manifests(root, compute_checksums=False)


def test_discover_skips_column_check_when_expected_empty(tmp_path):
    root = tmp_path / "skip_schema"
    root.mkdir()
    folder = root / "Benign"
    folder.mkdir()
    pd.DataFrame({"col_a": [1, 2]}).to_csv(folder / "data.csv", index=False)
    # Should not raise because validation is skipped
    manifests = discover_folder_manifests(root, expected_columns=[], compute_checksums=False)
    assert len(manifests) == 1


def test_discover_max_files_per_folder_limits_load(tmp_path):
    root = tmp_path / "multi"
    root.mkdir()
    _make_synthetic_folder(root, "Attack_Type", n_files=5, n_rows=10)
    manifests = discover_folder_manifests(
        root, expected_columns=CIC_IOT2023_EXPECTED_COLUMNS,
        max_files_per_folder=2, compute_checksums=False
    )
    assert len(manifests[0].csv_files) == 2


def test_discover_manifest_labels_are_correct(tmp_path):
    root = _make_synthetic_root(tmp_path, {"Benign": 5, "DDoS-ICMP_Flood": 5})
    manifests = discover_folder_manifests(root, compute_checksums=False)
    by_name = {m.folder_name: m for m in manifests}
    assert by_name["Benign"].label_binary == "Benign"
    assert by_name["Benign"].label_multiclass == "Benign"
    assert by_name["DDoS-ICMP_Flood"].label_binary == "Attack"
    assert by_name["DDoS-ICMP_Flood"].label_multiclass == "DDoS-ICMP_Flood"


# ---------------------------------------------------------------------------
# Loading tests
# ---------------------------------------------------------------------------


def test_load_manifest_frames_binary_strategy(tmp_path):
    root = _make_synthetic_root(tmp_path, {"Benign": 10, "DDoS-ICMP_Flood": 10})
    manifests = discover_folder_manifests(root, compute_checksums=False)
    features, labels = load_manifest_frames(manifests, label_strategy="binary")

    assert len(features) == 20
    assert len(labels) == 20
    assert set(labels.unique()) == {"Benign", "Attack"}
    assert "label" not in features.columns  # Label never added to features


def test_load_manifest_frames_multiclass_strategy(tmp_path):
    root = _make_synthetic_root(tmp_path, {"Benign": 10, "DDoS-ICMP_Flood": 8, "Port_Scan": 6})
    manifests = discover_folder_manifests(root, compute_checksums=False)
    features, labels = load_manifest_frames(manifests, label_strategy="multiclass")

    assert len(features) == 24
    assert set(labels.unique()) == {"Benign", "DDoS-ICMP_Flood", "Port_Scan"}


def test_load_manifest_frames_max_rows_per_folder(tmp_path):
    root = _make_synthetic_root(tmp_path, {"Benign": 100, "DDoS-ICMP_Flood": 100})
    manifests = discover_folder_manifests(root, compute_checksums=False)
    features, labels = load_manifest_frames(
        manifests, label_strategy="binary", max_rows_per_folder=20, random_seed=7
    )
    # At most 20 rows per folder × 2 folders
    assert len(features) <= 40
    assert len(features) == len(labels)


def test_sampled_loading_uses_bounded_chunk_reads(tmp_path, monkeypatch):
    root = _make_synthetic_root(tmp_path, {"Benign": 100, "DDoS-ICMP_Flood": 100})
    manifests = discover_folder_manifests(root, compute_checksums=False)
    original_read_csv = pd.read_csv
    chunksizes = []

    def recording_read_csv(*args, **kwargs):
        chunksizes.append(kwargs.get("chunksize"))
        return original_read_csv(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", recording_read_csv)
    features, labels = load_manifest_frames(
        manifests, label_strategy="binary", max_rows_per_folder=20, random_seed=7
    )

    assert len(features) == len(labels) == 40
    assert chunksizes and all(size == 100_000 for size in chunksizes)


def test_load_manifest_frames_reproducible_sampling(tmp_path):
    root = _make_synthetic_root(tmp_path, {"Benign": 100, "DDoS-ICMP_Flood": 100})
    manifests = discover_folder_manifests(root, compute_checksums=False)

    features_a, labels_a = load_manifest_frames(
        manifests, label_strategy="binary", max_rows_per_folder=15, random_seed=42
    )
    # Re-discover to reset row_count state
    manifests2 = discover_folder_manifests(root, compute_checksums=False)
    features_b, labels_b = load_manifest_frames(
        manifests2, label_strategy="binary", max_rows_per_folder=15, random_seed=42
    )
    assert features_a.equals(features_b)
    assert labels_a.tolist() == labels_b.tolist()


def test_load_manifest_frames_label_never_in_features(tmp_path):
    root = _make_synthetic_root(tmp_path, {"Benign": 10, "Attack_A": 10})
    manifests = discover_folder_manifests(root, compute_checksums=False)
    features, labels = load_manifest_frames(manifests, label_strategy="binary")

    for column_name in features.columns:
        assert column_name != "label", "Label column must not appear in the feature frame"


# ---------------------------------------------------------------------------
# High-level loader and audit tests
# ---------------------------------------------------------------------------


def test_load_cic_iot2023_returns_foundation(tmp_path):
    root = _make_synthetic_root(tmp_path)
    foundation = load_cic_iot2023(
        root, label_strategy="multiclass",
        compute_checksums=False, max_rows_per_folder=10
    )

    assert foundation.root == root
    assert foundation.label_strategy == "multiclass"
    assert len(foundation.features) == len(foundation.labels)
    assert len(foundation.features) > 0
    assert foundation.provenance["dataset_name"] == "CIC-IoT2023"
    assert foundation.provenance["label_strategy"] == "multiclass"
    assert foundation.provenance["sampling"] == {
        "max_rows_per_folder": 10,
        "random_seed": 42,
        "method": "chunked random-priority sample",
    }
    assert "CIC-IDS2017" in foundation.provenance["dataset_note"]  # Must warn about original dataset
    assert "has not been confirmed" in foundation.provenance["dataset_note"]


def test_load_cic_iot2023_provenance_has_all_required_keys(tmp_path):
    root = _make_synthetic_root(tmp_path)
    foundation = load_cic_iot2023(root, compute_checksums=False, max_rows_per_folder=5)
    p = foundation.provenance
    for key in (
        "dataset_name", "dataset_note", "source_url", "root_path",
        "label_strategy", "label_column_synthetic", "label_derivation",
        "benign_folder_tokens", "dataset_identity_verified", "source_note",
        "folder_manifests", "total_category_folders", "total_csv_files",
        "total_rows", "total_columns", "class_counts", "sampling",
        "missing_by_column", "constant_columns", "duplicate_rows_not_removed",
    ):
        assert key in p, f"Missing key: {key}"


def test_load_cic_iot2023_dataset_identity_not_verified(tmp_path):
    root = _make_synthetic_root(tmp_path)
    foundation = load_cic_iot2023(root, compute_checksums=False, max_rows_per_folder=5)
    assert foundation.provenance["dataset_identity_verified"] is False


def test_load_cic_iot2023_at_least_two_classes(tmp_path):
    root = _make_synthetic_root(tmp_path, {"Benign": 10, "DDoS-ICMP_Flood": 10})
    foundation = load_cic_iot2023(root, label_strategy="binary", compute_checksums=False)
    assert len(set(foundation.labels)) >= 2


def test_write_cic_iot2023_audit_creates_files(tmp_path):
    root = _make_synthetic_root(tmp_path)
    foundation = load_cic_iot2023(root, compute_checksums=False, max_rows_per_folder=5)
    output_dir = tmp_path / "audit_output"
    outputs = write_cic_iot2023_audit(foundation, output_dir)

    assert "json" in outputs
    assert "markdown" in outputs
    import json
    report = json.loads((output_dir / "cic-iot2023-audit.json").read_text())
    assert report["dataset_name"] == "CIC-IoT2023"
    md = (output_dir / "cic-iot2023-audit.md").read_text()
    assert "CIC-IDS2017" in md  # Disclaimer must be present
    assert "has not been confirmed" in md


def test_loader_raises_when_root_is_missing(tmp_path):
    with pytest.raises(CICIoT2023LoaderError):
        load_cic_iot2023(tmp_path / "nonexistent", compute_checksums=False)


def test_load_cic_iot2023_missing_values_reported(tmp_path):
    """Columns with NaN are reported in provenance; rows are not removed."""
    root = tmp_path / "nan_test"
    root.mkdir()
    folder = root / "Attack"
    folder.mkdir()
    df = pd.DataFrame(
        {col: [1.0, float("nan"), 3.0] for col in CIC_IOT2023_EXPECTED_COLUMNS}
    )
    df.to_csv(folder / "data.csv", index=False)

    foundation = load_cic_iot2023(root, compute_checksums=False)
    # At least one column should have missing values
    assert any(v > 0 for v in foundation.provenance["missing_by_column"].values())
    # Rows are not removed
    assert foundation.provenance["total_rows"] == 3
