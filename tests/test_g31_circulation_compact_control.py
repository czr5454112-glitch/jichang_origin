"""Exact compact queue consumption and real native continuation equivalence."""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.analytic_control import (
    _visible_demand, demand_signature, run_online_matching, transfer_candidates,
)
from scripts.experiments.g31_ics_circulation.native_host import load_native
from scripts.experiments.g31_ics_circulation.validate_analytic_control import scenarios
from scripts.experiments.g31_ics_circulation.validate_known_service_control import known_service_input, prefix


def _compact_fixture(full):
    """Independent serialized fixture, not a replacement physical projector."""
    compact = deepcopy(full)
    visible = _visible_demand(full)
    waiting = sorted((j for j in visible.values() if j["status"] == "waiting_for_tray"),
                     key=lambda j: (j["arrival"], j["business_bag_id"]))
    k = sum(t["mode"] != "quarantined" for t in full["trays"])
    grouped = defaultdict(list)
    for i, job in enumerate(waiting):
        origin = int(job["origin"])
        grouped[origin].append(dict(job, fifo_index=len(grouped[origin]), global_fifo_index=i))
    incoming = Counter(int(t["destination"]) for t in full.get("transfers", [])
                       if t["status"] in ("pending", "granted", "in_transit", "requested", "delivered",
                                          "undelivered", "dispatching", "departed", "received"))
    groups = []
    for origin, rows in grouped.items():
        limit = incoming[origin]+2*k if k else 0
        groups.append({"origin": origin, "count": len(rows), "jobs": rows[:limit],
                       "head_limit": limit, "covered_upper_bound": incoming[origin]+k,
                       "demand_observed_at": rows[-1]["demand_observed_at"]})
    tray_jobs = {t.get("business_bag_id") for t in full["trays"]}
    compact["jobs"] = [j for j in compact["jobs"] if j["business_bag_id"] in tray_jobs]
    for message in compact.get("delivered_messages", []):
        if message["kind"] == "demand":
            message["jobs"] = []
    compact["control_projection"] = {
        "schema": "g31.analytic_control_projection.v1", "candidate_limit": k,
        "exact_waiting_count": len(waiting), "waiting_groups": groups,
        "known_origin_nodes": sorted({int(j["origin"]) for j in visible.values()})}
    return compact


def _assert_decisions(full, compact):
    for key in ("intents", "supplies", "forecasts", "exact_waiting_count", "exact_demand_count",
                "clearing_pressure_without_available_source", "assignment_demand_count"):
        assert full[key] == compact[key], key


def _observation():
    return {
        "now": 3., "owner_id": "B", "version": 8,
        "node_records": [(0, 1, .1, 0, 0, [1]), (1, 1, .1, 1, 0, [2]), (2, 1, .1, 2, 0, [0])],
        "edge_records": [(0, 1, 2, 1), (1, 2, 2, 1), (2, 0, 2, 1)],
        "node_contracts": [{"node": i, "zone": "A" if i == 0 else "B", "capacity": 2} for i in range(3)],
        "jobs": [{"business_bag_id": "loaded", "origin": 0, "destination": 2, "arrival": 0,
                  "status": "storage", "storage_node": 1, "storage_entered_at": 2,
                  "storage_released_at": -1, "storage_release_at": 7, "storage_min_dwell": 2,
                  "unload_seconds": .5, "hold_seconds": 1}],
        "trays": [{"tray_id": "T", "node": 1, "mode": "storage", "edge_to": -1,
                   "business_bag_id": "loaded", "available_at": 0}], "transfers": [],
        "delivered_messages": [{"kind": "demand", "source_owner": "A", "observed_at": 1., "delivered_at": 2.,
            "jobs": [{"business_bag_id": f"queue-{i:05}", "origin": 0, "arrival": i/10000,
                      "status": "waiting_for_tray"} for i in range(1000)]}],
    }


@pytest.mark.parametrize("factor", ["zero_supply", "predictive", "received", "pledged", "reserve", "refusal", "overlap", "pressure"])
def test_compact_pure_counts_and_actions_match_complete_population(factor):
    obs = _observation()
    if factor == "zero_supply":
        obs["trays"] = []
    elif factor == "received":
        obs["transfers"] = [{"request_id": str(i), "tray_id": str(i), "destination": 0,
                              "status": "received", "received_at": 2} for i in range(20)]
    elif factor == "pledged":
        obs["transfers"] = [{"request_id": "pledged", "tray_id": "T", "destination": 0, "status": "pending"}]
    elif factor == "reserve":
        obs["jobs"].append({"business_bag_id": "local", "origin": 2, "arrival": .3, "status": "waiting_for_tray"})
    elif factor == "refusal":
        obs["node_contracts"][0]["allow_receive"] = False
    elif factor == "overlap":
        obs["delivered_messages"][0]["jobs"].insert(0, dict(obs["jobs"][0], status="waiting_for_tray"))
    elif factor == "pressure":
        obs["delivered_messages"] = []
        obs["trays"].append({"tray_id": "E", "node": 2, "mode": "empty", "edge_to": -1})
        obs["node_contracts"][2].update(capacity=1, occupancy=1)
    compact = _compact_fixture(obs)
    _assert_decisions(transfer_candidates(obs, predictive=True), transfer_candidates(compact, predictive=True))
    assert sum(len(g["jobs"]) for g in compact["control_projection"]["waiting_groups"]) <= 22


def test_compact_pure_incomplete_prefix_rejected_without_dropping_demand():
    obs = _observation()
    compact = _compact_fixture(obs)
    compact["control_projection"]["waiting_groups"][0]["jobs"] = []
    with pytest.raises(ValueError, match="insufficient_compact_fifo_coverage"):
        transfer_candidates(compact, predictive=True)
    with pytest.raises(ValueError, match="compact_projection_requires_equivalent_columns"):
        transfer_candidates(compact, predictive=True, compress_equivalent_demands=False)


def test_compact_pure_signature_ignores_row_order_and_signed_zero_but_not_contract():
    rows = [["托盘相关业务", 1, -0., -1.], ["second", 2, 3., 10.]]
    assert demand_signature(rows) == demand_signature(list(reversed(rows)))
    changed = deepcopy(rows); changed[0][2] = 0.
    assert demand_signature(rows) == demand_signature(changed)
    changed[0][3] = 15.
    assert demand_signature(rows) != demand_signature(changed)


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if binary is None:
        binary = str(next((Path(__file__).absolute().parents[1]/"build_lt_session_007/python").glob("czr005_circulation*.pyd")))
    return load_native(binary)


@pytest.mark.parametrize("name", list(scenarios()))
@pytest.mark.parametrize("predictive", [False, True])
def test_compact_native_full_and_compact_real_continuations_match(native, name, predictive):
    data, delay, demand_delay = scenarios()[name]
    parent = native.NativeSession(data)
    before = parent.offline_state_sha256()
    full, compact = [run_online_matching(parent.fork(), ["A", "B"], horizon=80., predictive=predictive,
                        message_delay=delay, demand_delay=demand_delay, compact_projection=use_compact)
                     for use_compact in (False, True)]
    assert parent.offline_state_sha256() == before
    assert full["submitted"] == compact["submitted"]
    for a, b in zip(full["control_records"], compact["control_records"], strict=True):
        assert a["owner_id"] == b["owner_id"] and a["replies"] == b["replies"]
        _assert_decisions(a["decision"], b["decision"])
        for x, y in zip(a["replans"], b["replans"], strict=True):
            _assert_decisions(x, y)
    for field in ("receipts", "jobs", "trays", "transfers", "population", "leg_identities"):
        assert full["result"][field] == compact["result"][field], field
    assert full["controller_state"] == compact["controller_state"]


def test_compact_native_controller_json_fork_switches_representation_without_events(native):
    data, delay, demand_delay = scenarios()["command_delay_2"]
    parent = native.NativeSession(data)
    pre = run_online_matching(parent, ["A", "B"], horizon=8., predictive=True,
                              message_delay=delay, demand_delay=demand_delay)
    saved = json.loads(json.dumps(pre["controller_state"]))
    full, compact = [run_online_matching(parent.fork(), ["A", "B"], horizon=80., predictive=True,
                        message_delay=delay, demand_delay=demand_delay,
                        controller_state=deepcopy(saved), compact_projection=use_compact)
                     for use_compact in (False, True)]
    assert full["submitted"] == compact["submitted"]
    assert full["controller_state"] == compact["controller_state"]
    assert full["result"]["receipts"] == compact["result"]["receipts"]


def test_compact_native_publication_digest_matches_full_signature_and_is_readonly(native):
    data, _, _ = scenarios()["command_delay_2"]
    session = native.NativeSession(data)
    for t in (0., .11, .5, 1., 5., 8., 12.):
        session.advance_to(t)
        for owner in ("A", "B"):
            before = session.offline_state_sha256()
            full = session.observe(owner)
            rows = [[j["business_bag_id"], j["origin"], j["arrival"], j.get("deadline", -1)]
                    for j in full["jobs"] if j["status"] in ("waiting", "waiting_for_tray")]
            assert session.demand_signature(owner) == demand_signature(rows)
            session.observe_control(owner)
            assert session.offline_state_sha256() == before


def test_compact_native_forecasts_pending_pledge_and_rejected_intents_match(native):
    data = known_service_input()
    parent, pre = prefix(native, data, predictive=True, windows=True)
    saved = json.loads(json.dumps(pre["controller_state"]))
    full, compact = [run_online_matching(parent.fork(), ["A", "B", "C"], horizon=40., predictive=True,
        message_delay=1., demand_delay=.2, respect_service_forecasts=True,
        controller_state=deepcopy(saved), compact_projection=mode) for mode in (False, True)]
    assert full["submitted"] == compact["submitted"]
    for a, b in zip(full["control_records"], compact["control_records"], strict=True):
        _assert_decisions(a["decision"], b["decision"])
    assert full["result"]["receipts"] == compact["result"]["receipts"]
    # A deliberate stale request must retain the same immediate refusal. The
    # projector cannot improve runtime permission by hiding version changes.
    candidate = transfer_candidates(parent.observe("B"), predictive=True, message_delay=1.,
                                    respect_service_forecasts=True)["intents"]
    assert candidate
    request = dict(candidate[0], expected_version=parent.observe("B")["version"]+1)
    a, b = parent.fork(), parent.fork()
    assert a.submit_transfer_intent(request) == b.submit_transfer_intent(request) == {
        "status": "rejected", "reason": "stale_observation"}


def test_compact_native_same_timestamp_delayed_publication_and_legacy_cache_migration(native):
    data, _, _ = scenarios()["command_delay_2"]
    parent = native.NativeSession(data)
    parent.advance_to(.5)
    parent.publish_demand("A", "B", 1.)
    parent.publish_demand("A", "B", .2)
    parent.advance_to(1.5)
    _assert_decisions(transfer_candidates(parent.observe("B"), predictive=True),
                      transfer_candidates(parent.observe_control("B"), predictive=True))
    state = {"schema": "g31.analytic_controller_state.v1", "start": 1.5, "next_tick": 0,
        "config": {"owners": ["A", "B"], "predictive": True, "control_period": .5,
                   "message_delay": 0, "demand_delay": 0, "publish": True,
                   "respect_service_forecasts": False}, "published": {}}
    for owner in ("A", "B"):
        state["published"][owner] = sorted([j["business_bag_id"], j["origin"], j["arrival"], j.get("deadline", -1)]
            for j in parent.observe(owner)["jobs"] if j["status"] == "waiting_for_tray")
    before = parent.offline_state_sha256()
    full, compact = [run_online_matching(parent.fork(), ["A", "B"], horizon=20., predictive=True,
        controller_state=deepcopy(state), compact_projection=mode) for mode in (False, True)]
    assert parent.offline_state_sha256() == before
    assert full["controller_state"] == compact["controller_state"]
    assert full["submitted"] == compact["submitted"]
    assert full["result"]["receipts"] == compact["result"]["receipts"]


def test_compact_native_pending_incoming_prefix_beyond_supply_limit(native):
    data, _, _ = scenarios()["command_delay_2"]
    template = deepcopy(data["jobs"][1])
    data["jobs"] = [dict(template, business_bag_id=f"waiting-{i:03}", arrival=0.) for i in range(50)]
    data["trays"] = [{"tray_id": "T0", "node": 4}, {"tray_id": "T1", "node": 4}]
    next(n for n in data["node_contracts"] if n["node"] == 4)["capacity"] = 2
    session = native.NativeSession(data)
    session.advance_to(1.)
    session.publish_demand("A", "B", 0.)
    session.advance_to(1.)
    for i in range(6):
        reply = session.submit_transfer_intent({"request_id": f"live:pending-{i}", "owner_id": "B",
            "tray_id": "T0", "source": 4, "destination": 0, "issued_at": 1.,
            "earliest_departure": 1., "expiry": 100., "message_delay": 20.})
        assert reply["status"] == "pending"
    full, compact = session.observe("B"), session.observe_control("B")
    projection = compact["control_projection"]
    group = next(g for g in projection["waiting_groups"] if g["origin"] == 0)
    assert len(group["jobs"]) > 2*projection["candidate_limit"]
    a, b = transfer_candidates(full, predictive=False), transfer_candidates(compact, predictive=False)
    _assert_decisions(a, b)
    assert a["intents"][0]["request_id"].endswith("waiting-006")
