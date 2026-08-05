"""Publish deterministic Stage-16K/L supervisor contract regressions."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from czr005.g4irsf16.contract_regression import (  # noqa: E402
    FAULT_REPORT_OUTPUT,
    FAULT_TABLE_OUTPUT,
    SUMMARY_OUTPUT,
    TAIL_REPORT_OUTPUT,
    TAIL_TABLE_OUTPUT,
    write_contract_regression,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the synthetic G4IRSF16 supervisor contract regression. "
            "This does not run a closed-loop TTH experiment."
        )
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT,
        help="Repository/output root (default: current repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = write_contract_regression(args.output_root.resolve())
    print("G4IRSF16_STAGE16K_L_SUPERVISOR_CONTRACT_REGRESSION_PASS")
    print(f"evaluation_scope={summary['evaluation_scope']}")
    print(f"tail_rows={summary['tail_pibt']['row_count']}")
    print(f"fault_rows={summary['fault']['row_count']}")
    unsafe_count = (
        summary["tail_pibt"]["unsafe_entry_count"]
        + summary["fault"]["unsafe_entry_count"]
    )
    print(f"unsafe_entry_count={unsafe_count}")
    print(f"tail_table={args.output_root / TAIL_TABLE_OUTPUT}")
    print(f"fault_table={args.output_root / FAULT_TABLE_OUTPUT}")
    print(f"tail_report={args.output_root / TAIL_REPORT_OUTPUT}")
    print(f"fault_report={args.output_root / FAULT_REPORT_OUTPUT}")
    print(f"summary={args.output_root / SUMMARY_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
