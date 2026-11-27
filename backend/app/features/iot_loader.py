"""CIC-IoT2023 recursive CSV loader with folder-derived label strategy.

The CIC-IoT2023 dataset is organised as:
  <root>/
    <category_folder>/     # e.g. "Benign", "DDoS-ICMP_Flood", …
      *.csv                # each with identical 39 numeric columns, NO label column

Labels are derived exclusively from the parent folder name and are never read
from the CSV content.  This module handles:

  - Recursive CSV discovery across all 34+ category folders.
  - Validation that every discovered CSV has the same 39 columns.
  - Folder-name normalisation and binary/multiclass label strategies.
  - Optional bounded-memory deterministic sampling for development or testing;
    without a row cap, the full discovered dataset is loaded into memory.
  - Per-folder and overall provenance reporting.

IMPORTANT — dataset-choice notice
----------------------------------
CIC-IoT2023 is the approved dataset choice for Workstream A. Approval does not
independently verify the exact local source, schema, or folder-derived labels.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CIC-IoT2023 column contract
# ---------------------------------------------------------------------------

#: 39-column header observed in the user-provided local CIC-IoT2023 sample.
#: This schema check is not independent verification of dataset provenance.
CIC_IOT2023_EXPECTED_COLUMNS: list[str] = [
    'Header_Length',
    'Protocol Type',
    'Time_To_Live',
    'Rate',
    'fin_flag_number',
    'syn_flag_number',
    'rst_flag_number',
    'psh_flag_number',
    'ack_flag_number',
    'ece_flag_number',
    'cwr_flag_number',
    'ack_count',
    'syn_count',
    'fin_count',
    'rst_count',
    'HTTP',
    'HTTPS',
    'DNS',
    'Telnet',
    'SMTP',
    'SSH',
    'IRC',
    'TCP',
    'UDP',
    'DHCP',
    'ARP',
    'ICMP',
    'IGMP',
    'IPv',
    'LLC',
    'Tot sum',
    'Min',
    'Max',
    'AVG',
    'Std',
    'Tot size',
    'IAT',
    'Number',
    'Variance',
]

#: Folder names that are considered benign (case-insensitive).
BENIGN_FOLDER_TOKENS: frozenset[str] = frozenset({"benign", "normal", "legitimate"})


class CICIoT2023LoaderError(ValueError):
    """Raised when the CIC-IoT2023 data directory structure is invalid."""


# ---------------------------------------------------------------------------
# Folder → label utilities
# ---------------------------------------------------------------------------


def _normalise_folder_name(folder_name: str) -> str:
    """Strip leading/trailing whitespace and collapse internal spaces."""
    return re.sub(r"\s+", " ", folder_name.strip())


def _is_benign_folder(folder_name: str) -> bool:
    normalised = _normalise_folder_name(folder_name).casefold()
    return any(token in normalised for token in BENIGN_FOLDER_TOKENS)


def _multiclass_label(folder_name: str) -> str:
    """Return the attack category name or 'Benign', preserving original casing."""
    normalised = _normalise_folder_name(folder_name)
    if _is_benign_folder(normalised):
        return "Benign"
    return normalised


def _binary_label(folder_name: str) -> str:
    """Map any folder to 'Benign' or 'Attack'."""
    return "Benign" if _is_benign_folder(folder_name) else "Attack"


def _derive_label(folder_name: str, strategy: Literal["binary", "multiclass"]) -> str:
    if strategy == "binary":
        return _binary_label(folder_name)
    return _multiclass_label(folder_name)


# ---------------------------------------------------------------------------
# Lightweight CSV header reader
# ---------------------------------------------------------------------------


def _read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        try:
            return next(csv.reader(stream))
        except StopIteration as exc:
            raise CICIoT2023LoaderError(f"CSV file is empty: {path}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@dataclass
class FolderManifest:
    """Metadata for one category folder."""

    folder_name: str
    folder_path: Path
    label_binary: str
    label_multiclass: str
    csv_files: list[Path] = field(default_factory=list)
    row_count: int = 0
    sha256_by_file: dict[str, str] = field(default_factory=dict)


def discover_folder_manifests(
    root: Path,
    *,
    expected_columns: list[str] | None = None,
    max_files_per_folder: int | None = None,
    compute_checksums: bool = True,
) -> list[FolderManifest]:
    """Recursively discover all category folders and their CSVs under *root*.

    Parameters
    ----------
    root:
        The top-level CIC-IoT2023 directory that contains the 34+ category
        subfolders.
    expected_columns:
        Columns that every CSV must have.  Defaults to
        :data:`CIC_IOT2023_EXPECTED_COLUMNS`.  Pass an empty list to skip
        column validation (not recommended for research).
    max_files_per_folder:
        Cap the number of CSV files loaded per folder.  Useful for fast
        iteration/testing without processing the full 309-file dataset.
    compute_checksums:
        Whether to compute SHA-256 digests.  Disable for speed during unit
        tests that use tiny synthetic files.

    Returns
    -------
    list[FolderManifest]
        One manifest per non-empty category folder, sorted by folder name.

    Raises
    ------
    CICIoT2023LoaderError
        If *root* does not exist, contains no category folders with CSVs, or
        any CSV header mismatches *expected_columns*.
    """
    if not root.exists():
        raise CICIoT2023LoaderError(
            f"CIC-IoT2023 root directory does not exist: {root}. "
            "Place the official dataset files locally and update data_path in the config."
        )
    if not root.is_dir():
        raise CICIoT2023LoaderError(
            f"Expected a directory for CIC-IoT2023 root, got a file: {root}"
        )

    columns_to_check = expected_columns if expected_columns is not None else CIC_IOT2023_EXPECTED_COLUMNS

    manifests: list[FolderManifest] = []
    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        csv_files = sorted(f for f in subdir.glob("**/*.csv") if f.is_file())
        if not csv_files:
            continue
        if max_files_per_folder is not None:
            csv_files = csv_files[:max_files_per_folder]

        folder_name = subdir.name
        manifest = FolderManifest(
            folder_name=folder_name,
            folder_path=subdir,
            label_binary=_binary_label(folder_name),
            label_multiclass=_multiclass_label(folder_name),
        )

        for csv_path in csv_files:
            # Validate column schema
            if columns_to_check:
                observed = _read_csv_header(csv_path)
                # Normalise observed column names (strip BOM/whitespace)
                observed_normalised = [c.strip() for c in observed]
                if observed_normalised != columns_to_check:
                    missing = [c for c in columns_to_check if c not in observed_normalised]
                    extra = [c for c in observed_normalised if c not in columns_to_check]
                    raise CICIoT2023LoaderError(
                        f"CSV column mismatch in {csv_path}. "
                        f"Missing: {missing}. Extra: {extra}. "
                        "All CIC-IoT2023 CSVs must share the same 39-column schema."
                    )
            manifest.csv_files.append(csv_path)
            if compute_checksums:
                manifest.sha256_by_file[str(csv_path)] = _sha256_file(csv_path)

        manifests.append(manifest)

    if not manifests:
        raise CICIoT2023LoaderError(
            f"No category folders with CSV files found under {root}. "
            "Verify that the CIC-IoT2023 directory is correctly structured."
        )
    return manifests


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_manifest_frames(
    manifests: list[FolderManifest],
    label_strategy: Literal["binary", "multiclass"],
    *,
    label_column: str = "label",
    max_rows_per_folder: int | None = None,
    random_seed: int = 42,
) -> tuple[pd.DataFrame, pd.Series]:
    """Load folder CSVs, optionally taking a reproducible bounded-memory sample.

    When ``max_rows_per_folder`` is set, CSVs are read in fixed-size chunks and
    uniform random priorities retain at most the requested number of rows per
    category folder. Memory use is bounded by one chunk plus the per-folder sample.
    Without a cap, all data are loaded into memory.
    """
    if max_rows_per_folder is not None and max_rows_per_folder < 1:
        raise ValueError("max_rows_per_folder must be positive when provided")

    rng = np.random.default_rng(random_seed)
    frames: list[pd.DataFrame] = []
    all_labels: list[str] = []

    for manifest in manifests:
        label_value = _derive_label(manifest.folder_name, label_strategy)
        folder_frames: list[pd.DataFrame] = []
        if max_rows_per_folder is None:
            for csv_path in manifest.csv_files:
                df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False)
                df.columns = [c.strip() for c in df.columns]
                folder_frames.append(df)
            if folder_frames:
                folder_df = pd.concat(folder_frames, ignore_index=True, sort=False)
            else:
                continue
        else:
            folder_df = pd.DataFrame()
            sample_priorities = np.empty(0, dtype=float)
            sample_positions = np.empty(0, dtype=np.int64)
            rows_seen = 0
            for csv_path in manifest.csv_files:
                for chunk in pd.read_csv(
                    csv_path,
                    encoding="utf-8-sig",
                    low_memory=False,
                    chunksize=100_000,
                ):
                    chunk.columns = [c.strip() for c in chunk.columns]
                    chunk_positions = np.arange(rows_seen, rows_seen + len(chunk), dtype=np.int64)
                    rows_seen += len(chunk)
                    candidate = pd.concat([folder_df, chunk], ignore_index=True, sort=False)
                    candidate_priorities = np.concatenate(
                        [sample_priorities, rng.random(len(chunk))]
                    )
                    candidate_positions = np.concatenate([sample_positions, chunk_positions])
                    keep_count = min(max_rows_per_folder, len(candidate))
                    keep = np.argpartition(candidate_priorities, keep_count - 1)[:keep_count]
                    keep = keep[np.argsort(candidate_positions[keep])]
                    folder_df = candidate.iloc[keep].reset_index(drop=True)
                    sample_priorities = candidate_priorities[keep]
                    sample_positions = candidate_positions[keep]
            if rows_seen == 0:
                continue

        folder_labels = [label_value] * len(folder_df)
        frames.append(folder_df)
        all_labels.extend(folder_labels)
        manifest.row_count = len(folder_df)

    if not frames:
        raise CICIoT2023LoaderError("No rows were loaded from any category folder.")

    full_frame = pd.concat(frames, ignore_index=True, sort=False)
    labels = pd.Series(all_labels, name=label_column, dtype="object")
    return full_frame, labels


# ---------------------------------------------------------------------------
# Provenance audit report
# ---------------------------------------------------------------------------


def build_provenance_report(
    root: Path,
    manifests: list[FolderManifest],
    label_strategy: Literal["binary", "multiclass"],
    total_rows: int,
    total_columns: int,
    missing_by_column: dict[str, int],
    infinity_by_column: dict[str, int],
    constant_columns: list[str],
    duplicate_rows: int,
    class_counts: dict[str, int],
    expected_columns: list[str],
    *,
    dataset_note: str = "",
) -> dict[str, Any]:
    """Build a machine-readable audit report for the loaded CIC-IoT2023 data."""
    folder_summary = [
        {
            "folder_name": m.folder_name,
            "label_binary": m.label_binary,
            "label_multiclass": m.label_multiclass,
            "csv_file_count": len(m.csv_files),
            "row_count": m.row_count,
            "sha256_by_file": m.sha256_by_file,
        }
        for m in manifests
    ]
    return {
        "dataset_name": "CIC-IoT2023",
        "dataset_note": dataset_note or (
            "CIC-IoT2023 is approved as the Workstream A dataset. This approval does not "
            "independently verify local source provenance, schema, or labels. Labels are "
            "derived from parent folder names, not from a CSV column."
        ),
        "source_url": "https://www.unb.ca/cic/datasets/iotdataset-2023.html",
        "root_path": str(root),
        "label_strategy": label_strategy,
        "label_column_synthetic": True,
        "label_derivation": "Parent folder name; Benign folders identified by token match.",
        "benign_folder_tokens": sorted(BENIGN_FOLDER_TOKENS),
        "dataset_identity_verified": False,
        "source_note": (
            "Local CSV contents were schema-audited; provenance is user-declared, "
            "not independently verified."
        ),
        "folder_manifests": folder_summary,
        "total_category_folders": len(manifests),
        "total_csv_files": sum(len(m.csv_files) for m in manifests),
        "total_rows": total_rows,
        "total_columns": total_columns,
        "expected_columns": expected_columns,
        "class_counts": class_counts,
        "missing_by_column": missing_by_column,
        "infinity_by_column_before_replacement": infinity_by_column,
        "constant_columns": constant_columns,
        "duplicate_rows_not_removed": duplicate_rows,
    }


# ---------------------------------------------------------------------------
# High-level convenience loader
# ---------------------------------------------------------------------------


@dataclass
class CICIoT2023Foundation:
    """Loaded, audited CIC-IoT2023 data ready for the pipeline.

    ``features`` and ``labels`` are aligned :class:`~pandas.DataFrame` /
    :class:`~pandas.Series` objects.  They have *not* been split yet;
    pass them to :func:`~app.features.data.load_and_audit` via a configured
    :class:`~app.models.dataset.DatasetConfig` after materialising to a CSV.
    """

    root: Path
    label_strategy: Literal["binary", "multiclass"]
    features: pd.DataFrame
    labels: pd.Series
    manifests: list[FolderManifest]
    provenance: dict[str, Any]


def load_cic_iot2023(
    root: Path,
    label_strategy: Literal["binary", "multiclass"] = "multiclass",
    *,
    expected_columns: list[str] | None = None,
    max_files_per_folder: int | None = None,
    max_rows_per_folder: int | None = None,
    random_seed: int = 42,
    compute_checksums: bool = True,
) -> CICIoT2023Foundation:
    """Discover, validate, and load the CIC-IoT2023 dataset.

    This is the single entry-point for the CIC-IoT2023 pipeline.  After
    calling this function you should write the combined frame + labels to a
    CSV and pass it to the standard :func:`~app.features.data.load_and_audit`
    pipeline so that all splitting, preprocessing, and audit logic remains
    shared with the CIC-IDS2017 path.

    Parameters
    ----------
    root:
        Top-level CIC-IoT2023 directory (contains the 34 category folders).
    label_strategy:
        ``'binary'`` for 2-class (Benign / Attack) or ``'multiclass'`` for
        one class per attack-category folder.
    expected_columns:
        Override the 39-column schema check.  ``None`` uses the canonical
        list; ``[]`` skips validation entirely.
    max_files_per_folder:
        Development/test: load at most this many CSVs per folder.
    max_rows_per_folder:
        Development/test: sample at most this many rows per folder.
    random_seed:
        Seed for reproducible row sampling.
    compute_checksums:
        Whether to compute SHA-256 file digests (slow for large datasets).
    """
    manifests = discover_folder_manifests(
        root,
        expected_columns=expected_columns,
        max_files_per_folder=max_files_per_folder,
        compute_checksums=compute_checksums,
    )
    features, labels = load_manifest_frames(
        manifests,
        label_strategy=label_strategy,
        max_rows_per_folder=max_rows_per_folder,
        random_seed=random_seed,
    )

    # Audit quality metrics
    numeric_cols = features.select_dtypes(include=[np.number]).columns
    infinity_by_column: dict[str, int] = {}
    for col in numeric_cols:
        count = int(np.isinf(features[col].to_numpy()).sum())
        if count:
            infinity_by_column[col] = count
            features[col] = features[col].replace([np.inf, -np.inf], np.nan)

    missing_by_column = {col: int(features[col].isna().sum()) for col in features.columns}
    constant_columns = [
        col for col in features.columns if features[col].nunique(dropna=False) <= 1
    ]
    duplicate_rows = int(features.duplicated(keep="first").sum())
    class_counts = labels.value_counts(dropna=False).sort_index().to_dict()
    class_counts = {str(k): int(v) for k, v in class_counts.items()}

    effective_expected = (
        expected_columns if expected_columns is not None else CIC_IOT2023_EXPECTED_COLUMNS
    )
    provenance = build_provenance_report(
        root=root,
        manifests=manifests,
        label_strategy=label_strategy,
        total_rows=len(features),
        total_columns=len(features.columns),
        missing_by_column=missing_by_column,
        infinity_by_column=infinity_by_column,
        constant_columns=constant_columns,
        duplicate_rows=duplicate_rows,
        class_counts=class_counts,
        expected_columns=effective_expected,
    )
    provenance["sampling"] = {
        "max_rows_per_folder": max_rows_per_folder,
        "random_seed": random_seed if max_rows_per_folder is not None else None,
        "method": "chunked random-priority sample" if max_rows_per_folder is not None else "full load",
    }
    return CICIoT2023Foundation(
        root=root,
        label_strategy=label_strategy,
        features=features,
        labels=labels,
        manifests=manifests,
        provenance=provenance,
    )


def write_cic_iot2023_audit(
    foundation: CICIoT2023Foundation, output_dir: Path
) -> dict[str, str]:
    """Write provenance JSON and a summary Markdown to *output_dir*."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "cic-iot2023-audit.json"
    md_path = output_dir / "cic-iot2023-audit.md"

    json_path.write_text(
        json.dumps(foundation.provenance, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    p = foundation.provenance
    lines = [
        "# CIC-IoT2023 Dataset Audit",
        "",
        "> [!IMPORTANT]",
        "> CIC-IoT2023 is the approved Workstream A dataset; approval does not verify local source provenance, schema, or labels.",
        "> Labels are derived from parent folder names — there is no label column in the CSVs.",
        "",
        f"- **Root path:** `{p['root_path']}`",
        f"- **Label strategy:** `{p['label_strategy']}`",
        f"- **Category folders:** {p['total_category_folders']}",
        f"- **Total CSV files:** {p['total_csv_files']}",
        f"- **Total rows:** {p['total_rows']}",
        f"- **Total columns:** {p['total_columns']}",
        f"- **Sampling:** `{json.dumps(p.get('sampling', {}), sort_keys=True)}`",
        f"- **Duplicate rows (not removed):** {p['duplicate_rows_not_removed']}",
        f"- **Constant columns:** {', '.join(p['constant_columns']) or 'none'}",
        "",
        "## Class distribution",
        "",
        "```json",
        json.dumps(p["class_counts"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Folder → label mapping",
        "",
        "| Folder | Binary label | Multiclass label | CSV files | Rows |",
        "|---|---|---|---|---|",
    ]
    for fm in p["folder_manifests"]:
        lines.append(
            f"| `{fm['folder_name']}` | {fm['label_binary']} | "
            f"{fm['label_multiclass']} | {fm['csv_file_count']} | {fm['row_count']} |"
        )
    lines.extend(
        [
            "",
            "## Missing values by column (after infinity replacement)",
            "",
            "```json",
            json.dumps(p["missing_by_column"], indent=2, ensure_ascii=False),
            "```",
            "",
            "> Dataset identity is user-declared and not independently verified by this audit.",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
