"""Generate the fail-closed G4IRSF11-J Java/CIE boundary evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.g4irsf11_java_cie_boundary import audit_repository, write_outputs  # noqa: E402


DEFAULT_ATTEMPTS = ROOT / "outputs" / "tables" / "g4irsf11_java_cie_attempt_audit.csv"
DEFAULT_GATES = ROOT / "outputs" / "tables" / "g4irsf11_java_cie_boundary_gate.csv"
DEFAULT_INVENTORY = ROOT / "outputs" / "tables" / "g4irsf11_java_cie_evidence_inventory.csv"
DEFAULT_REPORT = ROOT / "outputs" / "reports" / "g4irsf11_java_cie_boundary_report.md"
DEFAULT_STATUS = ROOT / "outputs" / "reports" / "g4irsf11_java_cie_boundary_status.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit historical Java/CIE evidence without executing or modifying legacy Java."
    )
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--attempt-table", type=Path, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--gate-table", type=Path, default=DEFAULT_GATES)
    parser.add_argument("--inventory-table", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--status-output", type=Path, default=DEFAULT_STATUS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audit = audit_repository(args.repo)
    write_outputs(
        args.repo,
        audit,
        attempt_table=args.attempt_table,
        gate_table=args.gate_table,
        inventory_table=args.inventory_table,
        report_path=args.report,
        status_path=args.status_output,
    )
    print(
        "[g4irsf11-java-cie]",
        f"status={audit.status}",
        f"g4j={audit.g4j_status}",
        f"attempts={len(audit.attempts)}",
        f"blockers={len(audit.blockers)}",
        flush=True,
    )
    return 0 if audit.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
