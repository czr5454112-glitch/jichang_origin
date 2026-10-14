"""Real shared-clock protocol tests, not simulated latency accounting only."""
from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.distributed_clock import (
    ClockRequest, DistributedClock, LocalRoutePlanner, OwnerOutage, TransportFault,
)
from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, Leg, Network, Node, RouteCandidate, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.partition_observation import PartitionObservation
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator


def scene(*, long=4, no_wait=False, bags=1, protected=False):
    nodes = {key: Node(key, key, "west" if key == "A" else "east", capacity=4,
                       can_wait=key != "J" or not no_wait) for key in ("A", "J", "V", "B")}
    edges = (Edge("AJ", "A", "J", long), Edge("JB", "J", "B", 2),
             Edge("JV", "J", "V", 2), Edge("VB", "V", "B", 2))
    tasks = {f"b{i}": Bag(f"b{i}", "A", "B", 0, 70, protected) for i in range(bags)}
    trays = {f"t{i}": Tray(f"t{i}", "A", "loaded", f"b{i}") for i in range(bags)}
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}), trays, tasks,
                    module=FixedLocalModule(unload_ticks=1, hold_by_node={"B": 2}),
                    load_times={bid: 0 for bid in tasks}, replaceable_trays=tuple(trays))


def request(name="r", i=0, **kwargs):
    return ClockRequest(name, "west", f"b{i}", f"t{i}", **kwargs)


def old_route(state, *, wait=0):
    length = state.network.edges["AJ"].travel_time
    legs = (Leg("AJ", 0, length), Leg("JB", length + wait, length + wait + 2))
    end = legs[-1].arrive + 1
    candidate = RouteCandidate("old", "b0", "t0", legs, end, end + 2, state.version, "old")
    assert ExecutionValidator().commit(state, candidate).accepted
    return state


def events(result, kind):
    return [event for event in result.trace if event["event"] == kind]


def test_two_owners_authorize_and_physics_really_moves_while_ack_in_transit():
    world = DistributedClock(scene(long=8), faults=(TransportFault("ACK", delay=8),))
    world.submit(request(timeout_ticks=15))
    middle = world.advance(10)
    assert middle.requests["r"].owner_committed and not middle.requests["r"].acknowledged
    assert middle.physical.final_trays["t0"].mode == "in_transit"
    assert middle.physical.final_trays["t0"].node is None
    assert {event["owner"] for event in events(middle, "owner_revalidation")} == {"west", "east"}
    result = world.advance(25)
    assert result.outcome_counts == {"new_route_success": 1}
    assert result.physical.completed == {"b0": 17}
    assert events(result, "physical_commit")[0]["time"] == 5
    assert result.requests["r"].finished_at == 13


def test_cross_owner_no_wait_chain_is_committed_before_entering():
    world = DistributedClock(scene(no_wait=True))
    world.submit(request())
    result = world.advance(20)
    assert result.physical.completed == {"b0": 13}
    plan = events(result, "physical_commit")[0]["candidate"]
    assert plan["legs"][0]["arrive"] == plan["legs"][1]["depart"]
    assert all(item["tray_positions"]["t0"]["node"] != "J" for item in events(result, "physical_observed"))


class InspectingPlanner(LocalRoutePlanner):
    def plan(self, view, module, req, anchor, attempt, departure_floor=0):
        assert type(view) is PartitionObservation
        assert not hasattr(view, "plans") and not hasattr(view, "pending_arrivals")
        assert all(slot.resource not in {"edge:JB", "node:B", "reception:B"} for slot in view.local_calendars)
        assert not any(b.bag_id == "future" for b in view.local_bags)
        return super().plan(view, module, req, anchor, attempt, departure_floor)


def test_planner_cannot_observe_remote_calendar_or_future_tape():
    world = DistributedClock(scene(), future_bags=(Bag("future", "B", "A", 30, 50),),
                             planner=InspectingPlanner())
    world.submit(request())
    result = world.advance(20)
    assert result.outcome_counts == {"new_route_success": 1}
    assert "future" not in result.physical.final_snapshot.bags


def test_message_delay_misses_real_departure_window_then_replans():
    world = DistributedClock(scene(), faults=(TransportFault("COMMIT", attempt=1, delay=8),), prepare_ttl=20)
    world.submit(request(timeout_ticks=20))
    result = world.advance(40)
    assert result.outcome_counts == {"new_route_success": 1}
    assert result.requests["r"].attempt == 2
    assert any("past" in row["reason"] or "time" in row["reason"] for row in result.requests["r"].failures)
    assert events(result, "physical_commit")[0]["time"] > 10


def test_prepare_expiry_is_not_a_commit_and_attempts_are_bounded():
    world = DistributedClock(scene(), prepare_ttl=1)
    world.submit(request(max_attempts=2))
    result = world.advance(25)
    assert result.outcome_counts == {"commit_failure": 1}
    assert result.requests["r"].attempt == 2
    assert not events(result, "physical_commit")
    assert result.physical.final_trays["t0"].node == "A"
    assert not result.physical.final_snapshot.plans
    assert events(result, "lease_expired")


def test_competing_requests_cannot_double_book_owner_calendar():
    world = DistributedClock(scene(bags=2))
    world.submit(request("one", 0, max_attempts=5))
    world.submit(request("two", 1, max_attempts=5))
    result = world.advance(40)
    assert result.outcome_counts == {"new_route_success": 2}
    assert len(result.physical.completed) == 2
    assert any("local_capacity" in row["reason"] for row in result.requests["two"].failures)
    committed = events(result, "physical_commit")
    intervals = [(event["candidate"]["legs"][0]["depart"], event["candidate"]["legs"][0]["arrive"])
                 for event in committed]
    assert intervals[0][1] <= intervals[1][0]


def test_old_remote_conflict_is_discovered_by_owner_not_planner():
    state = scene()
    state.trays["occupied"] = Tray("occupied", "B")
    state.network.nodes["B"] = replace(state.network.nodes["B"], capacity=1)
    world = DistributedClock(state)
    world.submit(request(max_attempts=2))
    result = world.advance(20)
    assert len(events(result, "local_proposal")) == 2
    assert result.outcome_counts == {"commit_failure": 1}
    rejected = [row for row in events(result, "owner_vote") if not row["vote"]["accepted"]]
    assert all(row["vote"]["owner"] == "east" for row in rejected)
    assert "occupied" not in repr(events(result, "local_proposal"))


def test_lost_ack_receipt_recovery_does_not_double_commit():
    world = DistributedClock(scene(), faults=(TransportFault("ACK", drop=True),))
    world.submit(request())
    result = world.advance(30)
    assert result.outcome_counts == {"new_route_success": 1}
    assert result.requests["r"].reason == "receipt_recovered"
    assert result.requests["r"].receipt_queries == 1
    assert len(events(result, "physical_commit")) == 1


def test_lost_ack_and_receipt_retains_unknown_protocol_outcome_and_offline_commit_fact():
    world = DistributedClock(scene(), faults=(TransportFault("ACK", drop=True), TransportFault("RECEIPT", drop=True)))
    world.submit(request())
    result = world.advance(30)
    assert result.outcome_counts == {"outcome_unknown": 1}
    assert result.requests["r"].owner_committed and not result.requests["r"].acknowledged
    assert result.physical.completed == {"b0": 13}
    assert len(events(result, "physical_commit")) == 1


def test_resolve_before_late_commit_fences_attempt_even_when_negative_reply_is_delayed():
    faults = (TransportFault("COMMIT", delay=8), TransportFault("RECEIPT", delay=3),
              TransportFault("ACK", drop=True))
    world = DistributedClock(scene(), faults=faults, prepare_ttl=30)
    # COMMIT arrives t12, QUERY observes no receipt t11, negative answer t14.
    # The departure at t17 is still legal: this isolates acknowledgement order.
    world.submit(request(departure_lead=15, timeout_ticks=10, max_attempts=1))
    result = world.advance(35)
    assert result.outcome_counts == {"communication_failure": 1}
    assert not result.requests["r"].owner_committed
    assert result.requests["r"].receipt_queries == 1
    assert not events(result, "physical_commit")
    assert events(result, "attempt_fenced")[0]["time"] == 11
    assert events(result, "fenced_commit_rejected")[0]["time"] == 12


def test_resolve_fence_allows_new_attempt_without_old_late_commit_double_admission():
    world = DistributedClock(scene(), faults=(TransportFault("COMMIT", attempt=1, delay=12),), prepare_ttl=30)
    world.submit(request(departure_lead=15, timeout_ticks=10, max_attempts=2))
    result = world.advance(45)
    assert result.outcome_counts == {"new_route_success": 1}
    assert result.requests["r"].attempt == 2
    assert len(events(result, "physical_commit")) == 1
    assert events(result, "fenced_commit_rejected")


def test_duplicate_reordered_messages_are_idempotent():
    faults = (TransportFault("OPEN", duplicate_delays=(0, 11)),
              TransportFault("PREPARE", destination="east", duplicate_delays=(0, 8)),
              TransportFault("VOTE", duplicate_delays=(0, 7)),
              TransportFault("COMMIT", duplicate_delays=(0, 9)),
              TransportFault("ACK", duplicate_delays=(0, 9)))
    world = DistributedClock(scene(), faults=faults)
    req = request()
    world.submit(req)
    world.submit(req)
    result = world.advance(25)
    assert sum(result.outcome_counts.values()) == 1
    assert len(events(result, "physical_commit")) == 1
    assert result.requests["r"].acknowledged
    assert events(result, "late_or_duplicate_ignored")
    with pytest.raises(ValueError, match="identity_conflict"):
        world.submit(replace(req, bag_id="other"))


def test_owner_outage_drops_prepare_then_recovery_retries_with_physics_running():
    state = old_route(scene(long=20))
    world = DistributedClock(state, outages=(OwnerOutage("east", 2, 8),))
    world.submit(request(intent="update_suffix", avoid_edges=("JB",), timeout_ticks=9))
    result = world.advance(40)
    assert result.outcome_counts == {"updated_route_success": 1}
    assert result.requests["r"].attempt == 2
    assert events(result, "owner_unavailable")
    assert any(row["time"] == 5 and row["tray_positions"]["t0"]["mode"] == "in_transit"
               for row in events(result, "physical_observed"))


def test_permanent_owner_failure_is_counted_and_cannot_authorize_remote_capacity():
    world = DistributedClock(scene(), outages=(OwnerOutage("east", 0, 100),))
    world.submit(request(max_attempts=2, timeout_ticks=6))
    result = world.advance(35)
    assert result.outcome_counts == {"owner_failure": 1}
    assert result.requests["r"].attempt == 2
    assert not result.requests["r"].owner_committed
    assert not events(result, "physical_commit")
    assert not any(participant.leases for participant in world.participants.values())


def test_owner_failure_after_votes_blocks_commit_and_preserves_update():
    state = old_route(scene(long=20))
    world = DistributedClock(state, outages=(OwnerOutage("east", 5, 10),))
    world.submit(request(intent="update_suffix", avoid_edges=("JB",), max_attempts=1))
    result = world.advance(30)
    assert result.outcome_counts == {"suffix_update_failed_old_route_kept": 1}
    assert "owner_unavailable" in result.requests["r"].reason
    assert result.physical.completed == {"b0": 23}
    assert not events(result, "physical_commit")


def test_explicit_suffix_update_preserves_long_entered_edge_and_all_old_slots_until_commit():
    state = old_route(scene(long=20))
    world = DistributedClock(state)
    world.submit(request(intent="update_suffix", avoid_edges=("JB",)))
    before = world.advance(4)
    assert before.physical.final_snapshot.plans["t0"] == state.plans["t0"]
    result = world.advance(30)
    assert result.outcome_counts == {"updated_route_success": 1}
    assert result.physical.completed == {"b0": 25}
    entered = [event for event in result.physical.trace if event["event"] == "depart"]
    # Frozen first edge retains its original [0,20) execution, not [commit,20).
    full = events(result, "physical_commit")[0]
    assert full["candidate"]["legs"][0]["edge_id"] == "JV"
    assert not any(e.get("edge_id") == "AJ" and e["time"] > 0 for e in entered)


def test_no_wait_update_freezes_entire_chain_until_safe_anchor():
    state = old_route(scene(long=20, no_wait=True), wait=0)
    world = DistributedClock(state)
    world.submit(request(intent="update_suffix", avoid_edges=("JB",)))
    result = world.advance(30)
    proposal = events(result, "local_proposal")[0]["proposal"]
    assert proposal["anchor"]["node"] == "B"
    assert [leg["edge_id"] for leg in proposal["anchor"]["frozen_legs"]] == ["AJ", "JB"]
    assert result.physical.completed == {"b0": 23}
    assert result.outcome_counts == {"updated_route_success": 1}


def test_late_update_anchor_has_physically_advanced_and_old_route_is_not_rolled_back():
    state = old_route(scene(long=8), wait=5)
    world = DistributedClock(state, faults=(TransportFault("COMMIT", delay=11),), prepare_ttl=30)
    world.submit(request(intent="update_suffix", avoid_edges=("JB",), max_attempts=1, timeout_ticks=25))
    result = world.advance(25)
    assert not events(result, "physical_commit")
    assert result.physical.completed == {"b0": 16}
    assert result.requests["r"].outcome in {"commit_failure", "suffix_update_failed_old_route_kept"}
    assert result.requests["r"].failures


def test_protected_full_plan_is_never_replaceable_but_keep_request_succeeds():
    world = DistributedClock(old_route(scene(long=20, protected=True)))
    world.submit(request("update", intent="update_suffix", max_attempts=1))
    world.submit(request("keep", intent="keep_valid"))
    result = world.advance(30)
    assert result.requests["update"].outcome == "suffix_update_failed_old_route_kept"
    assert "protected" in result.requests["update"].reason
    assert result.requests["keep"].outcome == "still_valid_old_route"
    assert len(events(result, "physical_commit")) == 0
    assert result.physical.completed == {"b0": 23}


def test_wrong_coordinator_cannot_update_an_explicitly_replaceable_tray():
    world = DistributedClock(old_route(scene(long=20)))
    world.submit(replace(request(intent="update_suffix", max_attempts=1), coordinator="east"))
    result = world.advance(30)
    assert result.outcome_counts == {"commit_failure": 1}
    assert result.requests["r"].reason == "coordinator_not_task_control_owner"
    assert not events(result, "local_proposal")
    assert result.physical.completed == {"b0": 23}


@pytest.mark.parametrize("pause", [0, 1, 3, 5, 7, 12, 14, 16])
def test_checkpoint_restores_queue_leases_consumed_faults_and_physical_costs_exactly(pause):
    world = DistributedClock(scene(), faults=(TransportFault("ACK", drop=True),
                                              TransportFault("VOTE", duplicate_delays=(9,))))
    world.submit(request())
    world.advance(pause)
    checkpoint = world.checkpoint()
    restored = DistributedClock.from_checkpoint(checkpoint)
    assert restored.advance(pause) == world.result()
    assert restored.advance(30) == world.advance(30)
    checkpoint.protocol["records"].clear()
    assert restored.records and world.records


def test_statically_disconnected_is_only_sound_infeasible_classification():
    state = scene()
    state.network.edges.clear()
    world = DistributedClock(state)
    world.submit(request(max_attempts=1))
    assert world.advance(8).outcome_counts == {"proven_infeasible": 1}
    bounded = DistributedClock(scene(), planner=LocalRoutePlanner(expansion_limit=1))
    bounded.submit(request(max_attempts=1))
    assert bounded.advance(8).outcome_counts == {"search_exhausted": 1}


class BrokenPlanner:
    def plan(self, *args):
        raise RuntimeError("broken local algorithm")


class OmitOwnerPlanner(LocalRoutePlanner):
    def plan(self, *args):
        proposal, reason = super().plan(*args)
        return replace(proposal, owners=("west",)), reason


@pytest.mark.parametrize("planner", [BrokenPlanner(), OmitOwnerPlanner()])
def test_broken_or_unauthorized_planner_cannot_drop_request_or_bypass_resource_owner(planner):
    world = DistributedClock(scene(), planner=planner)
    world.submit(request())
    result = world.advance(10)
    assert result.outcome_counts == {"local_processing_failure": 1}
    assert not events(result, "physical_commit")
    assert result.physical.final_trays["t0"].node == "A"


@pytest.mark.parametrize("kwargs", [{"max_attempts": True}, {"timeout_ticks": 1.5}, {"departure_lead": -1}])
def test_bad_integer_inputs_rejected_before_admission(kwargs):
    with pytest.raises(ValueError):
        request(**kwargs)
