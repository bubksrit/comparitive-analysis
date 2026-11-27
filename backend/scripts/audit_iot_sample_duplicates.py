"""Audit exact duplicates in a manifested CIC-IoT2023 development sample."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.features.iot_sample_audit import audit_prepared_sample


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = audit_prepared_sample(args.sample, args.manifest, args.output_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
