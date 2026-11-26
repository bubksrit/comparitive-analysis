# CIC-IDS2017 local data foundation

## Dataset availability in this workspace

On 2026-11-23, the project workspace was searched for CIC-named files and CSV, Parquet, ZIP, 7z, and XLSX data files. **No CIC-IDS2017 dataset files are present in the repository workspace. The real-data audit stage is blocked until the user obtains the official CSV bundle and configures its verified schema.** No data was downloaded or substituted.

## Supported manual download procedure

1. Open the official [Canadian Institute for Cybersecurity CIC-IDS2017 page](https://www.unb.ca/cic/datasets/ids-2017.html).
2. Download the published machine-learning CSV bundle (the official page identifies `MachineLearningCSV.zip`) or the official generated labelled-flow CSV bundle. Do this manually; the application never downloads data.
3. For this CSV audit workflow, extract the selected flow CSV file(s) into the ignored local directory `data/raw/cicids2017/`. Do not use PCAP files for this implementation: packet captures are not CSV flow tables and can be much larger. Retain the archive/source citation and record the retrieval date. The audit records SHA-256 checksums for the CSV inputs.
4. Inspect the actual headers and configure the target name, observed labels/mapping, expected columns, exclusions, and any validated group/time metadata in `backend/config/dataset.example.json` (copy it to a local config if preferred). The example target is intentionally a placeholder.
5. If the selected files contain verified day/scenario groups, configure `group_columns`; if they contain a verified timestamp suitable for chronological partitioning, configure `time_column`. If neither is available/reliable, leave both empty and the audit will use a prominently reported stratified random fallback. The fallback can mix related flows/scenarios.

The official page describes both CSV flow datasets and packet captures and identifies the machine-learning CSV archive. It does not make the local mirror/version/file choice for this project; that remains part of the run manifest. [Official CIC-IDS2017 dataset page](https://www.unb.ca/cic/datasets/ids-2017.html)

### Required local inputs

* At least one extracted CSV from the official labeled flow/ML feature files.
* A configured target-column name that exists exactly once in the CSV header.
* If `expected_columns` is set, the names verified from the selected file; strict checking is optional/configurable.
* For group/time-aware splitting, one or more verified grouping columns or one parseable time column. These are used only for splitting and excluded from model features by default.
* Any additional model-input exclusions explicitly listed with rationale. Identifier, address, port, time, and possible target/leakage columns are heuristically flagged for review, never silently discarded.

Column names and labels are not hard-coded to a presumed CIC-IDS2017 mirror. The audit rejects an absent target and reports the actual observed schema and labels. A source label map, when configured, must cover every observed label.

## Audit and split behavior

The local loader accepts a CSV file or a directory plus glob. Multiple selected files must have exactly matching headers and order. It audits per-column types, missing and infinite values, raw duplicate header names, duplicate rows, constant columns, duplicate-valued columns, class counts, and heuristic identifier/leakage candidates. Duplicate/constant columns and rows are reported but retained. Infinities are counted and then converted to missing values for imputation; no rows are silently removed.

`split_strategy: "auto"` uses configured group columns first, then a configured time column. If neither is configured, it conservatively detects day-like fields named `day`/`captureday` with 3–100 nonmissing values, then parseable columns named like a timestamp/date/time. The auto-detected exact column is reported and excluded from model features. If no such field is found, it uses the stratified-random fallback. Inspect these heuristics and explicitly configure the split for research runs. Group and chronological splits are deterministic. Group splitting keeps combined group keys disjoint but targets group proportions, so row proportions can vary. Time splitting orders unique timestamp values, so class distributions may differ. The exact strategy, group/time columns, seed, partition sizes, and per-partition class counts are saved in reports.

The split object exposes training and validation data to selection/tuning code. Test access requires an explicit `get_test_for_final_evaluation(final_choices_frozen=True)` call. Preprocessing is constructed from training feature names/types only and must be fitted on training data; validation/test data are transformed only.

## Shared Random Forest evaluator

The shared evaluator is in `app.features.evaluator.RandomForestEvaluator`. After loading and auditing a configured dataset:

```python
evaluator = RandomForestEvaluator()
baseline = evaluator.evaluate_full_feature_baseline(dataset_foundation)
candidate = evaluator.evaluate_validation(dataset_foundation, verified_feature_names)
# Do not call the test method during selection or tuning.
final = evaluator.evaluate_final_test(
    dataset_foundation,
    verified_feature_names,
    final_choices_frozen=True,
)
```

The validation and final-test paths both fit the preprocessing+Random Forest pipeline on training rows only. The final test method requires the explicit freeze flag and fits on training rows without using validation or test to fit. Each call writes a JSON run record beneath `output_dir/rf-evaluations/`; it includes the exact feature list, fixed model settings, data checksums, split metadata, target mapping, metrics/support, timings, seed, and software versions. The full-feature baseline uses the same evaluator/settings as a selected subset.

## Run the audit (Windows PowerShell)

From the repository root, first copy the example config and edit it using the verified local headers and labels:

```powershell
Copy-Item backend/config/dataset.example.json backend/config/dataset.local.json
notepad backend/config/dataset.local.json
```

Ensure `data_path` points to your extracted local CSV folder and replace `target_column`. Fill `expected_columns`, `expected_labels`, `label_mapping`, and explicit `excluded_columns` only after inspecting the actual data. Configure verified `group_columns` or `time_column` when supported. If you keep `split_strategy` at `auto` without grouping/time fields, the JSON and Markdown report will label the split `stratified_random_fallback`.

Then run:

```powershell
cd backend
..\.venv\Scripts\Activate.ps1
python -m app.features.audit --config config/dataset.local.json
```

Reports are written to the configured output directory as `audit.json`, `columns.csv`, and `audit.md`. Outputs and downloaded data are ignored by Git. The audit does not train a classifier, select features, or generate research results. CIC-IDS2017 remains the real-data source; synthetic test fixtures are used only by unit tests.
