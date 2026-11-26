# Architecture and Experimental Plan

## 1. Scope and separation

The project contains two separate experiments:

* **Study A — real-data classification:** select CIC-IDS2017 feature subsets with GA, binary PSO, and ACO; evaluate them and a full-feature baseline using the same Random Forest pipeline.
* **Study B — simulated routing:** compare seven load-balancing policies in a reproducible discrete-event simulator.

Study A results describe classification on CIC-IDS2017. Study B results describe simulated network behavior. They are different evidence sources and must remain separately labeled in APIs, charts, tables, exports, and the paper. The simulator is not a real network measurement. No results are claimed until experiments have run. Dataset release, file names, schema, label map, and resulting feature allowlist are intentionally not guessed; the run must be blocked until these are audited and recorded.

The detailed protocol, definitions, assumptions, decisions, and unresolved items are in [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

## 2. Proposed architecture

```text
React + TypeScript + Tailwind + Recharts
  └─ typed API client and request/response models
       └─ FastAPI routes (validation/orchestration only)
            ├─ Study A: dataset audit/split → common RF evaluator
            │          → GA / binary PSO / ACO selectors → metrics/artifacts
            └─ Study B: workload + heterogeneous servers → discrete-event engine
                       → RR / LC / weighted / RF / GA / PSO / ACO
                       → metrics/artifacts
```

Algorithms remain independent from HTTP and UI code. Modules exchange typed configuration and result objects. Runs record experiment ID, seed(s), configuration, software versions, hardware, timestamps, and data/simulation provenance. Begin with a local Python runner and JSON/CSV artifacts; add FastAPI and the React UI after the experiment core and schemas are stable. Long runs should use background jobs if exposed through HTTP.

## 3. Proposed folder structure

```text
backend/
  app/main.py                 # FastAPI application and health endpoint
  app/api/                    # future schemas and endpoints
  app/core/                   # validation, seeds, experiment manifests
  app/features/
    data.py                   # source manifest, audit, split
    preprocessing.py          # train-fitted preprocessing
    evaluators.py              # shared RF pipeline and classification metrics
    selection/                 # mask contract, GA, binary PSO, ACO
    service.py                 # Study A orchestration
  app/simulation/
    models.py                  # requests, servers, workload and event state
    engine.py                  # discrete-event mechanics
    workloads.py               # stable, increasing, bursty arrivals
    policies/                  # seven routing policies
    metrics.py                 # Study B definitions and aggregation
    service.py                 # paired scenario orchestration
  app/results/                 # run manifests and result artifacts
frontend/                      # React/TypeScript/Tailwind/Recharts shell
docs/
  EXPERIMENTS.md               # protocol, decision log, unresolved items
```

## 4. Module interfaces

### Study A

* `DatasetManifest`: exact source/release, checksums, input files, target, label map, eligible/excluded columns, and audit outcomes. The dataset path is local configuration; data is not silently downloaded or modified.
* `FeatureDataset`: names and train/validation/test partitions plus split provenance. Test data is inaccessible to feature fitness evaluation.
* `SelectionConfig`: algorithm, seed, initialization and operator parameters, stopping/evaluation budget, fitness weights, and selected-feature bounds.
* Selector contract: input feature count and training/validation-only fitness callback; output boolean mask, trace, number of model evaluations, and optimizer wall time. Enforce non-empty masks and configured feature bounds.
* `FeatureResult`: selected names/count/reduction, validation fitness, held-out metrics, optimizer time, RF fit/evaluation time, total time, seed, split and run provenance.

The shared evaluator owns preprocessing, RF parameters, folds/split, scoring, and metric conventions. The full-feature baseline and each selected subset use identical settings. Test data is used only for final reporting after choices are frozen.

### Study B

* `SimulationConfig`: seed, duration/request count, explicit time units, workload, server capacities/service model, failures/recovery, queue/deadline rules, metric window, and policy parameters.
* `RequestContext`: arrival time, request attributes available at arrival, observable queue and active counts, server health/capacity, and current time. No future arrivals or failure schedule is visible to a policy.
* `RoutingPolicy.choose_server(context)`: returns a healthy server or documented drop/fallback decision and measured/proxied decision cost.
* `SimulationResult`: request outcomes, server state/utilization series, transitions, policy overhead, metrics, shared-trace/scenario IDs, and run configuration.

RF uses separate simulated training scenarios and a heuristic target: choose the server with the lowest estimated completion cost using current observable state and configured service-rate estimates. It is a simulated heuristic/oracle label, not real-world ground truth. GA, PSO, and ACO use the same configurable objective and constraints; their rolling decision horizon and encoding are specified in the experiment protocol.

## 5. Development roadmap

1. **Protocol freeze:** resolve the blocking items in `docs/EXPERIMENTS.md`; validate a real dataset manifest and simulator assumptions before implementing experiment algorithms. The approved repository skeleton, typed models, and health endpoint may be built before those facts are known.
2. **Local foundations:** implement dataset audit/splitting and deterministic simulator/event model as independent modules.
3. **Shared evaluation:** implement the leakage-safe RF pipeline/full-feature baseline and the simulator/metrics; validate on hand-computable examples.
4. **Algorithms:** add and inspect GA, binary PSO, ACO feature selectors behind the same mask contract; then add RR, least connections, weighted, RF, GA, PSO, and ACO routing policies.
5. **Experiments:** add paired/repeated runs, manifests, exports, and uncertainty summaries; keep exploratory tuning separate from final evaluation.
6. **Product interface:** expose validated configurations/results with FastAPI, then build the two distinct UI workflows.
7. **Research release:** reproduce results from manifests, review artifacts, document limitations, and draft the IEEE paper from actual outputs.

Do not implement application features until the protocol blockers are resolved. Do not fabricate results.
