"""Binary Genetic Algorithm feature selection for Study A."""

from __future__ import annotations

import platform
import time
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from uuid import uuid4

import numpy as np

from app.features.data import DatasetFoundation
from app.features.evaluator import RandomForestEvaluator
from app.models.features import GeneticAlgorithmConfig, GeneticAlgorithmResult


def calculate_feature_fitness(
    validation_macro_f1: float,
    selected_feature_count: int,
    eligible_feature_count: int,
    *,
    fitness_performance_weight: float = 0.8,
    fitness_size_weight: float = 0.2,
) -> float:
    """Calculate the approved minimization objective for one feasible binary mask."""
    if not 0.0 <= validation_macro_f1 <= 1.0:
        raise ValueError("validation_macro_f1 must be between 0 and 1")
    if eligible_feature_count < 1:
        raise ValueError("eligible_feature_count must be positive")
    if not 1 <= selected_feature_count <= eligible_feature_count:
        raise ValueError("selected_feature_count must describe a non-empty feasible mask")
    if abs(fitness_performance_weight + fitness_size_weight - 1.0) > 1e-9:
        raise ValueError("Feature fitness weights must sum to 1.0")
    return float(
        fitness_performance_weight * (1.0 - validation_macro_f1)
        + fitness_size_weight * (selected_feature_count / eligible_feature_count)
    )


def repair_mask(
    mask: Sequence[int] | np.ndarray,
    feature_count: int,
    min_features: int,
    max_features: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Repair a binary mask to feature-count constraints; malformed masks raise errors.

    Empty and out-of-range-size masks are repaired by randomly turning bits on/off until
    the configured count is met. Wrong-length and non-binary masks are programmer errors
    and raise ``ValueError`` rather than being silently reinterpreted.
    """
    chromosome = np.asarray(mask)
    if chromosome.ndim != 1 or chromosome.size != feature_count:
        raise ValueError(f"Chromosome must be one-dimensional with length {feature_count}")
    if not np.isin(chromosome, [0, 1, False, True]).all():
        raise ValueError("Chromosome values must be binary (0 or 1)")
    if not 1 <= min_features <= max_features <= feature_count:
        raise ValueError("Feature constraints must satisfy 1 <= min <= max <= feature_count")

    repaired = chromosome.astype(np.int8, copy=True)
    selected_count = int(repaired.sum())
    if selected_count < min_features:
        candidates = np.flatnonzero(repaired == 0)
        chosen = rng.choice(candidates, size=min_features - selected_count, replace=False)
        repaired[chosen] = 1
    elif selected_count > max_features:
        candidates = np.flatnonzero(repaired == 1)
        chosen = rng.choice(candidates, size=selected_count - max_features, replace=False)
        repaired[chosen] = 0
    return repaired


def _random_chromosome(
    feature_count: int,
    min_features: int,
    max_features: int,
    rng: np.random.Generator,
) -> np.ndarray:
    selected_count = int(rng.integers(min_features, max_features + 1))
    chromosome = np.zeros(feature_count, dtype=np.int8)
    chromosome[rng.choice(feature_count, size=selected_count, replace=False)] = 1
    return chromosome


def _roulette_parent(fitnesses: Sequence[float], rng: np.random.Generator) -> int:
    values = np.asarray(fitnesses, dtype=float)
    # Lower fitness is better. This rank-like linear inversion remains stable at fitness 0.
    weights = values.max() - values + 1e-12
    probabilities = weights / weights.sum()
    return int(rng.choice(len(values), p=probabilities))


def _select_parent(
    population: list[np.ndarray],
    fitnesses: Sequence[float],
    config: GeneticAlgorithmConfig,
    rng: np.random.Generator,
) -> int:
    if config.selection_method == "roulette":
        return _roulette_parent(fitnesses, rng)
    sample_size = min(config.tournament_size, len(population))
    contestants = rng.integers(0, len(population), size=sample_size)
    return min(
        (int(index) for index in contestants),
        key=lambda index: (fitnesses[index], tuple(population[index].tolist())),
    )


def _crossover(
    first: np.ndarray,
    second: np.ndarray,
    probability: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    if first.size < 2 or rng.random() >= probability:
        return first.copy(), second.copy()
    point = int(rng.integers(1, first.size))
    return (
        np.concatenate((first[:point], second[point:])),
        np.concatenate((second[:point], first[point:])),
    )


def _mutate(chromosome: np.ndarray, probability: float, rng: np.random.Generator) -> np.ndarray:
    mutated = chromosome.copy()
    flips = rng.random(mutated.size) < probability
    mutated[flips] = 1 - mutated[flips]
    return mutated


def software_versions() -> dict[str, str]:
    import numpy
    import pandas
    import sklearn

    versions = {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "scikit_learn": sklearn.__version__,
    }
    for distribution in ("pydantic",):
        try:
            versions[distribution] = version(distribution)
        except PackageNotFoundError:
            continue
    return versions


def run_genetic_algorithm(
    dataset: DatasetFoundation,
    config: GeneticAlgorithmConfig | None = None,
    *,
    evaluator: RandomForestEvaluator | None = None,
) -> GeneticAlgorithmResult:
    """Search binary masks using validation-only shared Random Forest fitness.

    ``max_model_evaluations`` counts unique masks passed through the RF evaluator. Repeated
    masks use a deterministic fitness cache. The fitness callback only calls
    ``RandomForestEvaluator.evaluate_validation``; it never opens the held-out test partition.
    """
    settings = config or GeneticAlgorithmConfig()
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

    def fitness_callback(chromosome: np.ndarray) -> float | None:
        nonlocal fitness_request_count, model_evaluation_count, model_evaluation_time
        fitness_request_count += 1
        key = tuple(int(bit) for bit in chromosome)
        if key in fitness_cache:
            return fitness_cache[key]
        if model_evaluation_count >= settings.max_model_evaluations:
            return None
        selected = [name for bit, name in zip(chromosome, feature_names, strict=True) if bit]
        evaluation = active_evaluator.evaluate_validation(
            dataset, selected, persist_run=False
        )
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

    population = [
        _random_chromosome(feature_count, settings.min_features, maximum, rng)
        for _ in range(settings.population_size)
    ]
    fitnesses: list[float] = []
    for chromosome in population:
        fitness = fitness_callback(chromosome)
        if fitness is None:
            raise RuntimeError("Initial population exceeded the configured model-evaluation budget")
        fitnesses.append(fitness)

    best_key = min(fitness_cache, key=lambda key: (fitness_cache[key], key))
    best_fitness_trace = [fitness_cache[best_key]]
    stop_reason = "generations_complete"

    for _generation in range(1, settings.generations + 1):
        ranked_indices = sorted(
            range(len(population)),
            key=lambda index: (fitnesses[index], tuple(population[index].tolist())),
        )
        next_population = [population[index].copy() for index in ranked_indices[: settings.elitism_count]]
        budget_exhausted = False

        while len(next_population) < settings.population_size:
            first_parent = _select_parent(population, fitnesses, settings, rng)
            second_parent = _select_parent(population, fitnesses, settings, rng)
            first_child, second_child = _crossover(
                population[first_parent],
                population[second_parent],
                settings.crossover_probability,
                rng,
            )
            children = (first_child, second_child)
            for child in children:
                if len(next_population) >= settings.population_size:
                    break
                child = _mutate(child, settings.mutation_probability, rng)
                child = repair_mask(child, feature_count, settings.min_features, maximum, rng)
                fitness = fitness_callback(child)
                if fitness is None:
                    budget_exhausted = True
                    break
                next_population.append(child)
            if budget_exhausted:
                break

        if len(next_population) < settings.population_size:
            for index in ranked_indices:
                next_population.append(population[index].copy())
                if len(next_population) == settings.population_size:
                    break

        population = next_population
        fitnesses = [fitness_cache[tuple(int(bit) for bit in chromosome)] for chromosome in population]
        generation_best_key = min(fitness_cache, key=lambda key: (fitness_cache[key], key))
        if (fitness_cache[generation_best_key], generation_best_key) < (
            fitness_cache[best_key],
            best_key,
        ):
            best_key = generation_best_key
        best_fitness_trace.append(fitness_cache[best_key])
        if budget_exhausted:
            stop_reason = "evaluation_budget"
            break

    end_to_end_seconds = time.perf_counter() - started
    selector_seconds = max(end_to_end_seconds - model_evaluation_time, 0.0)
    selected_mask = list(best_key)
    selected_names = [name for bit, name in zip(selected_mask, feature_names, strict=True) if bit]

    artifact_dir = dataset.config.output_dir / "ga-runs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{uuid4()}.json"
    result = GeneticAlgorithmResult(
        selected_mask=selected_mask,
        selected_feature_names=selected_names,
        best_fitness=fitness_cache[best_key],
        best_fitness_trace=best_fitness_trace,
        evaluation_count=model_evaluation_count,
        fitness_request_count=fitness_request_count,
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
