"""Ant Colony Optimization feature selection for Study A."""

from __future__ import annotations

import time
from uuid import uuid4

import numpy as np

from app.features.data import DatasetFoundation
from app.features.evaluator import RandomForestEvaluator
from app.features.selection.genetic import calculate_feature_fitness, software_versions
from app.models.features import AntColonyConfig, AntColonyResult


def construct_binary_subset(
    pheromone: np.ndarray,
    config: AntColonyConfig,
    rng: np.random.Generator,
    heuristic: np.ndarray | None = None,
) -> np.ndarray:
    """Sample a feasible fixed-size subset without replacement.

    The target subset size is uniform between the configured bounds. For each feature,
    desirability is ``pheromone**alpha * heuristic**beta``; a neutral all-ones heuristic
    is used by default so the search has no unvalidated feature prior.
    """
    pheromone = np.asarray(pheromone, dtype=float)
    if pheromone.ndim != 1 or pheromone.size == 0:
        raise ValueError("pheromone must be a non-empty one-dimensional array")
    if not np.isfinite(pheromone).all() or np.any(pheromone <= 0):
        raise ValueError("pheromone values must be finite and positive")
    if heuristic is None:
        heuristic_values = np.ones_like(pheromone)
    else:
        heuristic_values = np.asarray(heuristic, dtype=float)
        if heuristic_values.shape != pheromone.shape:
            raise ValueError("heuristic must match the pheromone vector shape")
        if not np.isfinite(heuristic_values).all() or np.any(heuristic_values <= 0):
            raise ValueError("heuristic values must be finite and positive")

    feature_count = pheromone.size
    maximum = feature_count if config.max_features is None else config.max_features
    if not 1 <= config.min_features <= maximum <= feature_count:
        raise ValueError("Feature constraints must satisfy 1 <= min <= max <= feature_count")
    log_weights = (
        config.pheromone_alpha * np.log(pheromone)
        + config.heuristic_beta * np.log(heuristic_values)
    )
    log_weights -= log_weights.max()
    weights = np.exp(log_weights)
    probabilities = weights / weights.sum()

    selected_count = int(rng.integers(config.min_features, maximum + 1))
    selected_indices = rng.choice(feature_count, size=selected_count, replace=False, p=probabilities)
    mask = np.zeros(feature_count, dtype=np.int8)
    mask[selected_indices] = 1
    return mask


def update_pheromones(
    pheromone: np.ndarray,
    reinforced_mask: np.ndarray,
    fitness: float,
    *,
    evaporation_rate: float,
    deposit_scale: float,
    pheromone_min: float,
    pheromone_max: float,
) -> np.ndarray:
    """Evaporate all trails, then reinforce selected features by ``Q/(1+fitness)``."""
    trails = np.asarray(pheromone, dtype=float)
    mask = np.asarray(reinforced_mask)
    if trails.ndim != 1 or mask.shape != trails.shape:
        raise ValueError("pheromone and reinforced mask must be same-length vectors")
    if not np.isin(mask, [0, 1, False, True]).all():
        raise ValueError("reinforced_mask must be binary")
    if not 0 <= fitness <= 1:
        raise ValueError("fitness must be between 0 and 1")
    if not 0 <= evaporation_rate < 1 or deposit_scale <= 0:
        raise ValueError("invalid evaporation rate or deposit scale")
    if not 0 < pheromone_min < pheromone_max:
        raise ValueError("pheromone bounds must be positive and increasing")

    updated = trails * (1.0 - evaporation_rate)
    updated += mask.astype(float) * (deposit_scale / (1.0 + fitness))
    return np.clip(updated, pheromone_min, pheromone_max)


def run_ant_colony_optimization(
    dataset: DatasetFoundation,
    config: AntColonyConfig | None = None,
    *,
    evaluator: RandomForestEvaluator | None = None,
) -> AntColonyResult:
    """Search feasible feature subsets using validation-only shared RF fitness.

    A colony iteration samples each ant's subset size uniformly, then selects distinct
    features proportional to pheromone/heuristic desirability. The iteration's best ant
    deposits pheromone after global evaporation. Unique masks consume the model-evaluation
    budget; cached callback requests are counted but do not trigger another RF fit.
    """
    settings = config or AntColonyConfig()
    active_evaluator = evaluator or RandomForestEvaluator()
    feature_names = list(dataset.feature_columns)
    feature_count = len(feature_names)
    maximum = feature_count if settings.max_features is None else settings.max_features
    if not 1 <= settings.min_features <= maximum <= feature_count:
        raise ValueError(
            "Configured feature constraints must satisfy "
            f"1 <= min_features <= max_features <= {feature_count}"
        )

    rng = np.random.default_rng(settings.seed)
    started = time.perf_counter()
    fitness_cache: dict[tuple[int, ...], float] = {}
    fitness_request_count = 0
    model_evaluation_count = 0
    model_evaluation_time = 0.0

    def fitness_callback(mask: np.ndarray) -> float | None:
        nonlocal fitness_request_count, model_evaluation_count, model_evaluation_time
        fitness_request_count += 1
        key = tuple(int(bit) for bit in mask)
        if key in fitness_cache:
            return fitness_cache[key]
        if model_evaluation_count >= settings.max_model_evaluations:
            return None
        selected = [name for bit, name in zip(mask, feature_names, strict=True) if bit]
        evaluation = active_evaluator.evaluate_validation(dataset, selected, persist_run=False)
        fitness = calculate_feature_fitness(
            evaluation.metrics.macro_f1,
            len(selected),
            feature_count,
            fitness_performance_weight=settings.fitness_performance_weight,
            fitness_size_weight=settings.fitness_size_weight,
        )
        fitness_cache[key] = fitness
        model_evaluation_count += 1
        model_evaluation_time += evaluation.fit_time_seconds + evaluation.prediction_time_seconds
        return fitness

    pheromone = np.full(feature_count, settings.initial_pheromone, dtype=float)
    best_mask: np.ndarray | None = None
    best_fitness = float("inf")
    best_fitness_trace: list[float] = []
    iterations_completed = 0
    stop_reason = "iterations_complete"

    for _iteration in range(settings.iterations):
        evaluated_ants: list[tuple[float, tuple[int, ...]]] = []
        budget_exhausted = False
        for _ant in range(settings.ant_count):
            mask = construct_binary_subset(pheromone, settings, rng)
            fitness = fitness_callback(mask)
            if fitness is None:
                budget_exhausted = True
                break
            key = tuple(int(bit) for bit in mask)
            evaluated_ants.append((fitness, key))
            if (fitness, key) < (
                best_fitness,
                tuple(best_mask.tolist()) if best_mask is not None else (float("inf"),),
            ):
                best_fitness = fitness
                best_mask = mask.copy()

        if evaluated_ants:
            iteration_fitness, iteration_key = min(evaluated_ants)
            pheromone = update_pheromones(
                pheromone,
                np.asarray(iteration_key, dtype=np.int8),
                iteration_fitness,
                evaporation_rate=settings.evaporation_rate,
                deposit_scale=settings.deposit_scale,
                pheromone_min=settings.pheromone_min,
                pheromone_max=settings.pheromone_max,
            )
            best_fitness_trace.append(best_fitness)
            iterations_completed += 1
        if budget_exhausted:
            stop_reason = "evaluation_budget"
            break

    if best_mask is None:
        raise RuntimeError("ACO did not evaluate any feasible feature subset")
    end_to_end_seconds = time.perf_counter() - started
    selector_seconds = max(end_to_end_seconds - model_evaluation_time, 0.0)
    selected_mask = [int(bit) for bit in best_mask]
    selected_names = [name for bit, name in zip(selected_mask, feature_names, strict=True) if bit]

    artifact_dir = dataset.config.output_dir / "aco-runs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{uuid4()}.json"
    result = AntColonyResult(
        selected_mask=selected_mask,
        selected_feature_names=selected_names,
        best_fitness=best_fitness,
        best_fitness_trace=best_fitness_trace,
        evaluation_count=model_evaluation_count,
        fitness_request_count=fitness_request_count,
        iterations_completed=iterations_completed,
        selector_time_seconds=selector_seconds,
        model_evaluation_time_seconds=model_evaluation_time,
        end_to_end_time_seconds=end_to_end_seconds,
        seed=settings.seed,
        config=settings,
        stop_reason=stop_reason,
        dataset_name=dataset.config.dataset_name,
        dataset_provenance={"input_files": dataset.report["input_files"]},
        split_metadata=dataset.splits.split_details,
        software_versions=software_versions(),
        run_artifact=str(artifact_path),
    )
    temporary_path = artifact_path.with_suffix(".json.tmp")
    temporary_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    temporary_path.replace(artifact_path)
    return result
