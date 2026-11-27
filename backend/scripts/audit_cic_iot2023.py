"""Stream-audit a local CIC-IoT2023 CSV directory without copying the data."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import time
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from app.features.iot_loader import CIC_IOT2023_EXPECTED_COLUMNS, _derive_label


def audit_dataset(root: Path, output_dir: Path, chunk_size: int = 100_000) -> dict[str, Path]:
    """Audit every CSV header and stream data quality counters to JSON and Markdown."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset root is not a directory: {root}")

    output_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in root.rglob("*.csv") if path.is_file())
    folders = sorted(path for path in root.iterdir() if path.is_dir())
    header_mismatches = []
    file_inventory = []
    for path in files:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            try:
                header = next(csv.reader(stream))
            except StopIteration:
                header = []
        header = [value.strip() for value in header]
        if header != CIC_IOT2023_EXPECTED_COLUMNS:
            header_mismatches.append(
                {"file": str(path.relative_to(root)), "observed_columns": header}
            )
        file_inventory.append(
            {
                "file": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "folder": path.relative_to(root).parts[0],
            }
        )

    rows_by_folder = Counter()
    multiclass_counts = Counter()
    binary_counts = Counter()
    missing_counts = Counter()
    infinity_counts = Counter()
    parse_error_counts = Counter()
    duplicate_rows_within_chunks = 0
    zero_row_files = []
    scan_errors = []
    started = time.monotonic()
    for file_index, path in enumerate(files, 1):
        folder = path.relative_to(root).parts[0]
        multiclass = _derive_label(folder, "multiclass")
        binary = _derive_label(folder, "binary")
        try:
            file_rows = 0
            for chunk in pd.read_csv(
                path,
                chunksize=chunk_size,
                low_memory=False,
                encoding="utf-8-sig",
            ):
                chunk.columns = [str(column).strip() for column in chunk.columns]
                file_rows += len(chunk)
                duplicate_rows_within_chunks += int(chunk.duplicated().sum())
                for column in chunk.columns:
                    series = chunk[column]
                    missing_counts[column] += int(series.isna().sum())
                    numeric = pd.to_numeric(series, errors="coerce")
                    parse_error_counts[column] += int(
                        (series.notna() & numeric.isna()).sum()
                    )
                    infinity_counts[column] += int(
                        np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).sum()
                    )
            rows_by_folder[folder] += file_rows
            multiclass_counts[multiclass] += file_rows
            binary_counts[binary] += file_rows
            if file_rows == 0:
                zero_row_files.append(str(path.relative_to(root)))
        except Exception as exc:  # retain scan errors in the report instead of hiding them
            scan_errors.append(
                {
                    "file": str(path.relative_to(root)),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        if file_index % 25 == 0:
            print(f"Scanned {file_index}/{len(files)} CSV files", flush=True)

    report = {
        "report_title": "CIC-IoT2023 local CSV dataset audit",
        "audit_date": date.today().isoformat(),
        "dataset_identity_verified": False,
        "dataset_choice_approved": False,
        "root_path": str(root),
        "audit_method": {
            "reader": "pandas.read_csv with bounded chunks",
            "chunk_size_rows": chunk_size,
            "schema_validation": (
                "Exact ordered comparison with the user-observed 39-column header "
                "in backend/app/features/iot_loader.py"
            ),
            "duplicate_check": (
                f"Within each individual {chunk_size:,}-row chunk only; reported count is a "
                "lower bound. Duplicates across chunks or files were not checked."
            ),
            "labels": (
                "Derived from immediate parent category folder by the project loader; binary "
                "mapping is Benign versus Attack. Labels were not independently verified "
                "against file-level ground truth."
            ),
            "source_document_note": (
                "The local README_CSV.pdf was present but could not be extracted with available "
                "PDF tools. Official CIC dataset page describes 33 attacks in seven categories; "
                "this supports attack-name correspondence but not file-level label verification."
            ),
        },
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "directory_count": len(folders),
        "csv_file_count": len(files),
        "total_size_bytes": sum(item["size_bytes"] for item in file_inventory),
        "expected_columns": CIC_IOT2023_EXPECTED_COLUMNS,
        "schema_mismatch_count": len(header_mismatches),
        "schema_mismatches": header_mismatches,
        "rows_by_folder": dict(sorted(rows_by_folder.items())),
        "multiclass_counts_folder_derived": dict(sorted(multiclass_counts.items())),
        "binary_counts_folder_derived": dict(sorted(binary_counts.items())),
        "total_rows": int(sum(rows_by_folder.values())),
        "missing_values_by_column": dict(sorted(missing_counts.items())),
        "infinities_by_column": dict(sorted(infinity_counts.items())),
        "non_numeric_parse_errors_by_column": dict(sorted(parse_error_counts.items())),
        "duplicate_rows_within_chunks_lower_bound": int(duplicate_rows_within_chunks),
        "zero_row_files": zero_row_files,
        "scan_errors": scan_errors,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "files": file_inventory,
    }

    json_path = output_dir / "cic_iot2023_audit.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path = output_dir / "cic_iot2023_audit.md"
    lines = [
        "# CIC-IoT2023 local dataset audit",
        "",
        "> CIC-IoT2023 is an optional alternative; team/faculty dataset approval is not "
        "confirmed. Local file content was audited, but origin and label truth were not "
        "independently verified.",
        "",
        f"- Audit date: {report['audit_date']}",
        f"- Dataset root: `{root}`",
        f"- Top-level directories: {len(folders)}",
        f"- CSV files: {len(files)}",
        f"- Total input size: {report['total_size_bytes']:,} bytes",
        f"- Rows scanned: {report['total_rows']:,}",
        f"- Schema mismatches: {len(header_mismatches)}",
        f"- Scan errors: {len(scan_errors)}",
        f"- Duplicate rows within chunks (lower bound): {duplicate_rows_within_chunks:,}",
        "",
        "## Folder-derived class distribution (multiclass)",
        "",
        "| Folder label | Rows |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {label} | {count:,} |" for label, count in sorted(multiclass_counts.items())
    )
    lines.extend(
        [
            "",
            "## Data quality counts",
            "",
            "| Column | Missing | Infinite | Non-numeric parse errors |",
            "|---|---:|---:|---:|",
        ]
    )
    for column in CIC_IOT2023_EXPECTED_COLUMNS:
        lines.append(
            f"| {column} | {missing_counts[column]:,} | "
            f"{infinity_counts[column]:,} | {parse_error_counts[column]:,} |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Duplicate detection is within each read chunk only; cross-chunk and cross-file "
            "duplicates are not counted.",
            "- Folder labels are derived from names and not checked against independent row labels.",
            "- The official dataset page describes 33 attacks in seven categories; the local "
            "34 folders represent benign plus individual attack folders. This is not evidence "
            "of faculty approval or dataset provenance.",
            "- Per-file relative paths and byte sizes are recorded in the companion JSON report.",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="CIC-IoT2023 CSV root")
    parser.add_argument("--output-dir", type=Path, required=True, help="Audit report directory")
    parser.add_argument("--chunk-size", type=int, default=100_000)
    args = parser.parse_args()
    outputs = audit_dataset(args.root, args.output_dir, args.chunk_size)
    print(json.dumps({name: str(path) for name, path in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()
