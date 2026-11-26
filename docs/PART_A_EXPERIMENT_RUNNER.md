# Unified Part A experiment runner

`app.features.experiment.run_part_a_experiment` runs the full-feature Random Forest
baseline and the GA, Binary PSO, and ACO selectors against one `DatasetFoundation`. All
selectors share its frozen training/validation/test split, the eligible feature list,
Random Forest settings, fitness weights, feature-count bounds, and unique evaluation
budget. The runner rejects configuration drift across selectors.

## Evaluation order and test isolation

The runner first evaluates the full-feature baseline on validation, then runs every
selector for every configured seed using validation-only fitness. Once all candidates
and configs have returned, it evaluates the baseline and each finalized selector subset
on the test partition exactly once. Test metrics are reported after the choices are
frozen and are not used for optimizer fitness, hyperparameter selection, or seed choice.
Selector validation macro-F1 is recovered from its stored fitness and selected-feature
count using the approved fitness equation, avoiding another model fit.

Each individual selector writes its JSON artifact. The shared evaluator writes baseline
and final-test evaluation artifacts. The runner writes one experiment JSON summary and a
row-oriented CSV summary with distinct validation and final-test columns. The JSON also
contains the dataset report, source metadata, split description, full per-run configs,
individual artifact paths/IDs, software versions, execution environment, and seed list.

For each algorithm and numeric summary metric, the runner reports a mean. With at least
two stochastic runs it also reports sample standard deviation and a two-sided 95%
Student-t confidence interval. A single baseline observation has no standard deviation or
confidence interval. These intervals summarize seed-to-seed variability on this fixed
split; they do not represent uncertainty across independently sampled datasets.

## Run locally

From `backend/`, use `run_part_a_experiment(dataset, config)` in Python after loading and
auditing the local CIC-IDS2017 files. Configured seed lists and per-algorithm budgets are
stored in the summary. A small synthetic integration check is available with:

```powershell
py -m app.features.benchmark_experiment
```

The benchmark uses only the clearly named synthetic fixture and is software verification,
not CIC-IDS2017 research evidence. It writes artifacts to a temporary directory unless an
output directory is supplied.
