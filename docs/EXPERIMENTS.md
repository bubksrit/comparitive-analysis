# Experimental Protocol and Decision Register

**Status:** protocol draft. This file records choices supplied or selected for the initial study design; it is not a report of experimental results. No dataset facts are inferred from a filename or assumed from a commonly circulated copy. A final run is blocked until the dataset manifest and unresolved protocol items below are completed.

## 1. Study separation

Study A uses real CIC-IDS2017 records for supervised classification. Study B uses a synthetic discrete-event model for routing. Study B does not replay CIC-IDS2017 as network traffic and does not measure a physical network. Every artifact and visualization must state its source as either `CIC-IDS2017 classification` or `simulated load balancing`.

## 2. Study A — CIC-IDS2017 feature selection

### 2.1 Dataset identity and audit gate

The dataset is CIC-IDS2017, but the exact source URL/provider, release/archive version, download date, checksums, input filenames, target column, actual label values, and label mapping have **not yet been verified**. They must be recorded in a run-specific `DatasetManifest` before analysis. Do not silently combine differently processed mirrors or file variants.

The manifest must list every input file and its checksum; row counts; column names and types; target field and mapping from observed source labels to canonical labels; eligible feature columns in exact order; and excluded columns with reason. Candidate exclusion reasons include target/label fields, row identifiers, timestamps used only for grouping, duplicated columns, constants, and fields judged to leak labels or identify capture scenarios. These are audit categories, not assertions that any particular named field exists.

Before splitting, report missing values, positive/negative infinity counts, exact duplicate rows under the declared comparison columns, constant columns, duplicate columns, per-class counts, and possible identifier/leakage fields. Record cleaning actions and counts. Do not use test outcomes to decide exclusions or transformations. Deduplication policy (whether duplicates are removed, and on which columns) remains unresolved pending audit; no rows are removed by default.

### 2.2 Split protocol

Split records before fitting imputation, encoding, or scaling. Preferred protocol is group-disjoint assignment using verified capture day/time and/or attack-scenario metadata, keeping each group wholly within one partition. Record the actual group keys, group-to-partition map, row counts, class counts, and exact assignment seed/rule.

The exact group-aware split cannot be named until source files and metadata are inspected. Planned partition targets are 60% train, 20% validation, and 20% final test by rows, with whole groups assigned to partitions; actual proportions may differ due to group sizes and must be reported. Assignment is deterministic from a recorded seed, with class coverage and group counts audited without moving records based on model scores. If there are too few reliable groups or metadata does not support a defensible grouping, use a stratified random 60/20/20 split with a fixed seed, label it explicitly as a fallback and potentially optimistic because related flows/scenarios may cross partitions. Record why grouping was infeasible. Do not present the fallback as scenario-independent generalization.

The final test partition is sealed until all feature selection, RF settings, preprocessing, and other model choices are frozen. Selectors may evaluate masks only on training/validation data. The shared evaluator fits preprocessing and the classifier on the training partition only, then scores validation or (after the freeze gate) test data without fitting on either. Test labels and metrics must not feed back into choices. A future train+validation refit would require a documented protocol change.

### 2.3 Preprocessing and common classifier

Fit imputation and any encoding only from training data, then apply the fitted transforms to validation and test. Use scaling only if a selected model requires it; Random Forest and the planned mask optimizers do not inherently require feature scaling, so scaling is omitted unless a documented preprocessing/model choice changes that. Any categorical feature handling must be determined from the audited schema and fitted without validation/test information. Record transform parameters and missing/non-finite handling.

Use one common Random Forest evaluator for full-feature, GA, binary PSO, and ACO subsets: identical estimator parameters, class-weight policy, preprocessing, scoring convention, split, random-state policy, and parallelism. The initial fixed settings are `n_estimators=200`, `criterion=gini`, `max_depth=None`, `min_samples_split=2`, `min_samples_leaf=1`, `min_weight_fraction_leaf=0`, `max_features=sqrt`, `max_leaf_nodes=None`, `min_impurity_decrease=0`, `bootstrap=True`, `oob_score=False`, `class_weight=balanced_subsample`, `random_state=42`, `n_jobs=1`, `verbose=0`, `warm_start=False`, `ccp_alpha=0`, and `max_samples=None`. These are configurable as one frozen evaluator configuration, serialized in every run, and must be shared across subsets. A full-feature baseline is mandatory. Validation macro-F1 is the primary classification score; report accuracy, macro precision, macro recall, macro F1, weighted precision/recall/F1, confusion matrix, and support. Use zero-division=0 and record class order/counts.

### 2.4 Fitness, masks, optimizers, and cost accounting

Masks are boolean vectors over the eligible feature columns. Initial fitness is:

```text
fitness = 0.8 * (1 - validation_macro_F1)
        + 0.2 * (selected_feature_count / eligible_feature_count)
```

Lower is better. The initial weights (0.8 predictive performance, 0.2 subset size) are configurable and must be frozen before final test access. Macro-F1 is in [0,1], so both terms are in [0,1]. Record each term as well as total fitness. The search budget, RF settings, preprocessing, and validation protocol must be equal across selectors as far as practical.

Empty masks are invalid and receive worst possible fitness (1.0); the optimizer must repair them to the minimum-size feasible mask before evaluation. Default minimum selected features is 1 and default maximum is all eligible features. These bounds are configurable and recorded. If constraints cannot be satisfied, stop with a configuration error rather than silently changing them.

Optimizer definitions to freeze and record:

* **GA:** seeded random feasible binary initialization; tournament selection; one-point crossover; independent bit-flip mutation; elitism retaining the best feasible individual. Population size and rates are configurable.
* **Binary PSO:** seeded feasible binary positions; real-valued velocities; sigmoid transfer probability `sigmoid(v)` for each bit; sampled bits; standard inertia/cognitive/social velocity update with global-best topology. Coefficients and velocity clamp are configurable.
* **ACO:** seeded pheromone initialization per feature; ants construct masks by sampling each feature from pheromone-derived inclusion probabilities; evaporate and deposit pheromone based on ranked feasible solutions. Evaporation/deposit parameters and pheromone bounds are configurable.

These are initial algorithm choices, not implementation findings. Use deterministic tie-breaking by mask ordering/seed. Stop at a fixed maximum fitness-evaluation budget or configured generation/iteration limit, whichever comes first; optional early stopping requires a frozen patience rule. Record stopping reason and best-so-far trace. To compare fairly, enforce the same maximum number of RF fitness evaluations per selector, counting repeats and re-evaluations; cache identical masks and report both requested and actual fit counts. Full-feature baseline evaluation is reported separately and does not consume selector search budget.

Run stochastic optimizers over multiple seeds. Planned default is 10 seeds per optimizer, configurable before final experiments. If compute constraints reduce repetitions, record the actual count and limitation. Do not report only the best seed: provide per-seed results and aggregate distributions. Use the same validation data and model seed policy for competing selectors; distinct optimizer seeds are recorded.

Report selected count and reduction relative to eligible columns:

```text
reduction_percent = 100 * (1 - selected_feature_count / eligible_feature_count)
```

Record optimizer/search wall time separately from RF fit/evaluation time and preprocessing time, and report total end-to-end elapsed time. Report model evaluation count. Timing includes and excludes must be explicit; record hardware, software, thread/parallel settings, and timestamps.

## 3. Study B — simulated load balancing

### 3.1 Simulator model and units

Use a discrete-event simulator with explicit request arrival, queueing, service start/completion, server availability, failure, and recovery events. Simulation time is seconds; rates are requests/second; service times and latency are seconds; capacity is concurrent service slots per backend; server service rate is requests/second per slot. Each heterogeneous server has configured capacity, service-rate estimate, and optional routing weight. No physical CPU measurement is implied.

Request service demand is generated from a configured distribution and seed. Routing sees only request attributes available at arrival, current time, current server health, configured capacity/rates, active/queued counts, and any explicitly observable remaining-service estimates. It cannot see future arrivals, sampled future service demands, or future failures. Failure state becomes visible only when its event occurs. Failed servers receive no new assignments; behavior when no server is available is to queue up to a configured limit, then mark the request dropped/timed out under the configured deadline rule. The queue, deadline, and request-demand distribution parameters are mandatory run configuration.

### 3.2 Workloads and paired scenarios

Support:

* **Stable:** stationary Poisson arrivals at configurable constant rate.
* **Increasing:** piecewise-linear arrival rate rising from configured start to end rate over the run; arrivals sampled from the resulting non-homogeneous Poisson process.
* **Bursty:** configurable alternating low/high-rate periods or a declared burst process; selected form, rates, durations, and random seed are recorded.

The exact rate values, horizon, server fleet, service demand distribution, and failure schedules are experiment parameters, not hard-coded claims. For each paired comparison, all seven policies receive identical pre-generated arrival times/request attributes, server configurations, sampled service demands, and failure/recovery schedules. Use common random numbers and scenario IDs. Repeat independent scenario seeds; report the number and configuration of scenarios.

### 3.3 Policy definitions and information boundaries

All policies use the same eligible server set and observable context, and must use deterministic, seeded tie-breaking when needed.

1. **Round Robin:** advance a cyclic pointer over currently healthy eligible servers; define pointer behavior when servers fail/recover and when none is available.
2. **Least Connections:** route to healthy server with fewest active plus queued requests; tie-break by seeded server order.
3. **Weighted:** weighted random selection among healthy servers with configured nonnegative weights. Weights are recorded; zero-weight servers are ineligible. This is a routing-weight baseline, distinct from capacity-aware optimization.
4. **Random Forest:** supervised multiclass classifier trained on separate simulator training scenarios. For each training state, label the healthy server with the lowest estimated completion cost using only current observable state and configured server service-rate estimates. Training, validation/tuning, and final test scenario seeds are disjoint. The target is a simulated heuristic/oracle label, not real-world ground truth. If no healthy server exists, use common fallback.
5–7. **GA, PSO, ACO:** optimize candidate routing plans with common objective `J` below, subject to health, capacity, queue, and deadline constraints. They have access to current state only and use the same fallback as other policies.

The optimization objective is:

```text
J = w1 * normalized_response_time
  + w2 * normalized_load_imbalance
  + w3 * request_drop_rate
```

Lower is better. Initial configurable weights are equal (`w1=w2=w3=1/3`), frozen before final runs, and recorded. Normalize response time by a configured response-time reference/SLA `T_ref` and cap at 1: `min(predicted_response_time / T_ref, 1)`. Normalize imbalance as `CV / (1 + CV)`, where `CV` is the coefficient of variation of predicted per-server utilization among healthy servers (0 if no utilization or fewer than two healthy servers). Drop rate is dropped requests divided by requests considered in the candidate plan. Record raw components and normalized components. `T_ref` and objective horizon remain required configuration decisions before final experiments.

**Rolling planning definition:** at each arrival, candidate plans assign the current request and already queued, unassigned requests across currently healthy servers; no future request is added to the plan. The horizon is that finite set of pending requests, re-optimized at each new arrival. Commit only the current request's selected server; prior dispatched work is not moved. Predicted completion uses visible active/queued counts and configured mean service rates, not future sampled service demands. GA, PSO, and ACO must encode this same assignment problem and use the same candidate constraints and objective. This is a planned design; feasibility and encoding details require review before implementation.

Optimizer state persists between arrivals within a run (warm-start population/positions/pheromone where the method supports it); it resets between paired runs. Record update frequency (each arrival), initialization, stopping/evaluation budget, tie-breaking, and fallback. If no feasible plan exists or the optimizer exceeds its decision budget, choose least-connections among healthy servers; if none are healthy, use the common queue/drop rule. Measure wall-clock decision time and model evaluations/iterations per decision; also report simulated/proxied compute overhead separately from modeled server service. Do not imply wall-clock optimizer time is server CPU utilization.

### 3.4 Metrics

Compute from event records and state intervals, in simulation seconds unless otherwise stated:

* **Response time:** completion time minus arrival time for completed requests. Report mean and median plus P95/P99 over completed requests; include completed sample count. Dropped/timed-out requests are excluded from latency quantiles but reported separately.
* **Throughput:** completed requests divided by the fixed measurement-window duration (requests/second), after declared warm-up and before declared drain/end time. Also report completion count and window boundaries.
* **Drops/timeouts:** counts and rate over all offered requests; distinguish overload drops from deadline timeouts if both occur.
* **Server utilization:** busy service-slot time divided by healthy available server-slot time over the measurement window. Report per-server and aggregate `sum(busy slot-seconds) / sum(healthy available slot-seconds)`; exclude unavailable intervals from denominator and report unavailable time separately. This is simulated service utilization, not measured CPU utilization.
* **Load imbalance:** coefficient of variation (population standard deviation divided by mean) of per-server utilization fractions over the window among servers with positive healthy-available time. Report per-server fractions and define zero-mean case as zero; state when no eligible servers exist.
* **Recovery time:** for each failure, elapsed time from server recovery event until system throughput over a rolling configured window again reaches at least a configured fraction of its pre-failure baseline for a configured number of consecutive windows. Baseline window, fraction, window length, and consecutive count must be recorded. Report unrecovered cases as censored/unrecovered, not zero.
* **Policy overhead:** wall-clock time spent selecting routes and optimizer evaluations/iterations, plus any declared compute proxy. Report per-decision and total cost; the simulator's virtual time does not advance due to host wall-clock computation unless an explicit overhead model is configured.

Warm-up, drain, measurement window, request deadlines, and recovery threshold values remain configurable and must be frozen before final comparisons. Simulator assumptions and limitations (arrival/service distributions, queued-work visibility, service-rate estimation, no physical network/CPU effects, and event ordering) accompany results.

## 4. Cross-cutting analysis and run records

Every run records a unique experiment ID, timestamp, seeds, full configuration, code revision if available, Python/package versions, OS/CPU/memory, thread settings, dataset source/checksums or simulation scenario IDs, and all preprocessing/optimizer/policy parameters. Keep exploratory tuning runs separate and clearly marked; freeze settings before final test/scenario evaluation.

For repeated runs report mean, standard deviation, and 95% confidence intervals where appropriate. State the interval method and sample count. For policies compared on shared traces, use paired per-scenario differences. Choose paired statistical tests only after checking the assumptions of the selected test (including difference distribution/independence); report effect estimates and intervals, not only p-values. Do not treat requests within one simulation run as independent experimental replications. For Study A, use seed-level or split-level units appropriate to the design; one held-out test score is not evidence of repeatability across datasets.

No experimental result is present in this document. Claims of improvement require held-out or paired repeated results and disclosed uncertainty.

## 5. Decisions made

* The project has two independent studies and must label real CIC-IDS2017 classification separately from simulated network metrics.
* Study A uses GA, binary PSO, ACO, and a full-feature baseline with a common Random Forest evaluator.
* Study A's primary score is macro-F1; supporting scores include accuracy, macro precision/recall/F1, weighted precision/recall/F1, and confusion matrix.
* Initial Study A fitness weights are 0.8 validation macro-F1 loss and 0.2 selected-feature fraction; lower is better and weights remain configurable.
* Empty masks are invalid, repaired to a feasible non-empty mask, and otherwise penalized at fitness 1.0. Default mask bounds are 1 through all eligible features.
* Split precedes fitted preprocessing; train-only fitting; test is sealed until decisions are frozen; scaling is omitted unless required by a changed method.
* Planned split targets are 60/20/20 with group-aware assignment preferred and an explicitly labeled stratified random fallback if grouping cannot be supported.
* Selector comparisons use a common maximum RF evaluation budget; record fit counts and separate optimizer, RF evaluation, preprocessing, and end-to-end times.
* Planned stochastic repetition default is 10 seeds per feature optimizer; reductions are documented as limitations.
* Study B is a discrete-event model using seconds, req/s, service time, slot capacity, and explicit failure/recovery events.
* Workloads are stationary Poisson, linearly increasing non-homogeneous Poisson, and a declared configurable burst process.
* Paired policy comparisons share traces, server configurations, service demands, and failure schedules.
* RF labels are generated from separate scenarios using minimum estimated completion cost from observable state and configured service-rate estimates; this is a simulated heuristic/oracle target.
* GA/PSO/ACO use the same objective, equal initial weights, rolling pending-work planning, update each arrival, persistent state within run, reset between runs, and least-connections fallback when feasible.
* Metrics and denominators are defined in Section 3.4; simulated utilization is not physical CPU usage.
* Run metadata, uncertainty, paired analysis, and separation of exploratory tuning/final evaluation are mandatory.

## 6. Unresolved decisions and run blockers

### Dataset and Study A

1. Exact CIC-IDS2017 source/provider, release/version, archive/file names, retrieval date, checksums, and actual schema.
2. Verified target column and observed label mapping/canonical class names.
3. Exact eligible columns and excluded columns with evidence/reasons after dataset audit; exact duplicate and deduplication policy.
4. Whether reliable time/day/attack-scenario group fields exist in the chosen files; actual group-disjoint partition mapping and achieved row proportions/class coverage. If not, document evidence for the random-split fallback.
5. RF hyperparameters, class-weight policy, RF random-state policy, zero-division behavior, and exact transformation choices after schema audit.
6. Numeric GA/PSO/ACO parameters, initialization distributions, population sizes, operator rates, pheromone bounds, evaluation budget, early-stopping patience, and final number of repeats if not 10.

### Simulation and Study B

7. Scenario configurations: arrival-rate values, horizon, burst schedule, server fleet/rates/capacities/weights, service-demand distribution, failure/recovery schedules, queue bound, deadlines, and seed list.
8. `T_ref`, rolling objective plan feasibility for queued requests, feature-to-server assignment encoding for each optimizer, and numeric per-decision stopping budget. The proposed rolling plan is conceptual until these are checked against the event model.
9. Warm-up/drain/measurement-window settings and recovery baseline fraction/window/consecutive-window threshold values.
10. RF feature vector/encoding, training-scenario count, validation/tuning protocol, and classifier settings.
11. Whether policy computation overhead remains reporting-only (host wall time/proxy) or is explicitly modeled as simulation delay; default in this draft is reporting-only, with virtual simulation time unaffected.

### Cross-cutting

12. Exact installed Python/package versions and artifact format/versioning. The initial skeleton declares bounded Python dependencies in `backend/pyproject.toml`; platform support beyond the documented local Windows setup remains to be verified.
13. Confidence-interval and statistical-test procedures selected after the final experimental unit and sample size are established.

Items 1–6 and 7–10 block defensible final experiments. Until resolved, implementation may be limited to isolated scaffolding and synthetic/unit examples, not a claimed CIC-IDS2017 or comparative evaluation.
