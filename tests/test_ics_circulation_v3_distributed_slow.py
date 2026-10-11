"""Slow actions are real owner-authorized transfers on the physical clock."""
from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.distributed_clock import (
    AnchorMessage, ClockRequest, DistributedClock, LocalRoutePlanner, ResourceParticipant, TransportFault,
)
from scripts.experiments.ics_circulation_v3.distributed_slow import LocalClockController, PublishedDemand
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, FixedLocalModule, InFlight, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.partition_observation import observe_partition


def scene(*, stock=2, floor=0, loaded=False):
    nodes = {n: Node(n, n, "west" if n == "A" else "east", capacity=5) for n in ("A", "B")}
    edges = (Edge("AB", "A", "B", 5), Edge("BA", "B", "A", 5))
    bags = {"initial": Bag("initial", "A", "B", 0, 70)} if loaded else {}
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                    {f"t{i}": Tray(f"t{i}", "A") for i in range(stock)}, bags,
                    module=FixedLocalModule(1, {"B": 2}, export_min_stock=floor))


def controllers(mode="both", **kwargs):
    return {owner: LocalClockController(owner, mode=mode, **kwargs) for owner in ("west", "east")}


def transfers(result):
    return [record for record in result.requests.values() if record.request.intent == "empty_transfer"]


def test_empty_request_has_no_bag_and_exact_hold_before_real_fifo_reuse():
    state = scene()
    world = DistributedClock(state, (Bag("future", "B", "A", 12, 50),), controllers=controllers(),
                             publications=(PublishedDemand("future", "B", 12, 0, 60),))
    early = world.advance(15)
    record, = transfers(early)
    assert record.request.bag_id is None and record.request.destination_node == "B"
    assert set(early.physical.final_snapshot.bags) == {"future"}
    # Empty departure 9, arrival 14, hold until 16; arrival is not availability.
    assert early.physical.final_trays[record.request.tray_id].mode == "holding"
    assert "future" not in early.physical.final_snapshot.load_times
    result = world.advance(45)
    assert result.physical.final_snapshot.load_times["future"] == 16
    assert result.physical.completed == {"future": 28}
    assert len(transfers(result)) == 1
    assert result.physical.cost_components["empty_distance"] == 5
    assert sum(result.outcome_counts.values()) == len(result.requests)


def test_export_floor_is_checked_by_physical_owner_after_all_messages():
    world = DistributedClock(scene(stock=1, floor=1))
    world.submit(ClockRequest("empty", "west", None, "t0", intent="empty_transfer", destination_node="B", max_attempts=1))
    result = world.advance(20)
    assert result.outcome_counts == {"commit_failure": 1}
    assert "export" in result.requests["empty"].reason
    assert result.physical.final_trays["t0"].node == "A"


def test_destination_owner_deduplicates_same_named_demand_across_concurrent_transfers():
    world = DistributedClock(scene(stock=2))
    for index in range(2):
        world.submit(ClockRequest(f"e{index}", "west", None, f"t{index}", intent="empty_transfer",
                     destination_node="B", demand_id="unit", max_attempts=1))
    result = world.advance(25)
    assert sum(r.owner_committed for r in transfers(result)) == 1
    assert result.outcome_counts == {"empty_transfer_success": 1, "commit_failure": 1}
    assert any("demand_already" in r.reason for r in transfers(result))


def test_prediction_cannot_be_seen_before_publication_and_delivery():
    world = DistributedClock(scene(), (Bag("future", "B", "A", 30, 65),), controllers=controllers(),
                             publications=(PublishedDemand("future", "B", 30, 9, 70),))
    assert not transfers(world.advance(9))
    assert all(not c.forecasts for c in world.controllers.values())
    assert not transfers(world.advance(10))  # publication sent t9, not delivered until t10 is processed
    world.advance(14)
    assert all(c.trace[0]["time"] >= 10 for c in world.controllers.values() if c.trace and c.trace[0]["event"] == "forecast_received")
    assert transfers(world.result())


def test_overdue_identity_forecast_protects_source_until_observation_not_nominal_time():
    world = DistributedClock(scene(stock=1), (Bag("source", "A", "B", 18, 60),),
        controllers=controllers(mode="predictive"), publications=(
            PublishedDemand("source", "A", 6, 0, 50), PublishedDemand("remote", "B", 12, 0, 50)))
    before = world.advance(18)
    assert not transfers(before)
    assert before.physical.final_trays["t0"].node == "A"
    assert all("source" in row["source_protected_units"] for row in world.controllers["west"].trace
               if row["event"] == "slow_tick" and 6 <= row["time"] < 18)
    result = world.advance(45)
    assert "source" in result.physical.completed


def test_cancelled_prediction_fences_uncommitted_transfer_without_releasing_a_real_plan():
    world = DistributedClock(scene(), controllers=controllers(mode="predictive"), publications=(
        PublishedDemand("ghost", "B", 12, 0, 60), PublishedDemand("ghost", "B", 12, 5, 60, revision=2, cancelled=True)))
    result = world.advance(30)
    assert result.outcome_counts == {"cancelled_before_commit": 1}
    assert not any(r.owner_committed for r in transfers(result))
    assert result.physical.cost_components["empty_distance"] == 0
    assert all(t.node == "A" for t in result.physical.final_trays.values())


def test_prediction_reversal_after_commit_does_not_cancel_authorized_empty_route():
    world = DistributedClock(scene(), controllers=controllers(mode="predictive"), publications=(
        PublishedDemand("ghost", "B", 12, 0, 60), PublishedDemand("ghost", "B", 12, 10, 60, revision=2, cancelled=True)))
    result = world.advance(30)
    accepted = [r for r in transfers(result) if r.owner_committed]
    assert len(accepted) == 1
    assert result.physical.final_trays[accepted[0].request.tray_id].node == "B"
    assert result.physical.cost_components["empty_distance"] == 5
    assert "ghost" not in world.participants["east"].accepted_demands
    assert world.controllers["west"].statuses["east"]["available_empty"].get("B") == 1


def test_loaded_and_empty_paths_compete_on_same_real_edge_without_double_capacity():
    world = DistributedClock(scene(stock=3, loaded=True), (Bag("future", "B", "A", 25, 65),),
                             controllers=controllers(), publications=(PublishedDemand("future", "B", 25, 0, 65),))
    result = world.advance(65)
    commits = [event for event in result.trace if event["event"] == "physical_commit"]
    assert any(event["candidate"]["bag_id"] is None for event in commits)
    assert any(event["candidate"]["bag_id"] == "initial" for event in commits)
    intervals = sorted((leg["depart"], leg["arrive"]) for event in commits
                       for leg in event["candidate"]["legs"] if leg["edge_id"] == "AB")
    assert all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:]))
    assert set(result.physical.completed) == {"initial", "future"}


def test_lost_transfer_ack_does_not_cause_periodic_slow_duplicate():
    world = DistributedClock(scene(stock=3), (Bag("future", "B", "A", 30, 65),),
                             controllers=controllers(mode="predictive"),
                             publications=(PublishedDemand("future", "B", 30, 0, 65),),
                             faults=(TransportFault("ACK", drop=True),))
    result = world.advance(65)
    assert len(transfers(result)) == 1
    assert transfers(result)[0].reason == "receipt_recovered"
    assert "future" in result.physical.completed


def test_out_of_order_forecast_revision_never_resurrects_cancelled_demand():
    world = DistributedClock(scene(), controllers=controllers(mode="predictive"), publications=(
        PublishedDemand("ghost", "B", 12, 0, 60), PublishedDemand("ghost", "B", 12, 2, 60, revision=2, cancelled=True)),
        faults=(TransportFault("DEMAND_FORECAST", destination="west", delay=8),))
    result = world.advance(25)
    assert not transfers(result)
    assert world.controllers["west"].forecasts["ghost"].revision == 2


@pytest.mark.parametrize("pause", [1, 6, 9, 15, 21])
def test_checkpoint_preserves_periods_forecast_publication_claims_and_private_arrivals(pause):
    world = DistributedClock(scene(), (Bag("future", "B", "A", 12, 50),), controllers=controllers(),
                             publications=(PublishedDemand("future", "B", 12, 0, 60),))
    world.advance(pause)
    clone = DistributedClock.from_checkpoint(world.checkpoint())
    assert clone.advance(45) == world.advance(45)
    assert {key: controller.trace for key, controller in clone.controllers.items()} == {
        key: controller.trace for key, controller in world.controllers.items()}


def test_reactive_requires_delivered_actual_waiting_summary_not_forecast():
    world = DistributedClock(scene(), (Bag("future", "B", "A", 12, 60),), controllers=controllers(mode="reactive"),
                             publications=(PublishedDemand("future", "B", 12, 0, 60),))
    assert not transfers(world.advance(12))
    result = world.advance(60)
    first, = transfers(result)
    assert first.submitted_at >= 15
    assert "future" in result.physical.completed


def test_empty_request_schema_rejects_fake_bag_identity():
    with pytest.raises(ValueError, match="bag_id=None"):
        ClockRequest("fake", "west", "fake-bag", "t0", intent="empty_transfer", destination_node="B")


@pytest.mark.parametrize("reverse", [False, True])
def test_same_version_semantic_conflict_blocks_slow_export_independent_of_arrival_order(reverse):
    controller = LocalClockController("west", mode="predictive", period=1)
    publications = [PublishedDemand("same", "A", 10, 0, 30), PublishedDemand("same", "B", 10, 0, 30)]
    for item in publications[::-1] if reverse else publications:
        controller.receive("DEMAND_FORECAST", item, 0)
    state = scene()
    assert controller.step(observe_partition(state, "west"), state.module) == ()
    assert controller.forecast_conflicts == {"same"}
    assert "same" not in controller.forecasts
    # Neither a duplicate nor a lower version resurrects ambiguous content.
    controller.receive("DEMAND_FORECAST", publications[0], 0)
    assert controller.forecast_conflicts == {"same"}
    controller.receive("DEMAND_FORECAST", replace(publications[1], revision=2), 1)
    assert not controller.forecast_conflicts
    assert controller.forecasts["same"].node == "B"


def test_latest_expired_publication_never_falls_back_to_older_active_revision():
    controller = LocalClockController("west", mode="predictive", period=1)
    controller.receive("DEMAND_FORECAST", PublishedDemand("unit", "B", 10, 0, 30), 6)
    controller.receive("DEMAND_FORECAST", PublishedDemand("unit", "B", 10, 0, 5, revision=2), 6)
    state = scene()
    state.now = 6
    assert controller.step(observe_partition(state, "west"), state.module) == ()


def zone_scene(*, unreachable_stock=False):
    nodes = {"A": Node("A", "source_zone", "west"), "A2": Node("A2", "source_zone", "west"),
             "A3": Node("A3", "source_zone", "west"), "B": Node("B", "destination_zone", "east")}
    edges = (Edge("AA2", "A", "A2", 1), Edge("AB", "A", "B", 2), Edge("A3B", "A3", "B", 2))
    trays = {"reachable": Tray("reachable", "A"),
             "second": Tray("second", "A3" if unreachable_stock else "A")}
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}), trays, {})


def test_source_guard_matches_two_trays_to_two_other_node_same_zone_demands():
    state = zone_scene()
    controller = LocalClockController("west", mode="predictive", period=1)
    for unit, node in (("local1", "A2"), ("local2", "A2"), ("remote", "B")):
        controller.receive("DEMAND_FORECAST", PublishedDemand(unit, node, 10, 0, 30), 0)
    assert controller.step(observe_partition(state, "west"), state.module) == ()


def test_inaccessible_regional_tray_does_not_substitute_for_a_needed_reachable_tray():
    state = zone_scene(unreachable_stock=True)
    controller = LocalClockController("west", mode="predictive", period=1)
    for unit, node in (("local1", "A2"), ("remote", "B")):
        controller.receive("DEMAND_FORECAST", PublishedDemand(unit, node, 10, 0, 30), 0)
    requests = controller.step(observe_partition(state, "west"), state.module)
    assert len(requests) == 1
    assert requests[0].tray_id == "second"  # Unneeded A3 stock can reach B, not A2.


def test_old_in_transit_bag_never_becomes_a_false_remote_tray_demand():
    state = scene(stock=0)
    state.now = 1
    state.bags["carried"] = Bag("carried", "A", "B", 0, 40)
    state.trays.update(old=Tray("old", None, "in_transit", "carried"), spare=Tray("spare", "B"))
    state.old_in_transit = (InFlight("old", "AB", 0, 5),)
    world = DistributedClock(state, controllers=controllers(mode="reactive", period=1),
                             message_delay=0, status_period=1)
    result = world.advance(4)
    assert not transfers(result)
    assert result.physical.final_trays["old"].mode == "in_transit"
    assert "carried" in world.participants["west"].seen_loaded_bags
    assert "carried" not in world.participants["west"].waiting_units


def test_completed_initial_bag_is_not_resurrected_as_waiting_by_owner_summary():
    state = scene(stock=0)
    state.now = 7
    state.bags["done"] = Bag("done", "A", "B", 0, 40)
    state.completed["done"] = 6
    state.trays["spare"] = Tray("spare", "B")
    world = DistributedClock(state, controllers=controllers(mode="reactive", period=1),
                             message_delay=0, status_period=1)
    result = world.advance(12)
    assert not transfers(result)
    assert "done" in world.participants["west"].seen_loaded_bags


def test_delivered_claim_cannot_be_exported_away_when_its_forecast_message_was_lost():
    state = scene(stock=0)
    state.network = replace(state.network, edges={e.edge_id: e for e in (Edge("AB", "A", "B", 2), Edge("BA", "B", "A", 2))})
    state.module = FixedLocalModule()
    state.trays.update(t0=Tray("t0", "B"), t1=Tray("t1", "B"))
    world = DistributedClock(state, (Bag("u", "A", "A", 30, 70),), controllers=controllers(mode="predictive"),
        publications=(PublishedDemand("u", "A", 15, 0, 70),
                      PublishedDemand("v1", "B", 25, 10, 70), PublishedDemand("v2", "B", 25, 10, 70),
                      PublishedDemand("v1", "B", 25, 20, 70, revision=2, cancelled=True),
                      PublishedDemand("v2", "B", 25, 20, 70, revision=2, cancelled=True)),
        faults=(TransportFault("DEMAND_FORECAST", destination="west", drop=True),))
    middle = world.advance(25)
    assert middle.physical.final_trays["t0"].node == "A"
    assert world.participants["west"].accepted_demands["u"]["tray_id"] == "t0"
    result = world.advance(50)
    assert "u" in result.physical.completed
    assert "u" not in world.participants["west"].accepted_demands
    assert not any(r.owner_committed and r.request.destination_node == "B" for r in transfers(result))


def test_claim_ttl_is_delivered_with_request_even_when_destination_forecast_is_lost():
    state = scene(stock=0)
    state.trays["t0"] = Tray("t0", "B")
    world = DistributedClock(state, controllers=controllers(mode="predictive"),
        publications=(PublishedDemand("never", "A", 10, 0, 20),),
        faults=(TransportFault("DEMAND_FORECAST", destination="west", drop=True),))
    result = world.advance(25)
    assert any(r.owner_committed for r in transfers(result))
    assert not world.participants["west"].accepted_demands
    assert result.physical.final_trays["t0"].node == "A"


def test_remote_loaded_identity_is_monotonic_after_stock_summary_expires():
    state = scene(stock=0)
    state.trays["t0"] = Tray("t0", "B")
    controller = LocalClockController("east", mode="predictive", period=1, status_max_age=8)
    controller.receive("DEMAND_FORECAST", PublishedDemand("done", "A", 1, 0, 50), 0)
    controller.receive("OWNER_STATUS", {"owner": "west", "observed_tick": 0, "loaded_units": ("done",),
                                       "waiting_units": {}, "available_empty": {}, "accepted_demands": {},
                                       "prepared_demands": ()}, 0)
    assert controller.step(observe_partition(state, "east"), state.module) == ()
    state.now = 10
    assert controller.step(observe_partition(state, "east"), state.module) == ()
    assert "done" in controller.observed_loaded_units


@pytest.mark.parametrize("mode", ["reactive", "predictive", "both"])
def test_actual_waiting_identity_supersedes_expired_cancelled_forecast_and_status_ttl(mode):
    state = scene(stock=0)
    state.now = 12
    state.trays["t0"] = Tray("t0", "B")
    controller = LocalClockController("east", mode=mode, period=1, status_max_age=3)
    controller.receive("DEMAND_FORECAST", PublishedDemand("real", "A", 1, 0, 5, cancelled=True), 0)
    controller.receive("OWNER_STATUS", {"owner": "west", "observed_tick": 1, "loaded_units": (),
                                       "waiting_units": {"real": "A"}, "available_empty": {}, "accepted_demands": {},
                                       "prepared_demands": ()}, 1)
    requests = controller.step(observe_partition(state, "east"), state.module)
    assert len(requests) == 1 and requests[0].demand_id == "real"
    assert requests[0].demand_expires_at is None


def test_observed_waiting_origin_cannot_be_replaced_by_stale_forecast_location():
    state = zone_scene()
    state.trays.pop("second")
    controller = LocalClockController("west", mode="both", period=1)
    controller.receive("TASK_STATE", {"observed_tick": 0, "loaded_units": (), "waiting_units": {"u": "A2"}}, 0)
    controller.receive("DEMAND_FORECAST", PublishedDemand("u", "A3", 5, 0, 40), 0)
    controller.receive("DEMAND_FORECAST", PublishedDemand("remote", "B", 5, 0, 40), 0)
    assert controller.step(observe_partition(state, "west"), state.module) == ()
    assert controller.trace[-1]["source_protected_units"] == ("u",)


@pytest.mark.parametrize("source_information", ["forecast_before_prepare", "forecast_after_prepare", "actual_after_prepare"])
def test_source_owner_rechecks_newly_delivered_demand_before_physical_export(source_information):
    state = zone_scene()
    state.trays.pop("second")
    publications = [PublishedDemand("remote", "B", 15, 0, 50)]
    future = ()
    if source_information == "actual_after_prepare":
        future = (Bag("local", "A2", "B", 4, 50),)
    else:
        published = 2 if source_information == "forecast_before_prepare" else 4
        publications.append(PublishedDemand("local", "A2", 15, published, 50))
    world = DistributedClock(state, future, controllers=controllers(mode="predictive", period=1, departure_lead=8),
                             publications=publications, status_period=1)
    result = world.advance(12)
    assert transfers(result)
    assert not any(record.owner_committed for record in transfers(result))
    assert any("source_prefix_protection_changed" in event.get("reason", "")
               for event in result.trace if event["event"] == "attempt_failed")
    assert result.physical.final_trays["reachable"].node == "A"


def test_source_owner_cannot_use_published_but_still_in_transit_information_retroactively():
    state = zone_scene()
    state.trays.pop("second")
    world = DistributedClock(state, controllers=controllers(mode="predictive", period=1, departure_lead=8), status_period=1,
        publications=(PublishedDemand("remote", "B", 15, 0, 50), PublishedDemand("local", "A2", 15, 4, 50)),
        faults=(TransportFault("DEMAND_FORECAST", destination="west", delay=1),
                TransportFault("DEMAND_FORECAST", destination="west", delay=10)))
    middle = world.advance(8)
    assert any(record.owner_committed for record in transfers(middle))
    assert "local" not in world.participants["west"].demand_publications
    result = world.advance(20)
    assert world.participants["west"].demand_publications["local"].published_at == 4
    assert result.physical.final_trays["reachable"].node == "B"


def test_source_owner_cannot_use_another_named_claim_as_free_backing_stock():
    state = zone_scene()
    view = observe_partition(state, "west")
    owner = ResourceParticipant(view, state.module, source_guard_horizon=20)
    owner.accepted_demands["earlier"] = {"tray_id": "second", "destination_node": "A", "usable_at": 0, "expires_at": 50}
    owner.demand_publication(PublishedDemand("local", "A2", 10, 0, 40))
    req = ClockRequest("remote", "west", None, "reachable", intent="empty_transfer", destination_node="B", demand_id="remote")
    anchor = AnchorMessage("reachable", None, "A", 0, 0, destination_node="B")
    proposal, _ = LocalRoutePlanner().plan(view, state.module, req, anchor, 1)
    vote = owner.prepare(proposal, 8)
    assert not vote.accepted and vote.reason == "source_prefix_protection_changed"
