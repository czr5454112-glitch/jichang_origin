"""Resource waits wake from real native events, including cloned waits."""
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.native_host import (
    load_native, prepare_input, audit_result,
)


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if binary is None:
        binary = next((Path(__file__).absolute().parents[1]/"build_lt_session/python").glob("czr005_circulation*.pyd"))
    return load_native(binary)


def job(identity, origin, destination, arrival=0):
    return dict(business_bag_id=identity, origin=origin, destination=destination,
                arrival=arrival, deadline=50000, load_seconds=0,
                unload_seconds=0, hold_seconds=0)


def receiving_release():
    edges = [(0, 1, 1., 1.), (1, 2, 1., 1.), (2, 3, 1., 1.), (3, 0, 1., 1.)]
    return prepare_input(dict(
        node_records=[(n, 1, .01, n, 0, [v for u, v, _, _ in edges if u == n]) for n in range(4)],
        edge_records=edges,
        node_contracts=[dict(node=n, zone="A" if n < 2 else "B", capacity=1) for n in range(4)],
        edge_contracts=[{"from": u, "to": v, "capacity": 1, "entry_headway": .01} for u, v, _, _ in edges],
        trays=[dict(tray_id="A", node=0), dict(tray_id="B", node=1)],
        jobs=[job("waiting", 0, 2), job("departure", 1, 3, 10000)],
        transfers=[], faults=[], options=dict(max_events=1000, max_simulation_time=10030, trace_limit=1000)))


def edge_release(*, travel=1., headway=10000.):
    return prepare_input(dict(
        node_records=[(0, 1, .001, 0, 0, [1]), (1, 1, .001, 1, 0, [0])],
        edge_records=[(0, 1, travel, 1.), (1, 0, 1., 1.)],
        node_contracts=[dict(node=n, zone=str(n), capacity=2) for n in range(2)],
        edge_contracts=[{"from": 0, "to": 1, "capacity": 1, "entry_headway": headway},
                        {"from": 1, "to": 0, "capacity": 1, "entry_headway": .001}],
        trays=[dict(tray_id="A", node=0), dict(tray_id="B", node=0)],
        jobs=[job("first", 0, 1), job("second", 0, 1)],
        transfers=[], faults=[], options=dict(max_events=1000, max_simulation_time=25000, trace_limit=1000)))


def assert_complete_without_polling(data, result):
    audit_result(data, result)
    assert all(j["status"] == "completed" for j in result["jobs"])
    assert result["native_summary"]["event_count"] < 500
    assert any(r["event"] == "RESOURCE_WAIT" for r in result["receipts"])
    assert any(r["event"] == "RESOURCE_WAKE" for r in result["receipts"])
    assert not any(r["event"] == "LEG_FAILED" for r in result["receipts"])


def test_full_receiving_berth_wakes_after_real_departure(native):
    data = receiving_release()
    result = native.run(data)
    assert_complete_without_polling(data, result)
    wakes = [r for r in result["receipts"] if r["event"] == "RESOURCE_WAKE"]
    assert any(r["reason"] == "source_berth_departed" and r["time"] >= 10000 for r in wakes)
    assert result["jobs"][0]["completed_at"] > 10000


def test_committed_headway_expiry_does_not_poll(native):
    data = edge_release()
    result = native.run(data)
    assert_complete_without_polling(data, result)
    assert any(r["event"] == "RESOURCE_WAKE" and r["reason"] == "committed_headway_expired"
               for r in result["receipts"])
    entries = [r["time"] for r in result["receipts"] if r["event"] == "EDGE_ENTER" and r["from"] == 0]
    assert entries[1]-entries[0] >= 10000-1e-8


def test_inflight_capacity_wakes_on_real_edge_exit(native):
    data = edge_release(travel=10000, headway=.001)
    result = native.run(data)
    assert_complete_without_polling(data, result)
    assert any(r["event"] == "RESOURCE_WAKE" and r["reason"] == "edge_capacity_released"
               for r in result["receipts"])


def test_preferred_resource_wait_does_not_poll_an_unused_alternative(native):
    data = receiving_release()
    data["node_records"].append((4, 1, .01, 4, 0, [2]))
    data["node_records"][0] = (0, 1, .01, 0, 0, [1, 4])
    data["node_contracts"].append(dict(node=4, zone="A", capacity=1))
    for u, v, length in [(0, 4, 100.), (4, 2, 100.)]:
        data["edge_records"].append((u, v, length, 1.))
        data["edge_contracts"].append({"from": u, "to": v, "capacity": 1, "entry_headway": .01})
    data = prepare_input(data)
    result = native.run(data)
    assert_complete_without_polling(data, result)
    assert not any(r["event"] == "EDGE_ENTER" and r["to"] == 4 for r in result["receipts"])


def test_candidate_queue_change_recomputes_preferred_wait(native):
    edges = [(0, 1, .1, 1.), (1, 2, .1, 1.), (0, 4, .25, 1.),
             (4, 2, .1, 1.), (1, 5, 1., 1.), (5, 3, .1, 1.)]
    data = prepare_input(dict(
        node_records=[(n, 1, .01, n, 0, [v for u, v, _, _ in edges if u == n]) for n in range(6)],
        edge_records=edges,
        node_contracts=[dict(node=n, zone=str(n), capacity=1) for n in range(6)],
        edge_contracts=[{"from": u, "to": v, "capacity": 1, "entry_headway": .01} for u, v, _, _ in edges],
        trays=[dict(tray_id="A", node=0), dict(tray_id="B", node=1), dict(tray_id="C", node=5)],
        jobs=[job("waiting", 0, 2), job("new-queue", 1, 5, 100), job("release", 5, 3, 200)],
        transfers=[], faults=[], options=dict(max_events=1000, max_simulation_time=300, trace_limit=1000)))
    result = native.run(data)
    assert_complete_without_polling(data, result)
    assert any(r["event"] == "RESOURCE_WAKE" and r["reason"] == "candidate_score_state_changed"
               and r["tray_id"] == "A" for r in result["receipts"])
    # The original preferred berth 1 is occupied until after 200. Its queue
    # becoming nonempty changes S4's ranking and must wake A before then.
    assert any(r["event"] == "EDGE_ENTER" and r["from"] == 0 and r["to"] == 4
               and 100 <= r["time"] < 200 for r in result["receipts"])


def test_static_closed_domain_retains_unserved_bags_without_polling(native):
    data = edge_release()
    data["edge_contracts"][0]["capacity"] = 0
    session = native.NativeSession(data)
    result = session.result_at(20000)
    assert len(result["jobs"]) == len(data["jobs"]) == 2
    assert len(result["trays"]) == len(data["trays"]) == 2
    assert all(j["completed_at"] < 0 for j in result["jobs"])
    assert result["native_summary"]["event_count"] < 500
    assert any(r["event"] == "RESOURCE_WAIT" and r["reason"] == "no_static_legal_suffix"
               for r in result["receipts"])
    assert not any(r["event"] == "EDGE_ENTER" for r in result["receipts"])


@pytest.mark.parametrize("data_factory", [receiving_release, edge_release])
def test_pending_wait_checkpoint_and_sibling_continuation(native, data_factory):
    data = data_factory()
    parent = native.NativeSession(data)
    parent.advance_to(100)
    before = parent.offline_state_sha256()
    restored = native.NativeSession(data)
    restored.restore(parent.checkpoint())
    sibling = parent.fork()
    assert before == restored.offline_state_sha256() == sibling.offline_state_sha256()
    result = restored.result_at(data["options"]["max_simulation_time"])
    assert parent.offline_state_sha256() == sibling.offline_state_sha256() == before
    other = sibling.result_at(data["options"]["max_simulation_time"])
    assert result["receipts"] == other["receipts"]
    assert result["jobs"] == other["jobs"]
    assert restored.offline_state_sha256() == sibling.offline_state_sha256()
    assert_complete_without_polling(data, result)
