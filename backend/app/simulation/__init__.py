"""Discrete-event simulation for the Study B synthetic load-balancing study."""

from app.simulation.engine import run_paired_comparison, run_simulation
from app.simulation.trace import ArrivalSpec, SimulationTrace

__all__ = ["ArrivalSpec", "SimulationTrace", "run_paired_comparison", "run_simulation"]
