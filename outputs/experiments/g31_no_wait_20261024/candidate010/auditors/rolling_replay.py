"""Independent transaction/event replay for continuous-motion rolling certificates.

Reconstructs resources from routes instead of trusting native reservation totals.
Only explicit atomic exchanges remove future rights; actual arrivals are checked
against the certificate in force at that event. Final-route-only audit is weaker.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math

from .headway_audit import input_ticks, reported_ticks, ticks_per_second
from .future_metadata import audit_future_metadata, merge_future_result


def replay_rolling(rows, bags, profile, rolling_events, *, time_grid_seconds=1e-6,
                   edge_entry_headway_seconds=2.0, horizon=98259.0,
                   max_examples=20, require_nonincreasing_finish=False):
    """Replay source commits, physical arrivals, suffix exchanges and cleanup.

    Resource intervals are half open; all positive endpoint devices are checked.
    Source commit is its physical arrival; every later arrival must be logged.
    Gen 1 is the source certificate; an exchange increments its generation by one.
    ``horizon`` must be the executed simulation horizon, not an unexecuted target.
    Final business/STD and cross-leg EBS accounting remain separate runner gates.
    """
    rows, bags = list(rows), list(bags)
    future = audit_future_metadata(rows, bags, horizon=horizon, time_grid_seconds=time_grid_seconds)
    frequency = ticks_per_second(time_grid_seconds)
    headway = input_ticks(edge_entry_headway_seconds, frequency)
    end_tick = input_ticks(horizon, frequency)
    if headway < 0 or max_examples < 0:
        raise ValueError("invalid headway or example budget")
    canonical = {str(r["segment_id"]): r for r in rows}
    actual = {str(b["segment_id"]): b for b in bags}
    if len(canonical) != len(rows) or len(actual) != len(bags) or canonical.keys() != actual.keys():
        raise ValueError("full canonical segment identity changed")
    service = {int(n["location"]): input_ticks(n["service_time"], frequency)
               for n in profile["nodes"]}
    if any(s not in (0, 2 * frequency) for s in service.values()):
        raise ValueError("positive device service must equal 2 seconds")
    from decimal import Decimal
    travel = {(int(e["start"]), int(e["end"])):
              input_ticks(Decimal(str(e["length"])) / 2, frequency)
              for e in profile["edges"]}
    counts, stats = Counter(), Counter()
    examples = []
    states, reservations = {}, {}
    by_resource = defaultdict(dict)
    seen_ids = set()
    previous_order, previous_time = -1, -math.inf
    actual_commit_sequence = 0

    def violation(reason, sid=None, **details):
        counts[reason] += 1
        if len(examples) < max_examples:
            examples.append(dict(reason=reason, segment_id=sid, **details))

    def integer(value, label):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} must be a nonnegative integer")
        return value

    def rid(value):
        if value is None or value == 0:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("reservation id must be a nonzero integer or string")
        if isinstance(value, int) and value < 0 or value == "":
            raise ValueError("invalid reservation id")
        return str(value)

    def decode_route(raw):
        if not isinstance(raw, list) or not raw:
            raise ValueError("committed route is empty or malformed")
        decoded = []
        for point in raw:
            if not isinstance(point, (list, tuple)) or len(point) != 3:
                raise ValueError("malformed route point")
            node = integer(point[0], "node")
            if node not in service:
                raise ValueError("unknown route node")
            decoded.append((node, reported_ticks(point[1], frequency),
                            reported_ticks(point[2], frequency)))
        return decoded

    def ceil_epoch(tick):
        return ((tick + frequency - 1) // frequency) * frequency

    def validate_route(sid, route):
        row = canonical[sid]
        if route[0][0] != int(row["start"]) or route[-1][0] != int(row["goal"]):
            violation("route_endpoint_mismatch", sid)
        if len({p[0] for p in route}) != len(route):
            violation("cyclic_committed_route", sid)
        for i, (node, arrival, departure) in enumerate(route):
            if departure != arrival + service[node]:
                violation("incorrect_device_through_time", sid, node=node,
                          arrival_ticks=arrival, departure_ticks=departure)
            if i:
                prior = route[i - 1]
                edge = (prior[0], node)
                if edge not in travel:
                    violation("missing_edge", sid, edge=list(edge))
                elif arrival != prior[2] + travel[edge]:
                    violation("internal_wait_or_teleport", sid, node=node,
                              arrival_ticks=arrival, expected_ticks=prior[2] + travel[edge])

    def footprint(route, node_ids, edge_ids, sid):
        if len(node_ids) != len(route) or len(edge_ids) != len(route) - 1:
            raise ValueError("reservation-id arrays do not match route")
        result = {}
        for i, (node, arrival, departure) in enumerate(route):
            identity = node_ids[i]
            if service[node] == 0:
                if identity is not None:
                    raise ValueError("zero-duration node has a reservation id")
                continue
            if identity is None or identity in result:
                raise ValueError("positive-node id missing or duplicated")
            result[identity] = (sid, ("node", node), arrival, departure)
        for i, identity in enumerate(edge_ids):
            if identity is None or identity in result:
                raise ValueError("edge id missing or duplicated")
            edge = ("edge", route[i][0], route[i + 1][0])
            result[identity] = (sid, edge, route[i][2], route[i][2] + headway)
        return result

    def discard(identity):
        old = reservations.pop(identity, None)
        if old is not None:
            by_resource[old[1]].pop(identity, None)

    def publish(new, removed, sid):
        # Validate against the still-live old ledger while ignoring exactly the
        # exchanged future rights. Nothing is deleted before validation finishes.
        removed_set = set(removed)
        for identity, interval in new.items():
            _, resource, start, end = interval
            if identity in reservations and identity not in removed_set:
                if reservations[identity] != interval:
                    violation("retained_reservation_mutated", sid, reservation_id=identity)
                continue
            if identity in seen_ids:
                violation("reservation_id_reused", sid, reservation_id=identity)
            if start == end:
                continue
            for prior_id, prior in by_resource[resource].items():
                if prior_id in removed_set:
                    continue
                if start < prior[3] and prior[2] < end:
                    violation("commit_resource_conflict", sid, resource=list(resource),
                              reservation_id=identity, prior_id=prior_id,
                              prior_segment_id=prior[0], new_ticks=[start, end],
                              prior_ticks=list(prior[2:]))
        for identity in removed:
            discard(identity)
        for identity, interval in new.items():
            if identity not in reservations:
                reservations[identity] = interval
                by_resource[interval[1]][identity] = interval
                seen_ids.add(identity)
                stats["reservations_added"] += 1
        stats["reservations_removed_in_exchange"] += len(removed)

    for event_number, event in enumerate(rolling_events):
        sid = str(event.get("segment_id")) if isinstance(event, dict) else None
        try:
            if not isinstance(event, dict) or sid not in canonical:
                raise ValueError("event has unknown segment or malformed structure")
            order = integer(event["ledger_order"], "ledger_order")
            now = reported_ticks(event["time"], frequency)
            if order <= previous_order:
                violation("ledger_order_not_strictly_increasing", sid, order=order)
            if now < previous_time:
                violation("ledger_time_reversal", sid, time_ticks=now)
            if now > end_tick:
                violation("event_after_executed_horizon", sid, time_ticks=now)
            previous_order, previous_time = max(previous_order, order), max(previous_time, now)
            kind = event["kind"]
            stats[kind + "_events"] += 1
            state = states.get(sid)
            if kind in {"source_commit", "source_reserve", "replace_commit"}:
                route = decode_route(event["committed_route"])
                node_ids = [rid(x) for x in event["node_reservation_ids"]]
                edge_ids = [rid(x) for x in event["edge_reservation_ids"]]
                removed = [rid(x) for x in event["removed_ids"]]
                if None in removed or len(set(removed)) != len(removed):
                    raise ValueError("removed ids are empty or duplicated")
                old_gen = integer(event["old_generation"], "old_generation")
                new_gen = integer(event["new_generation"], "new_generation")
                current = event["current_index"]
                if kind == "source_reserve":
                    if isinstance(current, bool) or current != -1:
                        raise ValueError("source_reserve current_index must be -1")
                else:
                    current = integer(current, "current_index")
                cleanup = reported_ticks(event["resource_cleanup_epoch"], frequency)
                goal_arrival = reported_ticks(event["goal_arrival"], frequency)
                validate_route(sid, route)
                new = footprint(route, node_ids, edge_ids, sid)
                if goal_arrival != route[-1][1]:
                    violation("goal_arrival_metadata_mismatch", sid)
                expected_cleanup = ceil_epoch(max([ceil_epoch(route[-1][1]), route[-1][2]] +
                                                   [p[2] + headway for p in route[:-1]]))
                if cleanup != expected_cleanup:
                    violation("resource_cleanup_epoch_mismatch", sid, supplied_ticks=cleanup,
                              expected_ticks=expected_cleanup)
                if kind in {"source_commit", "source_reserve"}:
                    if state is not None:
                        raise ValueError("duplicate source certificate")
                    is_future = kind == "source_reserve"
                    if old_gen != 0 or new_gen != 1 or current != (-1 if is_future else 0) or removed:
                        violation("invalid_source_transaction", sid)
                    if not is_future and now != route[0][1]:
                        violation("source_commit_not_at_admission", sid)
                    if is_future:
                        if event.get("current_node", "missing") is not None:
                            violation("source_reserve_claims_current_node", sid)
                        if now >= route[0][1]:
                            violation("source_reserve_not_strictly_future", sid)
                        if reported_ticks(event["planned_admission"], frequency) != route[0][1]:
                            violation("source_reserve_admission_metadata_mismatch", sid)
                    if now < input_ticks(canonical[sid]["pass_time"], frequency):
                        violation("source_commit_before_release", sid)
                    state = dict(generation=new_gen, route=route, node_ids=node_ids, edge_ids=edge_ids,
                                 arrived_index=-1 if is_future else 0,
                                 actual_prefix=[] if is_future else [route[0]],
                                 actual_finish=now if len(route) == 1 and not is_future else None,
                                 cleanup_by_generation={}, cleanup_seen=set(), cleaned=False,
                                 arrival_order=None if is_future else order,
                                 future_reserved=is_future, launched=not is_future,
                                 reservation_order=order if is_future else None,
                                 reservation_time=now if is_future else None,
                                 initial_route=list(route), initial_node_ids=list(node_ids),
                                 initial_edge_ids=list(edge_ids), initial_cleanup=cleanup)
                    if not is_future:
                        actual_commit_sequence += 1
                        state["actual_commit_order"] = actual_commit_sequence
                    states[sid] = state
                else:
                    if state is None or state["cleaned"] or not state["launched"]:
                        raise ValueError("replacement without live source certificate")
                    if old_gen != state["generation"] or new_gen != old_gen + 1:
                        violation("replacement_generation_mismatch", sid)
                    if require_nonincreasing_finish and route[-1][1] > state["route"][-1][1]:
                        violation("replacement_extends_finish_against_policy", sid)
                    if (current != state["arrived_index"] or current <= 0
                            or current >= len(state["route"]) - 1):
                        raise ValueError("replacement is not at a current internal arrival")
                    if now != state["route"][current][1]:
                        violation("replacement_not_at_exact_current_arrival", sid)
                    if route[:current + 1] != state["route"][:current + 1]:
                        violation("executed_prefix_mutated", sid)
                    if (node_ids[:current + 1] != state["node_ids"][:current + 1]
                            or edge_ids[:current] != state["edge_ids"][:current]):
                        violation("executed_prefix_reservation_ids_mutated", sid)
                    expected_removed = set(x for x in state["node_ids"][current + 1:] if x is not None)
                    expected_removed.update(state["edge_ids"][current:])
                    if set(removed) != expected_removed:
                        violation("replacement_removes_wrong_rights", sid,
                                  expected_ids=sorted(expected_removed), actual_ids=sorted(removed))
                    for identity in removed:
                        if identity not in reservations or reservations[identity][0] != sid:
                            violation("removal_of_missing_or_other_owner_right", sid, reservation_id=identity)
                    # All suffix IDs must be fresh; retained prefix IDs remain.
                    new_suffix = set(x for x in node_ids[current + 1:] if x is not None)
                    new_suffix.update(edge_ids[current:])
                    if new_suffix & seen_ids:
                        violation("replacement_suffix_reuses_old_id", sid)
                    # Legacy next_commit counts rolling exchanges but the bag's
                    # commit_order remains the ordinal of its actual admission.
                    actual_commit_sequence += 1
                publish(new, removed, sid)
                state.update(generation=new_gen, route=route, node_ids=node_ids, edge_ids=edge_ids,
                             cleanup=cleanup)
                state["cleanup_by_generation"][new_gen] = cleanup
            elif kind == "source_launch":
                if (state is None or state["cleaned"] or not state["future_reserved"]
                        or state["launched"]):
                    raise ValueError("source launch without a pending future certificate")
                generation = integer(event["generation"], "generation")
                index = integer(event["index"], "index")
                node = integer(event["node"], "node")
                reference = integer(event["reference_reservation_order"], "reference_reservation_order")
                if generation != 1 or generation != state["generation"]:
                    violation("source_launch_generation_mismatch", sid)
                if reference != state["reservation_order"]:
                    violation("source_launch_wrong_reservation_reference", sid)
                if index != 0 or node != state["route"][0][0] or now != state["route"][0][1]:
                    violation("source_launch_not_at_reserved_source_time", sid)
                if any(event.get(k) for k in ("removed_ids", "node_reservation_ids", "edge_reservation_ids", "committed_route")):
                    violation("source_launch_attempts_resource_mutation", sid)
                expected_rights = footprint(state["route"], state["node_ids"], state["edge_ids"], sid)
                if any(reservations.get(identity) != interval for identity, interval in expected_rights.items()):
                    violation("source_launch_rights_missing_or_mutated", sid)
                state.update(launched=True, arrived_index=0, actual_prefix=[state["route"][0]],
                             actual_finish=now if len(state["route"]) == 1 else None,
                             arrival_order=order)
                actual_commit_sequence += 1
                state["actual_commit_order"] = actual_commit_sequence
            elif kind == "arrival":
                if state is None or state["cleaned"] or not state["launched"]:
                    raise ValueError("arrival without live certificate")
                generation = integer(event["generation"], "generation")
                index = integer(event["index"], "index")
                node = integer(event["node"], "node")
                if generation != state["generation"]:
                    violation("arrival_uses_stale_generation", sid)
                if index != state["arrived_index"] + 1 or index >= len(state["route"]):
                    raise ValueError("arrival skipped, duplicated or outside certificate")
                expected = state["route"][index]
                if node != expected[0] or now != expected[1]:
                    violation("arrival_not_on_current_certificate", sid, index=index,
                              actual_node=node, actual_ticks=now,
                              expected_node=expected[0], expected_ticks=expected[1])
                state["arrived_index"] = index
                state["actual_prefix"].append((node, now, now + service[node]))
                state["arrival_order"] = order
                if index == len(state["route"]) - 1:
                    state["actual_finish"] = now
            elif kind == "cleanup":
                if state is None:
                    raise ValueError("cleanup without source certificate")
                generation = integer(event["event_generation"], "event_generation")
                current_gen = integer(event["current_generation"], "current_generation")
                valid = event["valid"]
                removed = [rid(x) for x in event["removed_ids"]]
                if not isinstance(valid, bool):
                    raise ValueError("cleanup valid must be boolean")
                if generation not in state["cleanup_by_generation"]:
                    violation("cleanup_unknown_generation", sid)
                elif now != state["cleanup_by_generation"][generation]:
                    violation("cleanup_at_wrong_time", sid)
                if generation in state["cleanup_seen"]:
                    violation("duplicate_cleanup_event", sid)
                state["cleanup_seen"].add(generation)
                if current_gen != state["generation"]:
                    violation("cleanup_current_generation_mismatch", sid)
                expected_valid = generation == state["generation"] and not state["cleaned"]
                if valid != expected_valid:
                    violation("cleanup_validity_mismatch", sid)
                if not valid:
                    if removed:
                        violation("stale_cleanup_removed_rights", sid)
                    continue
                expected_ids = set(x for x in state["node_ids"] if x is not None)
                expected_ids.update(state["edge_ids"])
                if set(removed) != expected_ids or len(removed) != len(expected_ids):
                    violation("cleanup_removes_wrong_rights", sid)
                if state["actual_finish"] is None:
                    violation("resource_cleaned_before_actual_goal", sid)
                for identity in removed:
                    if identity not in reservations or reservations[identity][0] != sid:
                        violation("cleanup_of_missing_or_other_owner_right", sid, reservation_id=identity)
                    discard(identity)
                state["cleaned"] = True
            else:
                raise ValueError("unknown rolling event kind")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            violation("malformed_or_inconsistent_event", sid, event_number=event_number, detail=str(exc))

    for sid, bag in actual.items():
        state = states.get(sid)
        planned = bool(bag.get("route"))
        if planned != (state is not None and state["launched"]):
            violation("final_admission_transaction_mismatch", sid)
            continue
        if state is None:
            if bag.get("future_reserved") is True:
                violation("future_metadata_without_reservation_transaction", sid)
            continue
        try:
            if bool(bag.get("future_reserved", False)) != state["future_reserved"]:
                violation("future_reservation_flag_not_backed_by_transaction", sid)
            if state["future_reserved"]:
                if bag.get("future_pending") != (not state["launched"]):
                    violation("future_pending_flag_not_backed_by_launch", sid)
                if bag.get("reservation_order") != state["reservation_order"]:
                    violation("final_reservation_order_mismatch", sid)
                for field, expected in (("reservation_time", state["reservation_time"]),
                                        ("planned_admission", state["initial_route"][0][1]),
                                        ("planned_finish", state["initial_route"][-1][1]),
                                        ("planned_resource_cleanup_epoch", state["initial_cleanup"])):
                    if reported_ticks(bag[field], frequency) != expected:
                        violation("initial_reservation_clock_mutated", sid, field=field)
                if decode_route(bag["reserved_route"]) != state["initial_route"]:
                    violation("initial_reserved_route_mutated", sid)
                for field, expected in (("reserved_node_reservation_ids", state["initial_node_ids"]),
                                        ("reserved_edge_reservation_ids", state["initial_edge_ids"])):
                    if [rid(x) for x in bag[field]] != expected:
                        violation("initial_reserved_ids_mutated", sid, field=field)
            if not state["launched"]:
                if state["route"][0][1] <= end_tick:
                    violation("missing_due_source_launch", sid)
                if state["arrived_index"] != -1 or state["actual_prefix"] or state["actual_finish"] is not None:
                    violation("pending_certificate_has_physical_progress", sid)
                if state["cleaned"]:
                    violation("pending_certificate_already_cleaned", sid)
                continue
            final_route = decode_route(bag["route"])
            if "commit_order" in bag and bag["commit_order"] != state["actual_commit_order"]:
                violation("actual_admission_commit_order_mismatch", sid,
                          expected=state["actual_commit_order"], actual=bag["commit_order"])
            if final_route != state["route"]:
                violation("final_route_not_latest_certificate", sid)
            if reported_ticks(bag["admission"], frequency) != state["route"][0][1]:
                violation("final_admission_metadata_mismatch", sid)
            if reported_ticks(bag["finish"], frequency) != state["route"][-1][1]:
                violation("final_finish_metadata_mismatch", sid)
            for name, expected in (("route_generation", state["generation"]),
                                   ("actual_arrived_index", state["arrived_index"])):
                if name in bag and bag[name] != expected:
                    violation("final_state_metadata_mismatch", sid, field=name)
            for name, expected in (("node_reservation_ids", state["node_ids"]),
                                   ("edge_reservation_ids", state["edge_ids"])):
                if name in bag and [rid(x) for x in bag[name]] != expected:
                    violation("final_reservation_ids_mismatch", sid, field=name)
            reached = state["actual_finish"] is not None
            if bool(bag.get("completed")) != reached:
                violation("completion_not_backed_by_actual_goal_event", sid)
            if state["actual_prefix"] != state["route"][:state["arrived_index"] + 1]:
                violation("actual_prefix_not_preserved", sid)
            if (state["arrived_index"] + 1 < len(state["route"])
                    and state["route"][state["arrived_index"] + 1][1] <= end_tick):
                violation("missing_due_physical_arrival", sid)
            if state["cleanup"] <= end_tick and not state["cleaned"]:
                violation("missing_due_current_cleanup", sid)
        except (KeyError, ValueError, TypeError) as exc:
            violation("malformed_final_bag", sid, detail=str(exc))
    return merge_future_result(dict(schema="g31.nowait.rolling_transaction_replay.v1", passed=not counts,
                segment_denominator=len(rows), admitted_certificates=sum(s["launched"] for s in states.values()),
                reserved_certificates=sum(s["future_reserved"] for s in states.values()),
                pending_certificates=sum(not s["launched"] for s in states.values()),
                event_count=len(rolling_events), time_grid_seconds=time_grid_seconds,
                require_nonincreasing_finish=require_nonincreasing_finish,
                edge_headway_ticks=headway, executed_horizon_ticks=end_tick,
                violation_count=sum(counts.values()), violation_counts=dict(counts),
                violation_examples=examples, stats=dict(stats),
                current_live_reservations=len(reservations),
                boundary="Replays published serial transactions and actual-arrival records on integer ticks. Future-source reserve publishes rights before launch; launch only activates the existing certificate and cannot publish/remove rights. Initial reserved provenance survives later rolling replacement. Old rights remain until the same atomic replacement publishes new rights. Does not observe unlogged speculative writes, prove asynchronous distributed locking, validate physical geometry, or replace full-population EBS/business accounting."), future)
