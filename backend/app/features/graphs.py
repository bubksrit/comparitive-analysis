"""Generate comparison graphs from a completed Part A experiment JSON result.

Usage
-----
From the backend directory with the virtual environment active:

    python -m app.features.graphs --result <path-to-experiment.json> --output-dir <dir>

The script reads *only* from a previously saved experiment JSON.  It never
re-runs experiments or fabricates numbers.  All graphs are labelled with the
dataset name and a disclaimer that results are from CIC-IDS2017 or
CIC-IoT2023 intrusion-detection classification — not direct measurements of
real server CPU utilisation or load-balancer performance.

Outputs
-------
1. macro_f1_comparison.png  — validation and test macro-F1 per algorithm/seed.
2. accuracy_comparison.png  — validation and test accuracy per algorithm/seed.
3. feature_count.png        — selected feature count per run.
4. execution_time.png       — total optimizer wall-clock time per run.
5. confusion_matrices/      — one PNG per run (test confusion matrix).
6. graphs_manifest.json     — paths and descriptions of all saved files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")  # Headless backend; no display required.

DISCLAIMER = (
    "Results are from {dataset} intrusion-detection classification.\n"
    "These are NOT direct measurements of real server CPU utilisation\n"
    "or network load-balancer performance."
)

ALGORITHM_LABELS: dict[str, str] = {
    "full_feature_baseline": "Full Feature\nBaseline",
    "ga": "GA",
    "binary_pso": "BPSO",
    "aco": "ACO",
}

ALGORITHM_COLORS: dict[str, str] = {
    "full_feature_baseline": "#4472C4",
    "ga": "#ED7D31",
    "binary_pso": "#A9D18E",
    "aco": "#FF0000",
}


def _load_result(json_path: Path) -> dict[str, Any]:
    return json.loads(json_path.read_text(encoding="utf-8"))


def _safe_label(algorithm: str, seed: int | None) -> str:
    base = ALGORITHM_LABELS.get(algorithm, algorithm)
    if seed is None:
        return base
    return f"{base}\n(seed {seed})"


def _footer(dataset_name: str) -> str:
    return DISCLAIMER.format(dataset=dataset_name)


# ---------------------------------------------------------------------------
# Graph 1 — Macro-F1 comparison
# ---------------------------------------------------------------------------


def plot_macro_f1(runs: list[dict[str, Any]], dataset_name: str, output_path: Path) -> None:
    """Bar chart of validation vs test macro-F1 for every run."""
    labels = [_safe_label(r["algorithm"], r.get("seed")) for r in runs]
    val_f1 = [r.get("validation_macro_f1", 0.0) for r in runs]
    test_f1 = [r["final_test_metrics"]["macro_f1"] for r in runs]

    x = np.arange(len(runs))
    width = 0.35
    fig, ax = plt.subplots(figsize=(max(8, len(runs) * 1.4), 5))
    bars_val = ax.bar(x - width / 2, val_f1, width, label="Validation Macro-F1", color="#4472C4", alpha=0.85)
    bars_test = ax.bar(x + width / 2, test_f1, width, label="Test Macro-F1", color="#ED7D31", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Macro-F1")
    ax.set_title(f"Macro-F1 Comparison — {dataset_name}")
    ax.legend()
    ax.bar_label(bars_val, fmt="%.3f", padding=2, fontsize=7)
    ax.bar_label(bars_test, fmt="%.3f", padding=2, fontsize=7)
    fig.text(0.5, -0.08, _footer(dataset_name), ha="center", fontsize=7, style="italic", color="gray",
             transform=ax.transAxes)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Graph 2 — Accuracy comparison
# ---------------------------------------------------------------------------


def plot_accuracy(runs: list[dict[str, Any]], dataset_name: str, output_path: Path) -> None:
    labels = [_safe_label(r["algorithm"], r.get("seed")) for r in runs]
    test_acc = [r["final_test_metrics"]["accuracy"] for r in runs]

    x = np.arange(len(runs))
    fig, ax = plt.subplots(figsize=(max(8, len(runs) * 1.4), 5))
    colors = [ALGORITHM_COLORS.get(r["algorithm"], "#888888") for r in runs]
    bars = ax.bar(x, test_acc, color=colors, alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Accuracy (Test Partition)")
    ax.set_title(f"Test Accuracy Comparison — {dataset_name}")
    ax.bar_label(bars, fmt="%.3f", padding=2, fontsize=7)
    fig.text(0.5, -0.08, _footer(dataset_name), ha="center", fontsize=7, style="italic", color="gray",
             transform=ax.transAxes)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Graph 3 — Selected feature count
# ---------------------------------------------------------------------------


def plot_feature_count(runs: list[dict[str, Any]], dataset_name: str, output_path: Path) -> None:
    labels = [_safe_label(r["algorithm"], r.get("seed")) for r in runs]
    counts = [r.get("selected_feature_count", 0) for r in runs]
    eligible = runs[0].get("eligible_feature_count", 1) if runs else 1

    x = np.arange(len(runs))
    fig, ax = plt.subplots(figsize=(max(8, len(runs) * 1.4), 5))
    colors = [ALGORITHM_COLORS.get(r["algorithm"], "#888888") for r in runs]
    bars = ax.bar(x, counts, color=colors, alpha=0.85)
    ax.axhline(eligible, color="gray", linestyle="--", linewidth=1, label=f"Eligible ({eligible})")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Number of Selected Features")
    ax.set_title(f"Selected Feature Count — {dataset_name}")
    ax.legend()
    ax.bar_label(bars, padding=2, fontsize=7)
    fig.text(0.5, -0.08, _footer(dataset_name), ha="center", fontsize=7, style="italic", color="gray",
             transform=ax.transAxes)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Graph 4 — Execution time
# ---------------------------------------------------------------------------


def plot_execution_time(runs: list[dict[str, Any]], dataset_name: str, output_path: Path) -> None:
    labels = [_safe_label(r["algorithm"], r.get("seed")) for r in runs]
    opt_time = [r.get("selector_time_seconds", 0.0) for r in runs]
    eval_time = [r.get("model_evaluation_time_seconds", 0.0) for r in runs]

    x = np.arange(len(runs))
    width = 0.35
    fig, ax = plt.subplots(figsize=(max(8, len(runs) * 1.4), 5))
    ax.bar(x - width / 2, opt_time, width, label="Optimizer (search) time (s)", color="#4472C4", alpha=0.85)
    ax.bar(x + width / 2, eval_time, width, label="RF evaluation time (s)", color="#ED7D31", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Wall-clock seconds")
    ax.set_title(f"Execution Time Breakdown — {dataset_name}")
    ax.legend()
    fig.text(0.5, -0.08, _footer(dataset_name), ha="center", fontsize=7, style="italic", color="gray",
             transform=ax.transAxes)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_test_metric_mean_ci(
    result: dict[str, Any], metric: str, display_name: str, output_path: Path
) -> None:
    """Plot test-seed means and stored Student-t intervals when estimable."""
    aggregates = result.get("aggregate_metrics", {})
    algorithms = [
        name for name in ("full_feature_baseline", "ga", "binary_pso", "aco")
        if any(run["algorithm"] == name for run in result["runs"])
    ]
    means: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    labels: list[str] = []
    has_interval: list[bool] = []
    for algorithm in algorithms:
        summary = aggregates.get(algorithm, {}).get(metric)
        if summary is None:
            run_values = [
                run["final_test_metrics"][metric.removeprefix("final_test_")]
                for run in result["runs"] if run["algorithm"] == algorithm
            ]
            mean = float(np.mean(run_values))
            low = high = mean
            count = len(run_values)
        else:
            mean = float(summary["mean"])
            low = summary.get("confidence_interval_low")
            high = summary.get("confidence_interval_high")
            count = int(summary["sample_count"])
        has_ci = low is not None and high is not None
        means.append(mean)
        lower.append(max(0.0, mean - float(low)) if has_ci else 0.0)
        upper.append(max(0.0, float(high) - mean) if has_ci else 0.0)
        has_interval.append(has_ci)
        suffix = f"n={count}" if has_ci else f"n={count}, CI n/a"
        labels.append(f"{ALGORITHM_LABELS.get(algorithm, algorithm).replace(chr(10), ' ')}\n({suffix})")

    x = np.arange(len(algorithms))
    colors = [ALGORITHM_COLORS.get(algorithm, "#888888") for algorithm in algorithms]
    fig, ax = plt.subplots(figsize=(max(7, len(algorithms) * 2.1), 5))
    ax.scatter(x, means, color=colors, s=65, zorder=3)
    for index, available in enumerate(has_interval):
        if available:
            ax.errorbar(
                x[index], means[index], yerr=[[lower[index]], [upper[index]]],
                fmt="none", ecolor=colors[index], capsize=5, linewidth=1.5, zorder=2,
            )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel(display_name)
    ax.set_title(f"Mean Test {display_name} with 95% CI where estimable — {result['dataset_name']}")
    ax.grid(axis="y", alpha=0.2)
    fig.text(0.5, -0.08, _footer(result["dataset_name"]), ha="center", fontsize=7,
             style="italic", color="gray", transform=ax.transAxes)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Graph 5 — Confusion matrices
# ---------------------------------------------------------------------------


def plot_confusion_matrices(
    runs: list[dict[str, Any]], dataset_name: str, output_dir: Path
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for idx, run in enumerate(runs):
        metrics = run["final_test_metrics"]
        cm = np.array(metrics["confusion_matrix"])
        labels = metrics["label_order"]
        algo = run["algorithm"]
        seed = run.get("seed")
        title = f"{ALGORITHM_LABELS.get(algo, algo)}" + (f" seed={seed}" if seed is not None else "")

        fig, ax = plt.subplots(figsize=(max(5, len(labels) * 1.2), max(4, len(labels) * 1.1)))
        im = ax.imshow(cm, cmap="Blues")
        ax.set_xticks(range(len(labels)))
        ax.set_yticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        ax.set_yticklabels(labels, fontsize=7)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("True")
        ax.set_title(f"Test Confusion Matrix — {title}\n{dataset_name}", fontsize=9)
        fig.colorbar(im)
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                        color="white" if cm[i, j] > cm.max() * 0.5 else "black", fontsize=6)
        fig.text(0.5, -0.04, _footer(dataset_name), ha="center", fontsize=6, style="italic", color="gray",
                 transform=ax.transAxes)
        slug = f"{algo}_seed{seed}" if seed is not None else f"{algo}_baseline"
        out_path = output_dir / f"cm_{idx:02d}_{slug}.png"
        fig.tight_layout()
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        saved.append(str(out_path))
    return saved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate_graphs(result_path: Path, output_dir: Path) -> dict[str, Any]:
    """Generate all graphs from an existing experiment result JSON.

    Parameters
    ----------
    result_path:
        Path to a ``<experiment_id>.json`` produced by
        :func:`~app.features.experiment.run_part_a_experiment`.
    output_dir:
        Directory in which graphs are saved.  Created if absent.

    Returns
    -------
    dict
        ``graphs_manifest.json`` content mapping graph names to file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    result = _load_result(result_path)
    runs = result["runs"]
    dataset_name = result.get("dataset_name", "Unknown dataset")

    if result.get("dataset_identity_verified") is False:
        note = (
            "NOTICE: dataset_identity_verified=false in this experiment result. "
            "These graphs are based on user-declared provenance only."
        )
    else:
        note = ""

    manifest: dict[str, Any] = {
        "source_result": str(result_path),
        "dataset_name": dataset_name,
        "dataset_identity_verified": result.get("dataset_identity_verified"),
        "disclaimer": DISCLAIMER.format(dataset=dataset_name),
        "notice": note,
        "graphs": {},
    }

    f1_path = output_dir / "macro_f1_comparison.png"
    plot_macro_f1(runs, dataset_name, f1_path)
    manifest["graphs"]["macro_f1_comparison"] = {
        "path": str(f1_path),
        "description": "Validation and test macro-F1 per algorithm and seed.",
    }

    acc_path = output_dir / "accuracy_comparison.png"
    plot_accuracy(runs, dataset_name, acc_path)
    manifest["graphs"]["accuracy_comparison"] = {
        "path": str(acc_path),
        "description": "Test accuracy per algorithm and seed.",
    }

    fc_path = output_dir / "feature_count.png"
    plot_feature_count(runs, dataset_name, fc_path)
    manifest["graphs"]["feature_count"] = {
        "path": str(fc_path),
        "description": "Number of features selected per run vs eligible count.",
    }

    et_path = output_dir / "execution_time.png"
    plot_execution_time(runs, dataset_name, et_path)
    manifest["graphs"]["execution_time"] = {
        "path": str(et_path),
        "description": "Optimizer search time and RF evaluation time per run.",
    }

    macro_ci_path = output_dir / "test_macro_f1_mean_ci.png"
    plot_test_metric_mean_ci(result, "final_test_macro_f1", "Macro-F1", macro_ci_path)
    manifest["graphs"]["test_macro_f1_mean_ci"] = {
        "path": str(macro_ci_path),
        "description": (
            "Mean test macro-F1 with stored 95% Student-t intervals where estimable; "
            "deterministic baseline repeats are shown without an inferential interval."
        ),
    }

    accuracy_ci_path = output_dir / "test_accuracy_mean_ci.png"
    plot_test_metric_mean_ci(result, "final_test_accuracy", "Accuracy", accuracy_ci_path)
    manifest["graphs"]["test_accuracy_mean_ci"] = {
        "path": str(accuracy_ci_path),
        "description": (
            "Mean test accuracy with stored 95% Student-t intervals where estimable; "
            "deterministic baseline repeats are shown without an inferential interval."
        ),
    }

    cm_dir = output_dir / "confusion_matrices"
    cm_paths = plot_confusion_matrices(runs, dataset_name, cm_dir)
    manifest["graphs"]["confusion_matrices"] = {
        "directory": str(cm_dir),
        "files": cm_paths,
        "description": "One test confusion matrix PNG per run.",
    }

    manifest_path = output_dir / "graphs_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path,
                        help="Path to the experiment result JSON file.")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Directory in which to save all graphs.")
    args = parser.parse_args()
    if not args.result.exists():
        parser.error(f"Result file not found: {args.result}")
    manifest = generate_graphs(args.result, args.output_dir)
    print(f"Dataset: {manifest['dataset_name']}")
    if manifest.get("notice"):
        print(f"NOTICE: {manifest['notice']}")
    print(f"Graphs saved to: {args.output_dir}")
    for name, info in manifest["graphs"].items():
        if "path" in info:
            print(f"  {name}: {info['path']}")
        elif "directory" in info:
            print(f"  {name}/: {info['directory']} ({len(info.get('files', []))} files)")
    print(f"Manifest: {args.output_dir / 'graphs_manifest.json'}")
    print(manifest["disclaimer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
