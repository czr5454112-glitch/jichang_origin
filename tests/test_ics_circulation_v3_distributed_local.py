"""Opt-in local service preserves the old W2 artifact/source contract."""
from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.distributed_clock import ClockRequest, DistributedClock, TransportFault
from scripts.experiments.ics_circulation_v3.distributed_local import LocalDispatchClock, LocalDispatchController
from scripts.experiments.ics_circulation_v3.distributed_slow import LocalClockController, PublishedDemand
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray


def scene(stock=1, *, local_bag=True, reachable=True, floor=0):
    nodes = {"A": Node("A", "source", "west", 5), "A2": Node("A2", "source", "west", 5),
             "B": Node("B", "remote", "east", 5)}
    edges = [Edge("A2B", "A2", "B", 2), Edge("AB", "A", "B", 2), Edge("BA", "B", "A", 2)]
    if reachable:
        edges.append(Edge("AA2", "A", "A2", 3))
    bags = {"local": Bag("local", "A2", "B", 0, 60)} if local_bag else {}
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                    {f"t{i}": Tray(f"t{i}", "A") for i in range(stock)}, bags,
                    module=FixedLocalModule(1, {"A2": 2}, export_min_stock=floor))


def controllers(enabled, **kwargs):
    return {owner: LocalDispatchController(owner, local_dispatch=enabled, mode="both", period=1, **kwargs)
            for owner in ("west", "east")}


def empty_records(result):
    return [row for row in result.requests.values() if row.request.intent == "empty_transfer"]


def test_same_owner_reposition_physically_serves_existing_queue_after_hold():
    world = LocalDispatchClock(scene(), local_dispatch=True, controllers=controllers(True), status_period=1)
    early = world.advance(11)
    moved, = empty_records(early)
    assert moved.owner_committed and moved.request.destination_node == "A2"
    assert moved.request.bag_id is None and moved.request.demand_id == "local"
    assert early.physical.final_trays["t0"].node == "A2"
    assert early.physical.final_trays["t0"].mode == "holding"
    assert "local" not in early.physical.final_snapshot.load_times
    result = world.advance(35)
    assert result.physical.final_snapshot.load_times["local"] == 12
    assert result.physical.completed == {"local": 21}
    assert result.physical.cost_components["empty_distance"] == 3
    assert result.outcome_counts == {"empty_transfer_success": 1, "new_route_success": 1}
    approvals = [row for row in world.participants["west"].local_service_audit if row["accepted"]]
    assert approvals and all(row["usable_at"] == 12 for row in approvals)
    assert all(p["target_credit"] == 0 for row in approvals for p in row["prefixes"] if p["tick"] < row["usable_at"])


def test_disabled_new_clock_matches_frozen_controller_and_clock_exactly():
    state = scene(stock=2)
    old = DistributedClock(state, controllers={o: LocalClockController(o, mode="both", period=1) for o in ("west", "east")}, status_period=1)
    new = LocalDispatchClock(state, controllers=controllers(False), local_dispatch=False, status_period=1)
    assert old.advance(25) == new.advance(25)
    assert new.result().physical.uncompleted_bag_ids == ("local",)
    assert not new.result().requests


def test_same_zone_local_service_keeps_original_module_export_floor_semantics():
    world = LocalDispatchClock(scene(floor=1), controllers=controllers(True), local_dispatch=True, status_period=1)
    assert world.advance(35).physical.completed == {"local": 21}


def test_same_owner_cross_zone_local_service_still_requires_export_floor():
    state = scene(local_bag=False, floor=1)
    state.network.nodes["A2"] = replace(state.network.nodes["A2"], logistics_zone="other-zone")
    world = LocalDispatchClock(state, local_dispatch=True, controllers=controllers(True), status_period=1,
        publications=(PublishedDemand("target", "A2", 15, 0, 60),))
    world.submit(ClockRequest("manual-cross-zone", "west", None, "t0", intent="empty_transfer",
                              destination_node="A2", demand_id="target", max_attempts=1))
    result = world.advance(20)
    assert not any(row.owner_committed for row in empty_records(result))
    assert result.physical.final_trays["t0"].node == "A"
    assert result.requests["manual-cross-zone"].outcome == "commit_failure"


def test_earlier_source_requirement_is_not_discarded_to_enable_local_delivery():
    state = scene(local_bag=False)
    world = LocalDispatchClock(state, controllers=controllers(True), local_dispatch=True, status_period=1,
        publications=(PublishedDemand("earlier", "A", 8, 0, 60), PublishedDemand("target", "A2", 15, 0, 60)))
    result = world.advance(12)
    assert not any(row.owner_committed for row in empty_records(result))
    assert result.physical.final_trays["t0"].node == "A"
    assert any(row["event"] == "local_service_probe" and row["reason"] == "local_service_would_degrade_other_prefix"
               for row in world.controllers["west"].trace)


def test_owner_also_enforces_prefix_when_selection_is_bypassed():
    state = scene(local_bag=False)
    world = LocalDispatchClock(state, controllers=controllers(False), local_dispatch=True, status_period=1,
        publications=(PublishedDemand("earlier", "A", 8, 0, 60), PublishedDemand("target", "A2", 15, 0, 60)))
    world.submit(ClockRequest("manual", "west", None, "t0", intent="empty_transfer", destination_node="A2",
                              demand_id="target", max_attempts=1))
    result = world.advance(20)
    assert result.requests["manual"].outcome == "commit_failure"
    assert "local_service_would_degrade_other_prefix" in result.requests["manual"].reason
    assert result.physical.final_trays["t0"].node == "A"


def test_spare_real_stock_can_cover_other_prefix_without_double_counting():
    state = scene(stock=2, local_bag=False)
    world = LocalDispatchClock(state, controllers=controllers(True), local_dispatch=True, status_period=1,
        publications=(PublishedDemand("earlier", "A", 8, 0, 60), PublishedDemand("target", "A2", 15, 0, 60)))
    result = world.advance(18)
    assert sum(row.owner_committed for row in empty_records(result)) == 1
    assert sorted(tray.node for tray in result.physical.final_trays.values()) == ["A", "A2"]
    owner = world.participants["west"]
    assert any(any(p["target_credit"] == 1 for p in row.get("prefixes", [])) for row in owner.local_service_audit)


def test_same_service_prefix_requirement_is_protected_before_target_arrival():
    state = scene(local_bag=False)
    world = LocalDispatchClock(state, controllers=controllers(True), local_dispatch=True, status_period=1,
        publications=(PublishedDemand("same_prefix", "A", 10, 0, 60), PublishedDemand("target", "A2", 10, 0, 60)))
    result = world.advance(12)
    assert not any(row.owner_committed for row in empty_records(result))


def test_target_credit_cannot_hide_other_demand_loss_at_same_service_tick():
    world = LocalDispatchClock(scene(local_bag=False), controllers=controllers(False),
        local_dispatch=True, status_period=1,
        publications=(PublishedDemand("other", "A", 12, 0, 60),
                      PublishedDemand("target", "A2", 12, 0, 60)))
    world.submit(ClockRequest("same-tick", "west", None, "t0", intent="empty_transfer",
        destination_node="A2", demand_id="target", max_attempts=1, departure_lead=5))
    result = world.advance(20)
    assert not result.requests["same-tick"].owner_committed
    assert "local_service_would_degrade_other_prefix" in result.requests["same-tick"].reason
    rows = world.participants["west"].local_service_audit
    assert any(p["target_credit"] == 1 and p["before"] == p["after"] == 1
               and p["other_before"] == 1 and p["other_after"] == 0
               for row in rows for p in row["prefixes"])


@pytest.mark.parametrize("mode, expected_completed", [("reactive", True), ("predictive", False)])
def test_unpublished_actual_local_queue_obeys_original_slow_mode(mode, expected_completed):
    world = LocalDispatchClock(scene(), local_dispatch=True, status_period=1,
        controllers={owner: LocalDispatchController(owner, local_dispatch=True, mode=mode, period=1)
                     for owner in ("west", "east")})
    result = world.advance(35)
    assert ("local" in result.physical.completed) is expected_completed
    assert bool(empty_records(result)) is expected_completed


def test_predictive_local_service_follows_previously_published_unit_into_actual_queue():
    world = LocalDispatchClock(scene(), local_dispatch=True, status_period=1,
        publications=(PublishedDemand("local", "A2", 0, 0, 2),),
        controllers={owner: LocalDispatchController(owner, local_dispatch=True, mode="predictive", period=1)
                     for owner in ("west", "east")})
    result = world.advance(35)
    assert result.physical.completed == {"local": 21}
    assert empty_records(result)[0].request.demand_expires_at is None


def test_unreachable_local_queue_remains_in_task_denominator_and_search_diagnostics():
    world = LocalDispatchClock(scene(reachable=False), controllers=controllers(True), local_dispatch=True, status_period=1)
    result = world.advance(20)
    assert result.physical.uncompleted_bag_ids == ("local",)
    assert result.physical.cost_components["terminal_backlog"] == 1
    assert not result.requests
    assert any(row.get("reason") == "proven_infeasible_static_no_path" for row in world.controllers["west"].trace)


def test_local_service_lost_ack_recovers_one_receipt_and_one_empty_action():
    world = LocalDispatchClock(scene(), controllers=controllers(True), local_dispatch=True, status_period=1,
                              faults=(TransportFault("ACK", drop=True),))
    result = world.advance(40)
    moved, = empty_records(result)
    assert moved.reason == "receipt_recovered" and moved.owner_committed
    assert result.physical.cost_components["empty_distance"] == 3
    assert "local" in result.physical.completed


@pytest.mark.parametrize("pause", [1, 4, 7, 11, 13, 18])
def test_local_opt_in_checkpoint_keeps_service_guard_and_physical_continuation(pause):
    world = LocalDispatchClock(scene(), controllers=controllers(True), local_dispatch=True, status_period=1)
    world.advance(pause)
    clone = LocalDispatchClock.from_checkpoint(world.checkpoint())
    assert clone.local_dispatch
    assert clone.advance(40) == world.advance(40)
    assert clone.participants["west"].local_service_audit == world.participants["west"].local_service_audit


def test_local_permission_does_not_fabricate_a_target_task_or_allow_identity_free_reposition():
    world = LocalDispatchClock(scene(local_bag=False), local_dispatch=True)
    world.submit(ClockRequest("unknown", "west", None, "t0", intent="empty_transfer", destination_node="A2",
                              demand_id="nonexistent", max_attempts=1))
    result = world.advance(20)
    assert result.requests["unknown"].outcome == "commit_failure"
    assert "known_matching_demand" in result.requests["unknown"].reason
    assert not result.physical.final_snapshot.bags
