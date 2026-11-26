"""Binary Particle Swarm Optimization feature selection for Study A."""

from __future__ import annotations

import time
from uuid import uuid4

import numpy as np

from app.features.data import DatasetFoundation
from app.features.evaluator import RandomForestEvaluator
from app.features.selection.genetic import (
    calculate_feature_fitness,
    repair_mask,
    software_versions,
)
from app.models.features import BinaryPSOConfig, BinaryPSOResult


def _sigmoid(velocity: np.ndarray) -> np.ndarray:
    """Map bounded velocity values to independent feature-selection probabilities."""
    return 1.0 / (1.0 + np.exp(-velocity))


def _inertia_for_iteration(config: BinaryPSOConfig, iteration: int) -> float:
    """Linearly anneal inertia from its initial value to its final value."""
    if config.iterations <= 1:
        return config.inertia_start
    fraction = (iteration - 1) / (config.iterations - 1)
    return config.inertia_start + fraction * (config.inertia_end - config.inertia_start)


def run_binary_pso(
    dataset: DatasetFoundation,
    config: BinaryPSOConfig | None = None,
    *,
    evaluator: RandomForestEvaluator | None = None,
) -> BinaryPSOResult:
    """Optimize binary feature masks using validation-only shared RF fitness.

    Velocity follows ``v = w*v + c1*r1*(pbest-x) + c2*r2*(gbest-x)``, clipped to the
    configured velocity bounds. The sigmoid maps each velocity to a bit-inclusion
    probability; positions are sampled independently then repaired to the configured
    feature-count bounds. The model-evaluation budget counts unique masks, matching GA's
    budget semantics. Cached positions do not trigger duplicate RF fits.
    """
    settings = config or BinaryPSOConfig()
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

    def fitness_callback(position: np.ndarray) -> float | None:
        nonlocal fitness_request_count, model_evaluation_count, model_evaluation_time
        fitness_request_count += 1
        key = tuple(int(bit) for bit in position)
        if key in fitness_cache:
            return fitness_cache[key]
        if model_evaluation_count >= settings.max_model_evaluations:
            return None
        selected = [name for bit, name in zip(position, feature_names, strict=True) if bit]
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

    positions = np.zeros((settings.particle_count, feature_count), dtype=np.int8)
    for particle_index in range(settings.particle_count):
        sampled = (rng.random(feature_count) < 0.5).astype(np.int8)
        positions[particle_index] = repair_mask(
            sampled, feature_count, settings.min_features, maximum, rng
        )
    velocities = rng.uniform(
        settings.velocity_min,
        settings.velocity_max,
        size=(settings.particle_count, feature_count),
    )

    personal_best_positions = positions.copy()
    personal_best_fitness = np.empty(settings.particle_count, dtype=float)
    for particle_index, position in enumerate(positions):
        fitness = fitness_callback(position)
        if fitness is None:
            raise RuntimeError("Initial swarm exceeded the configured model-evaluation budget")
        personal_best_fitness[particle_index] = fitness

    global_best_index = min(
        range(settings.particle_count),
        key=lambda index: (
            personal_best_fitness[index],
            tuple(personal_best_positions[index].tolist()),
        ),
    )
    global_best_position = personal_best_positions[global_best_index].copy()
    global_best_fitness = float(personal_best_fitness[global_best_index])
    global_best_fitness_trace = [global_best_fitness]
    iterations_completed = 0
    stop_reason = "iterations_complete"

    for iteration in range(1, settings.iterations + 1):
        inertia = _inertia_for_iteration(settings, iteration)
        iteration_global_best = global_best_position.copy()
        budget_exhausted = False

        for particle_index in range(settings.particle_count):
            current_position = positions[particle_index]
            r1 = rng.random(feature_count)
            r2 = rng.random(feature_count)
            candidate_velocity = (
                inertia * velocities[particle_index]
                + settings.cognitive_coefficient
                * r1
                * (personal_best_positions[particle_index] - current_position)
                + settings.social_coefficient * r2 * (iteration_global_best - current_position)
            )
            candidate_velocity = np.clip(
                candidate_velocity, settings.velocity_min, settings.velocity_max
            )
            inclusion_probabilities = _sigmoid(candidate_velocity)
            candidate_position = (rng.random(feature_count) < inclusion_probabilities).astype(
                np.int8
            )
            candidate_position = repair_mask(
                candidate_position,
                feature_count,
                settings.min_features,
                maximum,
                rng,
            )
            candidate_fitness = fitness_callback(candidate_position)
            if candidate_fitness is None:
                budget_exhausted = True
                break

            velocities[particle_index] = candidate_velocity
            positions[particle_index] = candidate_position
            candidate_key = tuple(candidate_position.tolist())
            personal_key = tuple(personal_best_positions[particle_index].tolist())
            if (candidate_fitness, candidate_key) < (
                personal_best_fitness[particle_index],
                personal_key,
            ):
                personal_best_positions[particle_index] = candidate_position
                personal_best_fitness[particle_index] = candidate_fitness

        global_best_index = min(
            range(settings.particle_count),
            key=lambda index: (
                personal_best_fitness[index],
                tuple(personal_best_positions[index].tolist()),
            ),
        )
        global_best_position = personal_best_positions[global_best_index].copy()
        global_best_fitness = float(personal_best_fitness[global_best_index])
        global_best_fitness_trace.append(global_best_fitness)
        iterations_completed += 1
        if budget_exhausted:
            stop_reason = "evaluation_budget"
            break

    end_to_end_seconds = time.perf_counter() - started
    selector_seconds = max(end_to_end_seconds - model_evaluation_time, 0.0)
    selected_mask = [int(bit) for bit in global_best_position]
    selected_names = [name for bit, name in zip(selected_mask, feature_names, strict=True) if bit]

    artifact_dir = dataset.config.output_dir / "bpso-runs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{uuid4()}.json"
    result = BinaryPSOResult(
        selected_mask=selected_mask,
        selected_feature_names=selected_names,
        best_fitness=global_best_fitness,
        global_best_fitness_trace=global_best_fitness_trace,
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
