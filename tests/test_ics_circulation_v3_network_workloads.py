from dataclasses import replace
import json

import pytest

from scripts.experiments.ics_circulation_v3.audit_nanning import DEFAULT_PROFILE
from scripts.experiments.ics_circulation_v3.phase4_network_workloads import (
    NetworkAssumptions, file_sha, load_network, make_workload, projected_window, read_projected_tasks)
from scripts.experiments.ics_circulation_v3.run_workload_diagnostics import (
    DiagnosticBudget, RecordedFactory, WorkBudgetExceeded, empty_capacity_diagnostic, run, run_case)
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec
from scripts.experiments.ics_circulation_v3.runtime import assert_invariants


@pytest.fixture(scope="module")
def topology():
    return load_network()


def test_original_direction_capacity_and_zero_edge_are_preserved(topology):
    network, metadata = topology
    before = file_sha(DEFAULT_PROFILE)
    profile = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    original = {f"{e['start']}->{e['end']}": e for e in profile["edges"]}
    assert len(network.nodes) == 151
    assert len(network.edges) == 226
    assert set(network.edges) == {key for key, e in original.items() if e["capacity"] > 0}
    assert all(e.capacity == original[key]["capacity"] for key, e in network.edges.items())
    assert "97->98" not in network.edges
    assert metadata["closed_zero_capacity_edges"] == [{"start": "97", "end": "98", "capacity": 0, "reason": "closed_in_proxy"}]
    assert file_sha(DEFAULT_PROFILE) == before


def test_every_od_is_classified_including_nonreturnable_pairs(topology):
    network, metadata = topology
    assert metadata["all_loader_unloader_od_count"] == 462
    assert metadata["od_class_counts"] == {"outbound_unreachable": 66, "directed_cycle_available": 360, "return_unreachable": 36}
    for row in metadata["od_classes"]:
        for key, source, target in (("loaded_path", row["origin"], row["destination"]),
                                    ("return_path", row["destination"], row["origin"])):
            path = row[key]
            if path:
                assert network.edges[path[0]].source == source
                assert network.edges[path[-1]].target == target
                assert all(network.edges[a].target == network.edges[b].source for a, b in zip(path, path[1:]))
    assert len(metadata["no_wait_nodes"]) == 27
    assert all(metadata["source_node_roles"][key]["type"] == 4 for key in metadata["no_wait_nodes"])


def projection_files(tmp_path):
    raw = tmp_path / "raw.txt"
    raw.write_text("ID EntryTime(s) STD(s) star end Unloader Loader\n0 36010 39000 134 46 U L\n1 36020 45000 136 48 U L\n", encoding="utf-8")
    canonical = tmp_path / "canonical.jsonl"
    entries = []
    for identifier, origin, destination, arrival, deadline, legs in (
            (0, 134, 46, 36010, 39000, ("direct",)),
            (1, 136, 48, 36020, 45000, ("storage_in", "storage_out"))):
        for leg in legs:
            entries.append({"task_id": identifier, "segment_id": f"{identifier}:{leg}", "leg": leg,
                            "original_start": origin, "original_goal": destination,
                            "original_entry_time": arrival, "std": deadline})
    canonical.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema": "czr005.g4irsf31.nanning_workload_manifest.v1",
        "raw_task_count": 2, "expanded_segment_count": 3, "direct_raw_task_count": 1,
        "early_split_raw_task_count": 1, "raw_by_start": {"134": 1, "136": 1},
        "raw_by_goal": {"46": 1, "48": 1}, "flight_count": 1, "protocol": "synthetic_test_only",
        "mapping_rule": {}, "storage_pair": {"storage_in_goal": 53}}), encoding="utf-8")
    return raw, canonical, manifest


def test_full_projected_denominator_and_unsupported_lifecycle_remain_visible(tmp_path, topology):
    network, metadata = topology
    rows, audit = read_projected_tasks(*projection_files(tmp_path), metadata)
    assert audit["raw_task_count"] == 2
    assert audit["expanded_segment_count"] == 3
    assert audit["lifecycle_counts_all_original_bags"] == {"supported_direct_bag": 1, "unsupported_early_bag_storage_lifecycle": 1}
    scene = projected_window(rows, network, metadata)
    assert len(scene.future_bags) == 1
    assert scene.future_bags[0].bag_id == "projected:0"
    assert scene.provenance["all_bags_in_window"] == 2
    assert scene.provenance["unsupported_early_bags_in_window"] == 1
    assert scene.forecasts == ()
    assert scene.future_bags[0].arrival == 3
    assert_invariants(scene.initial)


def test_projected_duplicate_segment_or_manifest_count_is_rejected(tmp_path, topology):
    paths = projection_files(tmp_path)
    raw, canonical, manifest = paths
    canonical.write_text(canonical.read_text() + "\n" + canonical.read_text().splitlines()[0])
    with pytest.raises(ValueError, match="duplicate canonical"):
        read_projected_tasks(*paths, topology[1])
    paths = projection_files(tmp_path)
    data = json.loads(manifest.read_text())
    data["raw_task_count"] = 3
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="full-denominator mismatch"):
        read_projected_tasks(*paths, topology[1])


@pytest.mark.parametrize("name", ("short_cycle", "shared_receiver", "long_line", "capacity_one", "ample", "reversal", "closed_od", "one_way_return"))
def test_burn_in_is_accepted_not_hand_authored_and_graph_is_unchanged(name, topology):
    network, metadata = topology
    scene = make_workload(name, network, metadata, rounds=2)
    assert scene.initial.now == 1
    assert scene.initial.plans["warm_tray"].bag_id.endswith(":warm")
    assert scene.provenance["burn_in"]["invariant_checks"] >= 2
    assert scene.initial.network.edges == network.edges
    assert set(scene.initial.network.nodes) == set(network.nodes)
    assert_invariants(scene.initial)
    if name == "reversal":
        cancellations = [f for f in scene.forecasts if f.count == 0]
        assert len(cancellations) == 1
        cancelled = cancellations[0]
        observed = next(b for b in scene.future_bags if b.bag_id == cancelled.forecast_id + ":0")
        assert observed.origin != cancelled.node
        assert cancelled.published_at < observed.arrival
    if name == "ample":
        assert "not a stock-only" in scene.provenance["ample_qualification"]


def test_real_topology_cycle_reuses_trays_without_no_wait_stranding(topology):
    scene = make_workload("short_cycle", *topology, rounds=2)
    result = run_case(scene, predictive=False, budget=DiagnosticBudget(max_search_work=200000, max_wall_seconds=15))
    assert result["failure"] is None
    assert result["metrics"]["invariant_error"] is None
    assert result["metrics"]["status"] == "completed_all"
    assert result["metrics"]["completed"] == 3
    assert result["metrics"]["trays_serving_multiple_bags"] >= 1
    assert result["metrics"]["tray_identity_preserved"]
    assert result["metrics"]["protected_admitted_late"] == []


def test_budget_exhaustion_retains_unobserved_future_denominator(topology):
    scene = make_workload("cross_cycle", *topology, rounds=2)
    result = run_case(scene, predictive=True, budget=DiagnosticBudget(max_search_calls=1, max_search_work=1, per_search_work=1))
    assert result["metrics"]["status"] == "budget_exhausted"
    assert result["metrics"]["future_unobserved"] > 0
    assert result["metrics"]["all_scheduled_bag_denominator"] == 5
    assert result["metrics"]["completed"] + result["metrics"]["uncompleted_including_unobserved"] == 5
    assert result["metrics"]["search_work"] <= 1
    assert result["metrics"]["total_cost"] is None
    # The engine owns cloned callback state; reporting must read that state.
    assert result["metrics"]["actual_slow_trigger_times"] == [1]


def test_preserve_outputs_and_invalid_protocol_fails_before_creation(tmp_path):
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "original.txt").write_text("keep")
    with pytest.raises((ValueError, FileExistsError)):
        run(occupied, names=("short_cycle",))
    untouched = tmp_path / "invalid"
    with pytest.raises(ValueError):
        run(untouched, names=("not_a_scene",))
    assert not untouched.exists()
    assert (occupied / "original.txt").read_text() == "keep"


@pytest.mark.parametrize("kwargs", ({"tick_seconds": 0}, {"tick_seconds": float("nan")}, {"node_capacity": 0},
                                    {"no_wait_divert_modulus": -1}, {"unload_ticks": -1}))
def test_invalid_unknown_proxy_values_are_not_silently_filled(kwargs):
    with pytest.raises(ValueError):
        NetworkAssumptions(**kwargs)


def test_counterflow_alignment_uses_original_shared_edge_capacity(topology):
    scene = make_workload("counterflow", *topology, rounds=2)
    alignment = scene.provenance["counterflow_alignment"]
    assert len(scene.provenance["flows"]) == 3
    assert alignment["shared_edge"] == "28->29"
    assert alignment["preserved_capacity"] == topology[0].edges["28->29"].capacity == 2
    assert len(scene.future_bags) == 6
    assert scene.initial.network.edges == topology[0].edges
    for phase, flow in zip(alignment["flow_arrival_phases"][1:], scene.provenance["flows"][1:]):
        prefix = flow["loaded_path"][:flow["loaded_path"].index(alignment["shared_edge"])]
        assert phase + sum(topology[0].edges[e].travel_time for e in prefix) == alignment["nominal_empty_entry_tick"]


def test_capacity_one_empty_commit_delays_loaded_route_without_illegal_cooccupancy():
    from scripts.experiments.ics_circulation_v3.model import Bag, Edge, FixedLocalModule, Leg, Network, Node, RouteCandidate, Snapshot, Tray
    from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator
    network = Network({n: Node(n, n, n, capacity=2) for n in ("A", "B")}, {"AB": Edge("AB", "A", "B", 2, 1)})
    state = Snapshot(0, network, {"empty": Tray("empty", "A"), "loaded": Tray("loaded", "A", "loaded", "bag")},
                     {"bag": Bag("bag", "A", "B", 0, 10)}, module=FixedLocalModule(unload_ticks=0))
    empty = RouteCandidate("empty-route", None, "empty", (Leg("AB", 0, 2),), 2, 2, 0, "test", destination_node="B")
    assert ExecutionValidator().commit(state, empty).accepted
    loaded = RouteCandidate("loaded-route", "bag", "loaded", (Leg("AB", 2, 4),), 4, 4, state.version, "test")
    assert ExecutionValidator().validate(state, loaded).accepted
    before = state.clone()
    diagnostic = empty_capacity_diagnostic(state, "bag", "loaded", (loaded,))
    assert diagnostic["full_capacity_conflict"] == "capacity:edge:AB@0"
    assert diagnostic["without_committed_empty_capacity_conflict"] is None
    assert diagnostic["candidate_unload_delay_vs_static"] == 2
    assert any(r["resource"] == "edge:AB" and r["binding_empty_occupancy"] for r in diagnostic["resources"])
    assert diagnostic["counterfactual_executed"] is False
    assert state == before  # No plan, tray identity or owner resource is revoked.


@pytest.mark.parametrize("value", (float("nan"), float("inf"), -1))
def test_nonfinite_wall_safeguards_are_rejected(value):
    with pytest.raises(ValueError):
        DiagnosticBudget(max_wall_seconds=value)
