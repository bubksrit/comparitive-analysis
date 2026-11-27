"""Prepare a deterministic CIC-IoT2023 development sample; this runs no models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from app.features.iot_preparation import prepare_cic_iot2023_sample
from app.models.dataset import DatasetConfig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="CIC-IoT2023 DatasetConfig JSON")
    args = parser.parse_args()
    try:
        config = DatasetConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        result = prepare_cic_iot2023_sample(config)
    except (OSError, ValueError, ValidationError) as exc:
        parser.error(str(exc))
    print(json.dumps({key: str(value) for key, value in result.items() if key != "metadata"}, indent=2))
    print(f"Prepared rows: {result['metadata']['sample_row_count']}")
    print("No split, model fitting, test evaluation, or feature selection was run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
