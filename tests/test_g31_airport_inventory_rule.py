"""R0 public-data and fake-protocol semantic gates; no native constructors."""
from copy import deepcopy
import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_rule as r0
from scripts.experiments.g31_ics_circulation import foundation_airport_protocol_v2 as controller
from scripts.experiments.g31_ics_circulation import protocol_control as protocol


def tray(identity, node, **changes):
    return dict(tray_id=identity, node=node, mode="empty", edge_from=-1, edge_to=-1,
        reception_node=-1, generation=0, traversal_id=0, available_at=0.,
        business_bag_id="", **changes)


def observation(*, source=0, stock=1, remote=False):
    contracts = [{"node": n, "zone": "B" if remote and n == 2 else "A",
        "resource_owner": "B" if remote and n == 2 else "A",
        "capacity": 10, "export_min_stock": 0, "allow_export": True,
        "allow_receive": True, "actual_available": 0, "occupancy": 0} for n in range(3)]
    if remote:
        for key in ("actual_available", "occupancy"):
            contracts[2].pop(key)
    contracts[source].update(actual_available=stock, occupancy=stock)
    return {"schema": "g31.owner_protocol_observation.v1", "owner_id": "A", "now": 10.,
        "node_records": [(n, 10, .001, 0, 0, [i for i in range(3) if i != n]) for n in range(3)],
        "edge_records": [(a, b, float(b + 1), 1.) for a in range(3) for b in range(3) if a != b],
        "edge_contracts": [{"from": a, "to": b, "capacity": 10} for a in range(3) for b in range(3) if a != b],
        "node_contracts": contracts, "trays": [tray(f"E{i}", source) for i in range(stock)],
        "jobs": [], "delivered_messages": [], "known_faults": [],
        "client_transfer_ledger": [], "transfers": [], "planning_snapshots": [],
        "static_role_contract": {"schema": "g31.static_node_roles.v1", "loader_nodes": [1, 2]}}


def snapshot(*, stock=0, capture=8., delivery=9., expiry=30., sequence=1):
    captured_trays = []
    for index in range(stock):
        captured_trays.append({**tray(f"B{index}", 2), "ready_kind": "empty",
            "service_ready_at": 0., "service_ready_known": True, "load_complete_at": -1.,
            "committed_prefix": []})
    body = {"schema": "g31.planning_capture.v1", "message_id": f"m{sequence}",
        "source_owner": "B", "target_owner": "A", "publication_sequence": sequence,
        "captured_at": capture, "valid_until": expiry, "static_contract_sha256": "a" * 64,
        "semantics": dict(queue_discipline="fifo", resource_semantics="physical",
            event_semantics="native", scorer_mode="S4_queue_aware_rule_only", merge_grant_rule="M3",
            merge_grant_timing_mode="jit_fair_aging_deadline", minimum_service_seconds=.001),
        "jobs": [], "trays": captured_trays,
        "nodes": [{"node": 2, "actual_available": stock, "occupancy": stock, "unrepresented_occupancy": 0}],
        "known_faults": [], "coverage": {
            "scope": "source_waiting_or_locally_carried_released_jobs_and_local_trays",
            "complete_for_declared_local_scope": True, "future_arrivals_included": False,
            "local_node_ids": [2], "tray_ids": [t["tray_id"] for t in captured_trays],
            "business_bag_ids": [], "unrepresented_occupancy": 0}}
    return {"schema": "g31.planning_snapshot.v1", "kind": "planning_snapshot",
        "digest_format": "g31.planning_capture_digest.v1", "capture": body,
        "payload_sha256": r0.capture_digest(body), "delivered_at": delivery,
        "status": "conditional"}


def request(status="pending", received=-1.):
    return {"request_id": "r1", "tray_id": "E0", "source": 0, "destination": 2,
        "issued_at": 1., "status": status, "received_at": received,
        "status_scope": "own_payload_and_last_delivered_ack_only"}


def test_one_unloaded_tray_returns_without_any_future_job_or_two_tray_threshold():
    current = observation()
    before = deepcopy(current)
    result = r0.select_stock_return(current)
    assert current == before
    assert len(result["intents"]) == 1
    assert result["intents"][0]["control_reason"] == "ordinary_return_to_loader"
    assert result["intents"][0]["source"] == 0 and result["intents"][0]["destination"] == 1
    assert result["intents"][0]["forecast_ledger"] == "actual_available"


def test_loader_singleton_never_swaps_without_demand_but_two_can_fill_zero():
    assert r0.select_stock_return(observation(source=1))["intents"] == []
    current = observation(source=1, stock=2)
    result = r0.select_stock_return(current)
    assert result["intents"][0]["destination"] == 2
    assert result["intents"][0]["control_reason"] == "optional_zero_stock_replenishment"
    current["node_contracts"][1].update(actual_available=1, occupancy=1)
    current["node_contracts"][2].update(actual_available=1, occupancy=1)
    current["trays"][1]["node"] = 2
    assert r0.select_stock_return(current)["intents"] == []


def test_real_queue_has_priority_over_zero_stock_and_singleton_threshold():
    current = observation(source=1)
    current["jobs"] = [{"business_bag_id": f"J{i}", "origin": 2, "arrival": 1. + i * .01,
        "status": "waiting_for_tray"} for i in range(10)]
    base = r0.r0_priority_planner(current)
    assert base["intents"][0]["destination"] == 2
    assert r0.select_stock_return(current, base)["inventory_return"]["reason"] == "priority_intents_remain"
    current = observation()
    current["trays"].append(tray("local2", 2))
    current["node_contracts"][2].update(actual_available=1, occupancy=1)
    current["jobs"] = [{"business_bag_id": f"J{i}", "origin": 2, "arrival": 1. + i * .01,
        "status": "waiting_for_tray"} for i in range(10)]
    assert r0.r0_priority_planner(current)["intents"][0]["destination"] == 2


def test_fifo_and_export_min_stock_are_not_bypassed():
    current = observation(source=1, stock=2)
    current["node_contracts"][1]["export_min_stock"] = 1
    assert len(r0.select_stock_return(current)["intents"]) == 1
    current["jobs"] = [{"business_bag_id": "local", "origin": 1, "arrival": 1.,
        "status": "waiting_for_tray"}]
    assert not r0.select_stock_return(current)["intents"]


def test_unknown_is_not_zero_and_necessary_return_has_explicit_static_fallback():
    current = observation(remote=True)
    current["node_contracts"][1].update(actual_available=2, occupancy=2)
    current["trays"].extend([tray("L1", 1), tray("L2", 1)])
    assert r0.inventory_view(current)["nodes"][2]["reported_actual_empty"] is None
    assert r0.select_stock_return(current)["intents"][0]["destination"] == 1
    current["node_contracts"][1].pop("actual_available")
    result = r0.select_stock_return(current)
    assert result["inventory_return"]["fallback_reason"] == "inventory_unknown"
    assert result["intents"][0]["control_reason"] == "ordinary_return_to_loader"
    assert not r0.select_stock_return(observation(source=1, stock=2, remote=True))["intents"]


def test_newest_expired_revision_never_resurrects_older_stock():
    current = observation(remote=True)
    current["planning_snapshots"] = [snapshot(expiry=100.), snapshot(capture=9., expiry=10., sequence=2)]
    view = r0.inventory_view(current)
    assert not view["nodes"][2]["known"]
    assert view["nodes"][2]["reported_actual_empty"] is None
    assert view["nodes"][2]["reason"] == "latest_snapshot_expired_or_invalid_time"


def test_undelivered_inventory_change_has_no_actor_effect_and_digest_is_checked():
    current = observation(remote=True)
    current["planning_snapshots"] = [snapshot(stock=3)]
    before = r0.inventory_view(current)
    current["planning_snapshots"].append(snapshot(stock=0, capture=9.5, delivery=11., sequence=2))
    assert r0.inventory_view(current) == before
    current["planning_snapshots"][0]["capture"]["nodes"][0]["actual_available"] = 0
    assert not r0.inventory_view(current)["nodes"][2]["known"]


@pytest.mark.parametrize("status", ["pending", "granted", "dispatching", "departed", "in_transit"])
def test_nonterminal_own_coverage_blocks_duplicate_even_when_new_snapshot_is_zero(status):
    current = observation(remote=True)
    current["planning_snapshots"] = [snapshot()]
    current["client_transfer_ledger"] = [request(status), deepcopy(request(status))]
    current["transfers"] = deepcopy(current["client_transfer_ledger"])
    view = r0.inventory_view(current)
    assert len(view["known_own_assignment_coverage"][2]) == 1
    assert view["nodes"][2]["reported_actual_empty"] == 0
    assert not any(r["destination"] == 2 for r in r0.rank_return_destinations(current, 0, view=view))
    assert not r0.select_stock_return(current)["intents"]


def test_received_coverage_requires_new_inventory_and_never_adds_stock_twice():
    current = observation(remote=True)
    current["planning_snapshots"] = [snapshot(stock=0, capture=7.)]
    current["client_transfer_ledger"] = [request("received", received=8.)]
    assert 2 in r0.inventory_view(current)["known_own_assignment_coverage"]
    current["planning_snapshots"] = [snapshot(stock=1, capture=8.5, delivery=9.)]
    view = r0.inventory_view(current)
    assert view["known_own_assignment_coverage"] == {}
    assert view["nodes"][2]["reported_actual_empty"] == 1


@pytest.mark.parametrize("change", [{"mode": "quarantined"}, {"mode": "empty_transit"},
    {"edge_to": 1}, {"reception_node": 1}, {"available_at": 20.}])
def test_nonavailable_entity_cannot_be_exported(change):
    current = observation()
    current["trays"][0].update(change)
    assert not r0.select_stock_return(current)["intents"]


def test_actual_only_rejects_future_mode_and_private_future_changes_do_not_change_intents():
    current = observation()
    with pytest.raises(ValueError, match="actual_only"):
        r0.r0_priority_planner(current, predictive=True)
    with pytest.raises(ValueError, match="actual_only"):
        r0.r0_priority_planner(current, respect_service_forecasts=True)
    before = r0.select_stock_return(current)["intents"]
    current["private_future_job_tape"] = [{"arrival": 500., "origin": 2}]
    current["flight_plan"] = {"B1": "changed arbitrary future"}
    assert r0.select_stock_return(current)["intents"] == before


def test_warmup_wrapper_preserves_common_options_then_switches_actual_only():
    current = observation()
    planner = r0.make_r0_priority_planner(activate_at=20.)
    result = planner(current, predictive=True, respect_service_forecasts=True)
    assert result["policy"] == "analytic_predictive_matching"
    current["now"] = 20.
    result = planner(current, predictive=True, respect_service_forecasts=True)
    assert result["policy"] == r0.METHOD
    assert all(row["ledger"] == "actual_available" for row in result["forecasts"])


class PublicSession:
    """No simulator; records only documented public endpoint interactions."""
    physical_time = 10.
    def __init__(self):
        self.commands = []
        self.transfer_calls = []
        self.snapshots = []
        self.acks = {}
        self.current = observation()
    def observe_protocol(self, owner):
        return deepcopy(self.current)
    observe_protocol_control = observe_protocol
    def protocol_planning_snapshots(self, owner):
        return deepcopy(self.snapshots)
    def submit_protocol_command(self, payload):
        self.commands.append(deepcopy(payload))
        return {"status": "pending"}
    def submit_protocol_transfer(self, payload):
        self.transfer_calls.append(deepcopy(payload))
        return {"status": "pending"}
    def protocol_command(self, owner, identity):
        return deepcopy(self.acks.get(identity, {}))
    def protocol_request(self, owner, identity):
        return deepcopy(self.acks.get(identity, {}))


def test_snapshot_endpoint_opt_in_byte_timing_and_single_active_capture_command():
    session = PublicSession()
    client = protocol.ProtocolClient(session, inventory_snapshots=True)
    assert client.view("A")["planning_snapshots"] == []
    assert client.inventory_snapshot_reads[0]["encoded_utf8_bytes"] == 2
    state = {}
    opts = dict(now=10., command_delay=1., publication_delay=2., validity=120., refresh_period=60.)
    first = protocol._publish_inventory(client, "A", ["A", "B"], state, **opts)
    assert len(first) == 1
    assert set(session.commands[0]) == {
        "request_id", "owner_id", "kind", "target_owner", "message_delay", "publication_delay", "expiry"}
    assert not protocol._publish_inventory(client, "A", ["A", "B"], state, **opts)
    identity = first[0]["request_id"]
    session.acks[identity] = {"last_delivered_ack": {"status": "delivered",
        "planning_snapshot": snapshot(capture=11., delivery=13.)}}
    session.acks[identity]["last_delivered_ack"]["planning_snapshot"]["capture"].update(
        source_owner="A", target_owner="B", valid_until=130.)
    session.physical_time = 13.
    client.refresh(retry=False)
    assert not protocol._publish_inventory(client, "A", ["A", "B"], state, **{**opts, "now": 20.})
    assert len(protocol._publish_inventory(client, "A", ["A", "B"], state, **{**opts, "now": 71.})) == 1
    restored = protocol.ProtocolClient(session, state=client.state, inventory_snapshots=True)
    assert restored.state == client.state
    with pytest.raises(ValueError, match="configuration"):
        protocol.ProtocolClient(session, state=client.state)


def test_post_stage_refresh_quota_and_error_are_persistent(monkeypatch):
    session = PublicSession()
    client = protocol.ProtocolClient(session, inventory_snapshots=True)
    state = {"next_tick": 2}
    result = protocol._post_inventory_return(client, "A", state, compact=True,
        command_delay=1., priority_error=False)
    assert len(result["attempts"]) == len(session.transfer_calls) == 1
    assert result["decision"]["inventory_return"]["selected"]
    assert len(client.inventory_snapshot_reads) == 2  # fresh before and after submit
    again = protocol._post_inventory_return(client, "A", state, compact=True,
        command_delay=1., priority_error=False)
    assert again["reason"] == "owner_tick_return_quota_spent"
    state["next_tick"] = 3
    failed = protocol._post_inventory_return(client, "A", state, compact=True,
        command_delay=1., priority_error=True)
    assert failed["reason"] == "priority_submit_error"
    assert protocol._post_inventory_return(client, "A", state, compact=True,
        command_delay=1., priority_error=False)["reason"] == "priority_submit_error"
    assert len(session.transfer_calls) == 1


def test_post_stage_cannot_bypass_new_fresh_priority_demand():
    session = PublicSession()
    session.current["jobs"] = [{"business_bag_id": "J", "origin": 1,
        "arrival": 1., "status": "waiting_for_tray"}]
    client = protocol.ProtocolClient(session, inventory_snapshots=True)
    result = protocol._post_inventory_return(client, "A", {"next_tick": 1}, compact=True,
        command_delay=1., priority_error=False)
    assert result["reason"] == "fresh_priority_intents_remain"
    assert session.transfer_calls == []


def test_recovery_retries_original_generation_and_received_ack_is_terminal():
    session = PublicSession()
    entity = session.current["trays"][0]
    entity.update(mode="quarantined", generation=4)
    capability = {"schema": "g31.recover_failed_empty.v1", "owner_id": "A",
        "tray_id": "E0", "from": 0, "expected_generation": 4,
        "failed_transfer_request_id": "failed", "failed_transport_leg_id": "failed:empty_return:1",
        "failure_reason": "departure_lease_expired_before_physical_entry"}
    entity["failed_empty_recovery"] = capability
    client = protocol.ProtocolClient(session, retry_period=1.)
    state = {}
    result = protocol._recover_failed_empty(client, "A", state, now=10.,
        command_delay=1., lease_seconds=20.)
    identity = result[0]["request_id"]
    assert "failure_reason" not in session.commands[0]
    saved = deepcopy(session.commands[0])
    entity["generation"] = 5
    capability["expected_generation"] = 5
    session.physical_time = 11.
    client.refresh()
    assert session.commands == [saved, saved]
    assert protocol._recover_failed_empty(client, "A", state, now=11.,
        command_delay=1., lease_seconds=20.) == []
    session.acks[identity] = {"last_delivered_ack": {"status": "recovered", "result_id": "failed"}}
    client.refresh()
    assert client.state["outbox"][identity]["terminal"] is True
    assert protocol._recover_failed_empty(client, "A", state, now=11.,
        command_delay=1., lease_seconds=20.) == []
    assert session.commands == [saved, saved]


class TickSession(PublicSession):
    def __init__(self, *, reject_priority=False):
        super().__init__()
        self.physical_time = 0.
        self.current["now"] = 0.
        self.priority = ["mandatory", "business"]
        self.reject_priority = reject_priority
        self.trace = []
    def advance_to(self, at, max_events):
        self.physical_time = at
        self.current["now"] = at
        return {"status": "reached", "horizon_complete": True}
    def protocol_demand_signature(self, owner):
        return "unchanged"
    def observe_protocol(self, owner):
        self.trace.append(("view", tuple(self.priority)))
        return {**deepcopy(self.current), "priority_queue": self.priority.copy()}
    observe_protocol_control = observe_protocol
    def submit_protocol_transfer(self, payload):
        self.trace.append(("submit", payload["tray_id"]))
        if payload["tray_id"] in self.priority:
            if self.reject_priority:
                return {"status": "rejected"}
            assert payload["tray_id"] == self.priority[0]
            self.priority.pop(0)
        else:
            self.current["trays"][0]["mode"] = "empty_transit"
            self.current["node_contracts"][0]["actual_available"] = 0
        return super().submit_protocol_transfer(payload)
    def result_at(self, horizon):
        assert horizon == self.physical_time
        return {"advance": {"status": "reached", "horizon_complete": True}}


@pytest.mark.parametrize("reject_priority", [False, True])
def test_full_controller_submits_mandatory_and_business_before_fresh_post_stage(monkeypatch, reject_priority):
    original = r0.r0_priority_planner
    def priority(observation, **options):
        base = original(observation, **options)
        if observation["priority_queue"]:
            base["intents"] = [{"tray_id": identity,
                "control_reason": "terminal_receiving_pressure" if identity == "mandatory"
                else "observed_source_queue"} for identity in observation["priority_queue"]]
        return base
    monkeypatch.setattr(r0, "r0_priority_planner", priority)
    monkeypatch.setattr(controller, "_publish_services", lambda *a, **kw: [])
    session = TickSession(reject_priority=reject_priority)
    captured = []
    result = controller.run_airport_bounded_protocol_control(session, ["A"], horizon=0.,
        predictive=False, forecasts=False, routes=False, inventory_snapshots=True,
        stock_return=True, planner=priority, planner_identity=r0.METHOD,
        precommit_observer=lambda **kwargs: captured.append(deepcopy(kwargs["decision"])))
    order = [row[1] for row in session.trace if row[0] == "submit"]
    decision = result["control_records"][0]["owner_decisions"][0]
    if reject_priority:
        assert order == ["mandatory"]
        assert decision["inventory_return"]["reason"] == "priority_submit_error"
        assert len(captured) == 1
    else:
        assert order == ["mandatory", "business", "E0"]
        assert len(decision["attempts"]) == 2
        assert len(decision["inventory_return"]["attempts"]) == 1
        assert captured[-1]["inventory_return"]["selected"]
        quota = result["controller_state"]["inventory_return_quota"]["A"]
        assert quota["tick"] == 0 and quota["new_submissions"] == 1
        last_priority_submit = session.trace.index(("submit", "business"))
        return_submit = session.trace.index(("submit", "E0"))
        assert ("view", ()) in session.trace[last_priority_submit + 1:return_submit]


def test_controller_common_warmup_switches_publication_matching_and_post_phase_together(monkeypatch):
    session = TickSession()
    session.priority = []
    session.current["trays"] = []
    session.current["node_contracts"][0].update(actual_available=0, occupancy=0)
    services, matching, post = [], [], []
    def service(_client, _owner, _state, **options):
        services.append((session.physical_time, options["forecasts"]))
        return []
    def planner(current, **options):
        matching.append((current["now"], options["predictive"], options["respect_service_forecasts"]))
        return {"intents": []}
    def after(_client, _owner, state, **options):
        post.append(state["next_tick"])
        return {"attempts": [], "reason": "fixture"}
    monkeypatch.setattr(controller, "_publish_services", service)
    monkeypatch.setattr(controller, "_post_inventory_return", after)
    controller.run_airport_bounded_protocol_control(session, ["A"], horizon=60.,
        control_period=60., predictive=True, forecasts=True, inventory_snapshots=True,
        actual_only_activate_at=60., stock_return=True, stock_return_activate_at=60.,
        planner=planner, planner_identity="warmup_fixture")
    assert services == [(0., True), (60., False)]
    assert matching == [(0., True, True), (60., False, False)]
    assert post == [1]


def test_tick_start_evaluator_follows_complete_advance_before_refresh_and_publications(monkeypatch):
    session = TickSession()
    trace, captures = [], []
    original_advance = session.advance_to
    def advance(at, max_events):
        trace.append(("advance", at))
        return original_advance(at, max_events)
    session.advance_to = advance
    original_refresh = controller.ProtocolClient.refresh
    def refresh(client, **options):
        trace.append(("refresh", session.physical_time))
        return original_refresh(client, **options)
    def inventory(*args, **options):
        trace.append(("inventory", session.physical_time))
        return []
    def services(*args, **options):
        trace.append(("services", session.physical_time))
        return []
    def observe(*, session, controller_state, client_state, tick_at):
        assert session.physical_time == tick_at
        assert controller_state["next_tick"] == int(tick_at)
        trace.append(("observer", tick_at))
        captures.append(deepcopy(client_state))
    monkeypatch.setattr(controller.ProtocolClient, "refresh", refresh)
    monkeypatch.setattr(controller, "_publish_inventory", inventory)
    monkeypatch.setattr(controller, "_publish_services", services)
    result = controller.run_airport_bounded_protocol_control(session, ["A"],
        horizon=1., control_period=1., prebalance=False, inventory_snapshots=True,
        tick_start_observer=observe)
    for at in (0., 1.):
        observer_at = trace.index(("observer", at))
        assert trace[observer_at - 1] == ("advance", at)
        assert trace[observer_at + 1:observer_at + 4] == [
            ("refresh", at), ("inventory", at), ("services", at)]
    assert len(captures) == 2
    assert result["offline_tick_start_observer_seconds"] >= 0.
    assert all(r["offline_tick_start_observer_ms"] >= 0. for r in result["control_records"])
