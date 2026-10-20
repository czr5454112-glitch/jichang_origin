"""Pure C10 mechanism and boundary tests; no native constructors or fitting."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_strong_rule as rule
from scripts.experiments.g31_ics_circulation.foundation_airport_prospective_control import current_candidate_rows
from test_g31_foundation_airport_pairs import fixture, opportunity, PARENT
from test_g31_foundation_airport_pair_ranker import forecast_evidence


def setup():
    obs, baseline = fixture()
    obs.update(schema="g31.owner_protocol_observation.v1", observation_scope="controller_policy",
        control_projection={"schema": "g31.analytic_control_projection.v1", "waiting_groups": []},
        known_faults=[])
    for node in obs["node_contracts"]:
        node.update(actual_available=int(node["node"] in (10, 11)), occupancy=0)
    obs["edge_contracts"] = [{"from": edge[0], "to": edge[1], "capacity": 4}
                             for edge in obs["edge_records"]]
    return obs, baseline


def rows(obs=None, baseline=None, *, demand=None, patch_rank=1):
    if obs is None:
        obs, baseline = setup()
    parent = dict(PARENT, calendar_start_epoch_seconds=1700086400.)
    evidence = forecast_evidence({"parent": parent, "observation": obs})
    evidence["observed_at_epoch_seconds"] = parent["calendar_start_epoch_seconds"] + obs["now"]
    fc = evidence["forecast"]
    fc.update(forecast_origin=obs["now"], remaining_support_until=obs["now"]+1800.,
        bin_edges_seconds=[0., 300., 900., 1800.],
        new_demand_mean_by_region={f"airport_node_{node['node']}": (demand or {}).get(node["node"], [0., 0., 0.])
                                  for node in obs["node_contracts"]})
    fc["missing_mask_by_region"] = {key: False for key in fc["new_demand_mean_by_region"]}
    evidence["forecast_sha256"] = rule.digest(fc)
    return current_candidate_rows(obs, baseline, opportunity(obs, baseline),
        parent=parent, information_variant="C10", forecast_evidence=evidence, patch_rank=patch_rank)


def queue(obs, node, count):
    obs["control_projection"]["waiting_groups"].append(
        {"origin": node, "count": count, "demand_observed_at": obs["now"], "jobs": []})


def request(obs, status="departed", *, tray="c", destination=2):
    obs["client_transfer_ledger"].append({"request_id": "r-"+tray, "tray_id": tray,
        "source": 11, "destination": destination, "issued_at": 99., "earliest_departure": 99.,
        "status": status, "status_scope": "own_payload_and_last_delivered_ack_only"})
    obs["transfers"] = copy.deepcopy(obs["client_transfer_ledger"])


def test_demand_prepositions_before_observed_arrivals_without_mutation():
    pair = rows(demand={2: [1., 0., 0.]})
    before = copy.deepcopy(pair)
    report = rule.explain_pair(*pair)
    assert report["predicted_patch_advantage"] > 0
    assert report["selected_branch"] == "a_patch"
    assert report["patch"]["candidate_arrival_offset"] > 0
    assert report["outcome_labels_read"] is False
    assert pair == before


def test_observed_queue_can_outweigh_future_alternative():
    obs, baseline = setup()
    queue(obs, 1, 1)
    report = rule.explain_pair(*rows(obs, baseline, demand={2: [0., 0., 1.]}))
    assert report["selected_branch"] == "a_ref"


def test_source_future_opportunity_cost_supports_holding_same_tray():
    report = rule.explain_pair(*rows(demand={10: [1., 0., 0.]}, patch_rank=2))
    assert report["selected_branch"] == "a_patch"
    assert report["reference"]["shortage_by_node"][10]["1800"] > report["patch"]["shortage_by_node"][10]["1800"]
    assert report["patch"]["candidate_arrival_offset"] == 0.


def test_current_source_queue_is_not_silently_dropped():
    obs, baseline = setup()
    queue(obs, 10, 1)
    report = rule.explain_pair(*rows(obs, baseline, patch_rank=2))
    assert report["selected_branch"] == "a_patch"
    assert report["reference"]["shortage_by_node"][10]["1800"] == 1800.


def test_all_three_horizons_and_equal_weight_are_used():
    pair = rows(demand={2: [0., 0., 2.]})
    report = rule.explain_pair(*pair)
    areas = report["reference"]["shortage_by_horizon"]
    assert areas["300"] == areas["900"] == 0.
    assert areas["1800"] > 0.
    assert report["reference"]["visible_account_shortage_area"] == pytest.approx(sum(areas.values())/3.)


def test_ack_committed_inbound_reduces_value_pending_does_not_credit():
    obs, baseline = setup()
    without = rule.score_pair(*rows(obs, baseline, demand={2: [1., 0., 0.]}))
    request(obs, "pending")
    pending = rule.score_pair(*rows(obs, baseline, demand={2: [1., 0., 0.]}))
    assert pending == without
    obs["client_transfer_ledger"][0]["status"] = "departed"
    obs["transfers"] = copy.deepcopy(obs["client_transfer_ledger"])
    report = rule.explain_pair(*rows(obs, baseline, demand={2: [1., 0., 0.]}))
    assert report["predicted_patch_advantage"] < without
    assert sum(item["kind"] == "delivered_ACK_committed_inbound" for item in report["conditional_supply_events"]) == 1


def test_retained_batch_supply_prevents_double_prepositioning():
    obs, baseline = setup()
    without = rule.score_pair(*rows(obs, baseline, demand={2: [1., 0., 0.]}))
    baseline["intents"][1]["destination"] = 2
    report = rule.explain_pair(*rows(obs, baseline, demand={2: [1., 0., 0.]}))
    assert report["predicted_patch_advantage"] < without
    assert report["selected_branch"] == "a_ref"
    assert report["conditional_supply_events"][0]["tray_id"] == "b"


def test_current_local_release_is_conditional_supply_not_current_free():
    obs, baseline = setup()
    obs["trays"].append({"tray_id": "h", "node": 2, "mode": "hold",
        "edge_to": -1, "generation": 1, "available_at": 101.})
    report = rule.explain_pair(*rows(obs, baseline, demand={2: [1., 0., 0.]}))
    assert report["selected_branch"] == "a_ref"
    assert next(item for item in report["conditional_supply_events"] if item["tray_id"] == "h")["eta_offset"] == 1.


def test_same_current_route_pressure_increases_cost():
    obs, baseline = setup()
    initial = rule.explain_pair(*rows(obs, baseline, demand={2: [1., 0., 0.]}))
    next(item for item in obs["node_contracts"] if item["node"] == 2)["occupancy"] = 4
    congested = rule.explain_pair(*rows(obs, baseline, demand={2: [1., 0., 0.]}))
    assert congested["patch"]["visible_path_pressure_seconds"] == initial["patch"]["visible_path_pressure_seconds"] + 1.
    assert congested["predicted_patch_advantage"] == initial["predicted_patch_advantage"] - 1.


def test_visible_inflight_edge_pressure_uses_static_capacity():
    obs, baseline = setup()
    obs["trays"].append({"tray_id": "flight", "node": 10, "mode": "moving",
        "edge_from": 10, "edge_to": 2, "generation": 1, "available_at": 105.})
    report = rule.explain_pair(*rows(obs, baseline, demand={2: [1., 0., 0.]}))
    assert report["patch"]["visible_path_pressure_seconds"] == .5


def test_missing_source_forecast_and_remote_pressure_stay_explicit():
    pair = rows(demand={2: [1., 0., 0.]})
    for row in pair:
        evidence = row["forecast_evidence"]
        del evidence["forecast"]["new_demand_mean_by_region"]["airport_node_10"]
        evidence["forecast_sha256"] = rule.digest(evidence["forecast"])
    report = rule.explain_pair(*pair)
    assert report["account_coverage"][10]["forecast_missing"] is True
    assert report["account_coverage"][10]["unobserved_inventory_imputed_as_actual_zero"] is False


def test_exact_positive_piecewise_integral_and_late_supply():
    assert rule._positive_linear_integral(-1., 1., 10.) == 2.5
    assert rule._positive_linear_integral(1., -1., 10.) == 2.5
    assert rule._node_cost(1., 0., [(20., 1.)], [0., 100.], [0.], 100.) == 20.
    assert rule._node_cost(1., 0., [(101., 1.)], [0., 100.], [0.], 100.) == 100.


def test_destination_supply_after_horizon_cannot_create_preposition_benefit():
    obs, baseline = setup()
    obs["static_role_contract"]["loader_nodes"] = [1, 2]
    for edge in obs["edge_records"]:
        if edge[:2] == [10, 2]:
            edge[2] = 2000.
    report = rule.explain_pair(*rows(obs, baseline, demand={2: [1., 0., 0.]}))
    assert report["patch"]["candidate_arrival_offset"] > 1800.
    assert report["selected_branch"] == "a_ref"
    assert report["reference"]["shortage_by_node"][2] == report["patch"]["shortage_by_node"][2]


def test_exact_tie_keeps_reference():
    obs, baseline = setup()
    for edge in obs["edge_records"]:
        if edge[:2] == [10, 2]:
            edge[2] = 1.
    report = rule.explain_pair(*rows(obs, baseline))
    assert report["predicted_patch_advantage"] == 0.
    assert report["selected_branch"] == "a_ref"


@pytest.mark.parametrize("rank", [1, 2])
def test_no_copy_allocation_validation_matches_batch_patch(rank):
    from scripts.experiments.g31_ics_circulation.foundation_airport_batch_patch import apply_patch
    pair = rows(patch_rank=rank)
    obs, baseline = pair[0]["observation"], pair[0]["baseline_decision"]
    nodes = {n["node"]: n for n in obs["node_contracts"]}
    supply = next(s for s in baseline["supplies"] if s["tray_id"] == "a")
    for row in pair:
        validated = rule._selected_allocation(row, "a", supply, obs, nodes, obs["now"])
        full = apply_patch(obs, baseline, row["action"])
        expected = next((intent for intent in full["intents"] if intent["tray_id"] == "a"), None)
        assert validated == expected


@pytest.mark.parametrize("mutation,match", [
    ("labels", "no_targets"), ("different_forecast", "same_current"),
    ("forged_semantic", "semantic_action_exact"), ("offline", "actual_recorded_plan_receipt"),
    ("stale_forecast", "absolute_current"), ("future_job", "released_unique_public_job"),
    ("sensor_disagreement", "sensor_agreement"),
])
def test_invalid_information_and_actions_fail_closed(mutation, match):
    obs, baseline = setup()
    if mutation == "future_job":
        obs["jobs"] = [{"business_bag_id": "future", "arrival": 101., "status": "waiting_for_tray"}]
    if mutation == "sensor_disagreement":
        next(item for item in obs["node_contracts"] if item["node"] == 10)["actual_available"] = 0
    pair = rows(obs, baseline)
    if mutation == "labels":
        pair[0]["target_return"] = 1000000.
    elif mutation == "different_forecast":
        pair[1]["forecast_evidence"]["forecast_sha256"] = "wrong"
    elif mutation == "forged_semantic":
        pair[1]["semantic_action"]["destination"] = 3
    elif mutation in ("offline", "stale_forecast"):
        for row in pair:
            if mutation == "offline":
                row["forecast_evidence"]["forecast_provenance"] = "offline_reconstruction_from_predeclared_static_schedule"
            else:
                row["forecast_evidence"]["observed_at_epoch_seconds"] -= 1.
    with pytest.raises(ValueError, match=match):
        rule.score_pair(*pair)


def test_fixed_rule_contract_has_no_target_fit_or_execution_authority():
    contract = rule.contract()
    assert contract["parameters"]["windows_seconds"] == [300., 900., 1800.]
    assert not contract["parameters_fit_or_selected_from_targets"]
    assert not contract["native_execution_authority"]
    assert not contract["strict_nonharm_certified"]


def test_once_validated_freeze_binds_rule_source_and_rejects_parameter_change(tmp_path):
    frozen = {"schema": "g31.foundation.airport_C10_rule_freeze.v1",
        "rule_contract": rule.contract(),
        "scorer_source_sha256": rule.hashlib.sha256(rule.Path(rule.__file__).read_bytes()).hexdigest(),
        "outcome_based_parameter_selection": False, "heldout_test_outcomes_read": False}
    path = tmp_path / "freeze.json"
    path.write_text(rule.json.dumps(frozen), encoding="utf8")
    binding = {"path": str(path), "sha256": rule.hashlib.sha256(path.read_bytes()).hexdigest()}
    selector = rule.prepare_scorer(binding)
    assert selector(*rows(demand={2: [1., 0., 0.]})) > 0.
    frozen["rule_contract"]["parameters"]["window_weights"] = [1., 0., 0.]
    path.write_text(rule.json.dumps(frozen), encoding="utf8")
    with pytest.raises(ValueError, match="file_sha256"):
        rule.prepare_scorer(binding)
    binding["sha256"] = rule.hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="frozen_rule_contract"):
        rule.prepare_scorer(binding)
