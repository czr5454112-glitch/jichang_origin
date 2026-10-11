from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from test_ics_circulation_v3_business_inputs import case, rebind
from scripts.experiments.ics_circulation_v3.business_inputs import (BusinessInputError, load_business_workload,
                                                                   business_workload_sha256)
from scripts.experiments.ics_circulation_v3.business_runtime import build_business_runtime
from scripts.experiments.ics_circulation_v3.model import Bag
from scripts.experiments.ics_circulation_v3.storage_contracts import StorageBag, StorageSnapshot


@pytest.fixture
def adapted_case(case):
    profile = json.loads(case["graph_profile"].read_text())
    for node in profile["nodes"]:
        node["system_key"] = "fixture-system"
    profile["edges"] = [
        dict(start=0, end=2, length="10.000000000000000000000000000000000000001", speed="1", capacity=1),
        dict(start=2, end=1, length="10", speed="1", capacity=2),
        dict(start=1, end=0, length="10", speed="1", capacity=0)]
    case["graph_profile"].write_text(json.dumps(profile), encoding="utf-8")
    case["contract"]["graph_sha256"] = sha256(case["graph_profile"].read_bytes()).hexdigest()
    rebind(case)
    workload = load_business_workload(**case)
    contract = dict(schema="ics_business_runtime_proxy_v1", contract_id="test-runtime-proxy",
        evidence_status="proxy_research", input_contract_sha256=workload.contract.canonical_sha256,
        graph_sha256=workload.contract.graph_sha256,
        node_resource_policy="exact_bound_input_node_capacity_and_loaded_wait",
        empty_wait_policy="same_as_declared_loaded_wait_proxy",
        edge_permission_policy="both_modes_all_source_directed_edges_proxy",
        edge_capacity_policy="preserve_source_integer_including_closed_zero",
        travel_policy="exact_length_over_speed_ceil_to_input_tick",
        partition_by_node={n.node_id: "test-central" for n in workload.contract.nodes},
        module=dict(kind="existing_fixed_fifo_proxy", loading_seconds="0", unload_seconds="0.1",
            hold_seconds_by_node={n.node_id: "10.01" for n in workload.contract.nodes},
            reception_capacity=1, export_min_stock=0),
        routing=dict(route_mode="whole_route", search_horizon=80, candidate_count=4,
            expansion_limit=10000, static_path_limit=12, local_label_limit=3,
            dynamic_local=True, deadline_ms=None, cache_contract="isolated_replay_v1"),
        reactive_empty_dispatch=True, coordination_order="route_then_prebalance",
        evidence=[dict(field=k, source_ref="test fixture", assumption_id="test-"+k) for k in
            ("permissions", "module", "partition", "travel_capacity", "routing", "coordination")])
    return workload, case["graph_profile"], contract


def test_full_business_future_tape_and_empty_public_state(adapted_case):
    workload, path, contract = adapted_case
    result = build_business_runtime(workload, path, contract)
    assert isinstance(result.initial, StorageSnapshot)
    assert result.initial.now == 0 and result.initial.bags == {} and result.initial.storage_progress == {}
    assert len(result.future_bags) == result.source_business_count == 2
    assert result.source_segment_count == 3 and len(result.initial.trays) == 1
    early, direct = result.future_bags
    assert isinstance(early, StorageBag) and type(direct) is Bag
    assert early.destination == direct.destination == "1"
    assert early.storage.node_id == "2" and early.storage.release_at == 230
    assert early.storage.published_at == early.arrival == 1
    assert early.storage.evidence_status == "proxy"
    assert early.protected and direct.protected
    assert all(t.bag_id is None for t in result.initial.trays.values())


def test_exact_travel_ceil_and_closed_edge_preserved(adapted_case):
    result = build_business_runtime(*adapted_case)
    assert result.initial.network.edges["0->2"].travel_time == 2
    assert result.initial.network.edges["2->1"].travel_time == 1
    assert result.initial.network.edges["1->0"].capacity == 0
    assert result.closed_edge_ids == ("1->0",)
    assert len(result.initial.network.edges) == 3
    assert result.initial.module.unload_ticks == 1
    assert result.initial.module.hold_by_node == {"0": 2, "1": 2, "2": 2}


def test_generator_and_simulation_settings_are_explicit_and_isolated(adapted_case):
    result = build_business_runtime(*adapted_case)
    first = result.generator_factory()
    second = result.generator_factory(horizon=250)
    assert first.horizon == 80 and second.horizon == 250
    assert first.expansion_limit == 10000 and first.deadline_ms is None
    assert first.cache_contract == "isolated_replay_v1"
    assert first._owned_topology_cache is not second._owned_topology_cache
    args = result.simulation_kwargs()
    assert args["search_horizon"] == 80 and args["candidate_count"] == 4
    assert args["route_mode"] == "whole_route" and args["reactive_empty_dispatch"] is True
    assert args["coordination_order"] == "route_then_prebalance"


@pytest.mark.parametrize("key", ["node_resource_policy", "edge_permission_policy", "travel_policy",
                                  "partition_by_node", "module", "routing", "evidence"])
def test_missing_runtime_parameters_fail_closed(adapted_case, key):
    workload, path, contract = adapted_case
    del contract[key]
    with pytest.raises(BusinessInputError):
        build_business_runtime(workload, path, contract)


@pytest.mark.parametrize("key,value", [("kind", "supplier_claim"), ("loading_seconds", "0.1"),
    ("unload_seconds", None), ("hold_seconds_by_node", {"0": 0}), ("reception_capacity", True),
    ("export_min_stock", -1)])
def test_unsupported_or_incomplete_module_rejected(adapted_case, key, value):
    workload, path, contract = adapted_case
    contract["module"][key] = value
    with pytest.raises(BusinessInputError):
        build_business_runtime(workload, path, contract)


@pytest.mark.parametrize("key,value", [("search_horizon", 0), ("expansion_limit", None),
    ("candidate_count", True), ("deadline_ms", 100), ("cache_contract", None), ("route_mode", "unknown")])
def test_no_silent_route_budget_fallback(adapted_case, key, value):
    workload, path, contract = adapted_case
    contract["routing"][key] = value
    with pytest.raises(BusinessInputError):
        build_business_runtime(workload, path, contract)


def test_input_contract_cannot_be_replaced_after_runtime_contract_declaration(adapted_case):
    workload, path, contract = adapted_case
    contract["input_contract_sha256"] = "0" * 64
    with pytest.raises(BusinessInputError, match="input contract binding"):
        build_business_runtime(workload, path, contract)


def test_profile_change_and_denominator_loss_rejected(adapted_case):
    workload, path, contract = adapted_case
    with pytest.raises(BusinessInputError, match="workload content binding"):
        build_business_runtime(replace(workload, tasks=workload.tasks[:1]), path, contract)
    path.write_text(path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(BusinessInputError, match="profile bytes differ"):
        build_business_runtime(workload, path, contract)


def test_late_publication_or_direct_storage_discard_rejected(adapted_case):
    workload, path, contract = adapted_case
    early, direct = workload.tasks
    with pytest.raises(BusinessInputError, match="workload content binding"):
        build_business_runtime(replace(workload, tasks=(replace(early, published_at=early.arrival+1), direct)), path, contract)
    with pytest.raises(BusinessInputError, match="workload content binding"):
        build_business_runtime(replace(workload, tasks=(early, replace(direct, release_at=500))), path, contract)


def test_no_confimed_label_or_implicit_permissions(adapted_case):
    workload, path, contract = adapted_case
    contract["evidence_status"] = "confirmed"
    with pytest.raises(BusinessInputError, match="proxy_research"):
        build_business_runtime(workload, path, contract)
    contract["evidence_status"] = "proxy_research"
    contract["empty_wait_policy"] = None
    with pytest.raises(BusinessInputError, match="empty_wait_policy"):
        build_business_runtime(workload, path, contract)


@pytest.mark.parametrize("update", [
    {"protected": False}, {"deadline_seconds": 6000, "deadline": 600},
    {"lifecycle": "direct", "storage_node": None, "release_at": None, "published_at": None},
    {"origin": "1"},
])
def test_audited_business_task_cannot_change_between_input_and_adapter(adapted_case, update):
    workload, path, contract = adapted_case
    mutated = replace(workload, tasks=(replace(workload.tasks[0], **update), workload.tasks[1]))
    with pytest.raises(BusinessInputError, match="workload content binding"):
        build_business_runtime(mutated, path, contract)


@pytest.mark.parametrize("update,error", [
    ({"protected": False}, "protection policy"),
    ({"deadline_seconds": 6000, "deadline": 600}, "deadline policy"),
    ({"lifecycle": "direct", "storage_node": None, "release_at": None, "published_at": None}, "lifecycle policy"),
    ({"scheduled_release_seconds": 2301, "release_at": 231}, "release policy"),
])
def test_resealed_payload_still_cannot_override_explicit_business_policies(adapted_case, update, error):
    workload, path, contract = adapted_case
    mutated = replace(workload, tasks=(replace(workload.tasks[0], **update), workload.tasks[1]))
    mutated = replace(mutated, content_sha256=business_workload_sha256(mutated))
    with pytest.raises(BusinessInputError, match=error):
        build_business_runtime(mutated, path, contract)
