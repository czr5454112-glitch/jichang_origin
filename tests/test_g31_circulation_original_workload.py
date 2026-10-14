"""Source-denominator and contract tests for original-graph circulation input."""
from collections import Counter
from dataclasses import replace
import json

import pytest

from scripts.experiments.g31_ics_circulation.original_workload import (
    DEFAULT_MAP, ROOT, ProxyContract, build_input, static_diagnostics,
    summarize_execution, verify_source_map, return_contract_diagnostics, source_map,
)


CONTRACT = ProxyContract("test-proxy", 4, 64, 2, 1., 1., 0.,
                         "finite_berth_waiting_research_proxy")


@pytest.fixture(scope="module", params=(1, 2))
def prepared(request):
    return request.param, build_input(scale=request.param, contract=CONTRACT)


def test_complete_frozen_business_and_old_segment_denominators(prepared):
    scale, (data, manifest, crosswalk) = prepared
    frozen = json.loads((ROOT/f"artifacts/tasks/g4irsf31_nanning/nanning_{scale}x_manifest.json").read_text())
    assert len(data["jobs"]) == frozen["raw_task_count"] == scale*28506
    assert manifest["early_storage_count"] == frozen["early_split_raw_task_count"] == scale*15097
    assert manifest["old_segment_count"] == frozen["expanded_segment_count"] == scale*43603
    assert len({j["business_bag_id"] for j in data["jobs"]}) == len(data["jobs"])
    assert manifest["storage_pair"] == frozen["storage_pair"]
    assert dict(Counter(str(j["origin"]) for j in data["jobs"])) == frozen["raw_by_start"]
    assert dict(Counter(str(j["destination"]) for j in data["jobs"])) == frozen["raw_by_goal"]
    assert set(Counter(c["original_task_id"] for c in crosswalk).values()) == {scale}
    assert sum(c["synthetic_inserted"] for c in crosswalk) == (scale-1)*28506


def test_graph_and_source_services_are_not_relaxed(prepared):
    _, (data, manifest, _) = prepared
    profile = json.loads(DEFAULT_MAP.read_text(encoding="utf-8"))
    assert len(data["node_records"]) == 151
    assert len(data["edge_records"]) == 227
    assert {(u, v, length, speed) for u, v, length, speed in data["edge_records"]} == {
        (e["start"], e["end"], e["length"], e["speed"]) for e in profile["edges"]}
    assert {(e["from"], e["to"]): e["capacity"] for e in data["edge_contracts"]} == {
        (e["start"], e["end"]): e["pallet_capacity"] for e in profile["edges"]}
    assert manifest["closed_zero_capacity_edges"] == [[97, 98]]
    assert {r[0]: r[2] for r in data["node_records"]} == {
        n["location"]: n["service_time"] for n in profile["nodes"]}
    assert all(j["load_seconds"] == j["unload_seconds"] == 0 for j in data["jobs"])
    assert data["transfers"] == []  # A baseline cannot receive a prewritten return answer.
    assert len(data["trays"]) == 22
    assert all(n["resource_owner"].startswith("owner:system_") and
               n["control_partition"].startswith("partition:system_") and
               n["zone"] not in (n["resource_owner"], n["control_partition"])
               for n in data["node_contracts"])


def test_static_infeasibility_keeps_full_offered_denominator(prepared):
    scale, (data, _, _) = prepared
    diag = static_diagnostics(data)
    assert diag["offered"] == scale*28506
    assert diag["capacity_positive_path_unreachable"] == scale*4001
    assert diag["deadline_infeasible_even_without_queues"] == 0
    assert len(data["jobs"]) == scale*28506
    assert diag["arrival_to_release_is_not_a_valid_unconditional_occupancy_bound"]


def test_return_witnesses_preserve_direction_and_fixed_module_scope(prepared):
    scale, (data, _, _) = prepared
    diag = return_contract_diagnostics(data)
    assert diag["offered"] == scale*28506
    assert diag["pair_count"] == 42*11
    assert diag["pair_status_counts"] == {
        "same_zone_requires_internal_module_not_central_transfer": 226,
        "cross_zone_fixed_port_scope_candidate": 200,
        "no_positive_capacity_directed_path": 36}
    assert diag["offered_with_no_directed_return_to_any_loader"] == 0
    legal_edges = {(e["from"], e["to"]) for e in data["edge_contracts"] if e["capacity"] > 0}
    for pair in diag["pairs"]:
        path = pair["positive_capacity_path_witness"]
        if path:
            assert (path[0], path[-1]) == (pair["terminal"], pair["loader"])
            assert all(edge in legal_edges for edge in zip(path, path[1:]))
        if pair["status"] == "cross_zone_fixed_port_scope_candidate":
            assert pair["terminal_zone"] != pair["loader_zone"]


@pytest.mark.parametrize("changes", [
    {"waiting_contract": "all_positions_confirmed_safe"},
    {"node_berths": 0}, {"trays_per_loader": 5},
    {"hold_seconds": float("nan")}, {"entry_headway_seconds": -1.},
    {"storage_berths": float("inf")},
])
def test_unknown_or_invalid_contract_cannot_be_silently_accepted(changes):
    with pytest.raises(ValueError):
        replace(CONTRACT, **changes).validate()


def test_source_workbooks_match_profile_without_editing():
    profile = json.loads(DEFAULT_MAP.read_text(encoding="utf-8"))
    result = verify_source_map(profile, source_map.default_source_dir())
    assert result["status"] == "exact_source_rows_match"
    assert result["source_files_edited"] is False


def test_censored_unfinished_jobs_are_counted_not_zeroed():
    data = {"jobs": [{"arrival": 0, "deadline": 8}, {"arrival": 1, "deadline": 8}, {"arrival": 50, "deadline": 60}],
            "options": {"max_simulation_time": 100, "max_events": 5}}
    result = {"jobs": [
        {"status": "completed", "completed_at": 3, "loaded_at": 0, "deadline_met": True},
        {"status": "waiting_for_tray", "completed_at": -1, "loaded_at": -1, "deadline_met": False},
        {"status": "unreleased", "completed_at": -1, "loaded_at": -1, "deadline_met": False}],
        "trays": [{"mode": "empty", "reception_node": -1}], "physical_clock": 10,
        "native_summary": {"event_count": 5}}
    out = summarize_execution(data, result)
    assert (out["offered"], out["observed"], out["not_yet_observed"]) == (3, 2, 1)
    assert (out["completed"], out["uncompleted"], out["on_time"]) == (1, 2, 1)
    assert out["restricted_sojourn_sum_seconds_at_actual_clock"] == 12
    assert out["unfinished_past_deadline"] == 1
    assert out["event_budget_reached"] and not out["horizon_reached"]


def test_same_time_event_budget_does_not_claim_unprocessed_arrival_observed():
    data = {"jobs": [{"arrival": 10, "deadline": 100}],
            "options": {"max_simulation_time": 100, "max_events": 1}}
    result = {"jobs": [{"status": "unreleased", "completed_at": -1,
                         "loaded_at": -1, "deadline_met": False}],
              "trays": [], "physical_clock": 10,
              "native_summary": {"event_count": 1}}
    out = summarize_execution(data, result)
    assert out["offered"] == out["not_yet_observed"] == 1
    assert out["observed"] == 0
