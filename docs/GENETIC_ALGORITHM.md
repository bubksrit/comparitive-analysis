# Binary Genetic Algorithm feature selector

The Part A GA implementation is in `backend/app/features/selection/genetic.py`. A chromosome is a binary vector aligned to `DatasetFoundation.feature_columns`; `1` selects the corresponding feature and `0` excludes it. The GA calls only `RandomForestEvaluator.evaluate_validation(..., persist_run=False)` for fitness. It does not request the test partition.

## Fitness and mask constraints

For feasible masks:

```text
fitness = 0.8 * (1 - validation_macro_F1)
        + 0.2 * (selected_feature_count / eligible_feature_count)
```

Lower is better. Both weights are configurable but must sum to 1. Empty masks and masks outside the configured minimum/maximum feature count are repaired by random bit additions/removals using the run's seeded NumPy generator. Malformed masks (wrong length or non-binary values) raise `ValueError`. The mask passed to the evaluator is always non-empty and within bounds.

## Operators and budget

The default GA config uses a population of 20, 20 generations, tournament selection (size 3), one-point crossover with probability 0.8, per-bit mutation probability 0.02, and one elite. Selection can use tournament or roulette; roulette weights are linearly inverted so lower fitness receives greater selection probability. Elites and ties use stable mask-order tie-breaking. Every random operation uses `numpy.random.default_rng(seed)`.

`max_model_evaluations` limits unique masks scored with the RF evaluator. Duplicate masks reuse cached fitness and do not consume additional model fits. The result reports both unique model evaluations and fitness callback requests. The best-so-far trace contains generation 0 (initial population) followed by each completed generation and is non-increasing. `selector_time_seconds` is elapsed GA time minus summed RF fit/prediction time; `model_evaluation_time_seconds` is the sum of the shared evaluator's fit and prediction timings. The result JSON is written under the configured dataset output directory in `ga-runs/`.

## Software-test benchmark (not research evidence)

From `backend/`:

```powershell
py -m app.features.benchmark_ga
```

This command creates a small synthetic CSV in a temporary directory and labels its output `SOFTWARE TEST BENCHMARK ONLY`. It is a quick implementation check, not CIC-IDS2017 evaluation or research evidence.
