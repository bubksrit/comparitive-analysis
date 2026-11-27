"""Local CSV loading, schema audit, split construction, and train-only prep."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from app.models.dataset import DatasetConfig


class DatasetFoundationError(ValueError):
    """Raised when a local dataset does not satisfy the configured schema/protocol."""


@dataclass(frozen=True)
class DataPartition:
    """One partition. The test partition is deliberately not attached publicly."""

    features: pd.DataFrame
    labels: pd.Series


class DatasetSplits:
    """Training/validation view with an explicit final-evaluation test gate."""

    def __init__(
        self,
        train: DataPartition,
        validation: DataPartition,
        test: DataPartition,
        split_details: dict[str, Any],
    ) -> None:
        self.train = train
        self.validation = validation
        self.__test = test
        self.split_details = split_details

    def get_test_for_final_evaluation(self, *, final_choices_frozen: bool = False) -> DataPartition:
        """Release test data only after the caller declares all choices frozen."""
        if not final_choices_frozen:
            raise RuntimeError(
                "Test partition is sealed; pass final_choices_frozen=True only for final reporting"
            )
        return self.__test


@dataclass
class DatasetFoundation:
    config: DatasetConfig
    feature_columns: list[str]
    excluded_columns: list[dict[str, str]]
    column_audit: list[dict[str, Any]]
    report: dict[str, Any]
    splits: DatasetSplits


def _csv_files(data_path: Path, file_glob: str) -> list[Path]:
    if not data_path.exists():
        raise DatasetFoundationError(
            f"Dataset path does not exist: {data_path}. Place official CSV files locally or update data_path."
        )
    if data_path.is_file():
        if data_path.suffix.casefold() != ".csv":
            raise DatasetFoundationError(f"Expected a CSV file, received: {data_path.suffix}")
        return [data_path]
    files = sorted(path for path in data_path.glob(file_glob) if path.is_file())
    if not files:
        raise DatasetFoundationError(f"No CSV files matched {file_glob!r} under {data_path}")
    return files


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        try:
            return next(csv.reader(stream))
        except StopIteration as exc:
            raise DatasetFoundationError(f"CSV file is empty: {path}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _suggestion_for_column(column: str) -> str | None:
    """Heuristic only: suggestions never remove a column by themselves."""
    name = column.strip().casefold()
    compact = re.sub(r"[^a-z0-9]", "", name)
    if (
        compact in {"id", "flowid", "rowid", "index"}
        or re.search(r"(?:^|[_\s-])id$", name) is not None
        or name.startswith("unnamed:")
    ):
        return "Possible row/flow identifier; exclude only after checking its meaning."
    if any(token in compact for token in ("timestamp", "datetime", "date", "time")):
        return "Possible time/group metadata; verify whether it is needed as a feature."
    if compact in {"day", "captureday", "scenario", "scenarioid", "attackscenario"}:
        return "Possible capture/attack grouping metadata; verify leakage risk and split use."
    if any(
        token in compact
        for token in (
            "sourceip",
            "destinationip",
            "srcip",
            "dstip",
            "ipaddress",
            "srcaddr",
            "dstaddr",
            "sourceaddress",
            "destinationaddress",
        )
    ):
        return "Possible host/address identifier; may encode scenario identity."
    if "port" in compact:
        return "Port field; decide explicitly whether it is a meaningful predictive feature."
    if any(token in compact for token in ("label", "attack", "class")):
        return "Possible target/label leakage field; verify against the configured target."
    return None


def _duplicate_value_columns(frame: pd.DataFrame) -> dict[str, str]:
    duplicates: dict[str, str] = {}
    seen_by_hash: dict[str, list[str]] = {}
    columns = list(frame.columns)
    for right_index in range(len(columns)):
        right = columns[right_index]
        hashes = pd.util.hash_pandas_object(frame[right], index=False).to_numpy().tobytes()
        digest = hashlib.sha256(hashes).hexdigest()
        for left in seen_by_hash.get(digest, []):
            # Hashing narrows candidates; equality protects against a theoretical hash collision.
            if frame[left].equals(frame[right]):
                duplicates[right] = left
                break
        seen_by_hash.setdefault(digest, []).append(right)
    return duplicates


def _class_counts(labels: pd.Series) -> dict[str, int]:
    counts = labels.value_counts(dropna=False).sort_index()
    return {str(label): int(count) for label, count in counts.items()}


def _auto_group_columns(frame: pd.DataFrame) -> list[str]:
    """Conservatively find day-like columns; the chosen name is recorded in the report."""
    matches: list[str] = []
    for column in frame.columns:
        normalized = re.sub(r"[^a-z0-9]", "", column.casefold())
        if normalized not in {"day", "captureday"}:
            continue
        unique_groups = frame[column].nunique(dropna=False)
        if 3 <= unique_groups <= 100 and not frame[column].isna().any():
            matches.append(column)
    return matches


def _auto_time_column(frame: pd.DataFrame) -> str | None:
    """Find a date/timestamp-like field only when its observed values parse consistently."""
    for column in frame.columns:
        normalized = re.sub(r"[^a-z0-9]", "", column.casefold())
        if not any(token in normalized for token in ("timestamp", "datetime")) and normalized not in {
            "time",
            "date",
        }:
            continue
        parsed = pd.to_datetime(frame[column], errors="coerce", utc=True)
        if not parsed.isna().any() and parsed.nunique() >= 3:
            return column
    return None


def _make_partition(frame: pd.DataFrame, labels: pd.Series, indices: np.ndarray) -> DataPartition:
    return DataPartition(
        features=frame.iloc[indices].reset_index(drop=True),
        labels=labels.iloc[indices].reset_index(drop=True),
    )


def _group_overlap_details(
    groups: pd.Series, partition_indices: dict[str, np.ndarray]
) -> dict[str, Any]:
    """Compare observed group identifiers across each pair of split partitions."""
    group_sets = {
        name: set(groups.iloc[indices].astype(str))
        for name, indices in partition_indices.items()
    }
    overlaps: dict[str, list[str]] = {}
    names = list(group_sets)
    for left_index, left_name in enumerate(names):
        for right_name in names[left_index + 1 :]:
            shared_groups = sorted(group_sets[left_name] & group_sets[right_name])
            if shared_groups:
                overlaps[f"{left_name}__{right_name}"] = shared_groups
    return {"group_overlap": bool(overlaps), "group_overlap_by_partition": overlaps}


def _split_rows(
    frame: pd.DataFrame,
    labels: pd.Series,
    config: DatasetConfig,
    group_columns: list[str] | None = None,
    time_column: str | None = None,
    identical_feature_groups: pd.Series | None = None,
) -> tuple[dict[str, np.ndarray], str, list[str], dict[str, Any]]:
    indices = np.arange(len(frame))
    strategy = config.split_strategy
    if strategy == "auto":
        strategy = (
            "group" if group_columns else "time" if time_column
            else "group" if identical_feature_groups is not None
            else "stratified_random"
        )
    if strategy == "stratified_random" and identical_feature_groups is not None:
        raise DatasetFoundationError(
            "Identical-feature grouping is enabled; use split_strategy='auto' or 'group' "
            "to keep duplicate model vectors in one partition"
        )

    if strategy == "group":
        active_group_columns = group_columns or config.group_columns
        missing = [name for name in active_group_columns if name not in frame.columns]
        if missing:
            raise DatasetFoundationError(f"Configured grouping columns are absent: {missing}")
        if active_group_columns:
            group_values = frame[active_group_columns]
            if group_values.isna().any(axis=None):
                raise DatasetFoundationError("Configured grouping columns contain missing values")
            groups = group_values.astype(str).agg("\x1f".join, axis=1)
        elif identical_feature_groups is not None:
            groups = identical_feature_groups.astype(str)
        else:
            raise DatasetFoundationError("Group-aware split requires grouping columns or duplicate groups")
        if identical_feature_groups is not None and active_group_columns:
            # Combine verified metadata groups with feature-row groups so neither
            # relation can be split across partitions. Components are conservative:
            # any shared group or identical model vector remains in one partition.
            pairs = list(zip(groups.astype(str), identical_feature_groups.astype(str), strict=True))
            parent = list(range(len(pairs)))

            def find(item: int) -> int:
                while parent[item] != item:
                    parent[item] = parent[parent[item]]
                    item = parent[item]
                return item

            owners: dict[tuple[str, str], int] = {}
            for item, (metadata_group, feature_group) in enumerate(pairs):
                for key in (("metadata", metadata_group), ("feature", feature_group)):
                    previous = owners.setdefault(key, item)
                    left, right = find(item), find(previous)
                    if left != right:
                        parent[left] = right
            roots = [find(item) for item in range(len(parent))]
            groups = pd.Series(roots, index=frame.index)
        if groups.nunique() < 3:
            raise DatasetFoundationError(
                "Group-aware train/validation/test split requires at least three distinct groups; "
                "explicitly choose stratified_random only if the fallback is acceptable"
            )
        remain_fraction = config.train_fraction + config.validation_fraction
        validation_relative = config.validation_fraction / remain_fraction
        expected_classes = set(labels.astype(str))
        split_candidate = None
        for attempt in range(64):
            first = GroupShuffleSplit(
                n_splits=1,
                test_size=config.test_fraction,
                random_state=config.random_seed + 2 * attempt,
            )
            remaining_pos, test_pos = next(first.split(indices, labels, groups))
            second = GroupShuffleSplit(
                n_splits=1,
                test_size=validation_relative,
                random_state=config.random_seed + 2 * attempt + 1,
            )
            train_relative, validation_relative_indices = next(
                second.split(remaining_pos, labels.iloc[remaining_pos], groups.iloc[remaining_pos])
            )
            train_indices = remaining_pos[train_relative]
            validation_indices = remaining_pos[validation_relative_indices]
            test_indices = indices[test_pos]
            if all(
                set(labels.iloc[partition].astype(str)) == expected_classes
                for partition in (train_indices, validation_indices, test_indices)
            ):
                split_candidate = (train_indices, validation_indices, test_indices)
                break
        if split_candidate is None:
            raise DatasetFoundationError(
                "Could not construct a group-disjoint split with every target class in all "
                "three partitions after 64 deterministic attempts; inspect class/group counts"
            )
        train_indices, validation_indices, test_indices = split_candidate
        details = {
            "strategy": "group_aware",
            "group_columns": active_group_columns,
            "identical_feature_rows_kept_together": identical_feature_groups is not None,
            "group_counts": {
                "train": int(groups.iloc[train_indices].nunique()),
                "validation": int(groups.iloc[validation_indices].nunique()),
                "test": int(groups.iloc[test_indices].nunique()),
            },
            "limitations": "GroupShuffleSplit targets proportions by group count; row proportions may differ.",
        }
        partition_indices = {
            "train": train_indices,
            "validation": validation_indices,
            "test": test_indices,
        }
        details.update(_group_overlap_details(groups, partition_indices))
        return partition_indices, "group_aware", details["group_columns"], details

    if strategy == "time":
        if identical_feature_groups is not None:
            raise DatasetFoundationError(
                "Time-ordered splitting cannot also guarantee identical-feature groups stay together"
            )
        active_time_column = time_column or config.time_column
        if active_time_column not in frame.columns:
            raise DatasetFoundationError(f"Configured time column is absent: {active_time_column}")
        timestamps = pd.to_datetime(frame[active_time_column], errors="coerce", utc=True)
        if timestamps.isna().any():
            raise DatasetFoundationError(
                f"Configured time column {active_time_column!r} contains values that cannot be parsed"
            )
        unique_times = pd.Index(timestamps.unique()).sort_values()
        if len(unique_times) < 3:
            raise DatasetFoundationError("Time-aware split requires at least three distinct timestamps")
        train_end = max(
            1,
            min(int(round(len(unique_times) * config.train_fraction)), len(unique_times) - 2),
        )
        validation_end = max(
            train_end + 1,
            min(
                int(round(len(unique_times) * (config.train_fraction + config.validation_fraction))),
                len(unique_times) - 1,
            ),
        )
        train_cutoff = unique_times[train_end - 1]
        validation_cutoff = unique_times[validation_end - 1]
        train_indices = indices[timestamps <= train_cutoff]
        validation_indices = indices[(timestamps > train_cutoff) & (timestamps <= validation_cutoff)]
        test_indices = indices[timestamps > validation_cutoff]
        if min(len(train_indices), len(validation_indices), len(test_indices)) == 0:
            raise DatasetFoundationError("Time-aware split produced an empty partition")
        partition_indices = {
            "train": train_indices,
            "validation": validation_indices,
            "test": test_indices,
        }
        return (
            partition_indices,
            "time_ordered",
            [active_time_column],
            {
                "time_cutoffs_utc": {
                    "train_through": pd.Timestamp(train_cutoff).isoformat(),
                    "validation_through": pd.Timestamp(validation_cutoff).isoformat(),
                    "test_after": pd.Timestamp(validation_cutoff).isoformat(),
                }
            },
        )

    try:
        train_validation, test_indices = train_test_split(
            indices,
            test_size=config.test_fraction,
            random_state=config.random_seed,
            stratify=labels,
        )
        validation_relative = config.validation_fraction / (
            config.train_fraction + config.validation_fraction
        )
        train_indices, validation_indices = train_test_split(
            train_validation,
            test_size=validation_relative,
            random_state=config.random_seed + 1,
            stratify=labels.iloc[train_validation],
        )
    except ValueError as exc:
        raise DatasetFoundationError(
            "Stratified fallback could not preserve class representation in all partitions. "
            "Review class counts or use verified group/time metadata. "
            f"Underlying split error: {exc}"
        ) from exc
    return (
        {
            "train": train_indices,
            "validation": validation_indices,
            "test": test_indices,
        },
        "stratified_random_fallback",
        [],
        {},
    )


def load_and_audit(config: DatasetConfig) -> DatasetFoundation:
    """Load configured local CSV file(s), audit them, and create leakage-aware splits."""
    files = _csv_files(config.data_path, config.file_glob)
    file_headers = {str(path): _read_header(path) for path in files}
    first_header = next(iter(file_headers.values()))
    schema_mismatches = {
        filename: header
        for filename, header in file_headers.items()
        if header != first_header
    }
    if schema_mismatches:
        raise DatasetFoundationError(
            "Input CSV files do not have identical header names/order; choose compatible files "
            f"or audit them separately. Mismatches: {list(schema_mismatches)}"
        )
    duplicate_header_names = sorted({name for name in first_header if first_header.count(name) > 1})
    if config.target_column not in first_header:
        raise DatasetFoundationError(
            f"Configured target column {config.target_column!r} is absent. "
            f"Observed CSV columns: {first_header}"
        )
    if config.target_column in duplicate_header_names:
        raise DatasetFoundationError("Configured target header occurs more than once in the CSV")

    frames = [pd.read_csv(path, encoding="utf-8-sig", low_memory=False) for path in files]
    frame = pd.concat(frames, ignore_index=True, sort=False)
    observed_columns = list(frame.columns)
    missing_expected = [name for name in config.expected_columns if name not in observed_columns]
    extra_columns = [name for name in observed_columns if name not in config.expected_columns] if config.expected_columns else []
    expected_order_matches = observed_columns == config.expected_columns if config.expected_columns else None
    if config.strict_expected_columns and (missing_expected or extra_columns or not expected_order_matches):
        raise DatasetFoundationError(
            "Strict schema verification failed; "
            f"missing={missing_expected}, extra={extra_columns}, "
            f"column_order_matches={expected_order_matches}"
        )
    if frame[config.target_column].isna().any():
        raise DatasetFoundationError("Configured target contains missing values")

    raw_labels = frame[config.target_column].map(str)
    if config.label_mapping:
        unmapped = sorted(set(raw_labels) - set(config.label_mapping))
        if unmapped:
            raise DatasetFoundationError(f"Observed target labels lack a configured mapping: {unmapped}")
        labels = raw_labels.map(config.label_mapping)
    else:
        labels = raw_labels
    if labels.nunique() < 2:
        raise DatasetFoundationError("Target must contain at least two distinct classes")
    unexpected_labels = sorted(set(labels) - set(config.expected_labels)) if config.expected_labels else []
    missing_labels = sorted(set(config.expected_labels) - set(labels)) if config.expected_labels else []
    if unexpected_labels or missing_labels:
        raise DatasetFoundationError(
            f"Target labels differ from configured expected_labels; "
            f"unexpected={unexpected_labels}, missing={missing_labels}"
        )

    duplicate_rows = int(frame.duplicated(keep="first").sum())
    missing_counts_before_replacement = {
        column: int(frame[column].isna().sum()) for column in frame.columns
    }
    infinity_counts: dict[str, int] = {}
    for column in frame.select_dtypes(include=[np.number]).columns:
        values = frame[column].to_numpy()
        count = int(np.isinf(values).sum())
        if count:
            infinity_counts[column] = count
            frame[column] = frame[column].replace([np.inf, -np.inf], np.nan)

    duplicate_values = _duplicate_value_columns(frame)
    constant_columns = [
        column for column in frame.columns if frame[column].nunique(dropna=False) <= 1
    ]
    if frame.columns.duplicated().any():
        raise DatasetFoundationError("Pandas found duplicate column names after CSV parsing")

    auto_group_columns: list[str] = []
    auto_time_column: str | None = None
    if config.split_strategy == "auto" and not config.group_columns and not config.time_column:
        auto_group_columns = _auto_group_columns(frame)
        if not auto_group_columns:
            auto_time_column = _auto_time_column(frame)
    active_group_columns = config.group_columns or auto_group_columns
    active_time_column = config.time_column or auto_time_column

    excluded: dict[str, str] = {config.target_column: "Supervised target label, never a model input."}
    for column, reason in config.excluded_columns.items():
        if column not in frame.columns:
            raise DatasetFoundationError(f"Explicitly excluded column does not exist: {column}")
        excluded[column] = reason
    for column in active_group_columns:
        if column not in frame.columns:
            raise DatasetFoundationError(f"Configured grouping column is absent: {column}")
        excluded.setdefault(column, "Used only to keep related rows in one split; excluded from model inputs.")
    if active_time_column:
        if active_time_column not in frame.columns:
            raise DatasetFoundationError(f"Configured time column is absent: {active_time_column}")
        excluded.setdefault(active_time_column, "Used only for chronological splitting; excluded from model inputs.")

    feature_columns = [column for column in frame.columns if column not in excluded]
    if not feature_columns:
        raise DatasetFoundationError("No eligible feature columns remain after explicit exclusions")
    exact_feature_duplicate_rows = int(frame[feature_columns].duplicated(keep="first").sum())
    identical_feature_groups = None
    if config.group_identical_feature_rows:
        # Equal vectors always receive equal IDs. A 64-bit collision can only
        # merge distinct vectors into one group, which is conservative for split
        # leakage prevention and does not assert duplicate identity.
        identical_feature_groups = pd.util.hash_pandas_object(
            frame[feature_columns], index=False
        ).astype("uint64").map(lambda value: f"{value:016x}")
    column_audit: list[dict[str, Any]] = []
    for column in frame.columns:
        suggestion = _suggestion_for_column(column)
        column_audit.append(
            {
                "column": column,
                "dtype": str(frame[column].dtype),
                "missing_count_before_infinity_replacement": missing_counts_before_replacement[column],
                "missing_count_after_infinity_replacement": int(frame[column].isna().sum()),
                "positive_or_negative_infinity_count": infinity_counts.get(column, 0),
                "constant": column in constant_columns,
                "duplicate_of": duplicate_values.get(column, ""),
                "excluded": column in excluded,
                "exclusion_reason": excluded.get(column, ""),
                "possible_identifier_or_leakage_note": suggestion or "",
                "eligible_feature": column in feature_columns,
            }
        )

    row_splits, actual_strategy, split_columns, split_strategy_details = _split_rows(
        frame, labels, config, active_group_columns, active_time_column,
        identical_feature_groups,
    )
    partitions = {
        name: _make_partition(frame[feature_columns], labels, indices)
        for name, indices in row_splits.items()
    }
    split_details = {
        "partition_row_index_sha256": {
            name: hashlib.sha256(np.asarray(indices, dtype="<i8").tobytes()).hexdigest()
            for name, indices in row_splits.items()
        },
        "requested_strategy": config.split_strategy,
        "actual_strategy": actual_strategy,
        "group_or_time_columns": split_columns,
        "identical_feature_groups_used_for_split": config.group_identical_feature_rows,
        "requested_fractions": {
            "train": config.train_fraction,
            "validation": config.validation_fraction,
            "test": config.test_fraction,
        },
        "random_seed": config.random_seed,
        "row_counts": {name: len(part.features) for name, part in partitions.items()},
        "class_counts": {name: _class_counts(part.labels) for name, part in partitions.items()},
        "row_fractions": {
            name: len(part.features) / len(frame) for name, part in partitions.items()
        },
        "test_partition_sealed": True,
        "limitations": (
            "Stratified random split may mix related flows/scenarios."
            if actual_strategy == "stratified_random_fallback"
            else "Group split sizes may differ from requested row fractions."
            if actual_strategy == "group_aware"
            else "Chronological split may have class imbalance and is ordered by configured time field."
        ),
    }
    split_details.update(split_strategy_details)
    report = {
        "dataset_name_as_configured": config.dataset_name,
        "study_label_as_configured": config.study_label
        or f"{config.dataset_name} classification",
        "raw_data_path_as_configured": (
            str(config.raw_data_path) if config.raw_data_path is not None else None
        ),
        "folder_label_strategy_as_configured": config.label_strategy,
        "sample_rows_per_folder_as_configured": config.sample_rows_per_folder,
        "sample_random_seed_as_configured": (
            config.sample_random_seed if config.sample_rows_per_folder is not None else None
        ),
        "source_url_as_configured": config.source_url,
        "release_or_version_as_configured": config.release_or_version,
        "retrieval_date_as_configured": config.retrieval_date,
        "dataset_identity_verified": False,
        "source_note": "Local CSV contents were schema-audited; provenance is user-declared, not independently verified.",
        "input_files": [
            {"path": str(path), "sha256": _sha256(path), "rows": len(part)}
            for path, part in zip(files, frames, strict=True)
        ],
        "target_column_as_configured": config.target_column,
        "auto_detected_group_columns": auto_group_columns,
        "auto_detected_time_column": auto_time_column,
        "label_mapping_as_configured": config.label_mapping,
        "observed_source_label_counts": _class_counts(raw_labels),
        "canonical_label_counts": _class_counts(labels),
        "expected_columns_as_configured": config.expected_columns,
        "missing_expected_columns": missing_expected,
        "unlisted_columns": extra_columns,
        "expected_column_order_matches": expected_order_matches,
        "raw_duplicate_header_names": duplicate_header_names,
        "row_count": len(frame),
        "column_count": len(frame.columns),
        "eligible_feature_count": len(feature_columns),
        "eligible_feature_columns": feature_columns,
        "excluded_columns": [{"name": name, "reason": reason} for name, reason in excluded.items()],
        "exclusion_suggestions": [
            {
                "column": item["column"],
                "suggestion": item["possible_identifier_or_leakage_note"],
            }
            for item in column_audit
            if item["possible_identifier_or_leakage_note"]
        ],
        "missing_values_by_column": missing_counts_before_replacement,
        "missing_values_by_column_after_infinity_replacement": {
            col: int(frame[col].isna().sum()) for col in frame.columns
        },
        "infinities_by_column_before_replacement": infinity_counts,
        "duplicate_row_count_not_removed": duplicate_rows,
        "identical_eligible_feature_rows_not_removed": exact_feature_duplicate_rows,
        "group_identical_feature_rows_as_configured": config.group_identical_feature_rows,
        "constant_columns_not_removed": constant_columns,
        "duplicate_value_columns_not_removed": duplicate_values,
        "split": split_details,
        "column_audit_csv": "columns.csv",
    }
    return DatasetFoundation(
        config=config,
        feature_columns=feature_columns,
        excluded_columns=[{"name": name, "reason": reason} for name, reason in excluded.items()],
        column_audit=column_audit,
        report=report,
        splits=DatasetSplits(
            train=partitions["train"],
            validation=partitions["validation"],
            test=partitions["test"],
            split_details=split_details,
        ),
    )


def write_audit_report(foundation: DatasetFoundation, output_dir: Path | None = None) -> dict[str, str]:
    """Write machine-readable JSON/CSV and a concise Markdown audit summary."""
    destination = output_dir or foundation.config.output_dir
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "audit.json"
    csv_path = destination / "columns.csv"
    markdown_path = destination / "audit.md"
    json_path.write_text(json.dumps(foundation.report, indent=2, ensure_ascii=False), encoding="utf-8")
    pd.DataFrame(foundation.column_audit).to_csv(csv_path, index=False)
    report = foundation.report
    lines = [
        f"# Dataset audit: {report['dataset_name_as_configured']}",
        "",
        "> Dataset identity is user-declared and not independently verified by this audit.",
        "",
        f"- Rows: {report['row_count']}",
        f"- Columns: {report['column_count']}",
        f"- Eligible features: {report['eligible_feature_count']}",
        f"- Target configured: `{report['target_column_as_configured']}`",
        f"- Actual split: `{report['split']['actual_strategy']}`",
        f"- Split rows: `{json.dumps(report['split']['row_counts'])}`",
        f"- Duplicate rows (not removed): {report['duplicate_row_count_not_removed']}",
        f"- Constant columns (not removed): {', '.join(report['constant_columns_not_removed']) or 'none'}",
        f"- Duplicate-valued columns (not removed): `{json.dumps(report['duplicate_value_columns_not_removed'])}`",
        "",
        "## Exclusions",
        "",
        "| Column | Rationale |",
        "|---|---|",
    ]
    lines.extend(f"| `{item['name']}` | {item['reason']} |" for item in report["excluded_columns"])
    lines.extend(
        [
            "",
            "## Potential identifier/leakage review (suggestions only)",
            "",
            "| Column | Review note |",
            "|---|---|",
        ]
    )
    lines.extend(
        f"| `{item['column']}` | {item['suggestion']} |"
        for item in report["exclusion_suggestions"]
    )
    lines.extend(
        [
            "",
            "## Class counts",
            "",
            "```json",
            json.dumps(report["canonical_label_counts"], indent=2, ensure_ascii=False),
            "```",
            "",
            "## Split details",
            "",
            "```json",
            json.dumps(report["split"], indent=2, ensure_ascii=False),
            "```",
            "",
            "Test data is sealed by the `DatasetSplits` API until final evaluation is explicitly requested.",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": str(json_path), "csv": str(csv_path), "markdown": str(markdown_path)}
