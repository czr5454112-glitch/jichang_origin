import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import diagnose_preexisting_v3_endpoints as replay
from scripts.experiments.g31_ics_circulation import preexisting_v3_endpoint_identity as binding
from scripts.experiments.g31_ics_circulation.planning_capture_v3_contract import capture_digest_v3


RAW = (Path(__file__).resolve().parents[1] / "outputs/experiments/g31_ics_lt2_sustained_20261014/"
       "native_preexisting_v3_run_business_001/block0_load0/frozen_later.json.gz")
RAW_SHA = "188cd1220fd776062b8b7474274b591c56b78957f95901ef823e9a607ad4dca7"


@pytest.fixture
def raw():
    data = RAW.read_bytes()
    assert hashlib.sha256(data).hexdigest() == RAW_SHA
    return json.loads(gzip.decompress(data))


def supplied(raw, owner="A"):
    decision = raw["decisions"][owner][0]
    info = decision["information"]
    endpoints = copy.deepcopy(info["raw_endpoints"])
    params = dict(retained=raw["retained_ledgers"][owner],
        own_actions=replay.actions_before_decision(raw, owner, decision), phase=decision["phase"],
        own_request_id=info["native_read"]["own_request_id"],
        peer_message_id=info["native_read"]["selected_peer_message_id"],
        collection_started_at=info["native_read"]["collection_started_at"],
        policy_quiet_since=info["native_read"]["collection_started_at"],
        own_request=copy.deepcopy(next(c["request"] for c in raw["calls"]
            if c["request"]["request_id"] == info["native_read"]["own_request_id"])))
    return endpoints, params


def check(endpoints, params):
    return binding.validate_collected_endpoints(endpoints["view"], endpoints["command"], endpoints["received"], **params)


@pytest.mark.parametrize("owner", ["A", "B"])
def test_actual_native_distinct_request_message_ids_reach_unchanged_guards(raw, owner):
    endpoints, params = supplied(raw, owner)
    ack = endpoints["command"]["last_delivered_ack"]
    assert params["own_request_id"] != ack["result_id"]
    original = copy.deepcopy(endpoints)
    result = check(endpoints, params)
    assert result["status"] == "conditional_validated_later_v3_data"
    assert result["native_delivery_verified"] is False
    assert result["online_information_delivered"] is False
    assert result["native_protection_certified"] is False
    assert endpoints == original


@pytest.mark.parametrize("field,value", [("request_id", "wrong"), ("kind", "planning_snapshot_v2"),
    ("status", "pending"), ("attempt", True), ("attempt", 0)])
def test_wrong_endpoint_identity_is_not_relaxed(raw, field, value):
    endpoints, params = supplied(raw)
    endpoints["command"][field] = value
    assert check(endpoints, params)["reasons"] == ["own_command_request_binding_mismatch"]


def test_request_id_is_not_accepted_as_generated_ack_result_id(raw):
    endpoints, params = supplied(raw)
    endpoints["command"]["last_delivered_ack"]["result_id"] = params["own_request_id"]
    assert check(endpoints, params)["reasons"] == ["own_ack_generated_message_binding_mismatch"]


@pytest.mark.parametrize("field,value", [("owner_id", "B"), ("target_owner", "A"),
    ("request_id", "wrong"), ("kind", "planning_snapshot_v2")])
def test_immutable_own_publication_binding(raw, field, value):
    endpoints, params = supplied(raw)
    params["own_request"][field] = value
    assert check(endpoints, params)["reasons"] == ["own_immutable_publication_payload_binding_mismatch"]


@pytest.mark.parametrize("kind", ["missing", "duplicate", "wrong_selected"])
def test_exact_peer_revision_remains_required(raw, kind):
    endpoints, params = supplied(raw)
    if kind == "missing": endpoints["received"] = []
    elif kind == "duplicate": endpoints["received"] *= 2
    else: params["peer_message_id"] = "wrong"
    assert check(endpoints, params)["reasons"] == ["selected_peer_message_missing_or_duplicate"]


def test_current_owner_change_is_not_hidden_by_request_fix(raw):
    endpoints, params = supplied(raw)
    endpoints["view"]["trays"][0]["generation"] += 1
    assert check(endpoints, params)["reasons"] == ["owned_tray_changed_after_v3_capture"]


def test_stale_capture_still_unknown(raw):
    endpoints, params = supplied(raw)
    endpoints["view"]["now"] += .1
    assert check(endpoints, params)["reasons"] == ["invalid_v3_channel_contract_or_causal_age"]


def test_missing_self_ack_delivery_still_unknown(raw):
    endpoints, params = supplied(raw)
    endpoints["command"]["last_delivered_ack"]["delivered_at"] = endpoints["view"]["now"] + .001
    assert check(endpoints, params)["reasons"] == ["missing_delivered_v3_self_copy"]


@pytest.mark.parametrize("relative", [0., .001])
def test_physical_ack_at_or_after_capture_union_floor_remains_unknown(raw, relative):
    endpoints, params = supplied(raw)
    own = endpoints["command"]["last_delivered_ack"]["planning_snapshot_v3"]
    peer = endpoints["received"][0]
    floor = min(e["capture"]["capture_v2"]["local_capture"]["captured_at"] for e in (own, peer))
    peer["capture"]["capture_v2"]["extension"]["submitted_physical_actions"][0]["last_delivered_ack"]["delivered_at"] = floor + relative
    peer["payload_sha256"] = capture_digest_v3(peer["capture"])
    result = check(endpoints, params)
    assert result["status"] == "unknown"
    assert "unsupported_later_model_state" in result["reasons"]
    assert any("action" in r for r in result["bundle"]["reasons"])


def test_reservation_without_observed_entry_remains_unknown(raw):
    endpoints, params = supplied(raw, "B")
    own = endpoints["command"]["last_delivered_ack"]["planning_snapshot_v3"]
    assert own["capture"]["extension"]["source_observed_inflight"]
    own["capture"]["extension"]["source_observed_inflight"] = []
    own["payload_sha256"] = capture_digest_v3(own["capture"])
    assert check(endpoints, params)["reasons"] == ["invalid_v3_observed_entry_extension"]


def test_predecision_action_ledger_does_not_include_new_or_future_actions(raw):
    owner = "A"
    decision = raw["decisions"][owner][0]
    actions = replay.actions_before_decision(raw, owner, decision)
    assert actions == [("live:1:A:initial-route", "route")]
    assert all(identity != decision["native_request_id"] for identity, _ in actions)


def test_new_runner_preserves_policy_domain_and_assessment_ast():
    root = Path(__file__).resolve().parents[1] / "scripts/experiments/g31_ics_circulation"
    def definitions(name):
        return {n.name:ast.dump(n, include_attributes=False) for n in ast.parse((root/name).read_text()).body
                if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    before = definitions("research_native_preexisting_v3_run.py")
    after = definitions("research_native_preexisting_v3_bound.py")
    for name in ("OwnerPolicy", "choose", "owner_first_action", "native_scene", "assess_cell", "assess",
                 "require_delivery_gate", "run_branch", "_admitted_worker"):
        # Receipt schema alone is independently versioned in the worker.
        if name == "_admitted_worker": continue
        assert before[name] == after[name], name


def test_pure_corrected_endpoint_replay_does_not_mint_online_decision_authority(raw):
    from scripts.experiments.g31_ics_circulation import research_native_preexisting_v3_bound as runner
    endpoints, params = supplied(raw)
    result = check(endpoints, params)
    result.update(status="conditional_native_delivered_later_v3_model_input", native_delivery_verified=True)
    assert runner.choose(result, "finite_horizon_enumeration")["status"] == "unknown_unverified_or_unsupported_input"
