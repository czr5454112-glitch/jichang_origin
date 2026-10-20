"""Read-only, source-bound aggregate of every saved rolling branch/decision."""
from __future__ import annotations
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path


def audit(directory):
    directory = Path(directory)
    protocol = json.loads((directory / "preregistered_protocol.json").read_text())
    receipt = json.loads((directory / "receipt.json").read_text())
    rows, counts = [], collections.Counter()
    for path in sorted(directory.glob("gate*/*.json.gz")):
        raw = json.loads(gzip.decompress(path.read_bytes()))
        decisions = []
        for owner, values in raw["decisions"].items():
            for value in values:
                info, decision = value["information"], value["decision"]
                verified = info.get("native_delivery_verified") is True
                counts["verified" if verified else "unknown"] += 1
                bundle = info.get("bundle", {})
                decisions.append({"owner": owner, "phase": value["phase"], "at": value["at"],
                    "native_delivery_verified": verified, "input_status": info["status"],
                    "reasons": info.get("reasons", []), "fallback": value["fallback_used"],
                    "selected_action": decision.get("selected_action"), "executed_action": value["executed_first_action"],
                    "native_request_id": value["native_request_id"], "model_gain": decision.get("model_gain"),
                    "evaluations": decision.get("evaluations"), "candidate_denominator": decision.get("candidate_denominator"),
                    "receiver_state": {k: bundle.get("trays", {}).get("E", {}).get(k) for k in ("node", "mode", "service_ready_at")},
                    "future_action_executed_without_replan": value["future_proposal_component_executed_without_replan"]})
        rows.append({"path": path.relative_to(directory).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "decisions": decisions, "physical_summary": raw["summary"]})
    return {"schema": "g31.lt2.saved_rolling_action_audit.v1", "directory": str(directory.resolve()),
        "receipt_sha256": hashlib.sha256((directory / "receipt.json").read_bytes()).hexdigest(),
        "preregistration_sha256": hashlib.sha256((directory / "preregistered_protocol.json").read_bytes()).hexdigest(),
        "expected_branch_count": receipt["branch_count"], "observed_branch_count": len(rows),
        "status": "complete_saved_denominator" if len(rows) == receipt["branch_count"] else "unknown_missing_rows",
        "decision_counts": dict(counts), "rows": rows, "native_calls": 0,
        "limits": ["Read-only aggregate; independent authority/physics review is separate.",
            "Prediction residuals retained; no certified error bound or native protection from model alone."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--input", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    args.output.write_text(json.dumps(audit(args.input), indent=2, allow_nan=False), encoding="utf-8")
