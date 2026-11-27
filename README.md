# Intelligent Network Load Balancing Research

This repository contains two distinct research workstreams. Their datasets, methods, and claims must be kept separate.

## Workstream A: CIC-IoT2023 intrusion classification

Workstream A uses **CIC-IoT2023**, approved by the faculty/team, for feature selection and intrusion classification. It evaluates Genetic Algorithm (GA), Binary Particle Swarm Optimization (BPSO), and Ant Colony Optimization (ACO) feature selection with a shared Random Forest (RF) evaluator and a full-feature baseline. These are intrusion-classification experiments; they do **not** demonstrate simulated or real network load-balancing performance.

The findings are preliminary and have these limitations:

- They use a class-capped sample, which changes the dataset's class distribution.
- Labels are derived from folder names and have not been independently verified against row-level ground truth.
- The exact provenance of the local files and the mismatch between the local schema and published information remain unresolved.
- The selector comparison uses three seeds on one fixed split, so its results are limited and inconclusive.

Dataset approval is separate from technical verification: source provenance, schema, labels, and the complete run manifest remain outstanding. See the [Workstream A research report](docs/WORKSTREAM_A_RESEARCH.md), [handover](docs/WORKSTREAM_A_HANDOVER.md), [experiment protocol](docs/EXPERIMENTS.md), [dataset approval record](docs/audits/CIC-IoT2023_DATASET_AUDIT.md), and [provenance and ground-truth audit](docs/audits/cic_iot2023_provenance_and_ground_truth.md).

The GA, BPSO, and ACO selectors and unified runner are documented in [docs/GENETIC_ALGORITHM.md](docs/GENETIC_ALGORITHM.md), [docs/BINARY_PSO.md](docs/BINARY_PSO.md), [docs/ANT_COLONY.md](docs/ANT_COLONY.md), and [docs/PART_A_EXPERIMENT_RUNNER.md](docs/PART_A_EXPERIMENT_RUNNER.md). From `backend/`, the `benchmark_ga`, `benchmark_bpso`, `benchmark_aco`, and `benchmark_experiment` commands use synthetic data for software checks; they are not research evidence.

## Workstream B: simulated network load balancing

Workstream B is a separate research workstream focused on comparing routing policies using a discrete-event simulation. Its implementation and results are maintained separately from Workstream A. Its outputs are simulated measurements, not physical network measurements. The simulation protocol and unresolved decisions are recorded in [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

## Prerequisites

* Windows 10/11 with PowerShell 7 or Windows PowerShell 5.1.
* Python 3.12 (3.11–3.13 supported) and the Python Launcher for Windows (`py`).
* Node.js 20 or newer with npm.

No secrets or environment variables are needed. The Vite dev server proxies `/api` to the local FastAPI service.

## Backend setup and run (PowerShell)

From the repository root:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload
```

Health check, in another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Expected response: `status = ok`, `service = research-api`. This only confirms the API process is responding; it does not mean an experiment ran.

## Frontend setup and run (PowerShell)

In another PowerShell window, from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite. The API health badge becomes `online` when the backend is running. Stop each server with `Ctrl+C`.

## Checks (PowerShell)

Backend tests and lint:

```powershell
cd backend
python -m pytest
python -m ruff check app tests
```

Frontend production build:

```powershell
cd frontend
npm run build
```

## Data and generated outputs

Do not commit CIC-IoT2023 downloads, processed datasets, model artifacts, or experiment outputs. `.gitignore` excludes common local data/output locations. Before making final Workstream A claims, complete technical source, file, schema, label, audit, and split-manifest verification described in `docs/EXPERIMENTS.md`.

## Project layout

```text
backend/app/core/       # deterministic seed helpers
backend/app/models/     # typed configs and result schemas
backend/app/main.py     # FastAPI health endpoint
backend/tests/          # backend unit and API tests
frontend/src/           # React/TypeScript shell and API types
docs/                   # architecture and experimental protocol
```
