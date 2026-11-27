"""Shared, leakage-safe Random Forest evaluation for Study A feature subsets."""

from __future__ import annotations

import platform
import time
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline

from app.features.data import DatasetFoundation
from app.features.preprocessing import build_preprocessor
from app.models.common import RunMetadata
from app.models.features import (
    ClassificationMetrics,
    FeatureSubsetEvaluationResult,
    RandomForestConfig,
)


def _software_versions() -> dict[str, str]:
    versions = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
    }
    for distribution in ("fastapi", "pydantic"):
        try:
            versions[distribution] = version(distribution)
        except PackageNotFoundError:
            continue
    return versions


def calculate_classification_metrics(
    y_true: Sequence[str] | pd.Series,
    y_pred: Sequence[str] | np.ndarray,
    *,
    class_order: Sequence[str] | None = None,
) -> ClassificationMetrics:
    """Calculate the declared metric set with explicit macro/weighted conventions."""
    truth = pd.Series(y_true, dtype="string").astype(str)
    predictions = pd.Series(y_pred, dtype="string").astype(str)
    if len(truth) == 0:
        raise ValueError("Cannot calculate classification metrics for an empty partition")
    if len(truth) != len(predictions):
        raise ValueError("y_true and y_pred must contain the same number of rows")
    labels = list(class_order) if class_order is not None else sorted(set(truth) | set(predictions))
    if not labels:
        raise ValueError("At least one class label is required")
    support = truth.value_counts().to_dict()
    support_by_class = {label: int(support.get(label, 0)) for label in labels}
    return ClassificationMetrics(
        accuracy=float(accuracy_score(truth, predictions)),
        macro_precision=float(
            precision_score(truth, predictions, labels=labels, average="macro", zero_division=0)
        ),
        macro_recall=float(
            recall_score(truth, predictions, labels=labels, average="macro", zero_division=0)
        ),
        macro_f1=float(f1_score(truth, predictions, labels=labels, average="macro", zero_division=0)),
        weighted_precision=float(
            precision_score(truth, predictions, labels=labels, average="weighted", zero_division=0)
        ),
        weighted_recall=float(
            recall_score(truth, predictions, labels=labels, average="weighted", zero_division=0)
        ),
        weighted_f1=float(
            f1_score(truth, predictions, labels=labels, average="weighted", zero_division=0)
        ),
        confusion_matrix=confusion_matrix(truth, predictions, labels=labels).astype(int).tolist(),
        label_order=labels,
        class_support=support_by_class,
        sample_count=len(truth),
    )


def build_rf_pipeline(
    training_features: pd.DataFrame,
    selected_features: Sequence[str],
    settings: RandomForestConfig,
) -> Pipeline:
    """Build one pipeline using only training data for preprocessing schema inference."""
    selected = list(selected_features)
    if not selected:
        raise ValueError("Feature subset cannot be empty")
    if len(set(selected)) != len(selected):
        raise ValueError("Feature subset cannot contain duplicate feature names")
    missing = [name for name in selected if name not in training_features.columns]
    if missing:
        raise ValueError(f"Features are not available in training data: {missing}")
    train_subset = training_features.loc[:, selected]
    preprocessor = build_preprocessor(train_subset)
    classifier = RandomForestClassifier(**settings.model_dump())
    return Pipeline([("preprocessor", preprocessor), ("classifier", classifier)])


class RandomForestEvaluator:
    """The common evaluator used for baseline and every candidate feature subset."""

    def __init__(self, settings: RandomForestConfig | None = None) -> None:
        self.settings = settings or RandomForestConfig()

    def evaluate_validation(
        self,
        dataset: DatasetFoundation,
        selected_features: Sequence[str],
        *,
        persist_run: bool = True,
    ) -> FeatureSubsetEvaluationResult:
        """Fit on training only and score validation; safe to use as optimizer fitness."""
        return self._evaluate(
            dataset,
            list(selected_features),
            "validation",
            "feature_subset",
            persist_run=persist_run,
        )

    def evaluate_full_feature_baseline(
        self, dataset: DatasetFoundation
    ) -> FeatureSubsetEvaluationResult:
        """Evaluate every eligible feature through the same validation pipeline."""
        return self._evaluate(
            dataset, dataset.feature_columns, "validation", "full_feature_baseline"
        )

    def evaluate_final_test(
        self,
        dataset: DatasetFoundation,
        selected_features: Sequence[str] | None = None,
        *,
        final_choices_frozen: bool = False,
    ) -> FeatureSubsetEvaluationResult:
        """Fit on training only and release test evaluation after choices are frozen."""
        if not final_choices_frozen:
            raise RuntimeError("Final test evaluation is blocked until all choices are frozen")
        # _evaluate obtains test rows through the gated accessor exactly once. The test
        # partition is never passed into preprocessing fit or model fit.
        features = list(dataset.feature_columns if selected_features is None else selected_features)
        role = "full_feature_baseline" if selected_features is None else "feature_subset"
        return self._evaluate(dataset, features, "test", role)

    def _evaluate(
        self,
        dataset: DatasetFoundation,
        selected_features: Sequence[str],
        partition_name: str,
        evaluation_role: str,
        *,
        persist_run: bool = True,
    ) -> FeatureSubsetEvaluationResult:
        selected = list(selected_features)
        invalid = [name for name in selected if name not in dataset.feature_columns]
        if invalid:
            raise ValueError(f"Feature subset contains ineligible or unknown features: {invalid}")
        train = dataset.splits.train
        pipeline = build_rf_pipeline(train.features, selected, self.settings)

        fit_started = time.perf_counter()
        pipeline.fit(train.features.loc[:, selected], train.labels)
        fit_seconds = time.perf_counter() - fit_started

        evaluation_partition = (
            dataset.splits.validation
            if partition_name == "validation"
            else dataset.splits.get_test_for_final_evaluation(final_choices_frozen=True)
        )
        prediction_started = time.perf_counter()
        predictions = pipeline.predict(evaluation_partition.features.loc[:, selected])
        prediction_seconds = time.perf_counter() - prediction_started
        label_order = sorted(
            set(train.labels.astype(str))
            | set(evaluation_partition.labels.astype(str))
            | set(pd.Series(predictions, dtype="string").astype(str))
        )
        metrics = calculate_classification_metrics(
            evaluation_partition.labels,
            predictions,
            class_order=label_order,
        )
        result = FeatureSubsetEvaluationResult(
            metadata=RunMetadata(
                experiment_id=str(uuid4()),
                seed=dataset.config.random_seed,
                software_versions=_software_versions(),
            ),
            evaluation_partition=partition_name,
            evaluation_role=evaluation_role,
            dataset_name=dataset.config.dataset_name,
            study_label=dataset.config.study_label or f"{dataset.config.dataset_name} classification",
            dataset_identity_verified=dataset.report["dataset_identity_verified"],
            target_column=dataset.config.target_column,
            label_mapping=dataset.config.label_mapping,
            selected_features=selected,
            selected_feature_count=len(selected),
            random_forest_config=self.settings,
            training_class_counts={
                str(name): int(count) for name, count in train.labels.value_counts().items()
            },
            metrics=metrics,
            primary_score=metrics.macro_f1,
            fit_time_seconds=fit_seconds,
            prediction_time_seconds=prediction_seconds,
            split_metadata=dataset.splits.split_details,
            dataset_provenance={
                "input_files": dataset.report["input_files"],
                "source_url_as_configured": dataset.config.source_url,
                "release_or_version_as_configured": dataset.config.release_or_version,
                "retrieval_date_as_configured": dataset.config.retrieval_date,
            },
            software_versions=_software_versions(),
        )
        if persist_run:
            self._save_run(dataset, result)
        return result

    @staticmethod
    def _save_run(
        dataset: DatasetFoundation, result: FeatureSubsetEvaluationResult
    ) -> Path:
        output_dir = dataset.config.output_dir / "rf-evaluations"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{result.metadata.experiment_id}.json"
        temporary_path = output_path.with_suffix(".json.tmp")
        temporary_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        temporary_path.replace(output_path)
        return output_path
