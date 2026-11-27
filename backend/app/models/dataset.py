"""User-supplied local dataset and audit configuration models."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.models.common import StrictModel


class DatasetConfig(StrictModel):
    """All dataset-specific names are user configured and checked against the files."""

    dataset_name: str = "CIC-IDS2017"
    study_label: str | None = None
    source_url: str | None = None
    release_or_version: str | None = None
    retrieval_date: str | None = None
    raw_data_path: Path | None = None
    label_strategy: Literal["binary", "multiclass"] | None = None
    sample_rows_per_folder: int | None = Field(default=None, ge=1)
    sample_random_seed: int = Field(default=42, ge=0)
    data_path: Path
    file_glob: str = "*.csv"
    target_column: str = Field(min_length=1)
    expected_columns: list[str] = Field(default_factory=list)
    strict_expected_columns: bool = False
    expected_labels: list[str] = Field(default_factory=list)
    label_mapping: dict[str, str] = Field(default_factory=dict)
    excluded_columns: dict[str, str] = Field(default_factory=dict)
    group_columns: list[str] = Field(default_factory=list)
    group_identical_feature_rows: bool = False
    time_column: str | None = None
    split_strategy: Literal["auto", "group", "time", "stratified_random"] = "auto"
    train_fraction: float = Field(default=0.6, gt=0, lt=1)
    validation_fraction: float = Field(default=0.2, gt=0, lt=1)
    test_fraction: float = Field(default=0.2, gt=0, lt=1)
    random_seed: int = Field(default=42, ge=0)
    output_dir: Path = Path("../outputs/cicids2017-audit")

    @model_validator(mode="after")
    def validate_config(self) -> "DatasetConfig":
        if abs(self.train_fraction + self.validation_fraction + self.test_fraction - 1.0) > 1e-9:
            raise ValueError("train_fraction, validation_fraction, and test_fraction must sum to 1")
        if self.raw_data_path is not None and self.label_strategy is None:
            raise ValueError("raw_data_path requires a folder-derived label_strategy")
        if self.sample_rows_per_folder is not None and self.raw_data_path is None:
            raise ValueError("sample_rows_per_folder requires raw_data_path")
        if self.strict_expected_columns and not self.expected_columns:
            raise ValueError("strict_expected_columns requires a non-empty expected_columns list")
        if len(set(self.group_columns)) != len(self.group_columns):
            raise ValueError("group_columns must not contain duplicates")
        if self.group_columns and self.time_column:
            raise ValueError("Configure group_columns or time_column, not both")
        if self.split_strategy == "group" and not self.group_columns:
            raise ValueError("split_strategy='group' requires configured group_columns")
        if self.split_strategy == "time" and not self.time_column:
            raise ValueError("split_strategy='time' requires a configured time_column")
        if self.target_column in self.excluded_columns:
            raise ValueError("The target column is excluded from features automatically")
        if any(not reason.strip() for reason in self.excluded_columns.values()):
            raise ValueError("Every explicit exclusion must include a non-empty rationale")
        return self
