"""Actual scope/campaign invariants; these tests do not start native."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation.analytic_control import transfer_candidates
from scripts.experiments.g31_ics_circulation.foundation_airport_action_campaign import parent_input


def local_observation():
    return {
        "now": 3., "owner_id": "A", "version": 1,
        "node_records": [(0, 1, .1, 0, 0, [1]), (1, 1, .1, 1, 0, [0])],
        "edge_records": [(0, 1, 2, 1), (1, 0, 2, 1)],
        "node_contracts": [{"node": n, "zone": "A", "resource_owner": "A", "capacity": 4}
                           for n in (0, 1)],
        "jobs": [{"business_bag_id": "waiting", "origin": 0, "destination": 1,
                  "arrival": 2., "status": "waiting_for_tray"}],
        "trays": [{"tray_id": "T", "node": 1, "mode": "empty", "edge_to": -1,
                   "business_bag_id": "", "available_at": 0}],
        "transfers": [], "delivered_messages": [],
        "static_role_contract": {"schema": "g31.static_node_roles.v1", "loader_nodes": [0]},
    }


def test_local_return_is_explicit_role_bound_current_actual_supply():
    obs = local_observation()
    before = copy.deepcopy(obs)
    decision = transfer_candidates(obs, predictive=True)
    assert len(decision["intents"]) == 1
    assert decision["intents"][0]["transfer_scope"] == "local_empty_return"
    assert obs == before
    obs.pop("static_role_contract")
    assert not transfer_candidates(obs, predictive=True)["intents"]
    obs = before
    obs["node_contracts"][0]["resource_owner"] = "B"
    assert not transfer_candidates(obs, predictive=True)["intents"]


def test_local_return_never_pledges_future_hold_release():
    obs = local_observation()
    obs["trays"][0].update(mode="hold", available_at=10.)
    assert not transfer_candidates(obs, predictive=True)["intents"]


def test_parent_variants_keep_population_od_and_nested_fleets():
    original, _ = parent_input()
    train, parent = parent_input(701)
    repeated, _ = parent_input(701)
    another, _ = parent_input(702)
    assert train == repeated and train["jobs"] != another["jobs"]
    assert parent["split"] == "train" and parent["synthetic"]
    assert len(train["jobs"]) == 28506
    for old, new in zip(original["jobs"], train["jobs"], strict=True):
        assert {k: v for k, v in old.items() if k != "arrival"} == {
            k: v for k, v in new.items() if k != "arrival"}
        assert abs(old["arrival"] - new["arrival"]) <= 120.000001
    small, _ = parent_input(701, 18)
    large, _ = parent_input(701, 26)
    ids = lambda data: {row["tray_id"] for row in data["trays"]}
    assert ids(small) < ids(train) < ids(large)
    assert {row["node"] for row in small["trays"]} == {row["node"] for row in train["trays"]}
    assert small["jobs"] == train["jobs"] == large["jobs"]
    with pytest.raises(ValueError, match="unregistered_parent"):
        parent_input(999)
