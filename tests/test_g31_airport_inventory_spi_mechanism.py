"""Small offline evidence fixtures; no native imports or simulations."""
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_spi_mechanism as audit
from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_rule as rule
from test_g31_airport_inventory_rule import observation, snapshot


def event(kind, at, *, leg="transfer:empty_return:0", tray="E0", node=2, **extra):
    return dict(event=kind, time=at, transport_leg_id=leg, tray_id=tray,
        node=node, business_bag_id="", reason="", **extra)


def fixture():
    current = observation(source=1, stock=2, remote=True)
    capture = snapshot()
    current["planning_snapshots"] = [capture]
    decision = rule.select_stock_return(current)
    intended = decision["intents"][0]
    transfer = dict(intended, request_id="transfer")
    publication = dict(request_id="publish", owner_id="B", kind="planning_snapshot",
        target_owner="A", expiry=30., message_delay=1., publication_delay=1.)
    calls = [
        dict(at=7., kind="planning_snapshot", retry=False, request=publication),
        dict(at=10., kind="transfer", retry=False, request=transfer),
        dict(at=11., kind="transfer", retry=True, request=deepcopy(transfer)),
    ]
    state = {"client": {"outbox": {
        "publish": {"kind": "planning_snapshot", "payload": publication, "terminal": True,
            "client_view": {"last_delivered_ack": {"status": "delivered", "result_id": "m1",
                "planning_snapshot": capture}}},
        "transfer": {"kind": "transfer", "payload": transfer, "terminal": True,
            "client_view": {"last_delivered_ack": {"status": "received", "received_at": 11.1}}},
    }}}
    post = {"reason": "inventory_return_submitted", "new_submissions": 1,
        "decision": decision, "attempts": [{"request_id": "transfer", "reply": {"status": "pending"}}]}
    records = [{"tick": 10, "at": 10., "preparation_compute_ms": 3., "offline_tick_start_observer_ms": 2.,
        "owner_decisions": [{"owner_id": "A", "compute_ms": 7., "offline_evaluator_ms": 5.,
            "inventory_return": post}]}]
    callbacks = [{"owner_id": "A", "observed_at": 10., "protocol_phase": "inventory_return",
        "observation": current, "chosen_decision": decision,
        "planning_wall_ms": 0., "planning_timing_not_captured_here": True}]
    data = {"trays": [{"tray_id": "E0", "node": 1}, {"tray_id": "E1", "node": 1}],
        "jobs": [{"business_bag_id": "J", "origin": 2, "arrival": 11.5}]}
    result = {"leg_identities": [{"transport_leg_id": "transfer:empty_return:0", "kind": "empty_return",
        "tray": 0, "job": -1}], "transfers": [{"request_id": "transfer", "tray": 0,
        "status": "received", "received_at": 11.1}], "receipts": [
            event("EDGE_ENTER", 10.1, node=1, **{"from": 1, "to": 2}),
            event("EDGE_EXIT", 11.1, **{"from": 1, "to": 2}),
            event("EMPTY_RECEIVED", 11.1),
            dict(event("LOAD_START", 12., leg="business"), business_bag_id="J")],
        "trays": [{"tray_id": "E0", "mode": "loaded"}, {"tray_id": "E1", "mode": "empty"}]}
    return dict(data=data, result=result, calls=calls, records=records, state=state,
        callbacks=callbacks, activate_at=10.)


def test_delivered_snapshot_request_native_receive_and_direct_load_are_bound():
    result = audit.analyze(**fixture())
    summary = result["inventory_returns"]
    assert summary["submitted"] == summary["delivered_snapshot_bound"] == 1
    assert summary["native_entity_chain_verified"] == summary["received_chain_verified"] == 1
    assert summary["direct_destination_next_load"] == summary["strict_prearrival_next_load"] == 1
    witness = summary["witnesses"][0]
    assert witness["inventory_binding"]["capture_request_id"] == "publish"
    assert witness["inventory_binding"]["target_stock"] == 0
    assert witness["retries"] == 1 and not witness["same_bag_wait_savings_claimed"]
    assert result["callback_coverage"]["planning_values_explicitly_unmeasured"] == 1
    assert result["timing"]["all"]["owner_planning_residual_post_and_submit_excluding_evaluator"]["sum_ms"] == 7.
    assert result["timing"]["all"]["shared_tick_preparation"]["sum_ms"] == 3.


@pytest.mark.parametrize("change", ["wrong_tray", "changed_retry", "stock_tamper", "missing_capture_ack"])
def test_incomplete_or_tampered_binding_never_passes(change):
    values = fixture()
    if change == "wrong_tray":
        values["result"]["leg_identities"][0]["tray"] = 1
    elif change == "changed_retry":
        values["calls"][-1]["request"]["expiry"] += 1.
    elif change == "stock_tamper":
        values["callbacks"][0]["chosen_decision"]["inventory_return"]["inventory"]["nodes"][2]["reported_actual_empty"] = 999
    else:
        values["state"]["client"]["outbox"]["publish"]["client_view"] = {}
    with pytest.raises(ValueError):
        audit.analyze(**values)


@pytest.mark.parametrize("intervening", [False, True])
def test_receipt_and_later_load_do_not_imply_direct_destination_service(intervening):
    values = fixture()
    if intervening:
        values["result"]["leg_identities"].append(dict(transport_leg_id="another:empty_return:0",
            kind="empty_return", tray=0, job=-1))
        values["result"]["receipts"].insert(-1,
            event("EDGE_ENTER", 11.2, leg="another:empty_return:0", **{"from": 2, "to": 1}))
    else:
        values["result"]["receipts"][-1]["node"] = 1
    summary = audit.analyze(**values)["inventory_returns"]
    assert summary["received_chain_verified"] == 1
    assert summary["direct_destination_next_load"] == summary["strict_prearrival_next_load"] == 0


def test_zero_post_opportunities_remain_zero_with_real_timing_coverage():
    values = fixture()
    values["records"][0]["owner_decisions"][0].pop("inventory_return")
    values["callbacks"] = []
    result = audit.analyze(**values)
    assert result["inventory_returns"]["submitted"] == 0
    assert result["inventory_returns"]["witnesses"] == []
    assert result["callback_coverage"]["records_examined"] == 0
    assert result["timing"]["all"]["owner_decisions"] == 1
    assert audit.distribution([])["p95_ms"] is None
    assert audit.distribution([1., 2., 3., 4., 100.])["p95_ms"] == pytest.approx(80.8)


def recovery_fixture():
    values = fixture()
    request = {"schema": "g31.recover_failed_empty.v1", "owner_id": "A", "tray_id": "E0",
        "from": 1, "expected_generation": 3, "failed_transfer_request_id": "failed",
        "failed_transport_leg_id": "failed:empty_return:0", "request_id": "recover",
        "kind": "recover_failed_empty", "expiry": 20., "message_delay": .01}
    capability = {k: v for k, v in request.items() if k not in ("request_id", "kind", "expiry", "message_delay")}
    capability["failure_reason"] = "departure_lease_expired_before_physical_entry"
    values["calls"] = [dict(at=10.+i, kind="recover_failed_empty", retry=bool(i),
        request=deepcopy(request)) for i in range(2)]
    values["state"] = {"client": {"outbox": {"recover": {"kind": "recover_failed_empty", "payload": request,
        "client_view": {"last_delivered_ack": {"status": "recovered", "result_id": "failed",
            "executed_at": 10.01}}}}},
        "failed_empty_recoveries": {"capability": {"request_id": "recover", "capability": capability}}}
    values["records"], values["callbacks"] = [], []
    values["result"] = {"leg_identities": [{"transport_leg_id": "failed:empty_return:0",
        "kind": "empty_return", "tray": 0, "job": -1}],
        "transfers": [{"request_id": "failed", "tray": 0, "status": "failed"}],
        "receipts": [
            dict(event("LEG_FAILED", 9., leg="failed:empty_return:0", node=1),
                reason="departure_lease_expired_before_physical_entry"),
            dict(event("EMPTY_RECOVERY_GRANTED", 10.01, leg="failed:empty_return:0", node=1,
                **{"from": 1, "to": 1}), reason="recover:owner_failed_empty_recovery")],
        "trays": [{"tray_id": "E0", "mode": "empty", "generation": 4}]}
    return values


def test_recovery_preserves_failed_history_and_counts_immutable_retry_separately():
    result = audit.analyze(**recovery_fixture())
    recovery = result["recovery"]
    assert recovery["requests"] == recovery["verified_recoveries"] == recovery["retry_count"] == 1
    assert recovery["all_native_failed_transfer_count"] == recovery["all_native_leg_failed_receipt_count"] == 1
    assert recovery["rows"][0]["failed_history_retained"]
    assert not recovery["recovery_is_learning_benefit"]
    assert result["inventory_returns"]["submitted"] == 0


def test_recovery_with_prior_physical_entry_cannot_be_certified():
    values = recovery_fixture()
    values["result"]["receipts"].insert(0,
        event("EDGE_ENTER", 8., leg="failed:empty_return:0", node=1, **{"from": 1, "to": 2}))
    with pytest.raises(ValueError, match="narrow_recovery_native_chain"):
        audit.analyze(**values)


@pytest.mark.parametrize("make", [fixture, recovery_fixture])
def test_streamed_refreshes_replace_full_controller_snapshot_history_without_losing_bindings(make):
    values = make()
    expected = audit.analyze(**values)
    if not values["records"]:
        values["records"] = [{"tick": 10, "at": 10., "owner_decisions": [],
            "preparation_compute_ms": 0.}]
    tick = values["records"][0]
    tick["refreshed"] = [{"request_id": identity, "kind": row["kind"], "view": row["client_view"]}
        for identity, row in values["state"]["client"]["outbox"].items()]
    tick["service_actions"] = [dict(kind="recover_failed_empty", **row)
        for row in values["state"].get("failed_empty_recoveries", {}).values()]
    values["state"] = None
    values["records"] = iter(values["records"])
    actual = audit.analyze(**values)
    assert actual["inventory_returns"] == expected["inventory_returns"]
    assert actual["recovery"] == expected["recovery"]
    assert actual["callback_coverage"]["ack_index_reconstructed_from_all_control_refreshes"]


def test_hash_chain_checks_every_record_count_and_tail(tmp_path):
    path = tmp_path/"audit.jsonl.gz"
    previous, envelopes = "0"*64, []
    for sequence in range(3):
        record = {"audit_sequence": sequence, "previous_record_sha256": previous, "value": sequence}
        previous = audit.digest(record)
        envelopes.append({"record_sha256": previous, "record": record})
    with gzip.open(path, "wt", encoding="utf8") as stream:
        for item in envelopes:
            stream.write(json.dumps(item)+"\n")
    receipt = {"records": 3, "tail_record_sha256": previous, "sha256": audit.sha(path)}
    coverage = {}
    assert len(list(audit.verified_callbacks(path, receipt, coverage))) == 3
    assert coverage["full_hash_chain_verified"] and coverage["records_verified"] == 3
    receipt["records"] = 4
    with pytest.raises(ValueError, match="callback_complete_tail"):
        list(audit.verified_callbacks(path, receipt, {}))


def test_running_or_uncreated_worker_is_not_read_as_closed(tmp_path):
    with pytest.raises(ValueError, match="worker_not_closed"):
        audit.audit_run(tmp_path)


def test_closed_artifact_audit_streams_records_and_binds_sources_end_to_end(tmp_path):
    values = fixture()
    tick = values["records"][0]
    tick["refreshed"] = [{"request_id": identity, "kind": row["kind"], "view": row["client_view"]}
        for identity, row in values["state"]["client"]["outbox"].items()]
    tick["service_actions"] = []
    def save(name, content):
        path = tmp_path/name
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "wt", encoding="utf8") as stream:
            json.dump(content, stream)
        return {"path": str(path), "sha256": audit.sha(path)}
    source_root = Path(audit.__file__).resolve().parents[3]
    paths = ["scripts/experiments/g31_ics_circulation/"+name for name in
        ("foundation_airport_inventory_rule.py", "foundation_airport_protocol_v2.py",
         "protocol_control.py", "analytic_control.py")]
    pins = {p: audit.sha(source_root/p) for p in paths}
    source = save("sources.json", {"root": str(source_root), "files": pins,
        "source_manifest_sha256": audit.digest(pins)})
    data = save("input.json", values["data"])
    save("plan.json", {"name": "PURE_ARTIFACT_FIXTURE", "method": "R0_current_stock_v1",
        "parent": {"fixture": True}, "input": data, "input_semantic_sha256": audit.digest(values["data"]),
        "source_bundle": source, "source_manifest_sha256": audit.digest(pins), "activate_at": 10.})
    save("worker_report.json", {"status": "complete", "wall_seconds": 1.,
        "final_physical_time": 12., "process_resources": {}})
    for name, value in (("final_result", values["result"]), ("client_calls", values["calls"]),
                       ("control_records", values["records"]), ("inventory_snapshot_reads", [])):
        save(name+".json.gz", value)
    # Only its raw SHA is needed; large full controller ACK bodies are not loaded.
    save("controller_final_state.json.gz", {"not_loaded_by_mechanism": True})
    record = dict(values["callbacks"][0], audit_sequence=0, previous_record_sha256="0"*64)
    record_sha = audit.digest(record)
    path = tmp_path/"callback_audit.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf8") as stream:
        stream.write(json.dumps({"record_sha256": record_sha, "record": record})+"\n")
    save("callback_audit_receipt.json", {"sha256": audit.sha(path), "records": 1,
        "tail_record_sha256": record_sha, "timings_ms": [{"planning": 0., "audit_persistence": 1.}]})
    output, result = audit.audit_run(tmp_path)
    assert output.is_file() and result["inventory_returns"]["direct_destination_next_load"] == 1
    assert result["callback_coverage"]["full_hash_chain_verified"]
    assert result["callback_coverage"]["ack_index_reconstructed_from_all_control_refreshes"]
    assert result["frozen_actor_source_sha256"] == pins
    assert result["native_runs_started"] == result["fits_started"] == 0
