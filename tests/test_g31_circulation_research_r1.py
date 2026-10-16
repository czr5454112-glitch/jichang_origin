"""Original-map permission isolation and actual native suffix execution."""
from copy import deepcopy
import os

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.original_mechanism import select_input
from scripts.experiments.g31_ics_circulation.original_workload import json_digest, research_r1_authorized
from scripts.experiments.g31_ics_circulation.research_r1 import candidate_census, suffix_choices, run_witness


def test_r1_contract_changes_only_explicit_permission_and_keeps_source_isolated():
    source = tiny_cycle()
    saved = deepcopy(source)
    result, contract = research_r1_authorized(source)
    assert source == saved
    assert contract["source_input_sha256"] == json_digest(source)
    assert all(j["allow_suffix_reroute"] for j in result["jobs"])
    for job in result["jobs"]:
        del job["allow_suffix_reroute"]
    del result["r1_authorization_contract"]
    assert result == source
    result["node_contracts"][0]["capacity"] = 999
    assert source == saved


def test_duplicate_authorization_is_not_silently_versioned_again():
    first, _ = research_r1_authorized(tiny_cycle())
    with pytest.raises(ValueError, match="already_authorized"):
        research_r1_authorized(first)


def test_suffix_domain_excludes_committed_prefix_loops():
    graph = {0: [(1, 1.), (2, 1.)], 1: [(3, 1.)], 2: [(0, 1.), (3, 1.)], 3: []}
    assert suffix_choices(graph, 0, 3) == [(0, 1, 3), (0, 2, 3)]
    assert suffix_choices(graph, 0, 3, [1]) == [(0, 2, 3)]
    assert suffix_choices(graph, 3, 3) == []


def test_census_keeps_unreachable_and_no_choice_in_denominator():
    data = tiny_cycle()
    data["edge_contracts"] = [dict(e, capacity=0) if e["from"] == 6 else e for e in data["edge_contracts"]]
    data["jobs"] += [dict(data["jobs"][0], business_bag_id="impossible", origin=6)]
    result = candidate_census(data)
    assert result["mother_offered"] == 3
    assert result["counts"] == {"no_route_choice": 2, "unreachable_required_stage": 1}
    assert not result["selection_uses_outcomes"]


@pytest.mark.skipif(not os.environ.get("G31_CIRCULATION_BINARY"), reason="explicit frozen native binary required")
@pytest.mark.parametrize("stage_filter", ["any", "post_storage_or_direct"])
def test_original_map_native_route_changes_real_traversal(stage_filter):
    source, _, _ = select_input(2)
    frozen = deepcopy(source)
    source["jobs"] = source["jobs"][:1]
    data, _ = research_r1_authorized(source)
    data["owner_protocol"] = {"enabled": True, "timeout": 5., "ack_delay": .2}
    data["owner_notifications"] = {"enabled": True}
    native = load_native(os.environ["G31_CIRCULATION_BINARY"])
    summary, raw = run_witness(native, data, stage_filter=stage_filter)
    assert summary["r1_physical_witness"]
    assert len(data["node_records"]) == 151 and len(data["edge_records"]) == 227
    assert all(not j.get("allow_suffix_reroute", False) for j in frozen["jobs"])
    assert summary["same_permission_control"] and summary["joint_status"] == "unknown"
    for branch in summary["branches"].values():
        assert branch["prefix_preserved_vs_control"]
        assert branch["event_audit"]["status"] == "passed"
        assert branch["completed"] == 1 and branch["horizon_complete"]
    for branch in raw["branches"].values():
        assert branch["result"]["jobs"][0]["storage_released_at"] >= data["jobs"][0]["storage_release_at"]


@pytest.mark.skipif(not os.environ.get("G31_CIRCULATION_BINARY"), reason="explicit frozen native binary required")
@pytest.mark.parametrize("authorized,delay,reason", [
    (True, 3., "stale_executed_prefix"), (False, .01, "service_obligation_disallows_reroute")])
def test_original_map_rejection_keeps_legal_control_continuation(authorized, delay, reason):
    data, _, _ = select_input(2)
    data["jobs"] = data["jobs"][:1]
    if authorized:
        data, _ = research_r1_authorized(data)
    data["owner_protocol"] = {"enabled": True, "timeout": 5., "ack_delay": .2}
    data["owner_notifications"] = {"enabled": True}
    native = load_native(os.environ["G31_CIRCULATION_BINARY"])
    summary, _ = run_witness(native, data, message_delay=delay)
    assert not summary["r1_physical_witness"]
    control = summary["branches"]["control"]
    for key, branch in summary["branches"].items():
        assert branch["completed"] == 1
        assert branch["executed_edges"] == control["executed_edges"]
        if key != "control":
            assert branch["ack"]["status"] == "rejected"
            assert branch["ack"]["reason"] == reason
