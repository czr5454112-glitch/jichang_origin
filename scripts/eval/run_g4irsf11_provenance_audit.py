"""Assemble the local Git and independently observed remote-CI gate."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.g4irsf11_provenance_audit import assemble_provenance_audit, write_provenance_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-audit", type=Path, required=True)
    parser.add_argument("--remote-head-sha", required=True)
    parser.add_argument("--remote-run-url", required=True)
    parser.add_argument("--remote-conclusion", required=True)
    parser.add_argument("--remote-workflow", default="g4irsf11-gate-integrity")
    parser.add_argument("--remote-branch", default="codex/czr005-rewrite")
    parser.add_argument("--remote-event", default="push")
    parser.add_argument("--observed-at")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs" / "reports" / "g4irsf11_gate_integrity_audit.json",
    )
    args = parser.parse_args()
    audit = assemble_provenance_audit(
        args.local_audit,
        remote_head_sha=args.remote_head_sha,
        remote_run_url=args.remote_run_url,
        remote_conclusion=args.remote_conclusion,
        remote_workflow=args.remote_workflow,
        remote_branch=args.remote_branch,
        remote_event=args.remote_event,
        observed_at=args.observed_at,
    )
    write_provenance_audit(args.output, audit)
    print(f"[g4irsf11-provenance] status={audit['overall_status']} output={args.output}")
    return 0 if audit["overall_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
