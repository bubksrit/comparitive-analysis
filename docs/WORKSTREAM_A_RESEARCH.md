# Research Documentation: Workstream A
## Intelligent Network Load Balancing — Feature Selection Study

**Author:** Aditi Priya (USN: 1MS24CY005)
**Branch:** `feature/aditi-research-experiments`
**Last updated:** 2026-11-27

---

> [!IMPORTANT]
> The current Study A experiment uses **CIC-IoT2023** for intrusion classification. Older CIC-IDS2017 setup text below is historical template context; no CIC-IDS2017 experiment is established by the current evidence.
> Study A is not direct measurement of real server CPU use or network load-balancer performance. Do not present its results as load-balancing evidence.

---

## 1. Datasets

### 1.1 Current dataset: CIC-IoT2023

CIC-IoT2023 is the final dataset choice for Workstream A, and the faculty/team has approved
that choice. Approval is not technical verification of the local data. Exact source-package
provenance, release identity, schema correspondence, labels, and the complete run manifest
remain unresolved. No CIC-IDS2017 experiment is established by the current repository evidence;
older CIC-IDS2017 setup instructions are historical template material, not the active protocol.

| Property | Value |
|---|---|
| Full name | Canadian Institute for Cybersecurity IoT Dataset 2023 |
| Source | https://www.unb.ca/cic/datasets/iotdataset-2023.html |
| Local audited format | 309 CSV files across 34 category folders; 39 numeric feature columns each; labels derived by this project's loader |
| Label strategy | Derived from parent folder name (e.g. `DDoS-ICMP_Flood/` -> class `DDoS-ICMP_Flood`) |
| Current experiment labels | Multiclass, one folder-derived class per category folder (34 classes) |
#### CIC-IoT2023 label derivation

In the local files, the saved audit found no raw label column. The project derives labels
from the immediate parent folder name:

- Folders whose names contain `benign`, `normal`, or `legitimate` (case-insensitive) → `Benign`
- All other folders → the folder name itself (multiclass) or `Attack` (binary)

This derivation is implemented in `app/features/iot_loader.py` and tested in `tests/test_cic_iot2023_loader.py`.
These are folder-derived proxy labels, not independently verified row-level ground truth.
The local `README_CSV.pdf` instead describes combined/shuffled CSVs with a `label` feature;
that discrepancy is unresolved. In particular, `Benign_Final` → `Benign` is a plausible
project normalization, but is not confirmed by the publisher materials inspected. See the
[provenance and ground-truth audit](audits/cic_iot2023_provenance_and_ground_truth.md).

#### CIC-IoT2023 column schema

The local audit found that all 309 CSVs share the **same 39 numeric feature columns** (see
`CIC_IOT2023_EXPECTED_COLUMNS` in `iot_loader.py`). The loader validates this local schema
on every discovered CSV. This establishes consistency within the local tree, not a verified
match to the official release: the official CIC feature summary includes fields absent
locally, and the local README describes a label-bearing combined schema.

#### Combining CIC-IoT2023 for the pipeline

After loading via `load_cic_iot2023()`, write the combined frame and label column to a CSV
and configure it via `backend/config/cic-iot2023.json` for the standard `load_and_audit()` pipeline.

---

## 2. Data provenance and audit procedure

The source, local package/schema discrepancy, folder-label evidence, license/citation status,
and unresolved provenance questions are assessed in the [CICIoT2023 provenance and
ground-truth audit](audits/cic_iot2023_provenance_and_ground_truth.md). The local source
tree has not been authenticated against a publisher archive or checksum. Treat results as
preliminary folder-labelled intrusion-classification experiments only.

### 2.1 Latest global duplicate-audit status and policy

The latest exact global audit is recorded at
`docs/audits/cic_iot2023_duplicate_audit_20261127T102218Z-b7c6e8c2/`. It read all
46,776,700 source rows, identified 5,786,051 candidate rows and completed 5,390,828 full
feature comparisons before stopping with `OperationalError: database is locked`. Its temporary SQLite index was cleaned up, so this is
not a resumable checkpoint. The audit is incomplete: **no exact global duplicate count is
available**. Do not substitute a lower-bound or sample count for a global total.

The development policy is to retain every raw and sampled record. For the development sample,
exact repeated model-input vectors are assigned to the same split, based on eligible feature
columns and independent of the label. This prevents an identical vector from appearing in more
than one partition, including when the same vector has conflicting folder-derived labels. The
policy does not claim capture/session independence. The raw source remains unchanged.

Duplicate statistics calculated on a prepared development sample are explicitly sample-scoped.
They can describe that sample and its split, but cannot support a global raw-dataset total.

The deterministic sample at
`data/processed/cic-iot2023-34class-5000-per-class-seed42.csv` contains 160,578 rows
across all 34 folder-derived labels. Its SHA-256 is recorded in the adjacent manifest. The
exact sample audit reports 2,524 repeated full records and 3,794 repeated feature vectors;
all were retained. See `docs/audits/cic_iot2023_sample_duplicate_audit_8f5fa66e8616.md`.

The 5,000-row-per-folder cap changes the original class prevalence: large classes are heavily
downsampled while folders with fewer than 5,000 rows remain at their full observed size. The
results below describe this development sample, not the source dataset's natural class mix.

An earlier version of this document recorded a split of 96,336 train / 32,139 validation /
32,103 test rows. That count conflicts with the final split recorded in the handover and
experiment protocol and is treated as stale/historical; the underlying earlier artifact is
not available here to verify its role. The final reported split is 96,305 training, 32,175
validation, and 32,098 test rows (seed 43). All 34 labels occur in each partition, and
identical eligible feature vectors have no partition overlap. This establishes feature-vector
group separation only, not capture/session independence. The final split audit is a local
artifact and is absent from this repository checkout.

The CIC-IoT2023 pipeline produces a machine-readable audit before splitting or model fitting:

| Audit output | Description |
|---|---|
| `audit.json` | Full column stats, missing values, infinities, duplicates, class counts |
| `columns.csv` | Per-column dtype, constant/duplicate flags, exclusion status |
| `audit.md` | Human-readable Markdown summary |

**Key audit checks:**
- Schema mismatch detection across CSV files
- Missing value and positive/negative infinity counts (infinities replaced with NaN before imputation)
- Constant columns (reported, not removed)
- Duplicate-valued column pairs (reported, not removed)
- Duplicate rows (reported, not removed)
- Heuristic review suggestions for identifier/leakage columns (advisory only)

> [!NOTE]
> The audit reports columns and counts but does **not** remove rows or columns.
> Decisions about deduplication and feature exclusion are user-confirmed and recorded in the config.

---

## 3. Data splitting

### 3.1 Split protocol

Splits are constructed **before** fitting any preprocessing.
Target fractions: **60% train / 20% validation / 20% test** (configurable).

| Strategy | When used |
|---|---|
| `group_aware` | When verified capture-day or attack-scenario group columns are configured |
| `time_ordered` | When a parseable timestamp column is configured |
| `stratified_random` | Fallback when no group/time metadata is available (must be explicitly labelled) |

> [!IMPORTANT]
> The stratified random fallback may mix related network flows across partitions.
> If used, it **must** be reported as a limitation, not presented as group-independent generalisation.

### 3.2 Test partition gate

The test partition is sealed by the `DatasetSplits` API.
It is accessible only through `get_test_for_final_evaluation(final_choices_frozen=True)`.
Feature selection, preprocessing fitting, and model/hyperparameter choices **must all be frozen** before this call.
Test labels and metrics must never feed back into any selection decision.

### 3.3 No-overlap guarantee (group split)

Group-aware splits use `GroupShuffleSplit`, ensuring each capture-day/scenario group appears in exactly one partition.
Overlap is detected and reported in `split_details["group_overlap"]`.

---

## 4. Preprocessing

Preprocessing is implemented in `app/features/preprocessing.py`.

| Transform | Columns | Fitted on |
|---|---|---|
| `SimpleImputer(strategy="median")` | Numeric | Training data only |
| `SimpleImputer(strategy="most_frequent")` | Categorical | Training data only |
| `OneHotEncoder(handle_unknown="ignore")` | Categorical | Training data only |

**No feature scaling** is applied. Random Forests do not require scaled inputs, and the fitness equation does not depend on scale.

After `fit()` on training data, the same fitted transformer is applied to validation and test data using `transform()` only. This prevents any validation or test statistics from influencing preprocessing parameters.

---

## 5. Random Forest classifier

The same `RandomForestClassifier` configuration is used for every evaluation (baseline, GA, BPSO, ACO):

| Parameter | Value |
|---|---|
| `n_estimators` | 50 |
| `criterion` | gini |
| `max_depth` | None |
| `max_features` | sqrt |
| `bootstrap` | True |
| `class_weight` | balanced_subsample |
| `random_state` | 42 |
| `n_jobs` | 1 |

The model is fitted on training data only. Validation data is scored to compute fitness. Test data is scored only once, after all choices are frozen.

---

## 6. Feature selection algorithms

### 6.1 Fitness function

The same minimisation objective is used for all three algorithms:

$$\text{fitness} = 0.8 \times (1 - \text{macro\_F1}_{val}) + 0.2 \times \frac{n_{selected}}{n_{eligible}}$$

Lower is better. The 0.8/0.2 weights are configurable but must be **identical** across GA, BPSO, and ACO for fair comparison.

### 6.2 Genetic Algorithm (GA)

- Binary chromosome over eligible feature columns
- Tournament selection (configurable size)
- One-point crossover (configurable probability)
- Bit-flip mutation (configurable per-bit probability)
- Elitism (best individual carried forward)
- Repair: chromosomes violating `[min_features, max_features]` have random bits toggled
- Stopping: `max_model_evaluations` unique RF fits or `generations` limit, whichever first
- Duplicate mask → fitness cache (counted but no new RF fit)

### 6.3 Binary Particle Swarm Optimization (BPSO)

- Real-valued velocities, sigmoid transfer to bit-inclusion probabilities
- Velocity update: $v = w \cdot v + c_1 r_1 (p_{best} - x) + c_2 r_2 (g_{best} - x)$
- Inertia annealed linearly from `inertia_start` to `inertia_end`
- Velocity clipped to `[velocity_min, velocity_max]`
- Positions repaired to `[min_features, max_features]`
- Stopping: `max_model_evaluations` unique RF fits or `iterations` limit

### 6.4 Ant Colony Optimization (ACO)

- Pheromone vector over features, initialised uniformly
- Subset size sampled uniformly in `[min_features, max_features]`
- Feature selection probability ∝ `pheromone^α × heuristic^β`
- Evaporation + best-ant pheromone deposit per iteration
- Deposit: $Q / (1 + \text{fitness})$ on selected features
- Pheromone clipped to `[pheromone_min, pheromone_max]`
- Stopping: `max_model_evaluations` unique RF fits or `iterations` limit

### 6.5 Evaluation budget

All three algorithms enforce an identical `max_model_evaluations` budget counting **unique** masks evaluated.
Repeated masks are served from a fitness cache; cache hits are counted separately as `fitness_request_count`.
The full-feature baseline evaluation is **not** counted against the selector budget.

---

## 7. Experiment protocol

### 7.1 Comparison methods

Every Part A run compares:
1. Full-feature Random Forest baseline (all eligible features)
2. GA + Random Forest
3. BPSO + Random Forest
4. ACO + Random Forest

### 7.2 Multiple seeds

Each stochastic selector is run over multiple independent random seeds (default: 3 seeds; planned: 10).
Per-seed results and cross-seed aggregates (mean, standard deviation, 95% confidence interval via Student's t) are reported.

### 7.3 Recorded metrics per run

| Metric | Source |
|---|---|
| Accuracy | Test partition |
| Macro precision, recall, F1 | Test partition |
| Weighted precision, recall, F1 | Test partition |
| Confusion matrix | Test partition |
| Validation macro-F1 | Validation partition (from fitness) |
| Selected feature count and names | Selector result |
| Feature reduction % | `100 × (1 − selected/eligible)` |
| Best fitness value | Selector result |
| Model evaluation count (unique) | Fitness cache |
| Callback request count | Fitness request counter |
| Optimizer (search) time | Wall-clock, excluding RF fit time |
| RF evaluation time | Wall-clock, summed across all fits |
| Total end-to-end time | Wall-clock |

### 7.4 Output files

| File | Description |
|---|---|
| `<experiment_id>.json` | Full experiment result with all runs, metrics, provenance |
| `<experiment_id>.csv` | One row per run for quick tabular inspection |
| `audit.json` | Dataset audit report |
| `columns.csv` | Per-column audit |
| `rf-evaluations/<uuid>.json` | Individual RF evaluation records |
| `ga-runs/<uuid>.json` | GA run artifact |
| `bpso-runs/<uuid>.json` | BPSO run artifact |
| `aco-runs/<uuid>.json` | ACO run artifact |
| Graphs (from `graphs.py`) | macro_f1, accuracy, feature_count, execution_time, confusion matrices |

### Development pilot (2026-11-27)

A one-seed pilot was run on the manifested 160,578-row development sample with a deliberately
small 10-tree Random Forest and four unique model-evaluation opportunities per selector. It is
software and runtime evidence, not a final research result. Test scores were generated only
after the pilot choices were frozen; they must not be used to tune or select final settings.

| Method | Validation macro-F1 | Pilot test macro-F1 | Pilot test accuracy | Selected features |
|---|---:|---:|---:|---:|
| Full-feature RF | 0.6150 | 0.6149 | 0.6454 | 39/39 |
| GA + RF | 0.5788 | 0.5772 | 0.6059 | 31/39 |
| BPSO + RF | 0.5869 | 0.5905 | 0.6214 | 20/39 |
| ACO + RF | 0.6108 | 0.6130 | 0.6436 | 31/39 |

The experiment JSON/CSV and generated comparison plots are under
`outputs/cic-iot2023-pilot/`. The graph manifest includes the classification-only disclaimer.
Dataset identity remains user-declared (`dataset_identity_verified=false`).

Before freezing the final classifier size, validation-only tree-count checks on the pilot split
compared 10, 50, 100, and 200 trees. Macro-F1 was 0.6150, 0.6287, 0.6308, and 0.6317,
respectively; measured fit times were 3.30, 15.35, 28.73, and 56.66 seconds. A separate
100-tree check with 75% bootstrap samples scored 0.6307 in 24.55 seconds. These checks never
opened the pilot test partition. The final run uses 50 trees on the full training rows: it keeps
most of the observed validation gain over 10 trees while reducing fitting cost versus 100/200.
Final selector comparisons use that one fixed RF configuration and an untouched split seed.

### Final development experiment (2026-11-27)

The final run used a new duplicate-grouped split (seed 43), separate from the pilot split
(seed 42). It used 50-tree Random Forests, GA/BPSO/ACO evaluation budgets of 12 unique
validation fits per seed, and selector seeds 42, 43, and 44. All methods used the same
preprocessing, RF settings, split, fitness weights, and feature bounds. Test evaluation began
only after all selector runs and configurations were frozen.

| Method | Validation macro-F1 | Test macro-F1 | Δ test macro-F1 vs baseline | Test accuracy | Mean selected features |
|---|---:|---:|---:|---:|---:|
| Full-feature RF | 0.6299 (3 identical repeats) | 0.6296 (SD 0; CI n/a) | Reference | 0.6593 (SD 0; CI n/a) | 39.0/39 |
| GA + RF | 0.5815 | 0.5806 ± 0.0212 (95% CI 0.5278–0.6333) | −0.0490 (95% CI −0.1018–0.0037) | 0.6114 ± 0.0236 | 15.0/39 |
| BPSO + RF | 0.5999 | 0.6013 ± 0.0175 (95% CI 0.5579–0.6447) | −0.0283 (95% CI −0.0717–0.0151) | 0.6313 ± 0.0181 | 18.3/39 |
| ACO + RF | 0.5756 | 0.5771 ± 0.0348 (95% CI 0.4906–0.6637) | −0.0525 (95% CI −0.1390–0.0341) | 0.6085 ± 0.0314 | 15.0/39 |

The selector confidence intervals use the Student-t method over three selector seeds on this
fixed sample and split. The baseline was fit three times with the exact saved RF settings,
including `random_state=42`; seeds 42/43/44 are comparison labels and do not alter the model.
All baseline metrics are identical, so a baseline confidence interval is not inferentially
meaningful. The delta intervals pair each selector seed with its matching baseline label and
are conditional on this split and RF random state. All three include zero; with three seeds,
this does not establish equivalence. Intervals do not quantify uncertainty across datasets or
split assignments. Feature reductions did not show a reliable macro-F1 improvement. The capped
class mix also means accuracy is not an estimate of performance under the raw corpus prevalence.

The split contains 96,305 train, 32,175 validation, and 32,098 test rows. All 34 classes occur
in every partition. The persisted split report records no overlap of identical eligible feature
vectors. The final JSON and CSV, per-seed selector/evaluator artifacts, and graphs are in
`outputs/cic-iot2023-final/`; the summary result ID is
`e19b2696-bfb4-4ed1-85eb-bd990556173e`. Dataset identity and folder-label ground truth remain
user-declared and unverified. These results concern intrusion-detection classification only,
not physical or simulated load-balancer performance.

The seed-matched baseline comparison is preserved separately under
`outputs/cic-iot2023-baseline-repeats/`. It contains three new baseline records and the original
nine selector records. Its seed-aligned delta intervals are in
`baseline_comparison_deltas.json`, and the updated seed and mean/CI graphs are in `graphs/`.
The original one-baseline JSON and graphs remain unchanged.

To reproduce in a fresh output directory, run from `backend/`:

```bash
python -m scripts.run_cic_iot2023_experiment \
  --dataset-config config/cic-iot2023-final.json \
  --experiment-config config/cic-iot2023-final-experiment.json \
  --output-dir ../outputs/cic-iot2023-final-rerun-01
```

The runner refuses an output directory that already exists. It prints the new result JSON path;
pass that path to `python -m app.features.graphs --result <result.json> --output-dir <new-graphs-dir>`
to regenerate the figures without rerunning models.

---

## 8. Random seeds and reproducibility

| Component | Seed mechanism |
|---|---|
| Final data split | Seed 43; the sample row-selection seed is 42 |
| Random Forest | `random_state=42` |
| GA | Per-run `seed` from `seeds` list |
| BPSO | Per-run `seed` from `seeds` list |
| ACO | Per-run `seed` from `seeds` list |
| CIC-IoT2023 row sampling | `random_seed` in `load_cic_iot2023()` |

All algorithms use `numpy.random.default_rng(seed)` isolated generators (not global state).
Given identical seeds and identical data, results are exactly reproducible.

---

## 9. Metrics and equations

**Macro-F1** (primary metric):

$$F1_{macro} = \frac{1}{C} \sum_{c=1}^{C} F1_c = \frac{1}{C} \sum_{c=1}^{C} \frac{2 \cdot P_c \cdot R_c}{P_c + R_c}$$

**Accuracy:**

$$\text{Accuracy} = \frac{\text{correct predictions}}{\text{total predictions}}$$

**Feature reduction:**

$$\text{reduction\\%} = 100 \times \left(1 - \frac{n_{selected}}{n_{eligible}}\right)$$

All metrics use `zero_division=0`. Class order is sorted and recorded in every run.

---

## 10. Validation vs test metrics

> [!CAUTION]
> Validation metrics are used **only during feature selection** to compute fitness.
> They must not be reported as final performance figures.
> Final test metrics are released only once, after all feature-selection, preprocessing, and model choices are frozen.
> Graphs labelled "Validation Macro-F1" show fitness-recovered validation scores; "Test Macro-F1" shows held-out performance.

---

## 11. Limitations and threats to validity

1. **Dataset scope:** The reported experiment uses a class-capped CIC-IoT2023 sample. Results cannot be directly generalized to production network conditions or server load-balancing scenarios.

2. **Labelling/provenance:** Local targets are derived from folder names and have not been independently matched to row-level ground truth. The local README describes a different, label-bearing combined layout; exact source provenance and the `Benign_Final` mapping remain unresolved.

3. **Stratified random fallback:** If group metadata is unavailable, the stratified split may assign related network flows to different partitions, potentially inflating performance estimates.

4. **Single test evaluation:** Each feature-set configuration is evaluated on the held-out test partition exactly once. One test score is not sufficient evidence of repeatability across datasets or capture environments.

5. **Synthetic evaluation budget:** The `max_model_evaluations` budget is chosen for practical experiment time, not statistically optimal. Larger budgets may yield different feature subsets.

6. **No scaling:** Scaling is omitted because Random Forests are scale-invariant. If a different classifier is added, this assumption should be revisited.

7. **Hardware dependence:** Timing results (optimizer time, RF evaluation time) are hardware-dependent and not portable across machines.

8. **Documentation history:** Older CIC-IDS2017 setup text is not evidence of a CIC-IDS2017 run and must not be used to characterize the current Workstream A experiment.
