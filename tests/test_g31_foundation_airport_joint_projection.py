"""Mechanism gates for public one-use inventory and independent spatial maps."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_projection as projection
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_rules as rules
from scripts.experiments.g31_ics_circulation import foundation_airport_loader_mapping as mapping
from scripts.experiments.g31_ics_circulation import foundation_airport_feasible_domain as frozen
from test_g31_airport_inventory_rule import observation, snapshot


def fixture(stocks=(2, 3, 0)):
    obs = observation(source=0, stock=stocks[0])
    obs.update(observation_scope="controller_policy", version=7,
        control_projection={"schema": "g31.analytic_control_projection.v1", "waiting_groups": []})
    obs["static_role_contract"]["loader_nodes"] = [0, 1, 2]
    obs["trays"] = []
    for node, count in enumerate(stocks):
        obs["node_contracts"][node].update(actual_available=count, occupancy=count)
        for index in range(count):
            obs["trays"].append({"tray_id": f"T{node}-{index}", "node": node, "mode": "empty",
                "available_at": 0., "edge_to": -1, "reception_node": -1, "generation": 0})
    return obs


def forecast(obs, masses=None, *, missing=None):
    values = {f"airport_node_{node}": list((masses or {}).get(node, [0.] * 30)) for node in range(3)}
    return {"schema": "g31.foundation.new_demand_forecast.v1", "owner_scope": obs["owner_id"],
        "forecast_origin": obs["now"], "remaining_support_until": obs["now"]+1800.,
        "bin_edges_seconds": [float(t) for t in range(0, 1801, 60)],
        "new_demand_mean_by_region": values,
        "missing_mask_by_region": {key: key in (missing or []) for key in values},
        "mapping_version": "test_known_nodes", "airport_mapping_sha256": "test_mapping"}


def catalog(obs, *, eta_a=2., eta_b=20.):
    candidates = [{"action_id": "noop", "action_type": "noop"}]
    for source, eta in [(0, eta_a), (1, eta_b)]:
        candidates.append({"action_id": f"move_{source}", "action_type": "transfer", "tray_id": f"T{source}-0",
            "source": source, "destination": 2, "earliest_departure": obs["now"],
            "nominal_arrival_time": obs["now"]+eta, "static_travel_time": eta})
    return {"catalog_id": "test", "candidates": candidates}


def add_request(obs, *, status="accepted", identity="T0-0", received_at=-1.):
    request = {"request_id": "r1", "tray_id": identity, "source": 0, "destination": 2,
        "issued_at": 1., "earliest_departure": 2., "status": status, "received_at": received_at,
        "status_scope": "own_payload_and_last_delivered_ack_only"}
    obs["client_transfer_ledger"] = [request]
    obs["transfers"] = copy.deepcopy(obs["client_transfer_ledger"])


def test_eta_inside_same_demand_bin_is_not_rounded_to_bin_start():
    kwargs = dict(stock=0., waiting=0., demand_edges=[0., 60.], demand_means=[1.],
                  horizon_seconds=60., service_rate=1000.)
    early = projection.simulate_node(**kwargs, supply_events=[(2., 1.)])
    late = projection.simulate_node(**kwargs, supply_events=[(59., 1.)])
    assert 0 < early["backlog_area"] < late["backlog_area"] < 30.
    assert late["backlog_area"] > 28.
    assert late["ending_inventory"] >= 0.


def test_service_capacity_is_finite_and_consumed_tray_never_returns():
    result = projection.simulate_node(stock=1., waiting=3., supply_events=[],
        demand_edges=[0., 60.], demand_means=[0.], horizon_seconds=60., service_rate=.5)
    assert result["served_mass"] == 1.
    assert result["ending_backlog"] == 2.
    assert result["ending_inventory"] == 0.
    assert result["backlog_area"] == 121.


def test_pending_is_not_inbound_and_accepted_removes_current_source():
    obs = fixture()
    add_request(obs, status="pending")
    pending = projection.prepare_inventory_projection(obs)
    assert "T0-0" not in pending.actual_by_tray
    assert pending.nodes[0]["stock"] == 1.
    assert not pending.nodes[2]["events"]
    add_request(obs, status="accepted")
    accepted = projection.prepare_inventory_projection(obs)
    assert len(accepted.nodes[2]["events"]) == 1
    assert accepted.nodes[2]["events"][0][0] > 0
    assert accepted.nodes[0]["stock"] == 1.


@pytest.mark.parametrize("status", ["received", "accepted"])
def test_current_destination_capture_deduplicates_prior_inbound(status):
    obs = fixture((1, 0, 1))
    obs["trays"][-1]["tray_id"] = "moved"
    add_request(obs, status=status, identity="moved", received_at=8.)
    prepared = projection.prepare_inventory_projection(obs)
    assert prepared.nodes[2]["stock"] == 1.
    assert prepared.nodes[2]["events"] == []
    assert sum(row["physical_tray_id"] == "moved" for row in prepared.supply_events) == 1


def test_remote_received_capture_dedup_preserves_actual_identity():
    obs = observation(remote=True)
    obs.update(observation_scope="controller_policy", version=7,
        control_projection={"schema": "g31.analytic_control_projection.v1", "waiting_groups": []})
    obs["planning_snapshots"] = [snapshot(stock=1)]
    add_request(obs, status="received", identity="B0", received_at=7.)
    prepared = projection.prepare_inventory_projection(obs)
    assert prepared.nodes[2]["stock"] == 1.
    assert prepared.nodes[2]["events"] == []


def test_historical_received_request_cannot_recreate_tray_after_next_cycle():
    obs = fixture((2, 0, 0))
    obs["node_contracts"][2].update(resource_owner="B", zone="B")
    obs["node_contracts"][2].pop("actual_available")
    add_request(obs, status="received", identity="T0-0", received_at=7.)
    prepared = projection.prepare_inventory_projection(obs)
    assert prepared.actual_by_tray["T0-0"] == 0
    assert not prepared.nodes[2]["events"]


def test_release_is_conditional_at_actual_unloader_never_original_loader():
    obs = fixture((0, 0, 0))
    obs["trays"] = [{"tray_id": "loaded", "node": 2, "generation": 1, "mode": "unloading",
        "available_at": 15., "business_bag_id": "bag", "edge_to": -1, "reception_node": -1}]
    obs["jobs"] = [{"business_bag_id": "bag", "arrival": 1., "origin": 0,
        "status": "unloading", "hold_seconds": 7.}]
    committed = projection.prepare_inventory_projection(obs)
    conditional = projection.prepare_inventory_projection(obs, supply_mode="conditional_next_release")
    assert not committed.nodes[2]["events"]
    assert conditional.nodes[2]["events"] == [(12., 1., "conditional_next_release")]
    assert not conditional.nodes[0]["events"]


def test_unknown_remote_inventory_and_waiting_stay_none():
    obs = fixture()
    obs["node_contracts"][2].update(resource_owner="B", zone="B")
    for key in ("actual_available", "occupancy"):
        obs["node_contracts"][2].pop(key)
    prepared = projection.prepare_inventory_projection(obs, forecast=forecast(obs, {2: [1.]+[0.]*29}))
    assert prepared.nodes[2]["stock"] is None
    assert prepared.nodes[2]["waiting"] is None
    result = rules.score_joint_catalog(prepared, catalog(obs), information_variant="C10")
    assert result["selected_action_id"] == "noop"
    features = rules.joint_candidate_features(prepared, catalog(obs))["move_0"]
    assert features["features_current"]["destination_stock"] is None
    assert features["features_current"]["destination_inventory_known"] == 0.


def test_source_opportunity_cost_can_prefer_farther_source():
    obs = fixture()
    f = forecast(obs, {0: [2.]+[0.]*29, 2: [1.]+[0.]*29})
    prepared = projection.prepare_inventory_projection(obs, forecast=f)
    actions = catalog(obs)
    assert rules.score_joint_catalog(prepared, actions, information_variant="C00")["selected_action_id"] == "move_0"
    result = rules.score_joint_catalog(prepared, actions, information_variant="C10")
    assert result["selected_action_id"] == "move_1"
    assert result["scores"][1]["projection"]["source_area_delta"] > 500.
    assert result["scores"][2]["projection"]["source_area_delta"] == 0.


def test_later_than_first_shortage_is_still_valuable_and_nonzero_stock_can_receive():
    obs = fixture((2, 3, 1))
    f = forecast(obs, {2: [2.]+[0.]*29})
    prepared = projection.prepare_inventory_projection(obs, forecast=f)
    result = rules.score_joint_catalog(prepared, catalog(obs, eta_a=50.), information_variant="C10")
    row = result["scores"][1]["projection"]
    assert row["destination_without_move"]["first_shortage_offset"] == pytest.approx(30.)
    assert row["arrival_offset"] == 50.
    assert row["proxy_gain"] > 0.
    assert result["selected_action_id"] != "noop"


def test_current_features_and_current_policy_are_independent_of_B1():
    obs = fixture()
    a = projection.prepare_inventory_projection(obs)
    b = projection.prepare_inventory_projection(obs, forecast=forecast(obs, {0: [99.]*30, 2: [99.]*30}))
    ca, cb = rules.joint_candidate_features(a, catalog(obs)), rules.joint_candidate_features(b, catalog(obs))
    assert {key: row["features_current"] for key, row in ca.items()} == {key: row["features_current"] for key, row in cb.items()}
    assert rules.score_joint_catalog(a, catalog(obs)) == rules.score_joint_catalog(b, catalog(obs))


def test_forecast_support_clips_postarrival_window_without_extrapolation():
    obs = fixture()
    prepared = projection.prepare_inventory_projection(obs, forecast=forecast(obs, {2: [1.]*30}))
    features = rules.joint_candidate_features(prepared, catalog(obs, eta_a=1750.))["move_0"]["features_forecast"]
    assert features["horizon_exceeded"] == 1.
    assert features["destination_demand_after_arrival_300s"] == pytest.approx(50./60.)


def test_preparation_detaches_forecast_and_binds_maximum_model_availability():
    obs = fixture()
    f = forecast(obs)
    f.update(model_sha256="B1", loader_mapping_model_available_at_epoch_seconds=400.,
        calendar_provenance={"absolute": {"information_cutoffs": {"model_frozen_at": 500.}}})
    prepared = projection.prepare_inventory_projection(obs, forecast=f)
    f["new_demand_mean_by_region"]["airport_node_2"][0] = 999.
    features = rules.joint_candidate_features(prepared, catalog(obs))["move_0"]
    assert features["features_forecast"]["destination_demand_300s"] == 0.
    assert features["model_available_at"] == 500.
    assert features["model_id"] == "B1"


def test_stale_catalog_cannot_use_prepared_feature_cache():
    obs = fixture()
    prepared = projection.prepare_inventory_projection(obs)
    actions = catalog(obs)
    actions["candidates"][0]["public_state_digest"] = "stale"
    with pytest.raises(ValueError, match="prepared_catalog_state"):
        rules.joint_candidate_features(prepared, actions)


def labels():
    return [{"label_id": f"label_{i}", "parent_id": "train_1", "split": "train",
        "region": "legacy_start_0", "loader": 0, "observed_at_epoch_seconds": 100.+i,
        "provenance_kind": "observed_entry"} for i in range(8)]


def fit(rows=None):
    return mapping.fit_loader_mapping(labels() if rows is None else rows,
        train_parent_ids=["train_1"], training_labels_closed_at_epoch_seconds=200.,
        model_available_at_epoch_seconds=201., input_domain={"split": "train",
            "labels_kind": "observed_entry_labels", "uses_future_crosswalk": False})


def regional():
    return {"schema": "g31.foundation.new_demand_forecast.v1", "owner_scope": "A", "forecast_origin": 202.,
        "bin_edges_seconds": [0., 60., 120.],
        "new_demand_mean_by_region": {region: [1., 2.] for region in mapping.flight.REGIONS},
        "missing_mask_by_region": {region: False for region in mapping.flight.REGIONS}}


def test_train_mapping_changes_region_weights_without_mutating_frozen_v2():
    trained = fit()
    row = trained["regions"]["legacy_start_0"]
    assert row["weights"][row["nodes"].index(0)] == pytest.approx(9./16.)
    assert trained["regions"]["legacy_start_1"]["fallback_to_prior"]
    with pytest.raises(ValueError, match="mapping_identity"):
        frozen.validate_mapping(trained)
    assert trained["source_mapping_sha256"] == mapping.calendar.static_mapping()["sha256"]


@pytest.mark.parametrize("change", ["test", "dev", "parent", "future", "crosswalk", "duplicate"])
def test_train_mapping_rejects_leakage_and_duplicate_entries(change):
    rows = labels()
    if change in ("test", "dev"):
        rows[0]["split"] = change
    elif change == "parent":
        rows[0]["parent_id"] = "heldout"
    elif change == "future":
        rows[0]["observed_at_epoch_seconds"] = 201.
    elif change == "crosswalk":
        rows[0]["provenance_kind"] = "future_balanced_assignment"
    else:
        rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError):
        fit(rows)


def test_mapping_mean_conservation_missing_propagation_and_no_node_intervals():
    trained, forecast = fit(), regional()
    projected = mapping.project_forecast(forecast, trained, now=202., owner="A")
    assert projected["projection_audit"]["mapped_known_mass_per_bin"] == pytest.approx([7., 14.])
    assert all(value is None for value in projected["uncertainty_by_region"].values())
    forecast["missing_mask_by_region"]["legacy_start_0"] = [True, False]
    forecast["new_demand_mean_by_region"]["legacy_start_0"] = [None, 2.]
    projected = mapping.project_forecast(forecast, trained, now=202., owner="A")
    assert projected["new_demand_mean_by_region"]["airport_node_0"][0] is None
    assert projected["new_demand_mean_by_region"]["airport_node_0"][1] > 0.
    assert projected["missing_mask_by_region"]["airport_node_134"] == [False, False]
    with pytest.raises(ValueError, match="not_yet_available"):
        mapping.project_forecast(regional(), trained, now=202., owner="A", now_epoch_seconds=200.)


def test_rehashed_mapping_cannot_backdate_labels_or_change_observed_domain():
    trained = fit()
    trained["training_labels_closed_at_epoch_seconds"] = 99.
    trained["sha256"] = mapping.digest({key: value for key, value in trained.items() if key != "sha256"})
    with pytest.raises(ValueError, match="observed_label_bounds"):
        mapping.validate_mapping(trained)
    trained = fit()
    trained["input_domain"]["uses_future_crosswalk"] = True
    trained["sha256"] = mapping.digest({key: value for key, value in trained.items() if key != "sha256"})
    with pytest.raises(ValueError, match="train_only_contract"):
        mapping.validate_mapping(trained)
