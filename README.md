# Intelligent Network Load Balancing Research Skeleton

This repository contains the development environment and typed skeleton for two distinct studies:

* **CIC-IDS2017 classification:** feature selection and Random Forest evaluation on real dataset records.
* **Simulated load balancing:** policy comparison in a discrete-event simulation. These are simulated measurements, not physical network results.

The CIC-IDS2017 local CSV loader, audit, split foundation, train-fitted preprocessing builder, shared Random Forest evaluator, and GA/Binary PSO/ACO feature selectors are implemented. A unified Part A runner produces JSON/CSV summaries and holds test evaluation until all selector runs are frozen. The Part B simulation behavior and frontend experiment workflows are **not implemented**. Protocol and unresolved research decisions are recorded in [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

The CIC-IDS2017 local CSV audit and split foundation is now available. See [docs/DATA_FOUNDATION.md](docs/DATA_FOUNDATION.md) for the manual official-source download steps, configurable schema expectations, and PowerShell audit command. The project does not download or include CIC-IDS2017 data.

The Part A GA, Binary PSO, and ACO selectors and unified runner are documented in [docs/GENETIC_ALGORITHM.md](docs/GENETIC_ALGORITHM.md), [docs/BINARY_PSO.md](docs/BINARY_PSO.md), [docs/ANT_COLONY.md](docs/ANT_COLONY.md), and [docs/PART_A_EXPERIMENT_RUNNER.md](docs/PART_A_EXPERIMENT_RUNNER.md). From `backend/`, run `py -m app.features.benchmark_ga`, `py -m app.features.benchmark_bpso`, `py -m app.features.benchmark_aco`, or `py -m app.features.benchmark_experiment`; each benchmark uses synthetic data and is explicitly not research evidence.

At the user's request, a separate CIC-IoT2023 development sample and three-seed Part A experiment are available locally. The [provenance and ground-truth audit](docs/audits/cic_iot2023_provenance_and_ground_truth.md) finds that exact local source provenance and folder-label truth remain unverified, and that the local README conflicts with the audited per-folder, label-free CSV layout. Results are preliminary intrusion-classification results, not load-balancer measurements. The sample audit, duplicate policy, metrics, and limitations are documented in [docs/WORKSTREAM_A_RESEARCH.md](docs/WORKSTREAM_A_RESEARCH.md). The exact global duplicate count remains unknown; see [the latest audit status](docs/audits/cic_iot2023_duplicate_audit_status.md). Generated data, experiment artifacts, and graphs remain in ignored local paths.

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

Do not commit CIC-IDS2017 downloads, processed datasets, model artifacts, or experiment outputs. `.gitignore` excludes common local data/output locations. Before running actual dataset experiments, complete the exact source, file, schema, label, audit, and split manifest described in `docs/EXPERIMENTS.md`.

## Project layout

```text
backend/app/core/       # deterministic seed helpers
backend/app/models/     # typed configs and result schemas
backend/app/main.py     # FastAPI health endpoint
backend/tests/          # backend smoke test
frontend/src/           # React/TypeScript shell and API types
docs/                   # architecture and experimental protocol
```
