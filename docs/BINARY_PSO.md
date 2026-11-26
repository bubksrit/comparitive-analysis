# Binary Particle Swarm Optimization feature selector

The Study A implementation is in `backend/app/features/selection/bpso.py`. Each particle is a binary vector aligned to `DatasetFoundation.feature_columns`: `1` selects a feature and `0` excludes it. BPSO calls the same `RandomForestEvaluator.evaluate_validation(..., persist_run=False)` and the same `calculate_feature_fitness` helper used by GA. It never opens the held-out test partition.

## Update equations and constraints

For particle `i`, feature dimension `j`, and iteration `t`:

```text
v[i,j](t+1) = clip(
    w(t) * v[i,j](t)
    + c1 * r1 * (pbest[i,j] - x[i,j](t))
    + c2 * r2 * (gbest[j] - x[i,j](t)),
    velocity_min,
    velocity_max
)

p[i,j] = sigmoid(v[i,j]) = 1 / (1 + exp(-v[i,j]))
x[i,j](t+1) = 1 if seeded_uniform(0,1) < p[i,j], else 0
```

`r1` and `r2` are independent per-dimension draws from the run's seeded NumPy generator. The default inertia decreases linearly from `w=0.9` to `w=0.4`; default cognitive and social coefficients are `c1=2.0` and `c2=2.0`; default velocity bounds are `[-4,4]`. Every value is configurable and saved in the run config. Initial velocities are sampled uniformly within the bounds. The first configured inertia applies on the first iteration; the final inertia applies on the last when there is more than one iteration.

Sampled positions are projected into the configured feature-count bounds using the same `repair_mask` helper as GA. Empty or undersized positions gain randomly selected bits; oversized positions lose randomly selected bits. Wrong-length or non-binary masks are invalid and raise an error. Personal best updates only on a lower fitness (or a lexicographically smaller mask on a tie); global best is selected from personal bests with the same deterministic tie break.

The shared minimization fitness is:

```text
0.8 * (1 - validation_macro_F1)
+ 0.2 * (selected_feature_count / eligible_feature_count)
```

`max_model_evaluations` limits unique masks scored through the RF evaluator, matching GA's budget semantics. Repeated masks use cached fitness. Results record unique model-evaluation count, callback request count, global-best trace (initial swarm plus each completed/attempted iteration), selector time excluding summed RF fit/prediction time, model-evaluation time, seed, config, provenance, split metadata, and software versions. Each run is written under the configured output directory in `bpso-runs/`.

## Software-test benchmark (not research evidence)

From `backend/`:

```powershell
py -m app.features.benchmark_bpso
```

It creates a temporary synthetic CSV and labels output `SOFTWARE TEST BENCHMARK ONLY`. It is a software check, not CIC-IDS2017 performance or research evidence.
