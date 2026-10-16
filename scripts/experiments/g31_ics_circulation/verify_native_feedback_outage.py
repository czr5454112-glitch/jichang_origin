"""Reassess all117 rows, before-fault information parity and causal contrast."""
from __future__ import annotations
import argparse
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from . import research_native_feedback_outage as study
from . import research_native_public_joint as online


def load_row(path, key, row):
    source = Path(row["prior_file"]) if row["reuse_prior"] else path / (key + ".json.gz")
    if row["reuse_prior"] and online.sha(source) != row["prior_sha256"]:
        raise ValueError("reused_raw_identity")
    return json.load(gzip.open(source, "rt"))


def check_raw(raw, row):
    errors = []
    expected = study.v1.scene(row["gate"])
    if row["regime"] == "outage": expected["owner_protocol"]["owner_outages"] = [study.outage_contract()]
    if raw["input"] != json.loads(json.dumps(expected)): errors.append("input_or_exogenous_contract_changed")
    if row["reuse_prior"]:
        selected = raw["owners"]["A"]["decision"]["selected_action"]
    else:
        selected = raw["executed_action"]
        if selected["later_mode"] != ("native_keep" if row["policy"] == "joint_no_feedback" else "adaptive"):
            errors.append("later_action_identity_mismatch")
        if row["policy"] == "offline_fixed_reference" and (selected["initial_next"] != 1 or selected["departure"] != row["departure"]):
            errors.append("offline_reference_action_identity_mismatch")
    for owner, record in raw["owners"].items():
        if not record["information"]["native_delivery_verified"]: errors.append("undelivered_initial_information:" + owner)
        info = record["information"]
        for envelope in info["envelopes"].values():
            body = envelope["capture"]
            if online.adapter.capture_digest(body) != envelope["payload_sha256"]: errors.append("capture_digest")
            if not (body["captured_at"] <= envelope["delivered_at"] <= .11 < study.outage_contract()["start"]):
                errors.append("capture_or_decision_after_fault")
        if row["policy"] != "offline_fixed_reference":
            policy = "joint_model" if row["policy"] == "joint_no_feedback" else row["policy"]
            if online.choose(info, policy) != record["decision"]: errors.append("proposal_not_from_recorded_owner_input")
    reassessed = study.v2.assess_cell(raw["input"], raw["result"], SimpleNamespace(rows=raw["outbox"], calls=raw["calls"]), raw["continuation"], selected)
    if reassessed["status"] != "assessed" or any(reassessed[k] != raw["summary"][k] for k in reassessed):
        errors.append("physical_full_population_reassessment")
    return errors


def verify(path, output):
    if output.exists(): raise ValueError("output_exists")
    plan = json.loads((path / "preregistered_protocol.json").read_text())
    rows = json.loads((path / "branch_ledger.json").read_text())
    errors, raw, checked = [], {}, {}
    if set(rows) != set(plan["rows"]) or len(rows) != 117: errors.append("incomplete_denominator")
    for source, digest in plan["source_sha256"].items():
        if online.sha(path / "source_archive" / Path(source).name) != digest: errors.append("source_archive_identity")
    previous = Path(plan["previous_healthy_evidence"])
    previous_plan = json.loads((previous / "preregistered_protocol.json").read_text())
    previous_receipt = json.loads((previous / "receipt.json").read_text())
    this_receipt = json.loads((path / "receipt.json").read_text())
    if (previous_receipt["source_changed"] or this_receipt["source_changed"]
            or previous_receipt["native_binary_sha256"] != this_receipt["native_binary_sha256"]):
        errors.append("reused_healthy_source_or_binary_changed")
    for source, digest in previous_plan["source_sha256"].items():
        if online.sha(previous / "source_archive" / Path(source).name) != digest:
            errors.append("reused_healthy_source_archive_identity")
    for key, spec in plan["rows"].items():
        try:
            raw[key] = load_row(path, key, spec)
            identity = [f for f in ("regime", "gate", "policy", "departure", "reuse_prior") if spec.get(f) != rows[key].get(f)]
            failures = ["ledger_identity:" + f for f in identity] + check_raw(raw[key], spec)
            checked[key] = {"status": "verified" if not failures else "failed", "errors": failures}
            errors.extend(key + ":" + e for e in failures)
        except Exception as exc:
            checked[key] = {"status": "unknown", "errors": [type(exc).__name__ + ":" + str(exc)]}
            errors.extend(key + ":" + e for e in checked[key]["errors"])
    parity, causal = {}, {}
    for gate in study.v1.GATES:
        for policy in ("incumbent", "fixed_route_model", "joint_model", "joint_no_feedback"):
            healthy, outage = [raw[f"{regime}/gate{int(gate)}/{policy}"] for regime in ("healthy", "outage")]
            facts_same = all(healthy["owners"][o]["information"]["envelopes"] == outage["owners"][o]["information"]["envelopes"] for o in ("A", "B"))
            decisions_same = all(healthy["owners"][o]["decision"] == outage["owners"][o]["decision"] for o in ("A", "B"))
            parity[f"gate{int(gate)}/{policy}"] = {"native_captured_inputs_identical": facts_same, "initial_decisions_identical": decisions_same}
            if not facts_same or not decisions_same: errors.append("before_fault_information_or_policy_parity")
        prefix = f"outage/gate{int(gate)}/"
        adaptive, kept = [raw[prefix + p] for p in ("joint_model", "joint_no_feedback")]
        initial = lambda r: [c for c in r["calls"] if c["at"] <= .11]
        if initial(adaptive) != initial(kept): errors.append("paired_initial_requests_differ")
        choices = adaptive["continuation"]["route_choices"]
        evidence = []
        for choice in choices:
            job, request = choice["job"], choice["request_id"]
            edge = lambda r: [x for x in r["result"]["receipts"] if x["event"] == "EDGE_ENTER" and x["business_bag_id"] == job and x["from"] == 7]
            evidence.append({"job": job, "decision_at": choice["at"], "selected_next": choice["next"],
                "delivered_forecasts": choice["delivered_forecasts"], "local_node3": choice["local_node3"],
                "delivered_route_ACK": adaptive["outbox"][request]["ack"] if request else None,
                "adaptive_actual_edge": edge(adaptive), "native_keep_actual_edge": edge(kept)})
        causal[str(gate)] = {"initial_requests_identical": initial(adaptive) == initial(kept), "later_evidence": evidence}
    report = {"schema": "g31.lt2.feedback_outage_reassessment.v1", "status": "verified" if not errors else "failed_or_unknown",
        "denominator": 117, "all31_native_reference_per_gate": all(checked.get(f"outage/gate{int(g)}/offline_time{i:02d}", {}).get("status") == "verified" for g in study.v1.GATES for i in range(31)),
        "reused_healthy_source_archives_verified": not any("reused_healthy" in e for e in errors),
        "errors": errors, "rows": checked,
        "before_fault_information_parity": parity, "causal_route_evidence": causal, "comparisons": study.comparison(rows),
        "claim_limits": ["generic feedback efficacy under declared outage", "no joint gain over fixed route plus same feedback in outage domain",
                         "no atomic agreement", "no rolling joint optimizer", "no calibrated model guarantee", "no100ms certificate"],
        "native_calls": 0}
    online.write(output, report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"rows", "comparisons", "causal_route_evidence", "before_fault_information_parity"}}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(args.evidence, args.output)
