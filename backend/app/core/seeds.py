"""Deterministic random seed helpers; no experiment algorithms live here."""

import random

import numpy as np


def set_global_seed(seed: int) -> None:
    """Seed Python and NumPy global generators for reproducible local runs."""
    random.seed(seed)
    np.random.seed(seed)


def make_numpy_rng(seed: int) -> np.random.Generator:
    """Return an isolated NumPy generator for code that accepts one explicitly."""
    return np.random.default_rng(seed)
