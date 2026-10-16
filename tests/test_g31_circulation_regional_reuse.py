"""Observation-scoped regional routing must preserve actual public behavior."""
from copy import deepcopy
from functools import partial
import json
import os
import random

import pytest

from scripts.experiments.g31_ics_circulation import regional_control as regional
from scripts.experiments.g31_ics_circulation import protocol_control as protocol


def observation():
    return {"now": .2, "owner_id": "A", "jobs": [
        {"business_bag_id": f"J{i}", "destination": 3, "storage_node": -1, "allow_suffix_reroute": True}
        for i in range(2)],
        "trays": [{"tray_id": f"T{i}", "node": 0, "mode": "loaded", "edge_to": -1,
                   "business_bag_id": f"J{i}", "generation": 1, "traversal_id": 0,
                   "committed_prefix": [0], "available_at": .3} for i in range(2)],
        "node_records": [(n, 1, .1, n, 0, []) for n in range(4)],
        "edge_records": [(0, 1, 1., 1.), (0, 2, 1., 1.), (1, 3, 1., 1.), (2, 3, 1., 1.)],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1} for u, v in [(0, 1), (0, 2), (1, 3), (2, 3)]],
        "node_contracts": [{"node": n, "zone": "A", "resource_owner": "A", "capacity": 2, "occupancy": 0} for n in range(4)],
        "known_faults": [], "delivered_messages": []}


@pytest.mark.parametrize("seed", range(30))
def test_repeated_sources_goals_and_float_ties_match_fresh_astar_exactly(seed):
    rng = random.Random(seed)
    obs = observation()
    obs["node_records"] = [(n, 1, rng.choice([0., .1, .2, 1.]), n, 0, []) for n in range(12)]
    obs["node_contracts"] = [{"node": n, "zone": "A", "occupancy": rng.randrange(3)} for n in range(12)]
    obs["edge_records"] = [(u, v, rng.choice([.001, .1, .2, 1., 1e6, 1e-8]), 1.)
        for u in range(12) for v in range(12) if u != v and rng.random() < .2]
    obs["edge_contracts"] = [{"from": u, "to": v, "capacity": 0 if rng.random() < .1 else 1}
                             for u, v, _, _ in obs["edge_records"]]
    obs["known_faults"] = [{"from": u, "to": v, "active": rng.choice([False, True])}
                            for u, v, _, _ in obs["edge_records"][::8]]
    original = deepcopy(obs)
    routing = regional._ObservationRouting(obs)
    for source, goal in [(rng.randrange(12), rng.randrange(12)) for _ in range(100)]:
        assert regional.public_astar(obs, source, goal, _routing=routing) == regional.public_astar(obs, source, goal)
    assert obs == original


def test_reuse_rejects_different_snapshot_or_advanced_clock():
    obs = observation(); routing = regional._ObservationRouting(obs)
    regional.public_astar(obs, 0, 3, _routing=routing)
    with pytest.raises(ValueError, match="routing_observation_mismatch"):
        regional.public_astar(deepcopy(obs), 0, 3, _routing=routing)
    obs["now"] += .1
    with pytest.raises(ValueError, match="routing_observation_mismatch"):
        regional.public_astar(obs, 0, 3, _routing=routing)


def test_packet_and_route_dictionary_isolation_and_later_faults():
    obs = observation(); routing = regional._ObservationRouting(obs)
    fresh = protocol.route_payload(obs, "T0", message_delay=.01, lease_seconds=5.)
    reused = protocol.route_payload(obs, "T0", message_delay=.01, lease_seconds=5., _routing=routing)
    assert fresh == reused
    reused[0]["next"] = 99
    assert protocol.route_payload(obs, "T0", message_delay=.01, lease_seconds=5., _routing=routing) == fresh
    obs["known_faults"] = [{"from": 0, "to": 1, "active": True}]
    changed = regional._ObservationRouting(obs)
    assert regional.public_astar(obs, 0, 3, _routing=changed) == (0, 2, 3)
    obs["known_faults"][0]["active"] = False
    obs["node_contracts"][1]["occupancy"] = 10
    assert regional.public_astar(obs, 0, 3) == (0, 2, 3)
    obs["edge_contracts"][1]["capacity"] = 0
    assert regional.public_astar(obs, 0, 3) == (0, 1, 3)


class LocalSession:
    def __init__(self, view, reject):
        self.view, self.reject = deepcopy(view), reject
        self.physical_time = view["now"]
    def observe_protocol_control(self, owner):
        return deepcopy(self.view)
    def submit_protocol_command(self, payload):
        # Submission changes the live session but never the already-read dict.
        self.view["node_contracts"][1]["occupancy"] += 10
        return {"status": "rejected" if self.reject else "pending", "reason": "test"}


@pytest.mark.parametrize("routes,forecasts", [(True, True), (True, False), (False, True), (False, False)])
@pytest.mark.parametrize("reject", [False, True])
def test_publications_payloads_and_policy_state_exact_even_after_submission(routes, forecasts, reject):
    results = []
    for reuse in (False, True):
        obs = observation(); frozen = deepcopy(obs)
        client = protocol.ProtocolClient(LocalSession(obs, reject))
        state = {"routes": {}, "forecasts": {}}
        records = protocol._publish_services(client, "A", state, command_delay=.01,
            publication_delay=.01, routes=routes, forecasts=forecasts, lease_seconds=5.,
            observation=obs, _reuse_route_work=reuse)
        assert obs == frozen
        results.append((records, state, client.state))
    assert results[0] == results[1]


def test_no_route_work_is_lazy_even_for_empty_static_contract():
    obs = {"now": 0., "owner_id": "A", "trays": [], "jobs": [], "node_contracts": []}
    for reuse in (False, True):
        client = protocol.ProtocolClient(LocalSession(obs, False))
        state = {"routes": {}, "forecasts": {}}
        assert protocol._publish_services(client, "A", state, command_delay=0., publication_delay=0.,
            routes=True, forecasts=True, lease_seconds=5., observation=obs, _reuse_route_work=reuse) == []


def native_scene(fault):
    from scripts.experiments.g31_ics_circulation.native_host import tiny_cycle
    data = tiny_cycle(); data["transfers"] = []
    for job in data["jobs"]:
        job["allow_suffix_reroute"] = True
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": 0.}
    if fault == "lost_ack":
        data["owner_protocol"]["drop_ack_packets"] = 1
    elif fault == "duplicate":
        data["owner_protocol"].update(duplicate_acks=True, duplicate_ack_delay=0.)
    else:
        data["faults"] = [{"from": 1, "to": 2, "start": 1., "end": 12.}]
    data["owner_notifications"] = {"enabled": True}
    return data


def patch_mode(monkeypatch, reuse):
    from scripts.experiments.g31_ics_circulation import event_protocol_control
    monkeypatch.setattr(event_protocol_control, "_publish_services", partial(protocol._publish_services, _reuse_route_work=reuse))
    return event_protocol_control.run_event_protocol_control


def calls(run):
    return [{k: v for k, v in c.items() if k != "submit_compute_ms"} for c in run["client_calls"]]


@pytest.mark.skipif(not os.environ.get("G31_CIRCULATION_BINARY"), reason="explicit native binary required")
@pytest.mark.parametrize("fault", ["lost_ack", "duplicate", "closure"])
@pytest.mark.parametrize("compact", [False, True])
def test_native_full_compact_fault_expiry_and_zero_delay_equivalence(monkeypatch, fault, compact):
    from scripts.experiments.g31_ics_circulation.native_host import load_native
    native = load_native(os.environ["G31_CIRCULATION_BINARY"])
    runs, hashes = [], []
    for reuse in (False, True):
        execute = patch_mode(monkeypatch, reuse)
        session = native.NativeSession(native_scene(fault))
        runs.append(execute(session, ["A", "B"], horizon=30., compact=compact,
            control_period=1., command_delay=0., publication_delay=0., retry_period=.5,
            forecast_validity=2., forecast_refresh_period=1., lease_seconds=2.))
        hashes.append(session.offline_state_sha256())
    assert calls(runs[0]) == calls(runs[1])
    assert runs[0]["controller_state"] == runs[1]["controller_state"]
    assert hashes[0] == hashes[1]
    for key in ("jobs", "trays", "transfers", "receipts", "leg_identities"):
        assert runs[0]["result"][key] == runs[1]["result"][key]


@pytest.mark.skipif(not os.environ.get("G31_CIRCULATION_BINARY"), reason="explicit native binary required")
def test_json_native_resume_switches_only_ephemeral_route_reuse(monkeypatch):
    from scripts.experiments.g31_ics_circulation.native_host import load_native
    native = load_native(os.environ["G31_CIRCULATION_BINARY"])
    options = dict(control_period=1., command_delay=0., publication_delay=0., retry_period=.5)
    execute = patch_mode(monkeypatch, False)
    full_session = native.NativeSession(native_scene("lost_ack"))
    full = execute(full_session, ["A", "B"], horizon=30., **options)
    split = native.NativeSession(native_scene("lost_ack"))
    prefix = execute(split, ["A", "B"], horizon=7.37, **options)
    execute = patch_mode(monkeypatch, True)
    resumed_session = split.fork()
    resumed = execute(resumed_session, ["A", "B"], horizon=30.,
        state=json.loads(json.dumps(prefix["controller_state"])), **options)
    assert calls(full) == calls(prefix) + calls(resumed)
    assert full["controller_state"] == resumed["controller_state"]
    assert full_session.offline_state_sha256() == resumed_session.offline_state_sha256()
