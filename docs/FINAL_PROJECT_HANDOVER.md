# Final Project Handover

- **Repository:** [bubksrit/comparitive-analysis](https://github.com/bubksrit/comparitive-analysis)
- **Project:** Intelligent Network Load Balancing Research
- **Scope:** Workstream A classification and Workstream B simulated load balancing

## 1. Project overview and objectives

This repository contains two related but methodologically separate research workstreams:

- **Study A — intrusion classification:** evaluate GA, BPSO and ACO feature selection using a shared Random Forest (RF) classifier on a CIC-IoT2023 development sample.
- **Study B — simulated load balancing:** compare Round Robin, Least Connections and capacity-aware Weighted routing in a discrete-event simulation.

Study A measures classification outcomes on a sampled dataset. Study B measures outcomes from a model of arrivals, service slots, queues and failures. Study B is not a physical network deployment; Study A does not measure load-balancer performance. Keep these datasets, metrics and conclusions separate in presentations and future publications.

## 2. Study A — CIC-IoT2023 feature selection

### Dataset and method

CIC-IoT2023 is the faculty/team-approved dataset choice for Workstream A. The local loader derives the 34-class target from the parent folder name because the audited CSV files do not have a label column. The final development sample is documented as 160,578 rows, capped at 5,000 rows per folder with sampling seed 42. This cap changes the source class distribution.

The final documented split uses seed 43: **96,305 training, 32,175 validation and 32,098 test rows**. Identical eligible feature vectors were grouped into one partition, which does not establish capture- or session-independent evaluation. The final experiment used a shared 50-tree RF configuration (`max_features=sqrt`, `class_weight=balanced_subsample`, `random_state=42`, `n_jobs=1`). GA, BPSO and ACO each used selector seeds 42, 43 and 44 with a limit of 12 unique validation RF evaluations per seed. The common fitness objective weights validation macro-F1 at 0.8 and selected-feature proportion at 0.2.

### Documented results

The table reports the final development results recorded in the [Workstream A handover](WORKSTREAM_A_HANDOVER.md). Selector intervals are Student-t 95% intervals over three selector seeds on one fixed sample and split.

| Method | Test macro-F1 | Reported 95% interval or note | Test accuracy | Mean selected features |
|---|---:|---:|---:|---:|
| Full-feature RF | 0.6296 | Three identical deterministic repeats; interval not meaningful | 0.6593 | 39/39 |
| GA + RF | 0.5806 | 0.5278–0.6333 | 0.6114 | 15.0/39 |
| BPSO + RF | 0.6013 | 0.5579–0.6447 | 0.6313 | 18.3/39 |
| ACO + RF | 0.5771 | 0.4906–0.6637 | 0.6085 | 15.0/39 |

Seed-aligned macro-F1 changes versus the baseline were GA −0.0490 (95% CI −0.1018 to 0.0037), BPSO −0.0283 (−0.0717 to 0.0151), and ACO −0.0525 (−0.1390 to 0.0341). Each interval includes zero. With three optimizer seeds and one fixed split, the comparison is inconclusive; it does not establish equivalence or broad generalization.

### Dataset and reproducibility limitations

- The exact provenance and release identity of the local source files are unverified. The local README, audited CSV structure and published feature information have unresolved differences.
- Labels are folder-derived proxies, not independently verified row-level ground truth. The `Benign_Final` to `Benign` normalization is plausible but unverified.
- Dataset approval records the selection decision only; it does not verify source, schema, labels or results.
- The global exact-duplicate scan is incomplete and has no valid global duplicate total. Duplicate counts available for the prepared sample apply only to that sample.
- **The dataset, prepared sample/manifest, and generated final run artifacts are unavailable in this checkout.** The documented real-data results have not been independently reproduced from this final checkout.

## 3. Study B — discrete-event load-balancing simulation

### Model, policies and configuration

The simulator gives requests a common FIFO waiting queue and routes each queue head when a service slot becomes available. The default heterogeneous fleet has three servers with 2, 4 and 6 slots, respectively; every slot processes 10 work units/second. Default request work demand is exponential with mean 1 work unit. Service time is demand divided by the selected server's per-slot processing rate.

The three implemented policies are:

- **Round Robin:** cycles through eligible healthy servers with free slots.
- **Least Connections:** selects the eligible server with the fewest active requests.
- **Weighted:** selects the eligible server with the lowest estimated outstanding work normalized by its effective capacity. This is capacity-aware workload balancing, not weighted-random selection.

All policies in a paired replication receive the same generated arrivals, service demands and failure schedule. The standard protocol uses 10 replications from master seed 42. The arrival horizon is 600 seconds; the first 60 seconds are warm-up, measured outcomes use arrivals in `[60,600)`, and a 60-second drain follows arrival generation. The shared queue limit is 1,000 requests and the deadline is 30 seconds. These are simulated workload and server-state values, not hardware measurements.

### Four documented workload scenarios

| Scenario | Configuration |
|---|---|
| Stable | 60 requests/second throughout the arrival period; no failure in the stable baseline. |
| Increasing Traffic | Linear arrival-rate ramp from 30 to 150 requests/second over the 600-second arrival period. |
| Server Failure | Stable workload with `server-2` failing at simulation time 300 seconds and recovering at 360 seconds. |
| Bursty | 30 requests/second for 45 seconds, then 150 requests/second for 15 seconds, repeating on a 60-second cycle. |

The failure schedule is a configuration applied to the arrival workload, rather than a separate arrival-process distribution. All failure times are relative to simulation start. In-flight requests on a failing server are dropped; queued requests remain in FIFO order; a recovered server returns idle.

### Dashboard and metrics

The React dashboard submits runs to FastAPI, polls status/progress, supports cancellation, and retrieves completed results. It displays configuration and seed provenance and comparisons for:

- Mean, median, P95 and P99 response time, plus completion throughput.
- Per-server utilization and request distribution/dispatch share.
- Queue-overflow, server-failure drops and timeouts.
- Load-imbalance coefficient of variation.
- Recovery duration and absolute recovery timestamp, separate from scheduled recovery time.
- Policy decision count and total, mean, median, P95, P99 and maximum decision overhead.

CPU values are labeled as a simulated busy-slot proxy. The project does not report actual CPU or memory measurements. The detailed metric definitions and API schemas are recorded in [EXPERIMENTS.md](EXPERIMENTS.md) and `backend/app/models/simulation.py`.

### Documented results

The following are exported replication-summary means from [Study B RESULTS.md](results/RESULTS.md); full per-policy intervals and figures are there. Latency, P95 and throughput values are nearly identical across policies in these exports. The displayed P95 is the mean of per-replication P95 values, not a pooled-request percentile.

| Scenario | Mean response time (s), RR / LC / Weighted | Mean P95 latency (s), RR / LC / Weighted | Throughput (req/s), RR / LC / Weighted |
|---|---|---|---|
| Stable | 0.1002 / 0.1002 / 0.1002 | 0.2996 / 0.2996 / 0.2996 | 59.897 / 59.897 / 59.897 |
| Increasing Traffic | 1.9380 / 1.9380 / 1.9380 | 8.4486 / 8.4486 / 8.4486 | 93.536 / 93.536 / 93.536 |
| Server Failure | 0.1019 / 0.1019 / 0.1019 | 0.3026 / 0.3026 / 0.3026 | 59.893 / 59.893 / 59.894 |
| Bursty | 1.3213 / 1.3213 / 1.3213 | 3.6478 / 3.6478 / 3.6478 | 59.896 / 59.896 / 59.896 |

Weighted's load-imbalance CV is lower in every exported scenario:

| Scenario | Round Robin | Least Connections | Weighted |
|---|---:|---:|---:|
| Stable | 0.2143 | 0.2914 | 0.1300 |
| Increasing Traffic | 0.0688 | 0.0992 | 0.0469 |
| Server Failure | 0.1969 | 0.2702 | 0.1294 |
| Bursty | 0.1461 | 0.1742 | 0.0860 |

Weighted therefore shows lower utilization dispersion in these simulation summaries, but the results do not show a meaningful latency or throughput advantage. Its mean route-decision overhead is higher in each workload: 6.012 μs (Stable), 5.233 μs (Increasing), 5.514 μs (Server Failure) and 7.069 μs (Bursty). Loss rates are 0% in Stable and Bursty, about 2.5272% for all policies in Increasing Traffic, and 0.0068% / 0.0074% / 0.0062% (RR / LC / Weighted) in Server Failure.

The raw exports contain aggregate summaries for 10 samples per policy/workload but omit per-replication data, paired differences, seed/trace identifiers and complete run configuration. Per-policy 95% intervals are reported in `RESULTS.md` using 10,000-resample percentile bootstrap summaries. The available separate policy intervals cannot reconstruct paired tests. No statistical significance, formal paired difference or equivalence claim is made here.

## 4. System architecture and technology

- **Backend:** Python, FastAPI, Pydantic, NumPy, pandas, scikit-learn and SciPy. `backend/app/api/` contains the simulation endpoints; `backend/app/simulation/` contains independent workload, policy, state, event-engine, metrics, comparison and run-lifecycle modules. `backend/app/features/` contains the Study A data, evaluator, selectors and experiment runner.
- **Frontend:** React and TypeScript, Vite, Recharts and Tailwind CSS. API calls are in `frontend/src/services/simulationApi.ts`; shared response types are in `frontend/src/types/api.ts`; dashboard components are in `frontend/src/features/simulation/`.
- **Run lifecycle:** `POST /api/v1/simulations` starts a run; `GET /api/v1/simulations/{run_id}` returns status/progress; `GET /api/v1/simulations/{run_id}/results` returns complete results; `DELETE /api/v1/simulations/{run_id}` requests cancellation. The run registry is single-process and in-memory. It does not use SQLite or durable storage, and run records/results do not survive backend restart. The dashboard can restore a saved run ID after a browser refresh only while the backend still retains that record.
- **Study A execution:** The feature-selection experiment is a Python runner/CLI workflow, not a dashboard workflow. No Study A simulation API is provided.

## 5. Automated and manual verification record

The project verification record supplied for this handover is:

- Backend suite: **197 passed in 38.20 seconds**.
- Frontend automated tests: **4 passed**.
- Frontend lint, TypeScript typecheck and production build: **passed**.
- Manual end-to-end checks: live dashboard/API connection, simulation submission/execution, results display, refresh recovery and cancellation were verified.

These counts describe the supplied final verification record. They do not establish reproduction of Study A's real-data experiment in this checkout.

## 6. Installation and launch (Windows PowerShell)

Prerequisites: Python 3.12 (3.11–3.13 supported), Python Launcher for Windows, and Node.js 20 or newer with npm.

From the repository root, start the backend in one PowerShell window:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second PowerShell window, start the frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Open the local address printed by Vite. Its development server proxies `/api` to `http://127.0.0.1:8000`; `frontend/.env.example` documents optional API URL settings. Verify API availability with:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Run checks from the repository root:

```powershell
cd backend
python -m pytest
python -m ruff check app tests
cd ..\frontend
npm test
npm run lint
npm run typecheck
npm run build
```

To regenerate the Study B report tables and six SVG figures from the committed raw exports:

```powershell
cd ..
python docs/results/analyze_results.py
```

Study A experiment commands and their local-data prerequisites are in [WORKSTREAM_A_HANDOVER.md](WORKSTREAM_A_HANDOVER.md). The CIC-IoT2023 raw dataset and generated Study A artifacts are not included in this checkout, so those commands require separately supplied local data and a fresh output directory.

## 7. Repository and key artifacts

- GitHub: [https://github.com/bubksrit/comparitive-analysis](https://github.com/bubksrit/comparitive-analysis)
- Main protocol and decision record: [docs/EXPERIMENTS.md](EXPERIMENTS.md)
- Study A report and handover: [WORKSTREAM_A_RESEARCH.md](WORKSTREAM_A_RESEARCH.md), [WORKSTREAM_A_HANDOVER.md](WORKSTREAM_A_HANDOVER.md)
- Dataset approval and technical caveats: [CIC-IoT2023 approval record](audits/CIC-IoT2023_DATASET_AUDIT.md), [provenance/ground-truth audit](audits/cic_iot2023_provenance_and_ground_truth.md), [duplicate audit status](audits/cic_iot2023_duplicate_audit_status.md)
- Study B result tables and interpretation: [docs/results/RESULTS.md](results/RESULTS.md)
- Study B raw source exports: `docs/results/raw/{stable,increasing,failure,bursty}_results.json`
- Study B figures: `docs/results/figures/` — mean response time, P95 latency, throughput, load-imbalance CV, request-loss rate and mean decision overhead.
- Study B regeneration script: `docs/results/analyze_results.py`.
- Study A configurations: `backend/config/cic-iot2023-final.json` and `backend/config/cic-iot2023-final-experiment.json`. Dataset files, sample/manifest and generated run outputs are local-only and absent here.

## 8. Known limitations and future improvements

### Known limitations

1. Study A's real-data result files and dataset are unavailable in this final checkout; the reported results have not been independently reproduced here.
2. CIC-IoT2023 source provenance, local schema correspondence, folder-derived ground truth and the `Benign_Final` normalization remain unverified. Dataset approval does not resolve these technical issues.
3. Study A uses a class-capped sample, one final split and three selector seeds. The fixed split/RF setting and small search budgets limit statistical generalization.
4. The exact global duplicate audit did not finish; no global duplicate total is available.
5. Study B is a discrete-event simulation. It is not a physical network deployment or hardware CPU/memory measurement.
6. Study B aggregate exports do not support reconstruction of paired statistical tests or independent verification of trace pairing.
7. Backend run records and results are process-local and are lost on backend restart or terminal-record eviction. This deployment design is for a local single process, not a durable multi-worker job service.

### Future improvements

- Preserve and checksum the precise CIC-IoT2023 source package, obtain a row/file label manifest, reconcile schema differences, and complete the run manifest before making stronger Study A claims.
- Retain the prepared sample, split manifest and final Study A JSON/CSV/selector artifacts with code revision and environment metadata in an appropriate research archive; rerun and independently verify the final experiment when data access is available.
- Increase Study A selector seeds and evaluate additional independently justified splits or datasets; keep test data sealed during selection.
- Export Study B per-replication metrics, trace/seed IDs, paired policy deltas and full configuration so paired uncertainty can be independently reconstructed.
- If long-lived or multi-process service is needed, design and validate a durable job/result store and worker architecture. No such persistence is present now.
- Consider a physical testbed study only as a separately designed validation effort with actual instrumentation and a distinct protocol.
- Treat any later Random Forest routing policy as a separate Study B model with its own training target and evaluation protocol; GA/BPSO/ACO remain Study A feature selectors unless scope is explicitly changed.
