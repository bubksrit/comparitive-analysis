"""Exact, disk-bounded CIC-IoT2023 duplicate audit.

The on-disk index contains only candidate fingerprints and source CSV record
locations. Full canonical feature values are reread from the immutable sources
and compared before any duplicate or label conflict is counted.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import sqlite3
import struct
import tempfile
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, BinaryIO

from app.features.iot_loader import CIC_IOT2023_EXPECTED_COLUMNS, _derive_label

GIB = 1024**3
AUDIT_SCRATCH_CAP_BYTES = 8 * GIB
MINIMUM_FREE_BYTES = 10 * GIB
RESERVED_FREE_BYTES = 2 * GIB
SQLITE_PAGE_SIZE = 4096
SQLITE_CACHE_KIB = 32 * 1024
DEFAULT_CHUNK_SIZE = 50_000
PANDAS_DEFAULT_NA_VALUES = frozenset({
    "", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan",
    "1.#IND", "1.#QNAN", "<NA>", "N/A", "NA", "NULL", "NaN", "None",
    "n/a", "nan", "null",
})
ESTIMATED_SCRATCH_BYTES_PER_ROW = 128
ESTIMATE_HEADROOM_FACTOR = 1.20


class AuditScratchLimitError(RuntimeError):
    """Raised internally when the audit-owned scratch cap is reached."""


class _BinaryCsvLines:
    """Decode binary physical lines lazily for csv.reader, preserving offsets."""

    def __init__(self, stream: BinaryIO):
        self.stream = stream
        self.first_line = True

    def __iter__(self) -> _BinaryCsvLines:
        return self

    def __next__(self) -> str:
        raw = self.stream.readline()
        if not raw:
            raise StopIteration
        encoding = "utf-8-sig" if self.first_line else "utf-8"
        self.first_line = False
        return raw.decode(encoding)


def _iter_records(stream: BinaryIO) -> Iterator[tuple[int, list[str]]]:
    """Yield logical CSV records and their exact starting byte offsets.

    csv.reader consumes physical lines lazily and handles quoted fields,
    escaped quotes, CRLF, and quoted multiline fields. The binary stream's
    logical tell() position before each reader call is therefore the record's
    byte offset, rather than a pandas chunk/row position.
    """
    reader = csv.reader(_BinaryCsvLines(stream), strict=True)
    while True:
        record_offset = stream.tell()
        try:
            record = next(reader)
        except StopIteration:
            return
        yield record_offset, record


def _canonical_payload(record: list[str]) -> bytes:
    expected_width = len(CIC_IOT2023_EXPECTED_COLUMNS)
    if len(record) > expected_width:
        raise ValueError(f"Expected at most {expected_width} feature values, got {len(record)}")
    # pandas.read_csv (used by the existing project pipeline) pads short CSV
    # records with trailing NaNs. Match that behavior; never discard any field.
    record = record + [""] * (expected_width - len(record))
    values: list[float] = []
    for text in record:
        if text in PANDAS_DEFAULT_NA_VALUES:
            value = float("nan")
        else:
            try:
                value = float(text)
            except ValueError as exc:
                raise ValueError(f"Non-numeric CIC-IoT2023 feature value: {text!r}") from exc
        if value == 0.0:
            value = 0.0
        elif math.isnan(value):
            value = float("nan")
        values.append(value)
    return struct.pack("<39d", *values)


def fingerprint_payload(payload: bytes) -> bytes:
    """Return a compact BLAKE2b candidate fingerprint (never an identity key)."""
    return hashlib.blake2b(payload, digest_size=16).digest()


def _label_for_file(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    if len(relative.parts) < 2:
        raise ValueError(f"CSV is not inside a category folder: {path}")
    # Match the project's loader: the first folder under root supplies label.
    return _derive_label(relative.parts[0], "multiclass")


def _audit_directory_bytes(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except FileNotFoundError:
                continue
    return total


def _monitor_scratch(path: Path, cap_bytes: int) -> int:
    used = _audit_directory_bytes(path)
    free = shutil.disk_usage(path).free
    if used > cap_bytes:
        raise AuditScratchLimitError(
            f"Audit scratch reached {used:,} bytes, above the {cap_bytes:,}-byte cap"
        )
    if free < RESERVED_FREE_BYTES:
        raise AuditScratchLimitError(
            f"Only {free:,} bytes remain on the scratch volume; "
            f"{RESERVED_FREE_BYTES:,} bytes must remain free"
        )
    return used


def estimate_scratch_bytes(row_count: int) -> int:
    """Conservative locator/representative index estimate with headroom."""
    if row_count < 0:
        raise ValueError("row_count cannot be negative")
    return math.ceil(
        row_count * ESTIMATED_SCRATCH_BYTES_PER_ROW * ESTIMATE_HEADROOM_FACTOR
    )


def _new_report_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _report_paths(output_dir: Path, report_id: str) -> dict[str, Path]:
    run_dir = output_dir / f"cic_iot2023_duplicate_audit_{report_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return {
        "json": run_dir / "report.json",
        "markdown": run_dir / "report.md",
    }


def _write_reports(output_dir: Path, report: dict[str, Any]) -> dict[str, Path]:
    paths = _report_paths(output_dir, report["report_id"])
    paths["json"].write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    preflight = report["scratch_preflight"]
    lines = [
        "# CIC-IoT2023 exact global duplicate audit",
        "",
        f"- Run ID: `{report['report_id']}`",
        f"- Status: `{report['status']}`",
        f"- Audit date: {report['audit_date']}",
        f"- Dataset root: `{report['root_path']}`",
        f"- CSV files: {report['csv_file_count']}",
        f"- Expected rows: {report['expected_total_rows']:,}",
        f"- Rows scanned: {report['total_rows_scanned']}",
        f"- Candidate rows fully verified: {report['candidate_rows_verified']}",
        f"- Scratch available at preflight: {preflight['available_bytes']:,} bytes",
        f"- Required free space: {preflight['required_free_bytes']:,} bytes",
        f"- Estimated peak scratch: {preflight['estimated_peak_scratch_bytes']:,} bytes",
        f"- Audit scratch hard cap: {preflight['audit_scratch_cap_bytes']:,} bytes",
        f"- Peak audit-owned scratch: {report['peak_audit_scratch_bytes']:,} bytes",
        "",
        "## Methodology",
        "",
        report["methodology"]["description"],
        "",
        report["methodology"]["record_offsets"],
        "",
        report["methodology"]["collision_safety"],
        "",
        report["methodology"]["duplicate_definitions"],
        "",
        "## Results",
        "",
    ]
    if report["status"] == "COMPLETE":
        lines.extend([
            f"- Exact duplicate occurrences: {report['exact_duplicate_occurrences']:,}",
            f"- Unique complete-row duplicate groups: {report['unique_duplicate_groups']:,}",
            f"- Within-file duplicate occurrences: {report['duplicates_within_same_file_occurrences']:,}",
            f"- Cross-file duplicate occurrences: {report['duplicates_across_different_files_occurrences']:,}",
            f"- Identical feature rows with conflicting labels: {report['conflicting_label_feature_groups']:,} groups / {report['conflicting_label_feature_rows']:,} rows",
            f"- Distinct full rows sharing a fingerprint: {report['fingerprint_collision_groups']:,} fingerprint groups",
            "",
            "### Complete-row duplicate occurrences by class",
            "",
            "| Derived label | Duplicate occurrences |",
            "|---|---:|",
        ])
        lines.extend(
            f"| {label} | {count:,} |"
            for label, count in sorted(report["per_class_duplicate_occurrences"].items())
        )
    else:
        lines.extend([
            "No duplicate totals are reported as final because this run is incomplete.",
            f"- Rows processed before stopping: {report['rows_processed_before_abort']:,}",
            f"- Stop reason: {report['failure_reason'] or report['status']}",
        ])
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    paths["markdown"].write_text("\n".join(lines), encoding="utf-8")
    return paths


def _base_report(
    root: Path,
    files: list[Path],
    expected_rows: int,
    scratch_dir: Path,
    available_bytes: int,
    chunk_size: int,
    report_id: str,
    *,
    status: str = "INCOMPLETE",
    failure_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "report_title": "CIC-IoT2023 exact global duplicate audit",
        "report_id": report_id,
        "audit_date": date.today().isoformat(),
        "status": status,
        "root_path": str(root),
        "scratch_directory": str(scratch_dir),
        "csv_file_count": len(files),
        "expected_total_rows": expected_rows,
        "total_rows_scanned": None,
        "rows_processed_before_abort": 0,
        "candidate_rows_verified": 0,
        "full_feature_comparisons": 0,
        "peak_audit_scratch_bytes": 0,
        "failure_reason": failure_reason,
        "scratch_preflight": {
            "available_bytes": available_bytes,
            "estimated_peak_scratch_bytes": estimate_scratch_bytes(expected_rows),
            "estimated_bytes_per_source_row": ESTIMATED_SCRATCH_BYTES_PER_ROW,
            "estimate_headroom_factor": ESTIMATE_HEADROOM_FACTOR,
            "required_free_bytes": MINIMUM_FREE_BYTES,
            "audit_scratch_cap_bytes": AUDIT_SCRATCH_CAP_BYTES,
            "reserved_free_bytes": RESERVED_FREE_BYTES,
            "safe_to_run": (
                available_bytes >= MINIMUM_FREE_BYTES
                and estimate_scratch_bytes(expected_rows) <= AUDIT_SCRATCH_CAP_BYTES
            ),
        },
        "methodology": {
            "description": (
                "Pass 1 streams CSV records and writes only a 128-bit candidate fingerprint, "
                "file ID, and byte offset to a temporary SQLite index. Pass 2 considers only "
                "fingerprints occurring more than once, rereads those source records, and "
                "compares full canonical feature rows using disk-backed representative locators. "
                "No full feature row is persisted in the scratch database."
            ),
            "record_offsets": (
                "Offsets are captured from a binary stream immediately before csv.reader parses "
                "each logical record. Its lazy physical-line iterator preserves quoted fields, "
                "escaped quotes, CRLF and quoted multiline records. Candidate rereads seek to "
                "the captured byte offset and parse one complete logical CSV record."
            ),
            "canonicalization": (
                "Each CSV record is normalized to 39 numeric float64 values; short records are "
                "padded with trailing NaNs to match pandas.read_csv, and completely blank lines "
                "are skipped as pandas does. Values are encoded little-endian. Signed zero is "
                "normalized to positive zero and NaNs to the platform's canonical "
                "Python NaN encoding; infinities retain sign. Folder labels use the existing "
                "multiclass mapping, including Benign_Final to Benign."
            ),
            "collision_safety": (
                "BLAKE2b-128 is only a candidate fingerprint. Every candidate is reread and its "
                "complete 312-byte canonical row is compared against representative source rows. "
                "A fingerprint collision with different features creates separate representatives "
                "and is not counted as a duplicate."
            ),
            "duplicate_definitions": (
                "Complete-row identity is the canonical 39-feature row plus folder-derived label. "
                "Feature-only representatives separately identify conflicting-label groups. "
                "Duplicate occurrences are records beyond the first for a feature/label group; "
                "within-file excess and additional represented files are reported separately."
            ),
            "chunk_size_rows": chunk_size,
            "fingerprint": "BLAKE2b 128-bit candidate only; full 39-feature verification required",
            "scratch_estimate": (
                "128 bytes per source row plus 20% headroom; this is a planning estimate, "
                "while the 8 GiB audit-owned file cap is enforced during execution."
            ),
        },
        "exact_duplicate_occurrences": None,
        "unique_duplicate_groups": None,
        "duplicates_within_same_file_occurrences": None,
        "duplicates_across_different_files_occurrences": None,
        "duplicate_groups_within_same_file": None,
        "duplicate_groups_across_different_files": None,
        "conflicting_label_feature_groups": None,
        "conflicting_label_feature_rows": None,
        "fingerprint_collision_groups": None,
        "per_class_duplicate_occurrences": None,
        "limitations": [
            "Labels are provenance labels derived from category folders, not independent ground truth.",
            "The audit counts duplicates and never removes or changes source records.",
            "No capture/session independence is inferred from file boundaries.",
            "The 128-byte-per-row scratch estimate is a planning estimate, not a measured database size; the 8 GiB cap and 2 GiB free-space reserve are enforced during the run.",
            "A pathological fingerprint bucket containing many distinct rows can make exact representative comparisons slow; disk use remains capped and the audit stops incomplete if its cap or free-space reserve is threatened.",
        ],
    }


class _SourceRecordReader:
    """Small LRU cache of source files used for exact candidate rereads."""

    def __init__(self, files: list[Path], max_open: int = 16):
        self.files = files
        self.max_open = max_open
        self.streams: OrderedDict[int, BinaryIO] = OrderedDict()

    def read(self, file_id: int, offset: int) -> list[str]:
        stream = self.streams.pop(file_id, None)
        if stream is None:
            stream = self.files[file_id].open("rb")
        self.streams[file_id] = stream
        while len(self.streams) > self.max_open:
            _, oldest = self.streams.popitem(last=False)
            oldest.close()
        stream.seek(offset)
        try:
            return next(csv.reader(_BinaryCsvLines(stream), strict=True))
        except StopIteration as exc:
            raise ValueError(
                f"No CSV record found at byte offset {offset} in {self.files[file_id]}"
            ) from exc

    def close(self) -> None:
        for stream in self.streams.values():
            stream.close()
        self.streams.clear()


def _aggregate(connection: sqlite3.Connection, label_names: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "exact_duplicate_occurrences": 0,
        "unique_duplicate_groups": 0,
        "duplicates_within_same_file_occurrences": 0,
        "duplicates_across_different_files_occurrences": 0,
        "duplicate_groups_within_same_file": 0,
        "duplicate_groups_across_different_files": 0,
        "conflicting_label_feature_groups": 0,
        "conflicting_label_feature_rows": 0,
        "per_class_duplicate_occurrences": {},
    }
    per_class: dict[str, int] = {}
    cursor = connection.execute(
        "SELECT rep_id, label_id, file_id, occurrences "
        "FROM representative_counts ORDER BY rep_id, label_id, file_id"
    )
    current_rep: int | None = None
    rep_total = 0
    labels: set[int] = set()
    current_label: int | None = None
    label_total = 0
    label_file_counts: list[int] = []

    def finish_label() -> None:
        nonlocal label_total, label_file_counts
        if current_label is not None:
            extra = max(0, label_total - 1)
            if extra:
                result["exact_duplicate_occurrences"] += extra
                result["unique_duplicate_groups"] += 1
                same_file_extra = sum(max(0, count - 1) for count in label_file_counts)
                across_extra = max(0, len(label_file_counts) - 1)
                result["duplicates_within_same_file_occurrences"] += same_file_extra
                result["duplicates_across_different_files_occurrences"] += across_extra
                result["duplicate_groups_within_same_file"] += int(same_file_extra > 0)
                result["duplicate_groups_across_different_files"] += int(across_extra > 0)
                name = label_names[current_label]
                per_class[name] = per_class.get(name, 0) + extra
        label_total = 0
        label_file_counts = []

    def finish_rep() -> None:
        nonlocal rep_total, labels
        finish_label()
        if current_rep is not None and len(labels) > 1:
            result["conflicting_label_feature_groups"] += 1
            result["conflicting_label_feature_rows"] += rep_total
        rep_total = 0
        labels = set()

    for rep_id, label_id, _file_id, occurrences in cursor:
        if current_rep != rep_id:
            if current_rep is not None:
                finish_rep()
            current_rep = rep_id
            current_label = None
        if current_label != label_id:
            if current_label is not None:
                finish_label()
            current_label = label_id
            labels.add(label_id)
        label_total += occurrences
        rep_total += occurrences
        label_file_counts.append(occurrences)
    if current_rep is not None:
        finish_rep()
    result["per_class_duplicate_occurrences"] = dict(sorted(per_class.items()))
    result["fingerprint_collision_groups"] = sum(
        1
        for (_fingerprint,) in connection.execute(
            "SELECT fingerprint FROM representatives "
            "GROUP BY fingerprint HAVING COUNT(*) > 1"
        )
    )
    return result


def _inventory(root: Path) -> tuple[list[Path], dict[str, int]]:
    files = sorted(path for path in root.rglob("*.csv") if path.is_file())
    sizes = {str(path.relative_to(root)): path.stat().st_size for path in files}
    return files, sizes


def audit_dataset(
    root: Path,
    scratch_dir: Path,
    output_dir: Path,
    *,
    expected_rows: int,
    expected_inventory: dict[str, int] | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    available_scratch_bytes: int | None = None,
    scratch_limit_bytes: int = AUDIT_SCRATCH_CAP_BYTES,
) -> dict[str, Any]:
    """Run exact global duplicate audit; all scratch files are audit-owned and cleaned."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if not 0 < scratch_limit_bytes <= AUDIT_SCRATCH_CAP_BYTES:
        raise ValueError(f"scratch_limit_bytes must be in (0, {AUDIT_SCRATCH_CAP_BYTES}]")
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset root is not a directory: {root}")
    if not scratch_dir.is_dir():
        raise FileNotFoundError(f"Scratch directory is not a directory: {scratch_dir}")

    files, current_inventory = _inventory(root)
    available = (
        available_scratch_bytes
        if available_scratch_bytes is not None
        else shutil.disk_usage(scratch_dir).free
    )
    report_id = _new_report_id()
    report = _base_report(
        root, files, expected_rows, scratch_dir, available, chunk_size, report_id
    )
    if expected_inventory is not None and current_inventory != expected_inventory:
        report["failure_reason"] = "CSV path/size inventory differs from the approved inventory"
        report["inventory_mismatch"] = {
            "missing_or_changed": sorted(
                key for key, value in expected_inventory.items()
                if current_inventory.get(key) != value
            ),
            "unexpected": sorted(set(current_inventory) - set(expected_inventory)),
        }
        report["limitations"].append("No CSV row contents were read because inventory validation failed.")
        report["report_paths"] = {
            key: str(value) for key, value in _write_reports(output_dir, report).items()
        }
        return report
    estimated_peak = report["scratch_preflight"]["estimated_peak_scratch_bytes"]
    if available < MINIMUM_FREE_BYTES or estimated_peak > scratch_limit_bytes:
        report["failure_reason"] = (
            f"Scratch preflight failed: {available:,} bytes free (minimum "
            f"{MINIMUM_FREE_BYTES:,}); estimated peak {estimated_peak:,} bytes "
            f"(cap {scratch_limit_bytes:,})"
        )
        report["limitations"].append("No CSV row contents were read because scratch preflight failed.")
        report["report_paths"] = {
            key: str(value) for key, value in _write_reports(output_dir, report).items()
        }
        return report

    labels = sorted({_label_for_file(root, path) for path in files})
    label_ids = {name: index for index, name in enumerate(labels)}
    file_labels = [_label_for_file(root, path) for path in files]
    audit_dir: Path | None = None
    connection: sqlite3.Connection | None = None
    source_reader = _SourceRecordReader(files)
    rows_scanned = 0
    candidates_verified = 0
    comparisons = 0
    peak_bytes = 0
    started = time.monotonic()
    try:
        # Validate each CSV header before creating the row index.
        for path in files:
            with path.open("rb") as stream:
                records = _iter_records(stream)
                try:
                    _header_offset, header = next(records)
                except StopIteration as exc:
                    raise ValueError(f"CSV is empty: {path}") from exc
            if [value.strip() for value in header] != CIC_IOT2023_EXPECTED_COLUMNS:
                raise ValueError(f"Input schema mismatch in {path}")

        audit_dir = Path(tempfile.mkdtemp(prefix="ciciot-duplicate-audit-", dir=scratch_dir))
        database_path = audit_dir / "index.sqlite"
        connection = sqlite3.connect(database_path)
        connection.execute(f"PRAGMA page_size={SQLITE_PAGE_SIZE}")
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute(f"PRAGMA cache_size=-{SQLITE_CACHE_KIB}")
        connection.execute("PRAGMA mmap_size=0")
        max_pages = scratch_limit_bytes // SQLITE_PAGE_SIZE
        connection.execute(f"PRAGMA max_page_count={max_pages}")
        connection.execute(
            "CREATE TABLE row_refs ("
            "fingerprint BLOB NOT NULL, file_id INTEGER NOT NULL, byte_offset INTEGER NOT NULL, "
            "PRIMARY KEY(fingerprint, file_id, byte_offset)) WITHOUT ROWID"
        )
        connection.execute(
            "CREATE TABLE representatives ("
            "fingerprint BLOB NOT NULL, rep_id INTEGER NOT NULL, file_id INTEGER NOT NULL, "
            "byte_offset INTEGER NOT NULL, PRIMARY KEY(fingerprint, rep_id)) WITHOUT ROWID"
        )
        connection.execute(
            "CREATE TABLE representative_counts ("
            "rep_id INTEGER NOT NULL, label_id INTEGER NOT NULL, file_id INTEGER NOT NULL, "
            "occurrences INTEGER NOT NULL, PRIMARY KEY(rep_id, label_id, file_id)) WITHOUT ROWID"
        )
        upsert_ref = "INSERT INTO row_refs VALUES (?, ?, ?)"
        batch: list[tuple[bytes, int, int]] = []
        for file_id, path in enumerate(files):
            with path.open("rb") as stream:
                records = _iter_records(stream)
                try:
                    next(records)  # header
                except StopIteration as exc:
                    raise ValueError(f"CSV is empty: {path}") from exc
                for byte_offset, record in records:
                    # Match pandas' default skip_blank_lines=True behavior.
                    if not record:
                        continue
                    payload = _canonical_payload(record)
                    batch.append((fingerprint_payload(payload), file_id, byte_offset))
                    rows_scanned += 1
                    if len(batch) >= chunk_size:
                        connection.executemany(upsert_ref, batch)
                        connection.commit()
                        batch.clear()
                        peak_bytes = max(peak_bytes, _monitor_scratch(audit_dir, scratch_limit_bytes))
                        report["rows_processed_before_abort"] = rows_scanned
            if batch:
                connection.executemany(upsert_ref, batch)
                connection.commit()
                batch.clear()
                peak_bytes = max(peak_bytes, _monitor_scratch(audit_dir, scratch_limit_bytes))
            report["rows_processed_before_abort"] = rows_scanned

        if rows_scanned != expected_rows:
            raise RuntimeError(
                f"Observed {rows_scanned:,} rows; expected {expected_rows:,} from inventory"
            )

        # Candidate fingerprint groups are read in primary-key order. Full rows
        # are reread and compared to representative source locations, never hashes alone.
        next_rep_id = 0
        group_cursor = connection.execute(
            "SELECT fingerprint, COUNT(*) FROM row_refs "
            "GROUP BY fingerprint HAVING COUNT(*) > 1 ORDER BY fingerprint"
        )
        for fingerprint, _candidate_count in group_cursor:
            refs = connection.execute(
                "SELECT file_id, byte_offset FROM row_refs WHERE fingerprint=? "
                "ORDER BY file_id, byte_offset",
                (fingerprint,),
            )
            for file_id, byte_offset in refs:
                current_payload = _canonical_payload(source_reader.read(file_id, byte_offset))
                candidates_verified += 1
                match_rep_id: int | None = None
                representatives = connection.execute(
                    "SELECT rep_id, file_id, byte_offset FROM representatives "
                    "WHERE fingerprint=? ORDER BY rep_id",
                    (fingerprint,),
                )
                for rep_id, rep_file_id, rep_offset in representatives:
                    rep_payload = _canonical_payload(
                        source_reader.read(rep_file_id, rep_offset)
                    )
                    comparisons += 1
                    if current_payload == rep_payload:
                        match_rep_id = rep_id
                        break
                if match_rep_id is None:
                    match_rep_id = next_rep_id
                    next_rep_id += 1
                    connection.execute(
                        "INSERT INTO representatives VALUES (?, ?, ?, ?)",
                        (fingerprint, match_rep_id, file_id, byte_offset),
                    )
                label_id = label_ids[file_labels[file_id]]
                connection.execute(
                    "INSERT INTO representative_counts VALUES (?, ?, ?, 1) "
                    "ON CONFLICT(rep_id, label_id, file_id) DO UPDATE "
                    "SET occurrences=occurrences+1",
                    (match_rep_id, label_id, file_id),
                )
                if candidates_verified % 5_000 == 0:
                    connection.commit()
                    peak_bytes = max(peak_bytes, _monitor_scratch(audit_dir, scratch_limit_bytes))
            connection.commit()
            peak_bytes = max(peak_bytes, _monitor_scratch(audit_dir, scratch_limit_bytes))

        # Fingerprint singleton rows cannot be duplicates: equal canonical rows
        # always produce equal fingerprints. All matching fingerprints were verified.
        metrics = _aggregate(connection, labels)
        report.update(metrics)
        report["status"] = "COMPLETE"
        report["total_rows_scanned"] = rows_scanned
        report["rows_processed_before_abort"] = rows_scanned
        report["candidate_rows_verified"] = candidates_verified
        report["full_feature_comparisons"] = comparisons
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report["source_files"] = [
            {"file": str(path.relative_to(root)), "size_bytes": current_inventory[str(path.relative_to(root))]}
            for path in files
        ]
        report["limitations"].append(
            "Rows with singleton fingerprints need no pairwise comparison; deterministic canonical hashing guarantees equal canonical rows share a fingerprint."
        )
    except Exception as exc:
        report["status"] = "INCOMPLETE"
        report["total_rows_scanned"] = None
        report["rows_processed_before_abort"] = rows_scanned
        report["candidate_rows_verified"] = candidates_verified
        report["full_feature_comparisons"] = comparisons
        report["failure_reason"] = f"{type(exc).__name__}: {exc}"
        # Ensure no partial values are exposed as final metrics.
        for key in (
            "exact_duplicate_occurrences", "unique_duplicate_groups",
            "duplicates_within_same_file_occurrences",
            "duplicates_across_different_files_occurrences",
            "duplicate_groups_within_same_file", "duplicate_groups_across_different_files",
            "conflicting_label_feature_groups", "conflicting_label_feature_rows",
            "fingerprint_collision_groups", "per_class_duplicate_occurrences",
        ):
            report[key] = None
    finally:
        source_reader.close()
        if connection is not None:
            connection.close()
        if audit_dir is not None:
            try:
                shutil.rmtree(audit_dir)
            except OSError as exc:
                report["status"] = "INCOMPLETE"
                report["total_rows_scanned"] = None
                report["failure_reason"] = f"Temporary audit cleanup failed: {exc}"
                for key in (
                    "exact_duplicate_occurrences", "unique_duplicate_groups",
                    "duplicates_within_same_file_occurrences",
                    "duplicates_across_different_files_occurrences",
                    "duplicate_groups_within_same_file", "duplicate_groups_across_different_files",
                    "conflicting_label_feature_groups", "conflicting_label_feature_rows",
                    "fingerprint_collision_groups", "per_class_duplicate_occurrences",
                ):
                    report[key] = None

    report["peak_audit_scratch_bytes"] = peak_bytes
    report["scratch_preflight"]["safe_to_run"] = (
        available >= MINIMUM_FREE_BYTES and estimated_peak <= scratch_limit_bytes
    )
    report["report_paths"] = {
        key: str(value) for key, value in _write_reports(output_dir, report).items()
    }
    return report
