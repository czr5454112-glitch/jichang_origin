"""Pure adverse evidence tests; fabricated fixtures never establish native delivery."""
import copy
import gzip
import json
import pytest
from scripts.experiments.g31_ics_circulation import research_native_preexisting_occupancy as runner
from scripts.experiments.g31_ics_circulation import verify_preexisting_delivery as verify
from test_g31_circulation_preexisting_online_model import initial_pair


def raw_fixture(specification):
    case_index = runner.domain.cases().index(specification["case"]); fault = specification["fault"]
    data = runner.native_scene(specification["case"], fault); owners = {}; calls = []
    for owner, peer in (("A", "B"), ("B", "A")):
        view, ack, received = initial_pair(owner, case_index)
        view.update({k: copy.deepcopy(v) for k, v in data.items() if k not in ("jobs", "trays", "node_contracts")})
        for envelope in (ack["planning_snapshot"], received[0]):
            body = envelope["capture"]
            body["captured_at"] = .05 + .01
            body["valid_until"] = .08 if fault == "expired_capture" else .21
            envelope["delivered_at"] = body["captured_at"] + .01
            envelope["payload_sha256"] = runner.initial_adapter.capture_digest(body)
        ack.update(executed_at=.05+.01, completed_at=(.05+.01)+.01, delivered_at=((.05+.01)+.01)+.02)
        if fault == "expired_capture": received[0]["status"] = "expired"
        if fault == "missing_peer" and owner == "B": received = []
        if fault == "lost_self_ack" or fault == "missing_peer" and owner == "A": ack = {}
        result = runner.initial_adapter.validate_pair(view, ack, received)
        if result["status"] == "conditional_validated_data":
            result["status"] = "conditional_native_delivered_model_input"; result["native_delivery_verified"] = True
            result["native_read"] = {"fixture_only": True}
            information = result
        else:
            result["native_read"] = {"fixture_only": True}
            information = runner.adapter.unknown("missing_verified_initial_contract_capture", initial=result)
        owners[owner] = {"owner": owner, "information": information,
            "raw_endpoints": {"view": view, "received": received, "command": {
                "request_id": f"live:1:{owner}:initial-planning", "kind": "planning_snapshot", "attempt": 1, "last_delivered_ack": ack}},
            "decision": {"status": "delivery_probe_only", "selected_action": None}, "native_request_id": None}
        for kind, label in (("demand", "seed-demand"), ("planning_snapshot", "initial-planning")):
            request = {"request_id": f"live:1:{owner}:{label}", "owner_id": owner, "target_owner": peer,
                "message_delay": .01, "publication_delay": .1 if kind == "planning_snapshot" and fault == "missing_peer" and owner == "A" else .01, "kind": kind}
            if kind == "planning_snapshot": request["expiry"] = .08 if fault == "expired_capture" else .21
            calls.append({"at": .05, "retry": False, "kind": kind, "request": request, "reply": {"status": "pending", "reason": "command_enqueued"}})
    return {"specification": copy.deepcopy(specification), "input": data, "initial_owners": owners, "calls": calls,
        "outbox": {}, "summary": {"status": "readiness_observed", "both_inputs_verified": fault is None,
            "owner_status": {o: row["information"]["status"] for o, row in owners.items()}, "business_metrics": None,
            "physical_protection": "not_assessed"}}


@pytest.mark.parametrize("key", tuple(runner.protocol()["rows"]))
def test_all_nine_exact_predeclared_positive_and_negative_evidence_shapes(key):
    spec = runner.protocol()["rows"][key]; raw = raw_fixture(spec)
    result = verify.verify_branch(raw, spec, raw["input"])
    assert result["status"] == "passed", result
    assert {owner: row["reasons"] for owner, row in result["owners"].items()} == verify.EXPECTED_REASONS[spec["fault"]]


@pytest.mark.parametrize("defect", ("digest", "wrong_fault", "future_ack", "wrong_scope", "hidden_action", "wrong_local_job", "lying_summary", "missing_raw", "forged_information"))
def test_raw_verifier_rejects_different_or_unrelated_failure(defect):
    spec = runner.protocol()["rows"]["readiness/expired_capture"]; raw = raw_fixture(spec)
    endpoint = raw["initial_owners"]["B"]["raw_endpoints"]
    if defect == "digest": endpoint["received"][0]["capture"]["trays"][0]["generation"] += 1
    elif defect == "wrong_fault": endpoint["command"]["last_delivered_ack"] = {}
    elif defect == "future_ack": endpoint["command"]["last_delivered_ack"]["delivered_at"] = .12
    elif defect == "wrong_scope": endpoint["received"][0]["capture"]["coverage"]["business_bag_ids"] = []
    elif defect == "hidden_action": raw["calls"].append(copy.deepcopy(raw["calls"][0]))
    elif defect == "wrong_local_job": endpoint["view"]["jobs"][0]["load_seconds"] += 1
    elif defect == "lying_summary": raw["summary"]["both_inputs_verified"] = True
    elif defect == "missing_raw": del raw["initial_owners"]["B"]["raw_endpoints"]
    else: raw["initial_owners"]["B"]["information"]["initial"]["reasons"] = ["invalid_snapshot_or_view_shape"]
    result = verify.verify_branch(raw, spec, raw["input"])
    assert result["status"] == "unknown_or_failed" and not result["business_admitted"]


def saved_gate(tmp_path):
    output = tmp_path/"delivery"; plan = runner.prepare(output, "delivery_gate"); rows = copy.deepcopy(plan["rows"])
    for key, row in rows.items():
        raw = raw_fixture(row); path = output/(key+".json.gz"); path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as stream: json.dump(raw, stream)
        row.update(status="readiness_observed", summary=raw["summary"], raw_validation=verify.verify_branch(raw, row, raw["input"]),
            raw_artifact={"path": key+".json.gz", "sha256": runner.sha(path), "input_path": "inputs/"+key+".json",
                "input_sha256": runner.sha(output/"inputs"/(key+".json"))})
    receipt = {"status": "executed", "source_changed": [], "source_closure_changed": [], "binary_sha256": "a"*64,
        "branch_count": 9, "branch_status_counts": {"readiness_observed": 9}, "comparisons": runner.assess(rows, "delivery_gate"),
        "raw_artifacts": {key: row["raw_artifact"] for key, row in rows.items()}}
    runner.write(output/"branch_ledger.json", rows); runner.write(output/"receipt.json", receipt)
    return output, plan, rows, receipt


def test_gate_recomputes_nine_raws_instead_of_trusting_summary(tmp_path):
    output, plan, _, _ = saved_gate(tmp_path)
    result = runner.require_delivery_gate(output, "a"*64, plan)
    assert result["status"] == "passed" and result["raw_branches_independently_revalidated"] == 9


@pytest.mark.parametrize("defect", ("raw_missing", "raw_changed", "input_changed", "ledger_forged_true", "fault_replaced", "source_archive_drift", "raw_wrong_fault_rehashed", "source_missing", "receipt_lies"))
def test_evidence_gate_rejects_tampering_even_if_booleans_claim_success(tmp_path, defect):
    output, plan, rows, receipt = saved_gate(tmp_path); key = "readiness/expired_capture"
    raw_path = output/(key+".json.gz")
    if defect == "raw_missing": raw_path.unlink()
    elif defect == "raw_changed": raw_path.write_bytes(raw_path.read_bytes()+b"changed")
    elif defect == "input_changed": (output/"inputs"/(key+".json")).write_text("{}")
    elif defect == "ledger_forged_true": rows[key]["summary"]["both_inputs_verified"] = True
    elif defect == "fault_replaced": rows[key]["fault"] = "lost_self_ack"
    elif defect == "source_archive_drift": (output/next(iter(plan["source_archive"].values()))).write_text("changed")
    elif defect == "source_missing": (output/next(iter(plan["source_archive"].values()))).unlink()
    elif defect == "receipt_lies": receipt["comparisons"]["normal_count"] = 5
    else:
        with gzip.open(raw_path, "rt", encoding="utf-8") as stream: raw = json.load(stream)
        raw["initial_owners"]["B"]["raw_endpoints"]["command"]["last_delivered_ack"] = {}
        with gzip.open(raw_path, "wt", encoding="utf-8") as stream: json.dump(raw, stream)
        rows[key]["raw_artifact"]["sha256"] = runner.sha(raw_path)
        receipt["raw_artifacts"][key] = copy.deepcopy(rows[key]["raw_artifact"])
    runner.write(output/"branch_ledger.json", rows); runner.write(output/"receipt.json", receipt)
    with pytest.raises((ValueError, OSError, KeyError)):
        runner.require_delivery_gate(output, "a"*64, plan)


def test_summary_flags_without_raw_validation_cannot_pass_assessor():
    rows = runner.protocol()["rows"]
    for row in rows.values(): row["summary"] = {"both_inputs_verified": row["fault"] is None}
    assert runner.assess(rows, "delivery_gate")["status"] != "passed"
