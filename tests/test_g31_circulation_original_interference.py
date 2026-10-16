"""No native calls: immutable population, delay barrier and local action gates."""
import copy
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import research_original_interference as study


class Client:
    def __init__(self):
        self.state = {"outbox": {}}
        self.calls = []
    def submit(self, owner, kind, payload, *, request_id):
        self.calls.append(copy.deepcopy(payload))
        self.state["outbox"][request_id] = {"payload": {**payload, "owner_id": owner}, "client_view": {}}
        return request_id, {"status": "pending"}


def view():
    return {"owner_id": "owner:system_domestic", "now": 8359.100453,
        "node_contracts": [{"node": 112, "resource_owner": "owner:system_domestic"}],
        "trays": [{"tray_id": "initial:0:0", "business_bag_id": study.TARGET, "node": 112,
                   "mode": "loaded", "edge_to": -1, "generation": 1, "traversal_id": 5}],
        "jobs": [{"business_bag_id": study.TARGET, "storage_node": 53, "storage_released_at": -1.}]}


def test_preflight_keeps_full_original_population_permissions_and_two_second_barrier():
    data, _, permission = study.prepare_input()
    assert len(data["jobs"]) == 28506 and len(data["trays"]) == 22
    assert all(j["allow_suffix_reroute"] for j in data["jobs"])
    assert len(permission["authorized_business_ids"]) == 28506
    pre = study.timing_preflight(data)
    assert pre["status"] == "conditional_uncongested_first_stage_blocked"
    assert pre["first_blocking_stage"] == 0
    assert [s["normal_window_margin_seconds"] for s in pre["stages"]] == [-.5, -.5, 0.]
    assert pre["incoming_first_stage"]["same_owner"] is False
    assert pre["native_calls"] == 0 and not pre["message_delay_reduced"]
    assert data["jobs"][0]["destination"] == 99 and data["jobs"][0]["storage_release_at"] == 19500.


@pytest.mark.parametrize("defect", ["remote_owner", "not_here", "inflight", "wrong_bag", "not_loaded", "post_storage"])
def test_route_needs_actual_authorized_local_node_identity_and_stage(defect):
    v, client, intent = view(), Client(), study.ObservedIntent()
    if defect == "remote_owner": v["owner_id"] = "owner:system_international"
    elif defect == "not_here": v["trays"][0]["node"] = 29
    elif defect == "inflight": v["trays"][0]["edge_to"] = 112
    elif defect == "wrong_bag": v["trays"][0]["business_bag_id"] = study.BENEFICIARY
    elif defect == "not_loaded": v["trays"][0]["mode"] = "storage"
    else: v["jobs"][0]["storage_released_at"] = 19500.
    intent.observe(v, client)
    assert client.calls == [] and intent.status == "waiting_for_local_stage"


def test_request_payload_uses_observed_generation_and_cannot_skip_delivered_ack():
    v, client, intent = view(), Client(), study.ObservedIntent()
    intent.observe(v, client)
    r = client.calls[0]
    assert (r["from"], r["next"], r["expected_generation"], r["expected_traversal"], r["message_delay"]) == (112, 113, 1, 5, 2.)
    intent.observe(v, client)
    assert len(client.calls) == 1 and intent.stage == 0
    row = client.state["outbox"][intent.request_id]
    row["client_view"]["last_delivered_ack"] = {"status": "updated", "delivered_at": v["now"] + 2.2}
    intent.observe(v, client)
    assert intent.stage == 0
    v["now"] += 2.2
    intent.observe(v, client, allow_submit=False)
    assert intent.stage == 1 and len(client.calls) == 1


def test_stale_rejection_is_retained_and_never_replaced_with_faster_command():
    v, client, intent = view(), Client(), study.ObservedIntent()
    intent.observe(v, client)
    v["now"] += 2.2
    row = client.state["outbox"][intent.request_id]
    row["client_view"]["last_delivered_ack"] = {"status": "rejected", "reason": "stale_executed_prefix", "delivered_at": v["now"]}
    intent.observe(v, client)
    assert intent.status == "rejected_intent" and intent.stage == 0
    assert intent.decisions[0]["delivered_ack"]["reason"] == "stale_executed_prefix"
    intent.observe(v, client)
    assert len(client.calls) == 1 and client.calls[0]["message_delay"] == 2.


def test_absent_or_censored_arm_preserves_denominator_and_unknown_protection():
    data = {"jobs": [{"business_bag_id": str(i)} for i in range(28506)]}
    out = study.compare(data, {"control": {"status": "reached"}})
    assert out["offered_denominator"] == 28506
    assert out["mechanism_status"] == "unknown_missing_or_censored_arm"
    assert out["strict_protection_status"] == "unknown_unfinished_offered_jobs"
    assert not out["full_day_complete"]


def test_feasibility_gate_cannot_admit_ack_without_all_actual_edges():
    intent = study.ObservedIntent()
    intent.status = "complete_intents"
    edges = [{"from": u, "to": v} for u, v in study.PLAN]
    assert study.feasibility_status(intent, edges[:-1]) == "unknown_pending_or_missing_execution"
    assert study.feasibility_status(intent, edges) == "three_intents_and_edges_observed"
    intent.status = "awaiting_delivered_ack"
    assert study.feasibility_status(intent, edges) == "unknown_pending_or_missing_execution"


def test_rejected_gate_never_admits_even_if_other_edges_were_observed():
    intent = study.ObservedIntent()
    intent.status = "rejected_intent"
    edges = [{"from": u, "to": v} for u, v in study.PLAN]
    assert study.feasibility_status(intent, edges) == "rejected_intervention_not_admitted"
