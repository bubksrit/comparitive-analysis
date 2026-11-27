"""Run the exact CIC-IoT2023 duplicate audit after its disk-space preflight."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.features.iot_duplicate_audit import audit_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--scratch-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--inventory-report", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    args = parser.parse_args()
    inventory = json.loads(args.inventory_report.read_text(encoding="utf-8"))
    expected_inventory = {
        row["file"]: int(row["size_bytes"]) for row in inventory["files"]
    }
    report = audit_dataset(
        args.root,
        args.scratch_dir,
        args.output_dir,
        expected_rows=int(inventory["total_rows"]),
        expected_inventory=expected_inventory,
        chunk_size=args.chunk_size,
    )
    print(json.dumps({
        "status": report["status"],
        "rows_scanned": report["total_rows_scanned"],
        "scratch_preflight": report["scratch_preflight"],
        "report_paths": report["report_paths"],
    }, indent=2))
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
