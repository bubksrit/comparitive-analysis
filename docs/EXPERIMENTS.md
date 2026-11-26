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

### 3.0 Scope and methodology change record

The initial Study B implementation compares exactly three traditional policies: Round Robin, Least Connections, and capacity-aware Weighted Load Balancing. Random Forest is a later extension and is excluded until its separate simulation model, training target, and evaluation protocol are approved. GA, BPSO, and ACO remain feature-selection methods in Study A; they are not routing policies in this initial Study B scope. Adding any further routing policy requires an explicit scope and protocol revision.

**Explicit methodology change (approved 2026-11-27):** an earlier draft defined Weighted as random selection proportional to configured routing weights. That method is superseded for the initial Study B comparison by capacity-aware workload balancing, matching the project owner's approved prototype definition. This is a methodological change, not a wording-only edit. The initial policy selects the eligible server with the smallest estimated outstanding work divided by its effective processing capacity. The prior weighted-random policy is not part of the initial experiment. It may only be reintroduced later as a separately named baseline after protocol review. The existing `routing_weight` field is not used by the initial capacity-aware policy and should be deprecated or reserved rather than silently affecting results.

### 3.1 Simulator model and units

Use a discrete-event simulator with explicit request arrival, shared-queue wait, service start/completion, server availability, failure, and recovery events. Simulation time is seconds. Each server has a positive integer number of concurrent service slots and a positive service rate in work units/second/slot. Each request is served on one slot at a time. If its pre-generated work demand is `d` work units and the selected server's per-slot rate is `r` work units/second/slot, its service duration is exactly `d / r` seconds. The sampled service duration excludes queue waiting; response time is arrival-to-completion and therefore includes queue waiting. Exponential demand uses mean 1 work unit; deterministic diagnostic demand is 1 work unit. Effective processing capacity is `capacity_slots * service_rate_per_slot_per_second` in work units/second. This separates request size from heterogeneous server speed and makes the workload-to-capacity score dimensionally meaningful.

Requests wait in one shared, FIFO load-balancer queue until a healthy server has a free slot; the selected policy chooses the destination at dispatch time. This avoids policy-specific per-server queue placement and gives every policy the same waiting line. The queue has a configured global bound. Requests beyond that bound are dropped as queue-overflow drops. A configured end-to-end deadline starts at arrival; a request that has not completed by its deadline is timed out and removed from the shared queue or service. Completion at exactly the deadline counts as completed. Routing sees server health, configured capacities/rates, active request counts, and the shared queue depth, but not future arrivals or sampled service demands. It uses the configured mean demand when estimating workload. Failure schedules are visible only when their events occur.

CPU and memory are not physical measurements. The initial simulator may report a **simulated CPU proxy** equal to occupied service slots divided by configured slots. No memory-utilization value is reported in v1 because this model has no request-memory demand or memory capacity; adding a memory proxy requires an explicit model and configuration instead of an invented percentage.

### 3.2 Workloads and paired scenarios

The common default fleet has three heterogeneous servers:

| Server | Service slots | Rate per slot | Effective capacity |
| --- | ---: | ---: | ---: |
| `server-1` | 2 | 10 work units/s | 20 work units/s |
| `server-2` | 4 | 10 work units/s | 40 work units/s |
| `server-3` | 6 | 10 work units/s | 60 work units/s |

The default service-demand distribution is exponential with mean 1 work unit. A deterministic demand of 1 work unit is available as a test/diagnostic option, not as the confirmatory default. Request demand is sampled once per scenario trace and reused for every policy. The default shared queue limit is 1,000 requests and the default request deadline is 30 seconds.

The simulation clock starts at `t=0`. Generate arrivals only during the 600-second half-open interval `[0,600)`; the arrival process is stopped at `t=600`. The first 60 seconds `[0,60)` are warm-up: arrivals and service during warm-up affect server state and queues, but warm-up arrivals are excluded from measured request-outcome metrics. The measured arrival cohort is `[60,600)`, a 540-second measurement interval. After arrival generation stops, run a 60-second drain `[600,660]` with no new arrivals so remaining requests can complete or hit their 30-second deadline. Drain completions count toward the measured cohort's completion and throughput metrics; drain service time is excluded from the utilization measurement window `[60,600)`. All failure and recovery timestamps are absolute simulation times measured from `t=0`, not offsets from warm-up or the measurement window. Thus the canonical failure at `300 s` and recovery at `360 s` occur 300 and 360 seconds after simulation start. Increasing traffic ramps linearly from 30 requests/second at `t=0` to 150 requests/second at `t=600` over the full 600-second arrival period; arrivals are still generated only before `t=600`.

Support these reproducible arrival processes:

* **Stable:** stationary Poisson arrivals at 60 requests/second.
* **Increasing:** a linearly increasing non-homogeneous Poisson rate from 30 to 150 requests/second over the 600-second arrival horizon.
* **Bursty:** alternating Poisson rates of 30 requests/second for 45 seconds and 150 requests/second for 15 seconds, repeating on a 60-second period.

These defaults yield an aggregate mean service capacity of 120 requests/second under mean demand 1. The stable and burst-average rates are 50% of that capacity, while increasing traffic and burst peaks exceed it. Defaults are reproducible scenario parameters, not claims about a physical network. They remain configurable and must be serialized with every run.

For a confirmatory comparison, run 10 independent scenario replications derived deterministically from master seed 42 using NumPy `SeedSequence`. Each replication produces one immutable trace containing arrival times, request IDs/attributes, sampled service demands, and failure/recovery events. Replay that exact trace, server fleet, and configuration for all three policies (common random numbers). Keep independent RNG streams for trace generation and any policy tie-breaking so policy behavior cannot change later trace values. A quick interactive run may request one replication, but it must be marked exploratory. Report paired per-scenario results; requests within a replication are not independent experimental samples.

The default baseline has no failures. A canonical recovery scenario uses the same workload and fleet, with `server-2` unavailable from 300 through 360 seconds. Failure times are part of the shared trace/configuration. At a shared timestamp, process service completions first, then failure/recovery transitions, then deadline expirations. Next dispatch the existing FIFO queue into the slots that remain available. Process arrivals at that timestamp in generated request-ID order; after each arrival is admitted or dropped, dispatch FIFO requests into any remaining eligible slots. Thus a service completing exactly at its deadline succeeds, and an arrival exactly at failure time sees the server as unavailable. These event-order rules are deterministic and recorded.

### 3.3 Policy definitions and information boundaries

All policies receive the same request stream. The shared queue is strict FIFO: only its head request may be dispatched, so no policy can bypass an older waiting request. A server is eligible only if it is healthy and has at least one free service slot. When a slot becomes available, dispatch the FIFO head to the server selected by the policy, then recompute eligibility and select again for the next head while both queued requests and eligible slots remain. If there is no eligible server, leave the queue in place until a completion or recovery creates a slot. A newly arriving request joins the tail and is dispatched immediately only if it is now the FIFO head and a slot is available.

The policies use the following exact rules:

1. **Round Robin:** maintain a cursor in the configured server order. Starting at the cursor, scan forward cyclically and select the first eligible server. After selection, move the cursor to the configured position immediately after that server. Skip ineligible servers without changing their order. If none is eligible, make no selection and leave the cursor unchanged. Recovery does not reset the cursor.
2. **Least Connections:** among eligible servers, minimize the number of currently active requests on the server. The shared waiting queue is unassigned and is not counted against any server. If multiple eligible servers tie, choose the first in a deterministic server ordering generated from that scenario's tie-breaking seed.
3. **Weighted Load Balancing (capacity-aware workload):** for each eligible server `i`, calculate `score_i = (mean_request_demand * active_request_count_i) / (capacity_slots_i * service_rate_per_slot_i)`. Choose the eligible server with the smallest score, measured as estimated seconds of accumulated work at full capacity. The shared waiting queue is unassigned and excluded from each server's workload. If scores tie, use the same deterministic seeded server ordering as Least Connections. Recompute scores after every dispatch. This policy does not sample proportionally to `routing_weight` and does not inspect hidden sampled request demands.

All three policies see the same eligibility set and state. They do not see future arrivals or the current request's sampled service demand.

**Common failure model (applied identically to all policies):** at a failure timestamp, first finish any requests whose service-completion events occur at that exact time, per the event-order rule above. Mark the server unavailable so it receives no new dispatches. Fail every remaining in-flight request on that server immediately, count each as a failure drop, and release its slots; do not pause, migrate, or replay those requests after recovery. The shared FIFO queue contains unassigned requests, so it is unchanged by the failure and preserves its order. Requests in that queue remain subject to their original arrival-based deadlines and the common queue-overflow rule. At the configured recovery timestamp, mark the server healthy with all slots idle; dispatch any waiting queue head under the selected policy before admitting later arrivals at that timestamp. If every server is unavailable, continue queueing under the same limit and deadline rules.

**Later Random Forest extension (not in the initial three-policy API):** it must be a separate model trained on simulated states, not the CIC-IDS2017 feature-selection evaluator. Before implementation, approve its observable input features, target labels, separate training/validation/test scenario seeds, tuning protocol, server-selection/fallback logic, inference timing, and comparison design. A reasonable research target to evaluate later is the eligible server with the lowest estimated completion time using only the current observable state and configured service-rate estimates; this is a simulated heuristic label, not real-world ground truth. Do not present this proposal as an implemented or finalized RF method.

GA, BPSO, and ACO are out of initial Study B scope. The optimization objective, rolling planning design, and optimizer settings from the superseded seven-policy draft do not apply to this initial traditional-policy comparison. Their feature-selection use in Study A is unchanged.

The common dispatch rule is to wait if there is no eligible server, not to silently substitute another policy. Queue overflow and deadline expiration are handled identically for every policy and counted separately.

### 3.4 Metrics

Compute from event records and state intervals. Request-outcome metrics use the measurement arrival cohort `[warmup_seconds, workload.duration_seconds)`, including outcomes resolved during the drain:

* **Response time/latency:** completion timestamp minus arrival timestamp for completed requests in the measurement cohort. Report mean, median, P95, P99, and completed count. Queue-overflow drops, failure drops, and timeouts are excluded from latency statistics and reported separately. Empty latency samples produce `null` statistics.
* **Throughput:** number of measurement-cohort requests completed by the end of the drain divided by the 540-second measurement-window duration, in requests/second. This completion-yield measure may include requests completing during drain; report the count and exact window/cohort boundaries.
* **Drops and timeouts:** separately report queue-overflow drops, failure drops, and deadline timeouts, plus total and rate divided by measurement-cohort offered requests. Include warm-up counts separately only as diagnostics.
* **Server utilization:** per-server busy service-slot seconds divided by healthy available service-slot seconds in `[60,600)`. Aggregate utilization is `sum(busy slot-seconds) / sum(healthy available slot-seconds)`. Exclude failed intervals from the denominator and report unavailable seconds. It is a simulated service metric, not CPU utilization.
* **Simulated CPU proxy:** per-server and aggregate busy-slot fraction over the measurement window, calculated from occupied slots divided by configured slots and time-averaged over healthy intervals. Label it “simulated CPU proxy”; never call it hardware CPU measurement. It is closely related to server utilization and must be shown separately only when useful.
* **Memory utilization:** omitted in v1. No memory resource model exists, so report no memory percentage rather than fabricate a proxy.
* **Load imbalance:** coefficient of variation (population standard deviation divided by mean) of per-server utilization fractions for servers with positive healthy-available time. Report each server's fraction. Define the value as zero when the mean is zero; if no eligible server has healthy time, report `null`.
* **Request distribution:** per-server dispatched and completed counts and dispatch share (`server dispatches / all measurement-cohort dispatches`). Report zero share when there are no dispatches.
* **Recovery time:** for each failure, calculate baseline system throughput over the 60 seconds immediately before failure. After the server recovers, calculate system throughput in consecutive, non-overlapping 10-second windows. The threshold is 90% of that pre-failure baseline. Recovery is declared only after throughput is at or above the threshold for three consecutive windows (30 continuous measured seconds). Any window below the threshold resets the consecutive-window count to zero; the system must not remain below the threshold during the qualifying period. Report both recovery duration (elapsed time from the scheduled server recovery timestamp to the end of the third qualifying window) and the absolute recovery timestamp (that window-end simulation time); neither is the scheduled server recovery timestamp. Require a nonzero baseline and 60 seconds of pre-failure data; otherwise report `null` for both recovery fields with a reason. If three qualifying windows are not observed by the end of measurement/drain, mark both values unrecovered (`null`), not zero.
* **Policy decision overhead:** record host wall-clock duration for each route-selection decision and report decision count, total, mean, median, P95, P99, and maximum. Percentiles use linear interpolation. With no decisions, report zero for all aggregate fields. Wall-clock values do not advance virtual time or affect routing outcomes and are not server CPU utilization. Report optimizer evaluations only for a future optimizer extension.

The defaults above may be overridden in exploratory scenarios; every override is part of the run configuration. No physical network, CPU, or memory behavior is claimed. Assumptions and limitations, scenario ID, cohort boundaries, event-order rules, and metric denominators accompany every result.

### 3.5 Initial configuration defaults

| Setting | Default |
| --- | --- |
| Algorithms | `round_robin`, `least_connections`, `weighted` (capacity-aware workload) |
| Default workload | `stable` |
| Master seed / confirmatory replications | `42` / `10` |
| Servers | `server-1: 2 slots`, `server-2: 4 slots`, `server-3: 6 slots`; each `10 work units/s/slot` |
| Request service demand | Exponential, mean `1 work unit` |
| Arrival horizon | `600 s` |
| Warm-up / measurement / drain | `60 s` / `[60,600)` (`540 s`) / `60 s` |
| Queue | One shared FIFO queue, maximum `1,000` waiting requests |
| Request deadline | `30 s` from arrival |
| Stable arrivals | `60 requests/s` |
| Increasing arrivals | Linear `30` to `150 requests/s` over the horizon |
| Bursty arrivals | `30 requests/s` for `45 s`, then `150 requests/s` for `15 s`; repeat every `60 s` |
| Default failure schedule | None |
| Canonical recovery scenario | `server-2` fails at `300 s`, recovers at `360 s` |
| Recovery threshold | 60-second pre-failure baseline; 10-second windows; 90% threshold for 3 consecutive windows |
| RF, GA, BPSO, ACO routing | Excluded from initial Study B |

### 3.6 API contracts and local run lifecycle

The FastAPI simulation API uses a process-local run registry and cooperative cancellation. One worker thread executes paired runs; at most two records may be nonterminal (`queued`, `running`, or `cancelling`). The second accepted run can remain queued. Return HTTP `429` when both slots are occupied. Keep up to the latest 50 terminal records. Registry updates and status snapshots are protected by a lock. The executor is created at application-lifespan startup and joined at shutdown; queued runs become cancelled with a finish timestamp, while running runs receive cooperative cancellation and are joined. Restarting the same app lifespan creates a fresh executor and clears old process-local records. A process restart loses active and stored run records; this is a local single-process design, not a durable job service, and must not be used behind multiple application worker processes.

* `POST /api/v1/simulations` — accept a `SimulationRunRequest` with the `SimulationConfig` fields plus `policies` and `replications`. Policy IDs must be nonempty, unique and limited to `round_robin`, `least_connections`, and `weighted`; replications must be at least one. The default is all three policies and 10 replications. Return HTTP `202` with a unique `run_id`, initial `status: "queued"`, UTC creation time, and zeroed progress. Invalid request/configuration fields return FastAPI validation errors.
* `GET /api/v1/simulations/{run_id}` — return `run_id`, status (`queued | running | completed | failed | cancelling | cancelled`), UTC created/started/finished timestamps, completed and total replications/policy runs, and a safe error code/message when failed.
* `GET /api/v1/simulations/{run_id}/results` — return HTTP `409` until the entire paired run is completed. A completed response contains policy-level per-replication results, paired aggregate means/standard deviations/95% confidence intervals, the full configuration, master and replication seeds, assumptions and metric definitions. Return `404` for unknown/expired IDs and `409` for failed, queued, running, cancelling or cancelled runs without complete results.
* `DELETE /api/v1/simulations/{run_id}` — a queued run transitions directly to `cancelled`; a running run transitions to `cancelling` and stops cooperatively at the next simulation event boundary. Accepted requests return HTTP `202`; cancellation of an already terminal run is idempotent and returns its terminal status.

The simulation engine remains independent of FastAPI. It accepts optional progress and cancellation callbacks; completed-policy progress advances after each complete policy simulation and completed-replication progress advances after all policies for that replication finish. Cancellation is checked between discrete events and policy runs. Host wall-clock route-selection measurements do not advance simulation time or affect routing. Worker exceptions become failed run records and do not terminate the API process. The registry is in-memory, so its records and results do not survive an application restart.

## 4. Cross-cutting analysis and run records

Every run records a unique experiment ID, timestamp, seeds, full configuration, code revision if available, Python/package versions, OS/CPU/memory, thread settings, dataset source/checksums or simulation scenario IDs, and all preprocessing/optimizer/policy parameters. Keep exploratory tuning runs separate and clearly marked; freeze settings before final test/scenario evaluation.

For Study B's 10 paired scenario replications, report per-policy mean and standard deviation and paired per-scenario differences. Report 95% percentile bootstrap intervals from 10,000 resamples of the scenario-level paired units, using a deterministic bootstrap RNG derived from the master seed. Resample whole scenario rows so the three policies remain paired. State the method and sample count. Requests within one simulation run are not independent experimental replications. Treat the 10-seed interval as uncertainty across these simulated scenarios, not as evidence about physical networks. For Study A, use seed-level or split-level units appropriate to that design; one held-out test score is not evidence of repeatability across datasets.

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
* Study B v1 compares Round Robin, Least Connections, and capacity-aware Weighted Load Balancing. Weighted is the minimum estimated outstanding work divided by effective server capacity, with seeded deterministic tie-breaking; this explicitly supersedes the older weighted-random draft definition.
* Study B v1 excludes RF routing until its independent simulated training target and evaluation protocol are approved. GA, BPSO, and ACO remain Study A feature selectors and are not initial routing policies.
* Study B uses a shared FIFO queue, exponential service-demand default, server slot/rate configuration, and explicit failure/recovery events; the default fleet, workload rates, warm-up/drain, deadline, queue bound, and canonical recovery scenario are listed in Section 3.5.
* Stable arrivals are Poisson, increasing arrivals are linearly increasing non-homogeneous Poisson, and bursty arrivals alternate configured low/high Poisson rates.
* Paired policy comparisons replay identical pre-generated arrivals, request IDs/attributes, service demands, server definitions, and failure schedules. Ten scenario replications derive reproducibly from master seed 42.
* Metrics and denominators are defined in Section 3.4. Service utilization and CPU are simulated values/proxies; memory utilization is omitted without a memory model.
* Simulation API contracts and the process-local cancellable run lifecycle are documented in Section 3.6 and implemented for local single-process use.
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

7. RF routing model only if added later: observable features, target generation, training/validation/test scenario counts and seeds, tuning protocol, classifier settings, fallback, and inference-time procedure.
8. Whether a modeled memory proxy should be introduced later; v1 reports no memory percentage.

### Cross-cutting

9. Exact installed Python/package versions and artifact format/versioning. The initial skeleton declares bounded Python dependencies in `backend/pyproject.toml`; platform support beyond the documented local Windows setup remains to be verified.

Items 1–6 block defensible Study A experiments. Study B v1 configuration defaults and metric rules are specified in Sections 3.0–3.6 for project-owner review; they must be accepted before Phase 2 implementation. Item 7 blocks any RF routing extension, not the three-policy traditional simulator. No implementation may claim physical network results.
