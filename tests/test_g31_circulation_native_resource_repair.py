"""Pure first-action guards; these tests never load a native binary."""
import copy
from scripts.experiments.g31_ics_circulation import research_native_resource_repair as driver


class Session:
    def __init__(self, trays=()): self.trays = trays
    def observe_protocol(self, owner): return {"now": .11, "trays": copy.deepcopy(self.trays)}


def setup(monkeypatch, action):
    monkeypatch.setattr(driver.shared.adapter, "collect_native", lambda *a: {
        "status": "conditional_native_delivered_model_input", "native_delivery_verified": True, "bundle": {}})
    monkeypatch.setattr(driver.repair.model, "candidates_from_durations", lambda b: ([action], action))
    monkeypatch.setattr(driver.repair, "repair", lambda *a, **kw: {"status": "conditional_model_proposal", "selected_action": action})


def test_missing_verified_native_capture_never_observes_or_submits(monkeypatch):
    monkeypatch.setattr(driver.shared.adapter, "collect_native", lambda *a: {"status": "unknown_missing_self_ack", "native_delivery_verified": False})
    result = driver.owner_action(None, None, None, "A", "self-id", "coordinate_plateau")
    assert result["proposal"]["selected_action"] is None and result["request_id"] is None


def test_fresh_local_tray_change_withholds_model_selected_transfer(monkeypatch):
    setup(monkeypatch, {"initial_next": 2, "departure": .11, "later_mode": "adaptive"})
    result = driver.owner_action(None, Session(), None, "B", "self-id", "resource_pair_repair")
    assert result["proposal"]["status"] == "unknown_local_tray_changed" and result["request_id"] is None


def test_actual_route_command_required_for_route2_while_route1_is_explicit_keep(monkeypatch):
    tray = {"tray_id": "L", "mode": "loaded", "node": 0, "edge_to": -1, "business_bag_id": "loaded"}
    issued = []
    monkeypatch.setattr(driver.v1, "request_route", lambda *a: issued.append(a) or "actual-route-request")
    setup(monkeypatch, {"initial_next": 1, "departure": .11, "later_mode": "adaptive"})
    kept = driver.owner_action(None, Session([tray]), None, "A", "self-id", "coordinate_strict")
    assert kept["request_id"] is None and issued == []
    setup(monkeypatch, {"initial_next": 2, "departure": .11, "later_mode": "adaptive"})
    changed = driver.owner_action(None, Session([tray]), None, "A", "self-id", "coordinate_plateau")
    assert changed["request_id"] == "actual-route-request" and issued[0][3] == 2
