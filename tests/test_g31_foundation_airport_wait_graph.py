"""Current graph witnesses must come from actual diagnostic holds and waits."""
from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation.foundation_airport_wait_graph import analyze_wait_graph


def fixture():
    data = {"jobs": [], "node_contracts": [{"node": node, "capacity": 1} for node in [0, 1]],
        "edge_contracts": [{"from": 0, "to": 1, "capacity": 1}, {"from": 1, "to": 0, "capacity": 1}]}
    trays = [{"tray_id": name, "node": node, "mode": "loaded", "active_leg": node,
        "edge_from": -1, "edge_to": -1, "reception_node": -1}
        for name, node in [("a", 0), ("b", 1)]]
    diagnostic = {"schema": "g31.circulation.offline_diagnostics.v1", "now": 100.,
        "trays": trays, "legs": [{"runtime_id": node, "tray_index": node} for node in [0, 1]],
        "resource_waits": [{"runtime_id": node, "node": node, "generation": 3, "edge_indices": [],
            "receiving_nodes": [1-node], "ranking_nodes": [], "static_blocked": False} for node in [0, 1]]}
    result = {"physical_clock": 100., "advance": {"horizon_complete": True},
        "trays": [dict(row, available_at=0.) for row in trays], "jobs": [], "receipts": [],
        "transfers": [], "leg_identities": []}
    return data, result, diagnostic


def test_exact_reciprocal_wait_and_current_holds_produce_evidenced_cycle():
    data, result, diagnostic = fixture()
    report = analyze_wait_graph(data, result, diagnostic)
    assert len(report["witnessed_hold_wait_cycles"]) == 1
    assert len(report["witnessed_hold_wait_cycles"][0]["edges"]) == 4
    assert all(edge["evidence"]["at"] == 100. for edge in report["edges"])
    assert not report["cycle_is_global_deadlock_proof"]


def test_more_capacity_cannot_be_misreported_as_hold_cycle():
    data, result, diagnostic = fixture()
    data["node_contracts"][1]["capacity"] = 2
    report = analyze_wait_graph(data, result, diagnostic)
    assert not report["witnessed_hold_wait_cycles"]
    assert report["unknown_or_timed_waits"][0]["reason"] == "wait_index_but_current_capacity_not_saturated"


def test_unsaturated_edge_wait_remains_unknown_headway_without_invented_holder():
    data, result, diagnostic = fixture()
    diagnostic["resource_waits"] = [dict(diagnostic["resource_waits"][0],
        edge_indices=[0], receiving_nodes=[])]
    report = analyze_wait_graph(data, result, diagnostic)
    assert report["edges"] == []
    assert report["unknown_or_timed_waits"][0]["reason"].startswith("timed_headway")


def test_reception_lease_and_physical_occupancy_count_one_tray_once():
    data, result, diagnostic = fixture()
    diagnostic["trays"][1]["reception_node"] = 1
    data["node_contracts"][1]["capacity"] = 2
    report = analyze_wait_graph(data, result, diagnostic)
    assert not report["witnessed_hold_wait_cycles"]
    assert any(row["resource"] == "node:1" for row in report["unknown_or_timed_waits"])


def test_request_retries_and_native_rejection_events_are_separate_denominators():
    data, result, diagnostic = fixture()
    request = {"request_id": "r", "tray_id": "a", "owner_id": "A", "source": 0, "destination": 1}
    calls = [{"kind": "transfer", "at": 50., "retry": False, "request": request},
        {"kind": "transfer", "at": 60., "retry": True, "request": request}]
    result["transfers"] = [{"request_id": "r", "status": "rejected", "reason": "receiving_full"}]
    result["receipts"] = [{"event": "TRANSFER_REJECTED", "reason": "receiving_full"}] * 3
    counts = analyze_wait_graph(data, result, diagnostic, client_calls=calls)["request_denominators"]
    assert counts["unique_request_count"] == 1
    assert counts["actual_nonretry_submissions"] == counts["actual_retry_submissions"] == 1
    assert counts["native_rejection_event_count"] == 3
    assert counts["request_terminal_rejections_by_reason"]["receiving_full"] == 1


def test_mismatched_or_incomplete_native_timestamp_cannot_mint_current_graph():
    data, result, diagnostic = fixture()
    for mutated in (dict(diagnostic, now=101.), dict(diagnostic, schema="guess")):
        with pytest.raises(ValueError):
            analyze_wait_graph(data, result, mutated)
    result["advance"]["horizon_complete"] = False
    with pytest.raises(ValueError):
        analyze_wait_graph(data, result, diagnostic)
