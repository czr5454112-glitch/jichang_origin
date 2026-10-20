"""Structural counterexamples for new pair collection, with no native runs."""
from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_batch_patch as patch
from scripts.experiments.g31_ics_circulation import foundation_airport_opportunities as opportunities
from scripts.experiments.g31_ics_circulation import foundation_airport_paired_continuation as paired
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_dataset as dataset


PARENT = {"parent_seed": 701, "split": "train", "parent_group": "synthetic701"}
CONTROLLER = {"next_tick": 2, "client": {"sequences": {"A": 3}, "outbox": {}}}


def fixture():
    observation = {"now": 100., "owner_id": "A", "version": 7,
        "static_role_contract": {"schema": "g31.static_node_roles.v1", "loader_nodes": [1, 2, 3]},
        "node_contracts": [{"node": node, "zone": "A", "resource_owner": "A",
            "capacity": 4, "allow_receive": True, "allow_export": True} for node in [1, 2, 3, 10, 11]],
        "node_records": [[node, 0, 1.] for node in [1, 2, 3, 10, 11]],
        "edge_records": [[source, dest, float(dest), 1.] for source in [10, 11] for dest in [1, 2, 3]],
        "edge_contracts": [], "transfers": [], "client_transfer_ledger": [],
        "delivered_messages": [], "delivered_transfer_acks": [], "jobs": [],
        "trays": [{"tray_id": tray, "node": source, "mode": "empty", "available_at": 99.,
            "edge_to": -1, "reception_node": -1, "generation": 3}
            for tray, source in [("a", 10), ("b", 11)]]}
    supplies = [{"tray_id": tray["tray_id"], "node": tray["node"], "earliest": 100.,
        "estimate": 100., "ledger": "actual_available", "owner_id": "A", "version": 7,
        "dependency": tray["tray_id"] + ":empty", "latest": None} for tray in observation["trays"]]
    intents = [{"tray_id": tray["tray_id"], "source": tray["node"], "destination": dest,
        "issued_at": 100., "earliest_departure": 102., "expiry": 200., "message_delay": 2.,
        "owner_id": "A", "expected_version": 7, "transfer_scope": "local_empty_return",
        "forecast_ledger": "actual_available", "forecast_dependency": tray["dependency"],
        "control_reason": "observed_source_queue", "service_window": None}
        for tray, dest in zip(supplies, [1, 3])]
    return observation, {"intents": intents, "supplies": supplies, "demands": [],
        "includes_wait": True}


def opportunity(obs=None, baseline=None):
    if obs is None:
        obs, baseline = fixture()
    return opportunities.build_opportunity(obs, baseline, continuation_version="fixed",
        message_delay=2., respect_service_forecasts=False)


def planner(branch="a_patch", patch_rank=1, base=None):
    obs, baseline = fixture()
    base = (lambda *_args, **_kwargs: deepcopy(baseline)) if base is None else base
    return paired.make_paired_planner(base, branch=branch, window=(100., 300.),
        parent=PARENT, continuation_version="fixed", patch_rank=patch_rank)


def bind(planning, obs, controller=None):
    return planning.bind_prefix(native_state_sha256="a"*64,
        controller_state=CONTROLLER if controller is None else controller, observation=obs)


def test_static_catalog_and_patch_preserve_every_other_baseline_allocation():
    obs, base = fixture()
    original = deepcopy((obs, base))
    event = opportunity(obs, base)
    assert event["K"] == 3 and event["P"] == 2 and not event["catalog_uses_future_plan"]
    assert event["candidates"][1]["intent"]["destination"] == 2
    changed = patch.apply_patch(obs, base, event["candidates"][1])
    assert changed["intents"][1:] == base["intents"][1:]
    assert changed["intents"][0]["transfer_scope"] == "local_empty_return"
    assert (obs, base) == original
    assert not changed["batch_patch"]["strict_nonharm_certified"]


@pytest.mark.parametrize("change", ["pending", "future_supply", "in_transit", "wrong_owner", "reception_lease"])
def test_committed_or_nonactual_tray_is_never_an_intervention(change):
    obs, base = fixture()
    # Both trays are assigned; neither may be used if neither is available.
    for i in range(2):
        if change == "pending":
            obs["transfers"].append({"tray_id": base["supplies"][i]["tray_id"], "status": "pending"})
        elif change == "future_supply":
            base["supplies"][i]["ledger"] = "firm_release"
        elif change == "in_transit":
            obs["trays"][i]["edge_to"] = 2
        elif change == "reception_lease":
            obs["trays"][i]["reception_node"] = 2
        else:
            obs["node_contracts"][-2+i]["resource_owner"] = "B"
    assert opportunity(obs, base)["K"] == 1


def test_mandatory_first_batch_member_cannot_be_replaced_or_reordered():
    obs, base = fixture()
    base["intents"][0]["control_reason"] = "terminal_receiving_pressure"
    assert opportunity(obs, base)["K"] == 1


@pytest.mark.parametrize("change", ["version", "pending_ack", "batch"])
def test_stale_patch_fails_closed(change):
    obs, base = fixture()
    action = opportunity(obs, base)["candidates"][1]
    if change == "version":
        obs["version"] += 1
    elif change == "pending_ack":
        obs["delivered_transfer_acks"].append({"request_id": "known", "status": "granted"})
    else:
        base["intents"][1]["expiry"] += 1
    with pytest.raises(ValueError):
        patch.apply_patch(obs, base, action)


@pytest.mark.parametrize("field,value", [("destination", 10), ("transfer_scope", "cross_zone_transfer"),
    ("earliest_departure", 99.), ("forecast_dependency", "another-tray")])
def test_patch_payload_must_preserve_current_scope_source_and_timing(field, value):
    obs, base = fixture()
    action = opportunity(obs, base)["candidates"][1]
    action["intent"][field] = value
    with pytest.raises(ValueError):
        patch.apply_patch(obs, base, action)


def test_hold_drops_exactly_one_optional_intent_and_survives_residual_same_tick():
    obs, base = fixture()
    planning = planner(patch_rank=2)
    first = planning(obs, predictive=True, request_prefix="protocol:2")
    assert first["intents"] == base["intents"][1:]
    bind(planning, obs)
    residual = planning(obs, predictive=True, request_prefix="protocol:2:residual")
    assert residual["intents"] == base["intents"][1:]
    obs["now"] = 160.
    later = planning(obs, predictive=True, request_prefix="protocol:3")
    assert later["intents"] == base["intents"]
    assert planning.successor["actual_elapsed_seconds"] == 60.
    assert planning.successor["supported_actions"] == []


def test_missing_offline_prefix_hook_prevents_next_initial_decision():
    obs, _ = fixture()
    planning = planner()
    planning(obs, predictive=True, request_prefix="protocol:2")
    obs["now"] = 160.
    with pytest.raises(ValueError, match="bind_prefix"):
        planning(obs, predictive=True, request_prefix="protocol:3")


def test_exact_prefix_includes_pending_outbox_payload_and_retry_state():
    obs, _ = fixture()
    before = paired.exact_prefix("a"*64, CONTROLLER, obs)
    changed = deepcopy(CONTROLLER)
    changed["client"]["outbox"]["r"] = {"payload": {"tray_id": "a"}, "next_retry": 160., "terminal": False}
    assert before["complete_prefix_sha256"] != paired.exact_prefix("a"*64, changed, obs)["complete_prefix_sha256"]
    changed["client"]["outbox"]["r"]["next_retry"] = 161.
    assert paired.exact_prefix("a"*64, changed, obs)["client_state_sha256"] != before["client_state_sha256"]


def test_natural_successor_requires_positive_same_owner_time():
    obs, _ = fixture()
    planning = planner()
    planning(obs, predictive=True, request_prefix="protocol:2")
    bind(planning, obs)
    planning(obs, predictive=True, request_prefix="protocol:2:residual")
    assert planning.successor is None
    obs["owner_id"] = "B"
    obs["now"] = 160.
    planning(obs, predictive=True, request_prefix="protocol:3")
    assert planning.successor is None
    obs["owner_id"] = "A"
    planning(obs, predictive=True, request_prefix="protocol:3")
    assert planning.successor["observed_at"] == 160.


def test_seed_descendants_cannot_cross_parent_split():
    with pytest.raises(ValueError, match="reassigned"):
        paired.validate_parent(dict(PARENT, split="dev"))
    assert paired.validate_parent({"parent_seed": 0, "split": "historical_development"})["split"] != "train"


def native_fixture(completed=150., clock=1900.):
    data = {"jobs": [{"business_bag_id": "old", "arrival": 0., "deadline": 120.},
        {"business_bag_id": "new", "arrival": 200., "deadline": 1000.},
        {"business_bag_id": "future", "arrival": 2000., "deadline": 2300.}]}
    result = {"physical_clock": clock, "advance": {"status": "reached", "horizon_complete": True},
        "jobs": [{"business_bag_id": "old", "status": "completed", "completed_at": completed},
            {"business_bag_id": "new", "status": "waiting_for_tray", "completed_at": -1.},
            {"business_bag_id": "future", "status": "unreleased", "completed_at": -1.}],
        "population": {"observed": 2, "completed": 1}, "trays": [], "transfers": [], "leg_identities": [],
        "receipts": [{"event": "BAG_ARRIVAL", "time": 0., "business_bag_id": "old"},
            {"event": "BAG_ARRIVAL", "time": 200., "business_bag_id": "new"},
            {"event": "UNLOAD_COMPLETE", "time": completed, "business_bag_id": "old"}]}
    return data, result


def test_closed_full_population_cost_retains_unfinished_and_future_denominators():
    data, result = native_fixture()
    cost = dataset.window_cost(data, result, start=100., end=1900.)
    assert cost["backlog_integral_bag_seconds"] == 1750.  # old50 + new1700
    assert cost["physical_population"] == 3 and cost["arrived_by_end"] == 2
    assert cost["arrived_unfinished_by_end"] == 1
    assert cost["not_yet_arrived_by_end"] == 1 and cost["arrived_unfinished_past_deadline"] == 1
    assert not cost["completion_times_imputed"] and not cost["per_job_nonharm_certified"]


@pytest.mark.parametrize("change", ["population", "arrival", "partial_timestamp", "future_endpoint"])
def test_unclosed_or_different_business_domain_cannot_mint_reward(change):
    data, result = native_fixture()
    end = 1900.
    if change == "population":
        data["jobs"].pop()
    elif change == "arrival":
        data["jobs"][1]["arrival"] = 201.
    elif change == "partial_timestamp":
        result["advance"]["horizon_complete"] = False
    else:
        end += 1
    with pytest.raises(ValueError):
        dataset.window_cost(data, result, start=100., end=end)


def evidence(branch, completed=150., *, clock=1900., controller=None, rejected=False):
    obs, _ = fixture()
    planning = planner(branch=branch)
    decision = planning(obs, predictive=True, message_delay=2., request_prefix="protocol:2")
    bind(planning, obs, controller)
    request = deepcopy(decision["intents"][0])
    request.pop("expected_version", None)
    request["request_id"] = "actual"
    calls = [{"at": 100., "kind": "transfer", "retry": False, "request": request,
        "reply": {"status": "rejected" if rejected else "pending"}}]
    data, result = native_fixture(completed, clock)
    return dataset.branch_evidence(data=data, planner_report=planning.report(), result=result,
        client_calls=calls, stop_reason="reached" if clock == 1900. else "soft_deadline_reached")


def test_actual_pair_contrast_and_two_labels_never_create_unused_candidate_label():
    ref, changed = evidence("a_ref"), evidence("a_patch", 140.)
    pair = dataset.compare_pair(ref, changed)
    assert pair["advantage_bag_seconds"] == 10. and pair["action_difference"]
    assert pair["mechanism_direction"] == "patch_better" and not pair["rl_benefit_demonstrated"]
    assert pair["per_job_comparison_counts"] == {"improved": 1, "unknown_incomplete": 2}
    export = dataset.dataset_rows(ref, changed)
    assert len(export["rows"]) == 2 and export["unused_candidate_count"] == 1
    assert export["rows"][0]["semantic_action"]["tray_id"] == export["rows"][1]["semantic_action"]["tray_id"]
    assert export["rows"][0]["semantic_action"]["destination"] == 1
    assert export["rows"][1]["semantic_action"]["destination"] == 2
    assert not export["unused_candidates_have_labels"]
    assert all(row["transition"]["next_state"] is None and not row["transition"]["terminated"]
        for row in export["rows"])


def test_censored_branch_never_looks_better_due_to_early_stop():
    ref, changed = evidence("a_ref"), evidence("a_patch", clock=500.)
    assert changed["cost"] is None and changed["observed_partial_cost"]["label_end"] == 500.
    pair = dataset.compare_pair(ref, changed)
    assert pair["advantage_bag_seconds"] is None and pair["status"] == "not_comparable"
    assert dataset.dataset_rows(ref, changed)["failed_pair_retained"]


def test_native_rejected_attempt_remains_in_pair_and_training_denominator():
    ref, changed = evidence("a_ref"), evidence("a_patch", rejected=True)
    pair = dataset.compare_pair(ref, changed)
    assert pair["advantage_bag_seconds"] == 0.
    assert pair["patched_execution"]["attempts"][0]["submission_reply"]["status"] == "rejected"
    assert len(dataset.dataset_rows(ref, changed)["rows"]) == 2


def test_equal_public_observation_cannot_hide_different_protocol_pending_prefix():
    ref = evidence("a_ref")
    controller = deepcopy(CONTROLLER)
    controller["client"]["outbox"]["pending"] = {"payload": {"destination": 99}, "terminal": False}
    changed = evidence("a_patch", controller=controller)
    with pytest.raises(ValueError, match="different_complete"):
        dataset.compare_pair(ref, changed)


def test_actual_recorded_forecast_passes_through_without_fabricating_old_evidence():
    ref, changed = evidence("a_ref"), evidence("a_patch")
    assert all("forecast_evidence" not in row for row in dataset.dataset_rows(ref, changed)["rows"])
    ref["selected"]["forecast_evidence"] = {"actual_callback_consumption": True, "model_id": "recorded"}
    changed["selected"]["forecast_evidence"] = deepcopy(ref["selected"]["forecast_evidence"])
    rows = dataset.dataset_rows(ref, changed)["rows"]
    assert rows[0]["forecast_evidence"] == ref["selected"]["forecast_evidence"]
    rows[0]["forecast_evidence"]["model_id"] = "mutated-copy"
    assert ref["selected"]["forecast_evidence"]["model_id"] == "recorded"


def test_successor_forecast_stays_bound_to_successor_transition():
    obs, _ = fixture()
    planning = planner()
    planning(obs, predictive=True, request_prefix="protocol:2")
    bind(planning, obs)
    obs["now"] = 160.
    planning(obs, predictive=True, request_prefix="protocol:3")
    bind(planning, obs)
    planning.successor["forecast_evidence"] = {"actual_callback_consumption": True, "observed_at": 160.}
    data, result = native_fixture()
    item = dataset.branch_evidence(data=data, planner_report=planning.report(), result=result,
        client_calls=[])
    assert item["transition"]["forecast_evidence"]["observed_at"] == 160.
    assert "forecast_evidence" not in item["selected"]
