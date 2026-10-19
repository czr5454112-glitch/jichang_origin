"""Offline reassessment of delivered-input decisions and native physical results."""
from __future__ import annotations
import argparse
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from . import research_native_public_joint as run


def verify(path, output=None):
    output = output or path / "independent_reassessment.json"
    if output.exists(): raise ValueError("reassessment_output_already_exists")
    protocol = json.loads((path / "preregistered_protocol.json").read_text())
    ledger = json.loads((path / "branch_ledger.json").read_text())
    errors, checked, raws = [], {}, {}
    if set(ledger) != set(protocol["rows"]) or len(ledger) != 12: errors.append("incomplete_denominator")
    for source, digest in protocol["source_sha256"].items():
        archive = path / "source_archive" / Path(source).name
        if not archive.exists() or run.sha(archive) != digest: errors.append("archive_mismatch:" + str(archive))
    for key, spec in protocol["rows"].items():
        cell_errors = []
        try:
            raw = json.load(gzip.open(path / (key + ".json.gz"), "rt"))
            raws[key] = raw
            for field in ("gate", "policy", "fault", "scope"):
                if raw["specification"][field] != spec[field] or ledger[key][field] != spec[field]: cell_errors.append("action_identity:" + field)
            expected = run.v1.scene(spec["gate"])
            if spec["fault"] == "lost_A_self_ack": expected["owner_protocol"]["drop_ack_packets"] = 3
            if json.loads(json.dumps(expected)) != raw["input"]: cell_errors.append("input_changed")
            for owner, decision in raw["owners"].items():
                info = decision["information"]
                if spec["fault"]:
                    if decision["decision"].get("selected_action") is not None: cell_errors.append("unexpected_fault_first_action")
                    continue
                peer = "B" if owner == "A" else "A"
                own_request = "live:1:" + owner + ":initial-planning"
                peer_request = "live:1:" + peer + ":initial-planning"
                ack = raw["outbox"][own_request]["ack"]
                if info["own_delivered_ack"] != ack: cell_errors.append("self_copy_ack_changed")
                if info["envelopes"][peer]["capture"] != raw["outbox"][peer_request]["ack"]["planning_snapshot"]["capture"]:
                    cell_errors.append("peer_capture_not_same_native_source_copy")
                rechecked = run.adapter.validate_pair(decision["local_action_view"], ack, [info["envelopes"][peer]])
                if rechecked["status"] != "conditional_validated_data" or json.loads(json.dumps(rechecked["bundle"])) != info["bundle"]:
                    cell_errors.append("delivered_capture_validation_failed")
                # Offline recomputation checks decision determinism. It does not
                # promote caller dictionaries into native delivery credentials.
                proposal = run.choose(info, spec["policy"])
                if proposal != decision["decision"]: cell_errors.append("proposal_recompute_mismatch")
                if not info["native_delivery_verified"] or info["bundle"]["online_information_delivered"]:
                    cell_errors.append("provenance_claim_mismatch")
            if not spec["fault"]:
                selected = raw["owners"]["A"]["decision"]["selected_action"]
                if selected != raw["owners"]["B"]["decision"]["selected_action"]: cell_errors.append("owner_selection_disagreement")
                summary = run.v2.assess_cell(raw["input"], raw["result"], SimpleNamespace(rows=raw["outbox"], calls=raw["calls"]), raw["continuation"], selected)
                if summary["status"] != "assessed" or any(summary[k] != raw["summary"][k] for k in summary):
                    cell_errors.append("native_physical_reassessment_failed")
            checked[key] = {"status": "verified" if not cell_errors else "failed", "errors": cell_errors}
        except Exception as exc:
            checked[key] = {"status": "unknown", "errors": [type(exc).__name__ + ":" + str(exc)]}
        errors.extend(key + ":" + e for e in checked[key]["errors"])
    report = {"schema": "g31.lt2.native_public_joint_reassessment.v1", "status": "verified" if not errors else "failed_or_unknown",
        "denominator": 12, "normal_physical_count": sum(not r["fault"] for r in protocol["rows"].values()),
        "errors": errors, "rows": checked, "normal_comparisons": run.assess_normal(ledger),
        "fault_label_correction": {"historical_label": "lost_A_self_ack", "actual_native_semantics": "drop_ack_packets=3 initializes independent remaining_ack_drops for each immutable command/transfer",
            "observed": "both owners lack own snapshot ACK at.11 and both withhold; original prereg global-first3 interpretation was wrong",
            "separate_targeted_probe": "native_planning_asymmetry_001 uses drop1perrequest and exact B-only retry; no original artifact modified"},
        "native_calls": 0, "atomic_agreement_certified": False, "calibrated_model_protection_certified": False,
        "complete_request_100ms_certified": False}
    run.write(output, report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"rows", "normal_comparisons"}}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verify(args.evidence, args.output)
