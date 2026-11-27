#!/usr/bin/env python3
"""Rebuild Study B result tables and vector charts from the exported JSON files.

The input exports are PowerShell ``Out-File`` JSON (UTF-16LE with a BOM).
This script uses only the Python standard library and writes deterministic SVG
figures plus ``RESULTS.md`` under this directory.

Run from any working directory with::

    python docs/results/analyze_results.py
"""

from __future__ import annotations

import html
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw"
FIGURE_DIR = HERE / "figures"

WORKLOADS = (
    ("Stable", "stable_results.json"),
    ("Increasing Traffic", "increasing_results.json"),
    ("Server Failure", "failure_results.json"),
    ("Bursty", "bursty_results.json"),
)
POLICIES = (
    ("round_robin", "Round Robin", "#2878B5", "circle"),
    ("least_connections", "Least Connections", "#E07A1F", "square"),
    ("weighted", "Weighted", "#218739", "diamond"),
)


@dataclass(frozen=True)
class Metric:
    key: str
    title: str
    axis_label: str
    table_unit: str
    scale: float = 1.0
    decimals: int = 4
    filename: str = ""


METRICS = (
    Metric(
        "mean_response_time_seconds",
        "Mean response time",
        "Mean response time (s)",
        "s",
        decimals=4,
        filename="mean_response_time.svg",
    ),
    Metric(
        "p95_latency_seconds",
        "P95 latency",
        "P95 latency (s)",
        "s",
        decimals=4,
        filename="p95_latency.svg",
    ),
    Metric(
        "throughput_requests_per_second",
        "Completion throughput",
        "Throughput (completed requests/s)",
        "requests/s",
        decimals=3,
        filename="throughput.svg",
    ),
    Metric(
        "load_imbalance_cv",
        "Load imbalance",
        "Load imbalance (unitless CV)",
        "CV",
        decimals=4,
        filename="load_imbalance_cv.svg",
    ),
    Metric(
        "total_request_loss_rate",
        "Request loss rate",
        "Offered-request loss rate (%)",
        "% offered",
        scale=100.0,
        decimals=4,
        filename="request_loss_rate.svg",
    ),
    Metric(
        "mean_policy_decision_wall_seconds",
        "Mean policy decision overhead",
        "Mean policy decision overhead (µs/decision)",
        "µs/decision",
        scale=1_000_000.0,
        decimals=3,
        filename="mean_decision_overhead.svg",
    ),
)


def _load_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    # PowerShell Out-File emits UTF-16LE with a BOM. Accept UTF-8 as well to
    # keep the script usable if the exports are later re-saved conventionally.
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object at the root of {path}")
    return payload


def load_results() -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    expected_policy_ids = {policy_id for policy_id, *_ in POLICIES}
    for workload, filename in WORKLOADS:
        path = RAW_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required result export not found: {path}")
        payload = _load_json(path)
        if set(payload) != expected_policy_ids:
            raise ValueError(
                f"{filename}: expected policies {sorted(expected_policy_ids)}, "
                f"found {sorted(payload)}"
            )
        for policy_id, *_ in POLICIES:
            policy_metrics = payload[policy_id]
            if not isinstance(policy_metrics, dict):
                raise ValueError(f"{filename}:{policy_id} must contain a metric object")
            for metric in METRICS:
                summary = policy_metrics.get(metric.key)
                if not isinstance(summary, dict):
                    raise ValueError(f"{filename}:{policy_id} lacks {metric.key}")
                if not {"mean", "confidence_interval_95", "sample_count"} <= set(summary):
                    raise ValueError(f"{filename}:{policy_id}:{metric.key} has an incomplete summary")
                mean = summary["mean"]
                interval = summary["confidence_interval_95"]
                if (
                    not isinstance(mean, (int, float))
                    or not math.isfinite(mean)
                    or not isinstance(interval, list)
                    or len(interval) != 2
                    or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in interval)
                ):
                    raise ValueError(f"{filename}:{policy_id}:{metric.key} has invalid numeric values")
                if summary["sample_count"] < 1:
                    raise ValueError(f"{filename}:{policy_id}:{metric.key} has no samples")
        results[workload] = payload
    return results


def _summary(
    data: dict[str, dict[str, Any]], workload: str, policy_id: str, metric: Metric
) -> tuple[float, float, float, int]:
    summary = data[workload][policy_id][metric.key]
    mean = float(summary["mean"]) * metric.scale
    low, high = (float(value) * metric.scale for value in summary["confidence_interval_95"])
    return mean, low, high, int(summary["sample_count"])


def _fmt(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}"


def _table(data: dict[str, dict[str, Any]], metric: Metric) -> str:
    rows = [
        "| Workload | " + " | ".join(name for _, name, *_ in POLICIES) + " |",
        "|---|---:|---:|---:|",
    ]
    for workload, _ in WORKLOADS:
        cells = [workload]
        for policy_id, *_ in POLICIES:
            mean, low, high, sample_count = _summary(data, workload, policy_id, metric)
            value = _fmt(mean, metric.decimals)
            interval = f"{_fmt(low, metric.decimals)}, {_fmt(high, metric.decimals)}"
            cells.append(f"{value} [{interval}] (n={sample_count})")
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _observations(data: dict[str, dict[str, Any]]) -> str:
    lines: list[str] = []
    cv_metric = next(metric for metric in METRICS if metric.key == "load_imbalance_cv")
    response_metric = next(
        metric for metric in METRICS if metric.key == "mean_response_time_seconds"
    )
    throughput_metric = next(
        metric for metric in METRICS if metric.key == "throughput_requests_per_second"
    )
    overhead_metric = next(
        metric for metric in METRICS if metric.key == "mean_policy_decision_wall_seconds"
    )
    for workload, _ in WORKLOADS:
        rr_cv = _summary(data, workload, "round_robin", cv_metric)[0]
        lc_cv = _summary(data, workload, "least_connections", cv_metric)[0]
        weighted_cv = _summary(data, workload, "weighted", cv_metric)[0]
        reductions = []
        if rr_cv > 0:
            reductions.append(f"{(rr_cv - weighted_cv) / rr_cv * 100:.1f}% vs Round Robin")
        if lc_cv > 0:
            reductions.append(f"{(lc_cv - weighted_cv) / lc_cv * 100:.1f}% vs Least Connections")

        response_values = [
            _summary(data, workload, policy_id, response_metric)[0]
            for policy_id, *_ in POLICIES
        ]
        throughput_values = [
            _summary(data, workload, policy_id, throughput_metric)[0]
            for policy_id, *_ in POLICIES
        ]
        response_spread_pct = (
            (max(response_values) - min(response_values)) / (sum(response_values) / len(response_values)) * 100
            if sum(response_values)
            else 0.0
        )
        throughput_spread_pct = (
            (max(throughput_values) - min(throughput_values))
            / (sum(throughput_values) / len(throughput_values))
            * 100
            if sum(throughput_values)
            else 0.0
        )
        weighted_overhead = _summary(data, workload, "weighted", overhead_metric)[0]
        lines.append(
            f"- **{workload}:** Weighted's load-imbalance CV is {_fmt(weighted_cv, 4)}, "
            f"{'; '.join(reductions)}. The three policies' mean-response-time means span "
            f"{response_spread_pct:.4f}% and throughput means span {throughput_spread_pct:.4f}% "
            f"of their respective across-policy averages. Weighted's mean decision overhead is "
            f"{_fmt(weighted_overhead, 3)} µs/decision."
        )
    return "\n".join(lines)


def _results_markdown(data: dict[str, dict[str, Any]]) -> str:
    sample_counts = sorted(
        {
            int(data[workload][policy_id][metric.key]["sample_count"])
            for workload, _ in WORKLOADS
            for policy_id, *_ in POLICIES
            for metric in METRICS
        }
    )
    sample_count_text = ", ".join(str(count) for count in sample_counts)
    sections = [
        "# Study B Load-Balancing Results",
        "",
        "## Scope and provenance",
        "",
        "These results compare the three implemented simulated routing policies across Stable, "
        "Increasing Traffic, Server Failure, and Bursty workloads. They are discrete-event "
        "simulation results, not physical network or hardware measurements. The source exports "
        "are preserved byte-for-byte in [`raw/`](raw/). They were found in `frontend/` and are "
        "copied there under the requested workload filenames.",
        "",
        "The JSON structure is `{policy_id: {metric_name: {mean, standard_deviation, "
        f"confidence_interval_95, sample_count}}}}}}`. Each requested metric has a sample count of {sample_count_text} per "
        "policy/workload. Each displayed mean summarizes replication-level metric values; the "
        "P95 column is the mean of per-replication P95 latency values, not a pooled-request "
        "percentile. Tables show the exported mean and its exported 95% confidence interval in "
        "brackets. The report does not recompute or alter those values.",
        "",
        "The exports do not include per-replication observations, paired policy differences, "
        "seed IDs, trace IDs, or full run configuration. Therefore, paired confidence intervals "
        "cannot be independently reconstructed from these files. Overlap between separate policy "
        "intervals is not a formal test of equivalence or of a paired difference.",
        "",
        "## Experimental results",
        "",
    ]
    for metric in METRICS:
        sections.extend(
            [
                f"### {metric.title} ({metric.table_unit})",
                "",
                _table(data, metric),
                "",
                f"![{metric.title} comparison]({{FIGURE_DIR}}/{metric.filename})",
                "",
            ]
        )
    sections.extend(
        [
            "## Workload-wise observations",
            "",
            _observations(data),
            "",
            "## Interpretation",
            "",
            "Across all four exported workloads, Weighted has the lowest mean load-imbalance CV. "
            "Its destination choice therefore distributes measured utilization more evenly under "
            "the supplied capacity-aware policy. Load balance measures utilization dispersion; "
            "it does not increase the fleet's aggregate service capacity. With the same offered "
            "work and server fleet, improved balance can therefore coexist with nearly unchanged "
            "response and completion throughput. In Increasing Traffic, the reported loss-rate "
            "means are also nearly identical across policies. This is a plausible interpretation "
            "of the observed pattern, not a causal result established by these aggregate exports. "
            "However, mean response-time, P95-latency, and "
            "throughput point estimates are effectively coincident across policies in these "
            "exports. The results do not show a meaningful latency or throughput advantage for "
            "Weighted. The generated observations quantify the across-policy point-estimate "
            "spreads for each workload. This is a descriptive reading, not a paired significance "
            "test, because replication-level paired differences were not exported.",
            "",
            "Weighted also has the largest mean policy decision overhead in each workload in the "
            "provided summaries. These are host wall-clock measurements and should be interpreted "
            "as implementation overhead, not simulated server CPU or simulation-time delay.",
            "",
            "Increasing Traffic has the highest mean response time and P95 latency among the "
            "workloads, accompanied by the largest reported request-loss rate. Bursty traffic "
            "raises latency relative to Stable while the reported loss rate remains zero. The "
            "Server Failure scenario reports a small nonzero loss rate. Workload-level values and "
            "confidence intervals are shown in the tables above.",
            "",
            "## Statistical uncertainty",
            "",
            f"The exports provide per-policy 95% confidence intervals for each metric, based on "
            f"{sample_count_text} samples. The repository [comparison routine](../../backend/app/simulation/comparison.py) "
            "uses 10,000-resample "
            "percentile bootstrap intervals; these exported intervals are reproduced as supplied. "
            "They are not paired-difference intervals. Since paired scenario observations are "
            "absent, the report makes no formal claim that policy differences are statistically "
            "significant or equivalent.",
            "",
            "## Limitations",
            "",
            "- Results are from a discrete-event simulation; no physical network behavior, "
            "hardware CPU use, or hardware memory use is measured.",
            "- The files contain aggregate summaries only. Per-replication values and paired "
            "differences are unavailable, limiting independent verification and comparative "
            "inference.",
            "- Seeds, trace identifiers, detailed run configuration, and environment metadata "
            "are absent from the exports, so this report cannot independently verify that all "
            "policy runs used identical paired scenarios.",
            "- Decision-overhead timings depend on the host and runtime and should not be treated "
            "as simulated server resource consumption.",
            "- Confidence intervals are reported as exported; they do not account for variation "
            "across workload definitions or establish generalization beyond these four scenarios.",
            "",
            "## Final findings",
            "",
            "1. Weighted shows the lowest load-imbalance CV in all four workload summaries.",
            "2. The exported mean response time, P95 latency, and throughput are effectively "
            "the same across the three policies; these results do not demonstrate a meaningful "
            "latency or throughput improvement from Weighted.",
            "3. Weighted's mean route-decision overhead is higher in the supplied summaries, "
            "which is a relevant trade-off for the capacity-aware policy.",
            "4. Findings are limited to the supplied simulated experiment summaries and should "
            "not be generalized to physical networks or treated as formal paired significance "
            "claims without the replication-level exports.",
            "",
            "## Reproduction",
            "",
            "From the repository root, run `python docs/results/analyze_results.py`. The script "
            "reads the UTF-16 PowerShell exports in `docs/results/raw/`, validates the expected "
            "schema, and regenerates this file and all SVG figures in `docs/results/figures/`. "
            "It uses only the Python standard library.",
            "",
        ]
    )
    return "\n".join(sections).replace("{FIGURE_DIR}", "figures")


def _svg_text(x: float, y: float, text: str, *, size: int = 16, fill: str = "#243247", anchor: str = "middle") -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{size}" fill="{fill}" text-anchor="{anchor}">{html.escape(text)}</text>'
    )


def _marker(x: float, y: float, shape: str, color: str) -> str:
    if shape == "square":
        return f'<rect x="{x - 6:.2f}" y="{y - 6:.2f}" width="12" height="12" fill="{color}" />'
    if shape == "diamond":
        points = f"{x:.2f},{y - 7:.2f} {x + 7:.2f},{y:.2f} {x:.2f},{y + 7:.2f} {x - 7:.2f},{y:.2f}"
        return f'<polygon points="{points}" fill="{color}" />'
    return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6" fill="{color}" />'


def _figure_svg(data: dict[str, dict[str, Any]], metric: Metric) -> str:
    width, height = 1200, 660
    left, right, top, bottom = 115, 60, 105, 145
    plot_width = width - left - right
    plot_height = height - top - bottom
    points = [
        (workload, policy_id, *_summary(data, workload, policy_id, metric))
        for workload, _ in WORKLOADS
        for policy_id, *_ in POLICIES
    ]
    lows = [item[3] for item in points]
    highs = [item[4] for item in points]
    y_min = min(0.0, min(lows))
    y_max = max(highs)
    if y_max <= y_min:
        y_max = y_min + 1.0
    y_max *= 1.12
    y_span = y_max - y_min

    def y_coord(value: float) -> float:
        return top + (y_max - value) / y_span * plot_height

    x_centers = [left + plot_width * (index + 0.5) / len(WORKLOADS) for index in range(len(WORKLOADS))]
    offset_step = 24
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        _svg_text(width / 2, 42, metric.title, size=28, fill="#16283f"),
        _svg_text(width / 2, 72, f"Mean across exported replications; bars show exported 95% CIs · {metric.axis_label}", size=15, fill="#526174"),
    ]
    tick_count = 5
    for tick in range(tick_count + 1):
        value = y_min + y_span * tick / tick_count
        y = y_coord(value)
        chunks.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" stroke="#e3e8ef" stroke-width="1"/>')
        chunks.append(_svg_text(left - 14, y + 5, _fmt(value, metric.decimals), size=13, fill="#526174", anchor="end"))
    chunks.extend([
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#7a8797" stroke-width="1.5"/>',
        f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#7a8797" stroke-width="1.5"/>',
        f'<text x="28" y="{top + plot_height/2:.2f}" transform="rotate(-90 28 {top + plot_height/2:.2f})" font-family="Arial, Helvetica, sans-serif" font-size="15" fill="#243247" text-anchor="middle">{html.escape(metric.axis_label)}</text>',
    ])

    for workload_index, (workload, _) in enumerate(WORKLOADS):
        center = x_centers[workload_index]
        for policy_index, (policy_id, _label, color, shape) in enumerate(POLICIES):
            mean, low, high, _sample_count = _summary(data, workload, policy_id, metric)
            x = center + (policy_index - 1) * offset_step
            y_low = y_coord(low)
            y_high = y_coord(high)
            y_mean = y_coord(mean)
            chunks.extend([
                f'<line x1="{x:.2f}" y1="{y_high:.2f}" x2="{x:.2f}" y2="{y_low:.2f}" stroke="{color}" stroke-width="2"/>',
                f'<line x1="{x-7:.2f}" y1="{y_high:.2f}" x2="{x+7:.2f}" y2="{y_high:.2f}" stroke="{color}" stroke-width="2"/>',
                f'<line x1="{x-7:.2f}" y1="{y_low:.2f}" x2="{x+7:.2f}" y2="{y_low:.2f}" stroke="{color}" stroke-width="2"/>',
                _marker(x, y_mean, shape, color),
            ])
        chunks.append(_svg_text(center, height - bottom + 31, workload, size=14, fill="#243247"))

    legend_y = height - 40
    legend_start = width / 2 - 245
    for index, (_policy_id, label, color, shape) in enumerate(POLICIES):
        x = legend_start + index * 245
        chunks.append(_marker(x, legend_y - 5, shape, color))
        chunks.append(_svg_text(x + 18, legend_y, label, size=15, fill="#243247", anchor="start"))
    chunks.append("</svg>")
    return "\n".join(chunks) + "\n"


def main() -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    data = load_results()
    for metric in METRICS:
        destination = FIGURE_DIR / metric.filename
        destination.write_text(_figure_svg(data, metric), encoding="utf-8", newline="\n")
        print(f"Wrote {destination.relative_to(HERE.parent.parent)}")
    results_path = HERE / "RESULTS.md"
    results_path.write_text(_results_markdown(data), encoding="utf-8", newline="\n")
    print(f"Wrote {results_path.relative_to(HERE.parent.parent)}")


if __name__ == "__main__":
    main()
