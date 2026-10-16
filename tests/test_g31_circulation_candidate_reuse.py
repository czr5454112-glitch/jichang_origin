"""Same-observation reuse must preserve exact path ties, messages, and copies."""
from copy import deepcopy
from dataclasses import asdict
from functools import partial
import json
import os
import random

import pytest

from scripts.experiments.g31_ics_circulation import analytic_control as control


def observation():
    return {"now": 3., "owner_id": "A", "version": 4,
        "node_records": [(n, 1, .1, n, 0, []) for n in range(4)],
        "edge_records": [(0, 3, 1., 1.), (3, 1, 1., 1.), (0, 2, 1., 1.), (2, 1, 1., 1.), (1, 0, 1., 1.)],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1} for u, v in [(0, 3), (3, 1), (0, 2), (2, 1), (1, 0)]],
        "node_contracts": [{"node": n, "zone": "A" if n == 0 else "B", "capacity": 8} for n in range(4)],
        "jobs": [], "transfers": [], "known_faults": [],
        "trays": [{"tray_id": f"T{i}", "node": 0, "mode": "empty"} for i in range(3)],
        "delivered_messages": [{"kind": "demand", "source_owner": "B", "observed_at": 1., "delivered_at": 2.,
            "jobs": [{"business_bag_id": f"J{i}", "origin": 1 + i % 2, "arrival": .1 * i,
                      "status": "waiting_for_tray"} for i in range(6)]},
            {"kind": "service_forecast", "message_id": "M1", "source_owner": "B", "tray_id": "other",
             "generation": 1, "observed_at": 1., "delivered_at": 2., "entry_estimate": 4.,
             "release_estimate": 10., "next": 2, "status": "conditional", "publication_sequence": 1}]}


@pytest.mark.parametrize("seed", range(30))
def test_incremental_dijkstra_exact_for_arbitrary_target_order_and_float_ties(seed):
    rng = random.Random(seed)
    obs = observation()
    obs["node_records"] = [(n, 1, rng.choice([0., .1, .2, 1.]), n, 0, []) for n in range(12)]
    obs["edge_records"] = [(u, v, rng.choice([.001, .1, .2, 1., 1e6, 1e-8]), 1.)
        for u in range(12) for v in range(12) if u != v and rng.random() < .22]
    obs["edge_contracts"] = []
    fresh = control.PublicTravel(obs, _reuse_source_searches=False)
    reused = control.PublicTravel(obs)
    pairs = [(rng.randrange(12), rng.randrange(12)) for _ in range(150)]
    pairs += [(0, 0), (0, 99), (0, 1), (0, 11)]
    for source, target in pairs:
        assert reused.path(source, target) == fresh.path(source, target)
        assert reused.cache == fresh.cache


@pytest.mark.parametrize("predictive", [False, True])
@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("windows", [False, True])
def test_complete_candidate_values_order_and_nested_copies(predictive, compressed, windows):
    obs = observation()
    obs["trays"].append({"tray_id": "H", "node": 0, "mode": "hold", "available_at": 5.})
    frozen = deepcopy(obs)
    opts = dict(predictive=predictive, compress_equivalent_demands=compressed, respect_service_forecasts=windows)
    reused = control.transfer_candidates(obs, **opts)
    reference = control.transfer_candidates(obs, _reuse_observation_work=False, **opts)
    assert reused == reference and obs == frozen
    assert list(reused) == list(reference)
    assert reused["supplies"][0] is not reused["forecasts"][0]
    reused["forecasts"][0]["tray_id"] = "changed"
    assert reused["supplies"][0]["tray_id"] != "changed"
    if windows:
        first = reused["pool"][0]["service_window"]
        first["conditional_dependencies"].append("changed")
        assert all("changed" not in c["service_window"]["conditional_dependencies"] for c in reused["pool"][1:])
    assert control.transfer_candidates(obs, **opts) == reference


@pytest.mark.parametrize("change", ["fault_start", "fault_end", "capacity_zero", "expiry", "withdrawal", "same_epoch_revision", "undelivered"])
def test_next_call_rebuilds_for_fault_and_message_boundaries(change):
    obs = observation()
    old = control.transfer_candidates(obs, predictive=True, respect_service_forecasts=True)
    if change == "fault_start":
        obs["known_faults"] = [{"from": 0, "to": 2, "start": 3., "end": 5.}]
    elif change == "fault_end":
        obs["known_faults"] = [{"from": 0, "to": 2, "start": 0., "end": 3.}]
    elif change == "capacity_zero":
        obs["edge_contracts"][2]["capacity"] = 0
    elif change == "expiry":
        obs["delivered_messages"][1]["status"] = "expired"
    elif change == "withdrawal":
        obs["delivered_messages"].append(dict(obs["delivered_messages"][1], message_id="W1", status="withdrawn", supersedes="M1"))
    elif change == "same_epoch_revision":
        obs["delivered_messages"].append(dict(obs["delivered_messages"][1], message_id="M2", publication_sequence=2, release_estimate=20.))
    else:
        obs["delivered_messages"][1]["delivered_at"] = 4.
    if change == "undelivered":
        for reuse in [False, True]:
            with pytest.raises(ValueError, match="undelivered_service_forecast"):
                control.transfer_candidates(obs, predictive=True, respect_service_forecasts=True, _reuse_observation_work=reuse)
    else:
        actual = control.transfer_candidates(obs, predictive=True, respect_service_forecasts=True)
        assert actual == control.transfer_candidates(obs, predictive=True, respect_service_forecasts=True, _reuse_observation_work=False)
        if change in {"fault_start", "capacity_zero", "expiry", "withdrawal", "same_epoch_revision"}:
            assert actual != old


def test_window_revision_resolution_is_once_per_call_and_stays_lazy(monkeypatch):
    original, count = control.conditional_service_windows, []
    def counted(obs):
        count.append(obs["now"])
        return original(obs)
    monkeypatch.setattr(control, "conditional_service_windows", counted)
    obs = observation()
    control.transfer_candidates(obs, predictive=True, respect_service_forecasts=True)
    assert len(count) == 1
    count.clear()
    control.transfer_candidates(obs, predictive=True, respect_service_forecasts=True, _reuse_observation_work=False)
    assert len(count) > 1
    count.clear(); obs["trays"] = []
    obs["delivered_messages"][1]["delivered_at"] = 100.
    control.transfer_candidates(obs, predictive=True, respect_service_forecasts=True)
    assert not count


def test_forecast_scalar_fast_path_preserves_recursive_fallback():
    forecast = control.ReleaseForecast("T", 0, 1., 2., "test", "A", 0, "D")
    result = control._scalar_forecast_dict(forecast)
    assert result == asdict(forecast) and list(result) == list(asdict(forecast))
    unusual = control.ReleaseForecast({"nested": [1]}, 0, 1., 2., "test", "A", 0, "D")
    result = control._scalar_forecast_dict(unusual)
    assert result == asdict(unusual)
    result["tray_id"]["nested"].append(2)
    assert unusual.tray_id == {"nested": [1]}


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


def patch_candidate_mode(monkeypatch, reuse):
    from scripts.experiments.g31_ics_circulation import event_protocol_control, protocol_control
    function = partial(control.transfer_candidates, _reuse_observation_work=reuse)
    monkeypatch.setattr(event_protocol_control, "transfer_candidates", function)
    monkeypatch.setattr(protocol_control, "transfer_candidates", function)
    return event_protocol_control.run_event_protocol_control


def calls(run):
    return [{k: v for k, v in c.items() if k != "submit_compute_ms"} for c in run["client_calls"]]


@pytest.mark.skipif(not os.environ.get("G31_CIRCULATION_BINARY"), reason="explicit native binary required")
@pytest.mark.parametrize("fault", ["lost_ack", "duplicate", "closure"])
@pytest.mark.parametrize("compact", [False, True])
def test_native_fault_message_drains_and_controller_state_exact(monkeypatch, fault, compact):
    from scripts.experiments.g31_ics_circulation.native_host import load_native
    native = load_native(os.environ["G31_CIRCULATION_BINARY"])
    rows, states = [], []
    for reuse in (False, True):
        execute = patch_candidate_mode(monkeypatch, reuse)
        session = native.NativeSession(native_scene(fault))
        run = execute(session, ["A", "B"], horizon=30., compact=compact,
            control_period=1., command_delay=0., publication_delay=0., retry_period=.5,
            forecast_validity=2., forecast_refresh_period=1.)
        rows.append(run); states.append(session.offline_state_sha256())
    assert calls(rows[0]) == calls(rows[1])
    assert rows[0]["controller_state"] == rows[1]["controller_state"]
    assert states[0] == states[1]
    for key in ("jobs", "trays", "transfers", "receipts", "leg_identities"):
        assert rows[0]["result"][key] == rows[1]["result"][key]


@pytest.mark.skipif(not os.environ.get("G31_CIRCULATION_BINARY"), reason="explicit native binary required")
def test_native_json_resume_switches_only_runtime_work_reuse(monkeypatch):
    from scripts.experiments.g31_ics_circulation.native_host import load_native
    native = load_native(os.environ["G31_CIRCULATION_BINARY"])
    options = dict(control_period=1., command_delay=0., publication_delay=0., retry_period=.5)
    execute = patch_candidate_mode(monkeypatch, False)
    full_session = native.NativeSession(native_scene("lost_ack"))
    full = execute(full_session, ["A", "B"], horizon=30., **options)
    split = native.NativeSession(native_scene("lost_ack"))
    prefix = execute(split, ["A", "B"], horizon=7.37, **options)
    state = json.loads(json.dumps(prefix["controller_state"]))
    execute = patch_candidate_mode(monkeypatch, True)
    resumed_session = split.fork()
    resumed = execute(resumed_session, ["A", "B"], horizon=30., state=state, **options)
    assert calls(full) == calls(prefix) + calls(resumed)
    assert full["controller_state"] == resumed["controller_state"]
    assert full_session.offline_state_sha256() == resumed_session.offline_state_sha256()
