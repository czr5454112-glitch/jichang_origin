"""Explicit public arrival support is distinct from guessing missing stock."""
import copy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_arrival_support as support
from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_projection as projection
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_rules as rules


@pytest.fixture(scope="module")
def contract():
    parent = support.parents._expected_registration(2101, 0)
    # Deliberately fake offline-audit reference and fake receipt: unit fixtures
    # do not claim any native input audit, preload or simulation was performed.
    return support.build_arrival_support_contract(parent=parent, input_origin_support_audit_sha256="a"*64)


def receipt(contract, owner="A"):
    return support.record_controller_preload(contract, SimpleNamespace(physical_time=0.), owners=[owner])[owner]


def observation(*, remote_source=False):
    return {"schema": "g31.owner_protocol_observation.v1", "observation_scope": "controller_policy",
        "owner_id": "A", "now": 10., "version": 7,
        "static_role_contract": {"schema": "g31.static_node_roles.v1", "loader_nodes": list(support.domain.ACTIVE_LOADERS)},
        "node_contracts": [{"node": node, "resource_owner": "A", "zone": "A", "capacity": 4,
            "actual_available": int(node == 1), "occupancy": int(node == 1), "allow_receive": True,
            "allow_export": True, "export_min_stock": 0} for node in range(151)],
        "node_records": [[node, 4, .001] for node in range(151)],
        "edge_records": [[1, 0, 2., 1.], [1, 24, 20., 1.]], "edge_contracts": [],
        "trays": [{"tray_id": "returned", "node": 1, "generation": 0, "mode": "empty",
            "available_at": 0., "edge_to": -1, "reception_node": -1}], "jobs": [],
        "control_projection": {"schema": "g31.analytic_control_projection.v1", "waiting_groups": []},
        "transfers": [], "client_transfer_ledger": [], "delivered_messages": []}


def forecast(obs):
    return {"schema": "g31.foundation.new_demand_forecast.v1", "owner_scope": "A", "forecast_origin": obs["now"],
        "remaining_support_until": obs["now"]+1800., "bin_edges_seconds": list(range(0, 1801, 60)),
        "new_demand_mean_by_region": {f"airport_node_{node}": ([1.]+[0.]*29 if node == 24 else [0.]*30)
                                      for node in support.domain.ACTIVE_LOADERS},
        "missing_mask_by_region": {f"airport_node_{node}": False for node in support.domain.ACTIVE_LOADERS}}


def catalog(obs):
    return {"catalog_id": "fixture", "candidates": [{"action_type": "noop", "action_id": "noop"}]+[
        {"action_type": "transfer", "action_id": f"to_{node}", "tray_id": "returned", "source": 1,
            "destination": node, "earliest_departure": obs["now"], "nominal_arrival_time": obs["now"]+eta,
            "static_travel_time": eta} for node, eta in [(0, 2.), (24, 20.)]]}


def test_shared_explicit_support_enables_destination_forecast_for_ordinary_return(contract):
    obs, received = observation(), receipt(contract)
    unknown = projection.prepare_inventory_projection(obs, forecast=forecast(obs))
    declared = projection.prepare_inventory_projection(obs, forecast=forecast(obs),
        arrival_support_contract=contract, arrival_support_receipt=received)
    assert projection.demand_mass(unknown, 1, 0., 300.) is None
    assert projection.demand_mass(declared, 1, 0., 300.) == 0.
    assert rules.score_joint_catalog(unknown, catalog(obs), information_variant="C10")["selected_action_id"] == "to_0"
    assert rules.score_joint_catalog(declared, catalog(obs), information_variant="C10")["selected_action_id"] == "to_24"
    current = rules.joint_candidate_features(declared, catalog(obs))["to_24"]["features_current"]
    assert current["source_external_arrival_possible"] == 0.
    assert current["destination_external_arrival_possible"] == 1.


def test_structural_new_arrival_zero_never_erases_existing_waiting_or_missing_remote_stock(contract):
    obs = observation()
    obs["control_projection"]["waiting_groups"] = [{"origin": 1, "count": 3,
        "demand_observed_at": 10., "jobs": []}]
    obs["node_contracts"][2].update(resource_owner="B", zone="B")
    obs["node_contracts"][2].pop("actual_available")
    prepared = projection.prepare_inventory_projection(obs, forecast=forecast(obs),
        arrival_support_contract=contract, arrival_support_receipt=receipt(contract))
    assert projection.demand_mass(prepared, 1, 0., 300.) == 0.
    assert prepared.nodes[1]["waiting"] == 3.
    assert prepared.nodes[2]["stock"] is None and prepared.nodes[2]["waiting"] is None
    assert projection.demand_mass(prepared, 2, 0., 300.) == 0.
    assert not prepared.nodes[2]["inventory_known"]


def test_missing_active_loader_forecast_is_not_a_structural_zero(contract):
    obs, f = observation(), forecast(observation())
    f["new_demand_mean_by_region"].pop("airport_node_24")
    f["missing_mask_by_region"].pop("airport_node_24")
    prepared = projection.prepare_inventory_projection(obs, forecast=f,
        arrival_support_contract=contract, arrival_support_receipt=receipt(contract))
    assert projection.demand_mass(prepared, 24, 0., 300.) is None


@pytest.mark.parametrize("mutation", ["no_receipt", "owner", "future_receipt", "support_nodes", "generator", "business"])
def test_contract_or_receipt_cannot_be_forged_by_rehashing(contract, mutation):
    changed, received = copy.deepcopy(contract), receipt(contract)
    if mutation == "no_receipt":
        received = None
    elif mutation == "owner":
        received["owner_id"] = "B"
    elif mutation == "future_receipt":
        received["received_at_physical_seconds"] = 11.
    elif mutation == "support_nodes":
        changed["external_arrival_nodes"].remove(24)
    elif mutation == "generator":
        changed["parent_generator_source_sha256"] = "b"*64
    else:
        changed["business_semantic_sha256"] = "b"*64
    changed["sha256"] = support.digest({key: value for key, value in changed.items() if key != "sha256"})
    if received is not None:
        received["contract_sha256"] = changed["sha256"]
        received["receipt_sha256"] = support.digest({key: value for key, value in received.items() if key != "receipt_sha256"})
    with pytest.raises(ValueError):
        projection.prepare_inventory_projection(observation(), forecast=forecast(observation()),
            arrival_support_contract=changed, arrival_support_receipt=received)


def test_public_contract_cannot_override_conflicting_positive_forecast(contract):
    obs, f = observation(), forecast(observation())
    f["new_demand_mean_by_region"]["airport_node_1"] = [1.]+[0.]*29
    f["missing_mask_by_region"]["airport_node_1"] = False
    with pytest.raises(ValueError, match="conflicts_with_public_arrival_support"):
        projection.prepare_inventory_projection(obs, forecast=f,
            arrival_support_contract=contract, arrival_support_receipt=receipt(contract))


def test_contract_receipt_requires_actual_startup_clock_and_matches_parent(contract):
    with pytest.raises(ValueError, match="actual_startup_clock"):
        support.record_controller_preload(contract, SimpleNamespace(physical_time=1.), owners=["A"])
    with pytest.raises(ValueError, match="current_parent"):
        support.validate_arrival_support(contract, receipt(contract), now=10., owner="A",
            parent=support.parents._expected_registration(2102, 0))
    assert support.validate_arrival_support(contract, receipt(contract), now=0., owner="A",
        parent=contract["parent"]) == support.domain.ACTIVE_LOADERS
