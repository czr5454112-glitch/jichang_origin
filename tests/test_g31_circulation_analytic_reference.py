"""Information, prediction and finite-reference denominator regressions."""
import copy
import itertools
import math
import random

import pytest

from scripts.experiments.g31_ics_circulation.analytic_control import (
    _min_cost_matching, release_forecasts, transfer_candidates, conditional_service_windows,
    departure_avoiding_published_windows, ReleaseForecast, PublicTravel, _assignment_representatives,
)
from scripts.experiments.g31_ics_circulation.finite_reference import (
    Intervention, enumerate_interventions, headroom, outcome_cost, service_dominates, _horizon_completion,
)


def observation():
    return {
        "now": 3.0, "owner_id": "B", "version": 8,
        "node_records": [(0, 1, .1, 0, 0, [1]), (1, 1, .1, 1, 0, [2]),
                         (2, 1, .1, 2, 0, [0])],
        "edge_records": [(0, 1, 2, 1), (1, 2, 2, 1), (2, 0, 2, 1)],
        "node_contracts": [{"node": i, "zone": "A" if i == 0 else "B", "capacity": 2}
                           for i in range(3)],
        "jobs": [{"business_bag_id": "loaded", "origin": 0, "destination": 2,
                  "arrival": 0, "status": "storage", "storage_node": 1,
                  "storage_entered_at": 2, "storage_released_at": -1,
                  "storage_release_at": 7, "storage_min_dwell": 2,
                  "unload_seconds": .5, "hold_seconds": 1}],
        "trays": [{"tray_id": "T", "node": 1, "mode": "storage", "edge_to": -1,
                   "business_bag_id": "loaded", "available_at": 0}],
        "transfers": [], "delivered_messages": [{"kind": "demand", "source_owner": "A",
            "observed_at": 1, "delivered_at": 2,
            "jobs": [{"business_bag_id": "waiting", "origin": 0, "arrival": .2,
                      "status": "waiting_for_tray"}]}],
    }


def test_predicts_storage_release_before_real_availability_without_creation():
    obs = observation()
    frozen = copy.deepcopy(obs)
    forecasts = release_forecasts(obs)
    assert len(forecasts) == 1
    assert forecasts[0].ledger == "conditional_release"
    assert forecasts[0].estimate == pytest.approx(10.7)
    assert forecasts[0].latest is None
    predictive = transfer_candidates(obs, predictive=True)
    reactive = transfer_candidates(obs, predictive=False)
    assert len(predictive["intents"]) == 1 and not reactive["intents"]
    assert predictive["intents"][0]["source"] == 2
    assert predictive["intents"][0]["destination"] == 0
    assert obs == frozen


def test_prediction_tracks_storage_revision_and_inflight_residual():
    obs = observation()
    obs["jobs"][0]["storage_release_at"] += 10
    assert release_forecasts(obs)[0].estimate == pytest.approx(20.7)
    obs["trays"][0].update(mode="loaded", node=0, edge_from=0, edge_to=1, edge_exit_at=4)
    obs["jobs"][0].update(storage_entered_at=-1, storage_release_at=0)
    assert release_forecasts(obs)[0].estimate == pytest.approx(9.8)


def test_hold_is_firm_but_not_actual_and_quarantine_unknown():
    obs = observation()
    obs["trays"][0].update(mode="hold", node=2, available_at=5)
    assert release_forecasts(obs)[0].ledger == "firm_release"
    assert not transfer_candidates(obs, predictive=False)["intents"]
    obs["trays"][0]["mode"] = "quarantined"
    assert release_forecasts(obs) == []


def test_no_hidden_future_or_undelivered_demand_features():
    obs = observation()
    other = copy.deepcopy(obs)
    other["untrusted_environment_tape"] = {"future_jobs": ["different"]}
    assert transfer_candidates(obs, predictive=True) == transfer_candidates(other, predictive=True)
    other["jobs"][0]["arrival"] = 100
    with pytest.raises(ValueError, match="unpublished_future_job"):
        transfer_candidates(other, predictive=True)
    obs["delivered_messages"][0]["delivered_at"] = 100
    with pytest.raises(ValueError, match="undelivered_message"):
        transfer_candidates(obs, predictive=True)


def test_latest_delivered_demand_replaces_stale_queue():
    obs = observation()
    obs["delivered_messages"].append({"kind": "demand", "source_owner": "A", "observed_at": 2,
                                      "delivered_at": 3, "jobs": []})
    assert not transfer_candidates(obs, predictive=True)["intents"]


def test_conditional_service_window_requires_delivery_and_uses_latest_message():
    obs = observation()
    forecast = {"kind": "service_forecast", "message_id": "m1", "source_owner": "A",
                "tray_id": "T1", "generation": 2, "observed_at": 1., "delivered_at": 2.,
                "entry_estimate": 4., "release_estimate": 7., "next": 2, "status": "conditional"}
    obs["delivered_messages"].append(forecast)
    assert conditional_service_windows(obs) == [forecast]
    obs["delivered_messages"].append(dict(forecast, message_id="withdraw-m1", observed_at=2.,
                                          status="withdrawn", supersedes="m1"))
    assert conditional_service_windows(obs) == []
    obs["delivered_messages"][-1]["delivered_at"] = 100.
    with pytest.raises(ValueError, match="undelivered_service_forecast"):
        conditional_service_windows(obs)


def test_forecast_exact_tombstone_survives_overtaking_and_does_not_erase_new_revision():
    obs = observation()
    first = {"kind": "service_forecast", "message_id": "f1", "source_owner": "A", "tray_id": "T",
             "generation": 1, "observed_at": 1., "delivered_at": 2.8, "publication_sequence": 1,
             "entry_estimate": 5., "release_estimate": 7., "next": 2, "status": "conditional"}
    withdrawal = dict(first, message_id="withdraw-f1", supersedes="f1", status="withdrawn",
                      observed_at=1.2, delivered_at=1.4, publication_sequence=2)
    obs["delivered_messages"] = [withdrawal, first, copy.deepcopy(withdrawal)]
    frozen = copy.deepcopy(obs)
    assert conditional_service_windows(obs) == []
    assert obs == frozen  # No supply deletion, cancellation or duplicated decrement.
    revised = dict(first, message_id="f2", observed_at=1.1, delivered_at=1.3,
                   publication_sequence=3, next=1)
    obs["delivered_messages"].insert(0, revised)
    assert conditional_service_windows(obs) == [revised]
    # Withdrawing latest must not resurrect older f1 even if the old tombstone
    # is absent from this deliberately minimal independent projection.
    obs["delivered_messages"] = [first, revised, dict(withdrawal, supersedes="f2")]
    assert conditional_service_windows(obs) == []


def test_same_epoch_revision_uses_publication_sequence_not_delivery_or_opaque_id():
    obs = observation()
    old = {"kind": "service_forecast", "message_id": "z-old", "source_owner": "A", "tray_id": "T",
           "generation": 1, "observed_at": 1., "delivered_at": 3., "publication_sequence": 1,
           "entry_estimate": 5., "release_estimate": 7., "next": 2, "status": "conditional"}
    new = dict(old, message_id="a-new", delivered_at=2., publication_sequence=2, next=1)
    obs["delivered_messages"] = [new, old]
    assert conditional_service_windows(obs) == [new]
    old.pop("publication_sequence"); new.pop("publication_sequence")
    assert conditional_service_windows(obs) == []  # Ambiguous legacy epoch: no false ordering.
    obs["delivered_messages"] = [dict(old, release_estimate=3.)]
    assert conditional_service_windows(obs) == []  # Expired conditional estimate is not available inventory.


def test_point_estimate_departure_accounts_for_receiving_reservation_and_is_not_guarantee():
    from scripts.experiments.g31_ics_circulation.validate_coupled_control import coupled_input
    obs = coupled_input()
    obs.update(now=1.6, owner_id="B", version=1, delivered_messages=[{
        "kind": "service_forecast", "message_id": "m1", "source_owner": "A", "tray_id": "T1",
        "generation": 1, "observed_at": .61, "delivered_at": .81, "next": 1,
        "entry_estimate": 6.35, "release_estimate": 7.4, "status": "conditional"}])
    supply = ReleaseForecast("T0", 3, 1.6, 5.75, "conditional_release", "B", 1, "actual-B1")
    value = departure_avoiding_published_windows(obs, supply, 4, PublicTravel(obs), 1.)
    assert value["earliest_departure"] == pytest.approx(6.9)
    assert value["conditional_dependencies"] == ["m1"]
    assert value["hard_guarantee"] is False
    obs["delivered_messages"] = []
    assert departure_avoiding_published_windows(obs, supply, 4, PublicTravel(obs), 1.)["earliest_departure"] == 1.6


def test_arrived_transfer_covers_older_demand_message_until_fresh_snapshot():
    obs = observation()
    obs["transfers"] = [{"request_id": "earlier", "tray_id": "other", "destination": 0,
                          "status": "received", "received_at": 2}]
    assert not transfer_candidates(obs, predictive=True)["intents"]
    obs["delivered_messages"][0]["observed_at"] = 2.5
    obs["delivered_messages"][0]["delivered_at"] = 3
    assert len(transfer_candidates(obs, predictive=True)["intents"]) == 1


@pytest.mark.parametrize("status", ["pending", "undelivered", "dispatching", "departed"])
def test_same_tray_no_second_pledge(status):
    obs = observation()
    obs["transfers"] = [{"request_id": "existing", "tray_id": "T", "destination": 0, "status": status}]
    assert not transfer_candidates(obs, predictive=True)["intents"]


def test_source_stock_and_local_service_are_protected():
    obs = observation()
    obs["node_contracts"][2]["export_min_stock"] = 1
    assert not transfer_candidates(obs, predictive=True)["intents"]
    obs["node_contracts"][2]["export_min_stock"] = 0
    obs["jobs"].append({"business_bag_id": "local", "origin": 2, "arrival": 1,
                        "status": "waiting_for_tray"})
    assert not transfer_candidates(obs, predictive=True)["intents"]


def test_reasonable_reactive_baseline_clears_full_terminal_for_visible_loaded_bag():
    obs = observation()
    obs["delivered_messages"] = []
    obs["trays"].append({"tray_id": "empty", "node": 2, "mode": "empty", "edge_to": -1})
    obs["node_contracts"][2].update(capacity=1, occupancy=1)
    # Storage mode of the already observed loaded bag is public, and its final
    # destination is full. The return target is its actual observed origin.
    decision = transfer_candidates(obs, predictive=False)
    assert len(decision["intents"]) == 1
    assert decision["intents"][0]["tray_id"] == "empty"
    assert decision["intents"][0]["control_reason"] == "terminal_receiving_pressure"
    assert not transfer_candidates(obs, predictive=False, terminal_clearing=False)["intents"]


def test_permission_and_static_unreachable_are_not_ignored():
    obs = observation()
    obs["node_contracts"][0]["allow_receive"] = False
    assert not transfer_candidates(obs, predictive=True)["intents"]


def test_closed_capacity_edge_and_future_remote_owner_not_candidates():
    obs = observation()
    obs["edge_contracts"] = [{"from": 2, "to": 0, "capacity": 0}]
    assert not transfer_candidates(obs, predictive=True)["intents"]
    obs["edge_contracts"] = []
    obs["node_contracts"][2]["resource_owner"] = "remote_C"
    assert not transfer_candidates(obs, predictive=True)["intents"]
    obs["node_contracts"][0]["allow_receive"] = True
    obs["known_faults"] = [{"from": 2, "to": 0, "active": True}]
    assert not transfer_candidates(obs, predictive=True)["intents"]


def test_exact_matching_avoids_greedy_trap_and_matches_exhaustive():
    assert set(_min_cost_matching([[1, 2], [2, 100]])) == {(0, 1), (1, 0)}
    rng = random.Random(17)
    for n in range(1, 5):
        for _ in range(20):
            matrix = [[rng.randrange(1, 30) for _ in range(n)] for _ in range(n)]
            actual = sum(matrix[i][j] for i, j in _min_cost_matching(matrix))
            exact = min(sum(matrix[i][j] for i, j in enumerate(p)) for p in itertools.permutations(range(n)))
            assert actual == exact
    assert _min_cost_matching([[math.inf]]) == []


def test_equivalent_fifo_compression_matches_uncompressed_assignment_exhaustively():
    rng = random.Random(7281)
    for k in range(1, 5):
        for _ in range(40):
            groups = [rng.randrange(3) for _ in range(9)]
            demand = [{"business_bag_id": str(j), "origin": g, "demand_kind": "observed_source_queue"}
                      for j,g in enumerate(groups)]
            retained = _assignment_representatives(demand, k)
            group_cost = [[rng.choice([1, 2, 5, math.inf]) for _ in range(3)] for _ in range(k)]
            full = [[group_cost[i][g] for g in groups] for i in range(k)]
            reduced = [[row[j] for j,_ in retained] for row in full]
            a, b = _min_cost_matching(full), _min_cost_matching(reduced)
            assert len(a) == len(b)
            assert sum(full[i][j] for i,j in a) == sum(reduced[i][j] for i,j in b)
            # Independent brute force, not only two calls of one implementation.
            brute = [(len(pairs), sum(full[i][j] for i,j in pairs))
                     for size in range(k+1)
                     for rows in itertools.combinations(range(k), size)
                     for cols in itertools.permutations(range(len(groups)), size)
                     for pairs in [list(zip(rows, cols))]
                     if all(math.isfinite(full[i][j]) for i,j in pairs)]
            expected = min(brute, key=lambda value: (-value[0], value[1]))
            assert (len(b), sum(reduced[i][j] for i,j in b)) == expected


def test_compression_keeps_full_demand_and_no_supply_skips_travel(monkeypatch):
    import scripts.experiments.g31_ics_circulation.analytic_control as control
    obs = observation()
    obs["trays"] = [{"tray_id": f"E{i}", "node": 2, "mode": "empty"} for i in range(3)]
    obs["delivered_messages"][0]["jobs"] *= 1
    obs["delivered_messages"][0]["jobs"] = [
        {"business_bag_id": f"queue-{i}", "origin": 0, "arrival": .2, "status": "waiting_for_tray"}
        for i in range(20)]
    compressed = transfer_candidates(obs, predictive=False)
    full = transfer_candidates(obs, predictive=False, compress_equivalent_demands=False)
    assert compressed["intents"] == full["intents"]
    assert len(compressed["demands"]) == len(full["demands"]) == 20
    assert compressed["assignment_demand_count"] == 3
    assert full["assignment_demand_count"] == 20
    obs["trays"] = []
    monkeypatch.setattr(control, "PublicTravel", lambda observation: pytest.fail("zero supply performed graph construction"))
    empty = transfer_candidates(obs, predictive=False)
    assert not empty["intents"] and len(empty["demands"]) == 20


def test_cost_keeps_failed_unfinished_and_all_offered_denominators():
    specs = [{"business_bag_id": "done", "arrival": 0, "deadline": 8},
             {"business_bag_id": "failed", "arrival": 2, "deadline": 5},
             {"business_bag_id": "future", "arrival": 20, "deadline": 25}]
    result = {"jobs": [{"business_bag_id": "done", "status": "completed", "completed_at": 4},
                       {"business_bag_id": "failed", "status": "failed", "completed_at": -1},
                       {"business_bag_id": "future", "status": "unreleased", "completed_at": -1}]}
    metrics = outcome_cost(result, specs, 10)
    assert (metrics["offered"], metrics["completed"], metrics["unfinished"], metrics["failed"]) == (2, 1, 1, 1)
    assert metrics["cost"] == 12 and metrics["deadline_violations"] == 1
    assert service_dominates(metrics, metrics)
    result["jobs"] = result["jobs"][:1]
    with pytest.raises(ValueError, match="missing_offered_job"):
        outcome_cost(result, specs, 10)


def test_headroom_separates_pool_and_ranking_loss():
    reference = {"exhaustive": True, "rows": [
        {"action": {"action_id": key}, "status": "verified", "paired_service_preserved": True,
         "metrics": {"cost": cost}} for key, cost in [("baseline", 10), ("selected", 8), ("poolbest", 6), ("reference", 4)]]}
    result = headroom(reference, ["selected", "poolbest"], "selected", "baseline")
    assert (result["reference_headroom"], result["pool_loss"], result["ranking_loss"]) == (6, 2, 2)
    assert result["global_lower_bound"] is None


class _ReferenceStatusDouble:
    """A return-status test double, never a physical simulator or evidence."""
    physical_time = 0

    def __init__(self, budget=False, submission_status="rejected"):
        self.budget = budget
        self.submission_status = submission_status

    def fork(self):
        return _ReferenceStatusDouble(self.budget, self.submission_status)

    def submit_transfer_intent(self, request):
        return {"status": self.submission_status, "reason": "explicit_status_double_only"}

    def result_at(self, horizon):
        self.physical_time = horizon / 2 if self.budget else horizon
        return {"horizon": horizon, "physical_clock": self.physical_time,
                "advance": {"status": "budget_exhausted" if self.budget else "reached",
                            "physical_time": self.physical_time, "horizon_complete": not self.budget},
                "jobs": [{"business_bag_id": "j", "status": "completed", "completed_at": 1}]}


@pytest.mark.parametrize("branch_budget,event_budget", [(1, False), (2, True)])
def test_reference_budget_censoring_never_certifies_optimality(branch_budget, event_budget):
    result = enumerate_interventions(_ReferenceStatusDouble(event_budget),
        [Intervention("WAIT", "wait"), Intervention("other-wait", "wait")], horizon=5,
        job_contracts=[{"business_bag_id": "j", "arrival": 0}], max_branches=branch_budget,
        validate=lambda result, action: {"status": "passed"})
    assert result["optimality"] == "unknown" and not result["exhaustive"]


def test_reference_requires_positive_independent_audit_result():
    with pytest.raises(ValueError, match="independent_audit_did_not_pass"):
        enumerate_interventions(_ReferenceStatusDouble(), [Intervention("WAIT", "wait")],
            horizon=5, job_contracts=[{"business_bag_id": "j", "arrival": 0}],
            validate=lambda result, action: {"status": "failed"})


@pytest.mark.parametrize("status", ["timeout_unknown", "failed_no_safe_continuation"])
def test_unknown_submission_does_not_prove_infeasible_or_complete_domain(status):
    result = enumerate_interventions(_ReferenceStatusDouble(submission_status=status),
        [Intervention("WAIT", "wait"), Intervention("uncertain", "transfer", {"request_id": "live:uncertain"})],
        horizon=5, job_contracts=[{"business_bag_id": "j", "arrival": 0}],
        validate=lambda result, action: {"status": "passed"})
    assert result["optimality"] == "unknown" and not result["exhaustive"]
    assert result["rows"][1]["status"] == "unresolved_submission"


@pytest.mark.parametrize("mutation", [
    lambda r: r.pop("horizon"), lambda r: r.pop("physical_clock"),
    lambda r: r["advance"].pop("physical_time"),
    lambda r: r["advance"].pop("status"), lambda r: r.update(horizon=.1),
    lambda r: r.update(physical_clock=float("nan")),
    lambda r: r["advance"].update(physical_time=float("inf")),
    lambda r: r.update(control_continuation={"status": "budget_exhausted", "requested_horizon": 5., "physical_time": 5.}),
    lambda r: r.update(control_continuation={"status": "reached", "requested_horizon": 10., "physical_time": 5.}),
    lambda r: r["advance"].update(horizon_complete=False),
    lambda r: r["advance"].pop("horizon_complete"),
    lambda r: r.update(advance=None),
    lambda r: r.update(control_continuation={}),
    lambda r: r.update(control_continuation=None),
])
def test_missing_or_contradictory_horizon_evidence_cannot_be_verified(mutation):
    source = _ReferenceStatusDouble()
    def continuation(branch, horizon):
        result = branch.result_at(horizon)
        mutation(result)
        return result
    reference = enumerate_interventions(source, [Intervention("WAIT", "wait")],
        horizon=5., job_contracts=[{"business_bag_id": "j", "arrival": 0}], continuation=continuation,
        validate=lambda result, action: pytest.fail("incomplete prefix reached completion audit"))
    assert reference["optimality"] == "unknown" and not reference["exhaustive"]
    assert reference["rows"][0]["status"] == "incomplete_horizon"
    assert "metrics" not in reference["rows"][0]


def test_branch_clock_and_outer_status_cannot_be_hidden_by_result_metadata():
    branch = _ReferenceStatusDouble()
    result = branch.result_at(5.)
    branch.physical_time = .1
    assert _horizon_completion(result, branch, 5.)["status"] == "unknown"
    branch.physical_time = 5.
    assert _horizon_completion(result, branch, 5., "budget_exhausted")["status"] == "unknown"


@pytest.mark.parametrize("outer_status", [None, False, 0, [], {}, "missing"])
def test_present_invalid_envelope_status_is_not_absent_envelope(outer_status):
    def continuation(branch, horizon):
        return {"status": outer_status, "result": branch.result_at(horizon)}
    reference = enumerate_interventions(_ReferenceStatusDouble(), [Intervention("WAIT", "wait")],
        horizon=5., job_contracts=[{"business_bag_id": "j", "arrival": 0}], continuation=continuation,
        validate=lambda result, action: pytest.fail("invalid envelope status reached verification"))
    assert reference["optimality"] == "unknown" and not reference["exhaustive"]
    assert "outer_continuation_not_reached" in reference["rows"][0]["completion"]["problems"]
