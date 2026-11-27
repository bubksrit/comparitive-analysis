# Aditi Priya — Workstream A handover

**Project:** Intelligent Network Load Balancing <br>
**Owner:** Aditi Priya (1MS24CY005) <br>
**Branch at handover:** `feature/aditi-research-experiments` <br>
**Handover date:** 2026-11-27

## Scope and research objective

Workstream A implements a reproducible feature-selection and classifier comparison pipeline. The requested project question concerns machine-learning and traditional load-balancing approaches under dynamic traffic. Aditi's completed empirical work here evaluates Genetic Algorithm (GA), Binary Particle Swarm Optimization (BPSO), and Ant Colony Optimization (ACO) feature selection with a shared Random Forest (RF) evaluator on a CICIoT2023 development sample.

**These are preliminary intrusion-classification results. They do not measure actual or simulated load-balancer performance.** They contain no server assignment, latency, throughput, CPU load, or dynamic traffic response evaluation. Priyal's simulation/frontend work is outside this handover; this package does not claim the whole team project is complete.

## Completed implementation

- CICIoT2023 config, recursive CSV loading, local schema checks, dataset audit, checksums, deterministic per-folder sampling, and sample manifest.
- Train/validation/test splitting with train-fitted preprocessing, held-out test evaluation, and grouping identical eligible feature vectors across partitions.
- Shared RF evaluator; GA, BPSO, and ACO selectors using a common objective and capped validation-fit budgets.
- Unified runner, JSON/CSV summaries, per-run artifacts, metrics, confidence intervals, and comparison/feature/timing/confusion-matrix graphs.
- Full-feature RF baseline, plus three seed-labelled baseline repetitions, compared without rerunning feature selectors.
- Research methodology, duplicate status, and provenance/ground-truth documentation.

## Experimental protocol and results

- **Sample:** 160,578 rows, 34 folder-derived labels; cap of 5,000 rows per folder, sample seed 42. This changes source class prevalence, so accuracy does not estimate performance under the raw corpus distribution.
- **Split:** seed 43; 96,305 train / 32,175 validation / 32,098 test. Identical eligible feature vectors were group-disjoint; this does not establish capture/session independence.
- **RF:** 50 trees, `class_weight="balanced_subsample"`, `max_features="sqrt"`, fixed `random_state=42`. Selector seed labels are 42, 43, and 44; each selector had a maximum of 12 unique validation RF evaluations per seed.
- **Primary metric:** test macro-F1. Accuracy and other classification metrics are also saved. Selector 95% Student-t intervals use three seeds on one fixed sample/split.

| Method | Test macro-F1 | 95% CI or note | Test accuracy | Mean features |
|---|---:|---:|---:|---:|
| Full-feature RF | 0.6296 | Three identical deterministic repeats; CI not meaningful | 0.6593 | 39/39 |
| GA + RF | 0.5806 | 0.5278–0.6333 | 0.6114 | 15.0/39 |
| BPSO + RF | 0.6013 | 0.5579–0.6447 | 0.6313 | 18.3/39 |
| ACO + RF | 0.5771 | 0.4906–0.6637 | 0.6085 | 15.0/39 |

Seed-aligned selector-minus-baseline macro-F1 differences: GA −0.0490 (95% CI −0.1018 to 0.0037), BPSO −0.0283 (−0.0717 to 0.0151), ACO −0.0525 (−0.1390 to 0.0341). Each interval includes zero. With three optimizer seeds and one fixed split, the comparison is inconclusive and does not show equivalence. The baseline's seed labels do not change estimator randomness; the fixed-RF repetitions are identical and are not independent trials.

## Important paths

All repository paths below are relative to the repository root. Raw data and generated outputs are local-only and are excluded from version control.

### Reports and audits

- Detailed research report: `docs/WORKSTREAM_A_RESEARCH.md`
- Experiment protocol/history: `docs/EXPERIMENTS.md`
- This handover: `docs/WORKSTREAM_A_HANDOVER.md`
- Provenance and ground-truth audit: `docs/audits/cic_iot2023_provenance_and_ground_truth.md`
- Local structural audit: `docs/audits/cic_iot2023_audit.md` and `docs/audits/cic_iot2023_audit.json`
- Current global duplicate status: `docs/audits/cic_iot2023_duplicate_audit_status.md`
- Latest global duplicate attempt: `docs/audits/cic_iot2023_duplicate_audit_20261127T102218Z-b7c6e8c2/report.md` and `docs/audits/cic_iot2023_duplicate_audit_20261127T102218Z-b7c6e8c2/report.json`
- Sample duplicate audit: `docs/audits/cic_iot2023_sample_duplicate_audit_8f5fa66e8616.md` and `.json`
- Earlier global attempts: `docs/audits/cic_iot2023_duplicate_audit_20261127T075436Z-693bf4a1/` and `docs/audits/cic_iot2023_duplicate_audit_20261127T075618Z-952db451/` (historical, not current status)

### Data and configuration

- Raw local files (do not edit): `<LOCAL_CIC_IOT2023_CSV_ROOT>/`
- Local supplied README: `<LOCAL_CIC_IOT2023_CSV_ROOT>/README_CSV.pdf`
- Prepared sample: `data/processed/cic-iot2023-34class-5000-per-class-seed42.csv`
- Sample manifest: `data/processed/cic-iot2023-34class-5000-per-class-seed42.csv.manifest.json`
- Dataset config: `backend/config/cic-iot2023-final.json`
- Experiment config: `backend/config/cic-iot2023-final-experiment.json`

The CIC-IoT2023 configs set `raw_data_path` to `../data/raw/cic-iot2023/CSV`, interpreted relative to the `backend/` working directory used by the commands below. Place the supplied CSV directory there, or edit `raw_data_path` in the chosen config to point to another local location. The value is a portable default, not a verified download location.

### Experiment results and graphs

- Original final JSON: `outputs/cic-iot2023-final/part-a-experiments/e19b2696-bfb4-4ed1-85eb-bd990556173e.json`
- Original final CSV: `outputs/cic-iot2023-final/part-a-experiments/e19b2696-bfb4-4ed1-85eb-bd990556173e.csv`
- Original selector run JSONs: GA `outputs/cic-iot2023-final/ga-runs/71ec475d-7fae-42f0-b15a-4c6ee2906cf3.json`, `outputs/cic-iot2023-final/ga-runs/a6d1996c-f3ec-49bf-8474-bf20ecd12fd9.json`, `outputs/cic-iot2023-final/ga-runs/ff17b72a-5b46-4ec2-a432-85c69a3512a1.json`; BPSO `outputs/cic-iot2023-final/bpso-runs/1ebc2137-8726-4ecf-a114-0885ecc3efac.json`, `outputs/cic-iot2023-final/bpso-runs/97776a87-65e6-41f7-a1fb-693c57eeff20.json`, `outputs/cic-iot2023-final/bpso-runs/e49cd66e-007c-4ab4-965e-91370353de13.json`; ACO `outputs/cic-iot2023-final/aco-runs/0c671eee-91a7-4dc8-af36-7be22efc8824.json`, `outputs/cic-iot2023-final/aco-runs/b01f0b78-2377-4615-8128-f91f0b52add0.json`, `outputs/cic-iot2023-final/aco-runs/ce2504c0-7401-4847-bf51-fecb3f46786f.json`. RF fit artifacts are in `outputs/cic-iot2023-final/rf-evaluations/`.
- Original graphs: `outputs/cic-iot2023-final/graphs/` — `macro_f1_comparison.png`, `accuracy_comparison.png`, `feature_count.png`, `execution_time.png`, `confusion_matrices/`, and `graphs_manifest.json`.
- Seed-matched baseline JSON: `outputs/cic-iot2023-baseline-repeats/part-a-experiments/f45f44de-8303-465a-a84c-2e3440ccf988.json`
- Seed-matched baseline CSV: `outputs/cic-iot2023-baseline-repeats/part-a-experiments/f45f44de-8303-465a-a84c-2e3440ccf988.csv`
- Baseline paired deltas: `outputs/cic-iot2023-baseline-repeats/baseline_comparison_deltas.json`
- Baseline repeat manifest: `outputs/cic-iot2023-baseline-repeats/baseline_repeats_manifest.json`
- Updated graphs: `outputs/cic-iot2023-baseline-repeats/graphs/` — `macro_f1_comparison.png`, `accuracy_comparison.png`, `test_macro_f1_mean_ci.png`, `test_accuracy_mean_ci.png`, `feature_count.png`, `execution_time.png`, `confusion_matrices/`, and `graphs_manifest.json`.

Experiment artifacts are local and Git-ignored. A repository checkout alone does not contain these outputs or the prepared sample; preserve them with the raw data and manifests when transferring the work.

## Reproduction commands

Run from `backend` in the existing virtual environment. These commands are for fresh output paths and **were not run to prepare this handover**. Preparation and experiment runners refuse to overwrite existing outputs.

```bash
cd backend

# Only if the configured sample and its manifest do not already exist.
.venv/bin/python -m app.features.prepare_iot_sample \
  --config config/cic-iot2023-final.json

# Full selectors and baseline into a new output directory.
.venv/bin/python -m scripts.run_cic_iot2023_experiment \
  --dataset-config config/cic-iot2023-final.json \
  --experiment-config config/cic-iot2023-final-experiment.json \
  --output-dir ../outputs/cic-iot2023-final-rerun-01

# RF repeat comparison using saved selectors; new output directory.
.venv/bin/python -m scripts.run_seed_matched_baseline \
  --dataset-config config/cic-iot2023-final.json \
  --experiment-config config/cic-iot2023-final-experiment.json \
  --source-result ../outputs/cic-iot2023-final/part-a-experiments/e19b2696-bfb4-4ed1-85eb-bd990556173e.json \
  --output-dir ../outputs/cic-iot2023-baseline-repeats-rerun-01

# Graph regeneration from a saved result only.
.venv/bin/python -m app.features.graphs \
  --result ../outputs/cic-iot2023-final/part-a-experiments/e19b2696-bfb4-4ed1-85eb-bd990556173e.json \
  --output-dir ../outputs/cic-iot2023-final-rerun-01/graphs

# Verification.
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests scripts
```

Do not run sample preparation against the current config while its configured sample/manifest exist. To create another sample, first use a separate config with new `data_path` and `output_dir`, preserving source settings and seed.

### Previously verified checks

These results were recorded before the final read-only handover review; they were **not rerun during that review**:

- Full backend test suite: **84 passed**.
- Ruff: **passed**.
- `git diff --check`: **passed**.

## Limitations and unresolved decisions

1. **Dataset provenance/schema:** The official CIC page is configured, but local retrieval date, exact source package lineage and publisher-side checksum are absent. Local hashes provide integrity, not publisher authentication. The local `README_CSV.pdf` describes combined/shuffled CSVs with a label feature; the audited files are folder-separated with 39 features and no raw label. The local schema also differs from fields in CIC's published feature summary.
2. **Ground truth:** Targets are derived from immediate folder names and are not independently checked against row-level labels. `Benign_Final` → `Benign` is plausible but not source-verified.
3. **Sampling/splits:** The 5,000-row cap changes class prevalence. Grouping identical features across splits does not establish session/capture independence.
4. **Duplicate audit:** The global scan read all 46,776,700 rows, identified 5,786,051 candidate rows and completed 5,390,828 full feature comparisons before an SQLite lock error. It is incomplete, has no resumable checkpoint, and produced no exact global duplicate count. Duplicate counts for the prepared sample are sample-scoped only.
5. **Reproducibility:** Saved experiment artifacts contain software versions, hardware, configs, and sample checksum, but `code_revision` is null; configured retrieval date is also null. Record these in future reruns.
6. **Interpretation:** Results use one class-capped sample, one split, three optimizer seeds, and small search budgets. They are not load-balancer performance evidence or a broad equivalence finding.

### Faculty/team confirmation needed

- Confirm CICIoT2023 as an acceptable Workstream A dataset given the original CIC-IDS2017 specification and unresolved local provenance/schema conflict.
- Confirm whether folder-derived labels and the `Benign_Final` mapping are acceptable for preliminary work, or whether independently verified labels are required before final claims.
- Confirm that this intrusion-classification analysis is separate from Priyal's simulation-based load-balancing evaluation and agree how the two workstreams will be integrated in the final report.
- Confirm whether a new source-verified dataset run is needed before submission.

No faculty approval is asserted here. This is Aditi's Workstream A handover only; it does not claim the full team project is complete.
