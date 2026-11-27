"""Tests for the graph-generation script (synthetic-only; no research results).

These tests verify that the graph module produces files from an experiment
result JSON without crashing, and that required disclaimer text is present.
They do not assert exact pixel values or scientific claims.
"""

from __future__ import annotations

import json

import pytest

# ---------------------------------------------------------------------------
# Minimal synthetic experiment result builder
# ---------------------------------------------------------------------------


def _make_classification_metrics(labels: list[str]) -> dict:
    n = len(labels)
    return {
        "accuracy": 0.85,
        "macro_precision": 0.84,
        "macro_recall": 0.83,
        "macro_f1": 0.84,
        "weighted_precision": 0.85,
        "weighted_recall": 0.85,
        "weighted_f1": 0.85,
        "confusion_matrix": [[10 if i == j else 1 for j in range(n)] for i in range(n)],
        "label_order": labels,
        "class_support": {label: 11 for label in labels},
        "sample_count": 11 * n,
    }


def _make_run(algorithm: str, seed: int | None, labels: list[str]) -> dict:
    return {
        "algorithm": algorithm,
        "seed": seed,
        "selected_features": ["f1", "f2"],
        "selected_feature_count": 2,
        "eligible_feature_count": 5,
        "reduction_percent": 60.0,
        "validation_macro_f1": 0.80,
        "validation_fitness": 0.20,
        "unique_model_evaluation_count": 10,
        "callback_request_count": 12,
        "selector_time_seconds": 1.5,
        "model_evaluation_time_seconds": 2.0,
        "total_optimizer_time_seconds": 3.5,
        "final_test_metrics": _make_classification_metrics(labels),
        "final_test_fit_time_seconds": 0.5,
        "final_test_prediction_time_seconds": 0.1,
        "config": {},
        "selector_artifact": None,
        "validation_artifact_id": None,
        "final_test_artifact_id": "test-id-00",
    }


def _make_experiment_result(dataset_name: str = "CIC-IDS2017") -> dict:
    labels = ["Benign", "Attack"]
    runs = [
        _make_run("full_feature_baseline", None, labels),
        _make_run("ga", 42, labels),
        _make_run("ga", 43, labels),
        _make_run("binary_pso", 42, labels),
        _make_run("aco", 42, labels),
    ]
    return {
        "metadata": {"experiment_id": "test-exp", "seed": 42,
                     "created_at": "2026-01-01T00:00:00Z"},
        "study_label": f"{dataset_name} classification",
        "dataset_name": dataset_name,
        "dataset_identity_verified": False,
        "dataset_provenance": {},
        "split_metadata": {"actual_strategy": "stratified_random_fallback"},
        "eligible_features": ["f1", "f2", "f3", "f4", "f5"],
        "random_forest_config": {},
        "selector_seeds": [42, 43],
        "runs": runs,
        "aggregate_metrics": {},
        "summary_json_path": "",
        "summary_csv_path": "",
        "software_versions": {},
        "execution_environment": {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


pytest.importorskip("matplotlib", reason="matplotlib is required for graph tests")


def test_generate_graphs_creates_all_expected_files(tmp_path):
    from app.features.graphs import generate_graphs

    result = _make_experiment_result()
    result_path = tmp_path / "experiment.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    output_dir = tmp_path / "graphs"

    manifest = generate_graphs(result_path, output_dir)

    assert (output_dir / "macro_f1_comparison.png").exists()
    assert (output_dir / "accuracy_comparison.png").exists()
    assert (output_dir / "feature_count.png").exists()
    assert (output_dir / "execution_time.png").exists()
    assert (output_dir / "test_macro_f1_mean_ci.png").exists()
    assert (output_dir / "test_accuracy_mean_ci.png").exists()
    cm_files = list((output_dir / "confusion_matrices").glob("*.png"))
    assert len(cm_files) == len(result["runs"])
    assert (output_dir / "graphs_manifest.json").exists()
    assert manifest["dataset_name"] == "CIC-IDS2017"


def test_manifest_contains_disclaimer(tmp_path):
    from app.features.graphs import DISCLAIMER, generate_graphs

    result = _make_experiment_result("CIC-IoT2023")
    result_path = tmp_path / "exp.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    manifest = generate_graphs(result_path, tmp_path / "out")

    assert "DISCLAIMER" in DISCLAIMER.upper() or "NOT" in manifest["disclaimer"].upper()
    assert "intrusion-detection" in manifest["disclaimer"] or "NOT" in manifest["disclaimer"]


def test_manifest_includes_unverified_notice(tmp_path):
    from app.features.graphs import generate_graphs

    result = _make_experiment_result()
    result["dataset_identity_verified"] = False
    result_path = tmp_path / "exp2.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    manifest = generate_graphs(result_path, tmp_path / "out2")

    assert manifest["dataset_identity_verified"] is False


def test_generate_graphs_works_for_multiclass(tmp_path):
    from app.features.graphs import generate_graphs

    result = _make_experiment_result()
    # Replace labels with multi-class set
    labels = ["Benign", "DDoS-ICMP_Flood", "Port_Scan"]
    result["runs"] = [_make_run("ga", 42, labels), _make_run("aco", 42, labels)]
    result_path = tmp_path / "mc_exp.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    generate_graphs(result_path, tmp_path / "mc_out")

    cm_files = list((tmp_path / "mc_out" / "confusion_matrices").glob("*.png"))
    assert len(cm_files) == 2
