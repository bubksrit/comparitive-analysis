# Part A: Ant Colony Optimization feature selection

This module implements ACO for CIC-IDS2017 feature-subset search. It uses the same
validation-only Random Forest evaluator and fitness function as the GA and Binary PSO
selectors. The final test partition is not read by the optimizer.

## Subset construction

Each ant first samples a subset size uniformly from the configured inclusive range
`[min_features, max_features]`, then chooses that many distinct features without
replacement. At each draw, feature `j` has probability proportional to
`tau_j**alpha * eta_j**beta`, where `tau_j` is pheromone and `eta_j` is the heuristic.
The default heuristic is one for every feature, avoiding a prior derived from validation
or test outcomes. A caller may supply a positive heuristic vector to the construction
helper; the experiment runner uses the neutral default. This construction guarantees a
nonempty binary mask within configured feature-count bounds.

## Pheromone update

After an iteration, every trail evaporates and the iteration-best subset receives
reinforcement:

`tau_j <- clip((1 - rho) * tau_j + I(j selected) * Q / (1 + fitness), tau_min, tau_max)`

Here `rho` is the evaporation rate, `Q` is the deposit scale, and lower fitness produces
larger reinforcement. Initial trails, exponents, evaporation, deposit scale, and trail
bounds are recorded in `AntColonyConfig`. Ties are resolved lexicographically by the
binary mask so seeded runs remain deterministic.

## Fitness, budget, and artifacts

The minimization fitness is shared with GA and Binary PSO:

`0.8 * (1 - validation_macro_f1) + 0.2 * (selected_feature_count / eligible_feature_count)`

Weights are configurable but must sum to one. The evaluator is called only with training
and validation data. Unique masks consume `max_model_evaluations`; repeated callback
requests use the run-local cache, increment `fitness_request_count`, and do not refit the
Random Forest. Results record best-so-far fitness per completed colony iteration,
evaluation counts, selector and model-evaluation times, seed/config, split metadata,
dataset provenance, software versions, and a JSON artifact path under `aco-runs/`.

The fixture benchmark is a software check only. It uses synthetic data and is not research
evidence. Run it from `backend/` with `py -m app.features.benchmark_aco`.
