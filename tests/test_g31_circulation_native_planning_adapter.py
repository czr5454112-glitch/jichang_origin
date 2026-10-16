"""Delivery provenance, age, scope and conditional projection guards."""
import copy
import gzip
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import native_planning_adapter as adapter

EVIDENCE = Path(__file__).resolve().parents[1] / "outputs/experiments/g31_ics_lt2_sustained_20261014/reuse_v2_002/gate6/old_route1_window1.json.gz"


def data(owner="A"):
    with gzip.open(EVIDENCE, "rt") as stream:
        views = json.load(stream)["seed_views"]
    messages = {}
    for source in ("A", "B"):
        view = views[source]
        jobs, trays = copy.deepcopy(view["jobs"]), copy.deepcopy(view["trays"])
        for tray in trays:
            if tray["tray_id"] == "L":
                tray.update(mode="loading", available_at=.1, service_ready_at=.1, service_ready_known=True,
                            ready_kind="observed_load_completion", load_complete_at=.1)
                jobs[0].update(status="loading", loaded_at=-1.)
            else:
                tray.update(service_ready_at=0., service_ready_known=True, ready_kind="empty_available_at", load_complete_at=-1.)
        nodes = [{k: n[k] for k in ("node", "occupancy", "actual_available")} for n in view["node_contracts"] if n["resource_owner"] == source]
        for node in nodes: node["unrepresented_occupancy"] = 0
        body = {"schema": "g31.planning_capture.v1", "message_id": "planning:" + source,
            "source_owner": source, "target_owner": "B" if source == "A" else "A", "publication_sequence": 2,
            "captured_at": .05 + .01, "valid_until": .21, "static_contract_sha256": "a" * 64,
            "semantics": {"queue_discipline": "fifo", "resource_semantics": "R3_java_node_window_compatible",
                "event_semantics": "E4_batch_plus_destination_merge_request", "scorer_mode": "S4_queue_aware_rule_only",
                "merge_grant_rule": "M3", "merge_grant_timing_mode": "jit_fair_aging_deadline", "minimum_service_seconds": .001},
            "jobs": jobs, "trays": trays, "nodes": nodes, "known_faults": [],
            "coverage": {"scope": "released local obligations and locally visible trays/resources",
                "complete_for_declared_local_scope": True, "local_node_ids": sorted(n["node"] for n in nodes),
                "tray_ids": sorted(t["tray_id"] for t in trays), "business_bag_ids": sorted(j["business_bag_id"] for j in jobs),
                "unrepresented_occupancy": 0, "future_arrivals_included": False}}
        messages[source] = {"schema": "g31.planning_snapshot.v1", "kind": "planning_snapshot", "capture": body,
            "payload_sha256": adapter.capture_digest(body), "digest_format": "g31.planning_capture_digest.v1",
            "delivered_at": .07, "status": "conditional"}
    ack = {"status": "delivered", "executed_at": .05 + .01, "completed_at": .07,
           "delivered_at": .09, "result_id": messages[owner]["capture"]["message_id"], "planning_snapshot": messages[owner]}
    return views[owner], ack, [messages["B" if owner == "A" else "A"]]


def refresh_digest(message):
    message["payload_sha256"] = adapter.capture_digest(message["capture"])


def test_both_owner_local_inputs_produce_identical_conditional_model():
    a, b = [adapter.validate_pair(*data(o)) for o in ("A", "B")]
    assert a["status"] == b["status"] == "conditional_validated_data"
    assert a["bundle"] == b["bundle"]
    assert a["source_capture_pair_sha256"] == b["source_capture_pair_sha256"]
    assert not a["native_delivery_verified"] and not a["bundle"]["online_information_delivered"]
    assert not a["agreement_certified"] and not a["native_protection_certified"]
    transition = a["conditional_projection"][0]
    assert transition["source_captured_at"] == .05 + .01 and transition["projected_at"] == .11
    assert transition["source_known_load_complete_at"] == .1


@pytest.mark.parametrize("defect", ["missing_peer", "duplicate_peer", "missing_self", "lost_self_ack", "future_ack",
    "expired", "tampered_body", "future_observed_epoch", "missing_coverage", "unrepresented", "source_mismatch",
    "static_mismatch", "different_capture", "no_ready", "late_completion", "inflight", "local_changed", "malformed", "unsupported_scorer"])
def test_missing_forged_stale_uncovered_or_changed_input_fails_closed(defect):
    view, ack, messages = data("B")
    message = messages[0]
    body = message["capture"]
    if defect == "missing_peer": messages.clear()
    elif defect == "duplicate_peer": messages.append(copy.deepcopy(message))
    elif defect == "missing_self": ack.pop("planning_snapshot")
    elif defect == "lost_self_ack": ack["status"] = "pending_delivery"
    elif defect == "future_ack": ack["delivered_at"] = .12
    elif defect == "expired": message["status"] = "expired"
    elif defect == "tampered_body": body["jobs"][0]["storage_release_at"] += 1
    elif defect == "future_observed_epoch": body["jobs"][0]["loaded_at"] = .12
    elif defect == "missing_coverage": body["coverage"]["business_bag_ids"].pop()
    elif defect == "unrepresented": body["nodes"][1]["unrepresented_occupancy"] = 1
    elif defect == "source_mismatch": body["source_owner"] = "B"
    elif defect == "static_mismatch": body["static_contract_sha256"] = "b" * 64
    elif defect == "different_capture": body["captured_at"] += .001
    elif defect == "no_ready": body["trays"][0]["service_ready_known"] = False
    elif defect == "late_completion": body["trays"][0].update(service_ready_at=.12, load_complete_at=.12)
    elif defect == "inflight": body["trays"][0]["edge_to"] = 1
    elif defect == "local_changed": view["trays"][0]["generation"] += 1
    elif defect == "malformed": body.pop("jobs")
    elif defect == "unsupported_scorer": body["semantics"]["scorer_mode"] = "unsupported"
    if defect not in {"tampered_body", "malformed"}: refresh_digest(message)
    result = adapter.validate_pair(view, ack, messages)
    assert result["status"] == "unknown" and not result["native_delivery_verified"]


def test_caller_dictionary_cannot_certify_delivery_even_with_valid_digest():
    view, ack, received = data()
    before = copy.deepcopy((view, ack, received))
    result = adapter.validate_pair(view, ack, received)
    assert result["status"] == "conditional_validated_data" and not result["native_delivery_verified"]
    assert (view, ack, received) == before
    assert adapter.collect_native(SimpleNamespace(), SimpleNamespace(), "A", "fake")["status"] == "unknown"


def test_one_ready_owner_does_not_imply_peer_ready_or_atomic_commit():
    a = adapter.validate_pair(*data("A"))
    view, ack, received = data("B")
    b = adapter.validate_pair(view, {}, received)
    assert a["status"] == "conditional_validated_data" and b["status"] == "unknown"
    assert not a["agreement_certified"]


@pytest.mark.skipif(not os.environ.get("G31_CIRCULATION_BINARY"), reason="explicit native binary required")
def test_real_native_source_captured_pair_and_projection_conform():
    from scripts.experiments.g31_ics_circulation.native_host import load_native
    from scripts.experiments.g31_ics_circulation import research_synthetic_reuse_chain as v1
    native = load_native(os.environ["G31_CIRCULATION_BINARY"])
    if not hasattr(native.NativeSession, "protocol_planning_snapshots"):
        pytest.skip("planning snapshot was added in native020")
    session = native.NativeSession(v1.scene(6.))
    session.advance_to(.05)
    client = v1.Transport(session)
    for owner, peer in (("A", "B"), ("B", "A")):
        client.submit(owner, "demand", "seed-demand", target_owner=peer, message_delay=.01, publication_delay=.01)
    identities = {owner: client.submit(owner, "planning_snapshot", "initial-planning", target_owner=peer,
        message_delay=.01, publication_delay=.01, expiry=.21) for owner, peer in (("A", "B"), ("B", "A"))}
    session.advance_to(.11)
    results = {o: adapter.collect_native(native, session, o, identities[o]) for o in ("A", "B")}
    assert all(r["status"] == "conditional_native_delivered_model_input" for r in results.values()), results
    assert results["A"]["bundle"] == results["B"]["bundle"]
    assert results["A"]["native_delivery_verified"] and results["B"]["native_delivery_verified"]
    assert not results["A"]["native_protection_certified"]
