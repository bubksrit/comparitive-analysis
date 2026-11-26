"""CLI for local dataset auditing; it does not download files or run models."""

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from app.features.data import DatasetFoundationError, load_and_audit, write_audit_report
from app.models.dataset import DatasetConfig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="JSON DatasetConfig path")
    args = parser.parse_args()
    try:
        config_data = json.loads(args.config.read_text(encoding="utf-8"))
        config = DatasetConfig.model_validate(config_data)
        foundation = load_and_audit(config)
        outputs = write_audit_report(foundation)
    except (OSError, json.JSONDecodeError, ValidationError, DatasetFoundationError) as exc:
        parser.error(str(exc))
    print(f"Audited {foundation.report['row_count']} rows and {foundation.report['column_count']} columns")
    print(f"Eligible features: {foundation.report['eligible_feature_count']}")
    print(f"Actual split: {foundation.report['split']['actual_strategy']}")
    for kind, path in outputs.items():
        print(f"{kind}: {path}")
    print("Dataset identity remains user-declared; no model or feature selection was run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
