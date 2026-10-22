"""Airport protocol copy with bounded, timestamp-complete soft stopping.

The control loop retains the historical ProtocolClient, immutable submits,
retries, and delivered ACK handling. Without a triggered deadline its endpoint
order is unchanged. A soft stop occurs after a complete native timestamp and
before the next policy tick, exporting only that actual timestamp.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import math
import time
from typing import Any

from .analytic_control import transfer_candidates
from .protocol_control import (ProtocolClient, _publish_services, _cooldown_ready,
                              _publish_inventory, _post_inventory_return, _recover_failed_empty)

@contextmanager
def _owned_state_failure_guard(current: dict, enabled: bool):
    """A consumed state is unusable after any interrupted controller call."""
    try:
        yield
    except BaseException:
        if enabled:
            current["control_boundary_complete"] = False
        raise


def run_airport_bounded_protocol_control(session: Any, owners: list[str], *, horizon: float, control_period: float = .5,
                         predictive: bool = True, command_delay: float = .01, publication_delay: float = .02,
                         retry_period: float = .5, routes: bool = True, forecasts: bool = True,
                         prebalance: bool = True, compact: bool = True, lease_seconds: float = 5., forecast_validity: float = 120.,
                         forecast_refresh_period: float = 60., forecast_change_threshold: float = 1.,
                         rejection_cooldown: float = .2, state: dict | None = None,
                         event_budget: int = 100000, _use_policy_view: bool = True,
                         _use_recent_forecasts: bool = True, planner=None,
                         planner_identity: str | None = None, soft_deadline: float | None = None,
                         soft_clock=time.monotonic, precommit_observer=None, tick_start_observer=None,
                         inventory_snapshots: bool = False,
                         inventory_snapshot_validity: float = 120.,
                         inventory_snapshot_refresh_period: float = 60.,
                         stock_return: bool = False, stock_return_activate_at: float = 0.,
                         stock_return_selector=None, stock_return_selector_identity: str | None = None,
                         post_decision_observer=None, pre_stock_return_observer=None,
                         actual_only_activate_at: float | None = None,
                         recover_failed_empty: bool = False, _consume_state: bool = False,
                         defer_intermediate_result: bool = False) -> dict:
    """Advance common public ticks, including retries and both real control layers.

    Each call preserves the next unexecuted tick. Native + JSON client/controller
    state must be restored together; JSON alone cannot restore physical state.

    Private ``_consume_state=True`` transfers exclusive ownership of ``state``
    and all nested aliases to this call. Only the returned state may continue;
    an exception poisons the consumed state against partial-tick reuse. No
    histories are pruned. Evaluators must use their separate ``client_state``
    argument for the live client, regardless of ownership mode.

    ``defer_intermediate_result=True`` omits only a successful intermediate
    offline result export. The caller must leave it false at the final horizon.
    Native draining, control state and complete-timestamp checks are unchanged;
    a soft stop still exports its actual completed timestamp. Deferred calls
    carry the last bounded advance receipt instead of materializing history.
    """
    call_started = time.perf_counter()
    if type(_consume_state) is not bool:
        raise ValueError("airport_bounded_protocol:invalid_consume_state")
    if type(defer_intermediate_result) is not bool:
        raise ValueError("airport_bounded_protocol:invalid_defer_intermediate_result")
    if soft_deadline is not None and not math.isfinite(soft_deadline):
        raise ValueError("airport_bounded_protocol:invalid_soft_deadline")
    if tick_start_observer is not None and not callable(tick_start_observer):
        raise ValueError("airport_bounded_protocol:invalid_tick_start_observer")
    if post_decision_observer is not None and not callable(post_decision_observer):
        raise ValueError("airport_bounded_protocol:invalid_post_decision_observer")
    if pre_stock_return_observer is not None and not callable(pre_stock_return_observer):
        raise ValueError("airport_bounded_protocol:invalid_pre_stock_return_observer")
    if ((stock_return_selector is None) != (stock_return_selector_identity is None)
            or (stock_return_selector is not None and (not stock_return
                or not callable(stock_return_selector) or type(stock_return_selector_identity) is not str
                or not stock_return_selector_identity))):
        raise ValueError("protocol_control:explicit_stock_return_selector_identity_required")
    if not owners or len(set(owners)) != len(owners):
        raise ValueError("protocol_control:invalid_owners")
    if not all(math.isfinite(v) and v >= 0 for v in (horizon, command_delay, publication_delay, lease_seconds)) or control_period <= 0 or not math.isfinite(control_period):
        raise ValueError("protocol_control:invalid_timing")
    if horizon < session.physical_time:
        raise ValueError("protocol_control:horizon_before_physical_time")
    if not all(math.isfinite(v) and v > 0 for v in (forecast_validity, forecast_refresh_period, forecast_change_threshold, rejection_cooldown)):
        raise ValueError("protocol_control:invalid_lifecycle_period")
    if (type(inventory_snapshots) is not bool or type(stock_return) is not bool
            or type(recover_failed_empty) is not bool
            or (stock_return and (not inventory_snapshots or not prebalance))):
        raise ValueError("protocol_control:invalid_inventory_phase_configuration")
    if (not math.isfinite(stock_return_activate_at) or stock_return_activate_at < 0
            or (actual_only_activate_at is not None and
                (not math.isfinite(actual_only_activate_at) or actual_only_activate_at < 0))):
        raise ValueError("protocol_control:invalid_inventory_activation_time")
    if inventory_snapshots and (not all(math.isfinite(v) and v > 0 for v in
            (inventory_snapshot_validity, inventory_snapshot_refresh_period))
            or inventory_snapshot_validity <= command_delay + publication_delay):
        raise ValueError("protocol_control:invalid_inventory_snapshot_lifecycle")
    config = {"owners": owners, "control_period": control_period, "predictive": predictive,
              "command_delay": command_delay, "publication_delay": publication_delay,
              "retry_period": retry_period, "routes": routes, "forecasts": forecasts,
              "prebalance": prebalance, "compact": compact, "lease_seconds": lease_seconds,
              "forecast_validity": forecast_validity, "forecast_refresh_period": forecast_refresh_period,
              "forecast_change_threshold": forecast_change_threshold, "rejection_cooldown": rejection_cooldown}
    if (planner is None) != (planner_identity is None) or (planner is not None and
            (not callable(planner) or type(planner_identity) is not str or not planner_identity)):
        raise ValueError("protocol_control:explicit_planner_identity_required")
    # Keep the historical default configuration unchanged. A custom planner
    # sees only the same owner observation and never owns submit/ACK handling.
    if planner is not None:
        config["planner_identity"] = planner_identity
    if stock_return_selector is not None:
        config["stock_return_selector_identity"] = stock_return_selector_identity
        config["post_priority_control_contract"] = "post_priority_continuous_one_new_attempt_per_owner_tick_v1"
    if inventory_snapshots:
        config.update(inventory_snapshots=True, inventory_snapshot_validity=inventory_snapshot_validity,
            inventory_snapshot_refresh_period=inventory_snapshot_refresh_period, stock_return=stock_return)
        if stock_return:
            config["stock_return_activate_at"] = stock_return_activate_at
    if actual_only_activate_at is not None:
        config["actual_only_activate_at"] = actual_only_activate_at
    if recover_failed_empty:
        config["recover_failed_empty"] = True
    choose_transfers = transfer_candidates if planner is None else planner
    current = (state if _consume_state else copy.deepcopy(state)) if state is not None else {
        "schema": "g31.protocol_controller_state.v3", "config": config,
        "start": session.physical_time, "next_tick": 0, "published": {}, "routes": {}, "forecasts": {}}
    if current.get("schema") != "g31.protocol_controller_state.v3" or current["config"] != config:
        raise ValueError("protocol_control:state_configuration_mismatch")
    if current.get("control_boundary_complete") is False:
        raise ValueError("protocol_control:partial_tick_resume_not_supported")
    with _owned_state_failure_guard(current, _consume_state):
        client = ProtocolClient(session, retry_period=retry_period, rejection_cooldown=rejection_cooldown,
            forecast_validity=forecast_validity, state=current.get("client"), _use_policy_view=_use_policy_view,
            _use_recent_forecasts=_use_recent_forecasts, inventory_snapshots=inventory_snapshots,
            _consume_state=_consume_state)
        records, native_batches = [], []
        trace_sequence = 0
        last_advance = None

        def advance(target):
            nonlocal trace_sequence, last_advance
            start_at = session.physical_time
            started = time.perf_counter(); cpu = time.process_time()
            response = session.advance_to(target, max_events=event_budget)
            if defer_intermediate_result:
                last_advance = dict(response)
            native_batches.append({"target": target, "status": response["status"],
                                   "start_at": start_at, "end_at": session.physical_time, "trace_sequence": trace_sequence,
                                   "wall_ms": 1000*(time.perf_counter()-started),
                                   "cpu_ms": 1000*(time.process_time()-cpu),
                                   "processed_events": response.get("processed_events")})
            trace_sequence += 1
            return response.get("status") == "reached" and response.get("horizon_complete", False)

        complete, soft_stopped = True, False
        # An epsilon must never authorize executing an event after the requested
        # horizon; native time cannot then be rolled back to finish the call.
        while current["start"] + current["next_tick"] * control_period <= horizon:
            target = current["start"] + current["next_tick"] * control_period
            if target < session.physical_time:
                raise ValueError("protocol_control:missed_control_boundary")
            if not advance(target):
                complete = False; break
            # This check occurs after a bounded native advance completed the whole
            # timestamp, before any new online publication/refresh/action at this
            # tick. A partial artifact never advances result_at to the old horizon.
            if soft_deadline is not None and soft_clock() >= soft_deadline:
                soft_stopped = True
                break
            # Evaluator-only snapshot of the completed timestamp, before retries
            # or any policy-specific publication at the new control boundary.
            tick_start_evaluator_ms = 0.
            if tick_start_observer is not None:
                evaluator_started = time.perf_counter()
                tick_start_observer(session=session, controller_state=current,
                    client_state=client.state, tick_at=target)
                tick_start_evaluator_ms = 1000*(time.perf_counter()-evaluator_started)
            started = time.perf_counter()
            refreshed = client.refresh()
            actual_only = actual_only_activate_at is not None and target >= actual_only_activate_at
            effective_predictive = False if actual_only else predictive
            effective_forecasts = False if actual_only else forecasts
            publications, service_actions = [], []
            inventory_publications = []
            for owner in owners:
                signature = session.protocol_demand_signature(owner)
                channels = current["published"].setdefault(owner, {})
                for recipient in owners:
                    if recipient == owner:
                        continue
                    old_id = channels.get(recipient)
                    previous = client.state["outbox"].get(old_id)
                    if previous:
                        if not previous["terminal"]:
                            continue
                        ack = previous.get("client_view", {}).get("last_delivered_ack", {})
                        if ack.get("status") == "delivered":
                            # Native captures at source execution, not submission.
                            # Only the actually delivered ACK's immutable capture
                            # can justify suppressing an unchanged publication.
                            captured = ack.get("captured_demand_signature")
                            if captured is None:
                                raise ValueError("protocol_control:captured_demand_signature_required")
                            if captured == signature:
                                continue
                        elif not _cooldown_ready(previous, target):
                            continue
                    request_id, reply = client.submit(owner, "demand", {
                        "target_owner": recipient, "message_delay": command_delay,
                        "publication_delay": publication_delay})
                    channels[recipient] = request_id
                    publications.append({"request_id": request_id, "reply": reply})
                if inventory_snapshots:
                    inventory_publications.extend(_publish_inventory(client, owner, owners, current,
                        now=target, command_delay=command_delay, publication_delay=publication_delay,
                        validity=inventory_snapshot_validity,
                        refresh_period=inventory_snapshot_refresh_period))
                if recover_failed_empty:
                    service_actions.extend(_recover_failed_empty(client, owner, current,
                        now=target, command_delay=command_delay, lease_seconds=lease_seconds))
                service_actions.extend(_publish_services(client, owner, current, command_delay=command_delay,
                    publication_delay=publication_delay, routes=routes, forecasts=effective_forecasts, lease_seconds=lease_seconds,
                    forecast_refresh_period=forecast_refresh_period, forecast_change_threshold=forecast_change_threshold))
            preparation_ms = 1000*(time.perf_counter()-started)
            if not advance(target):
                complete = False; break
            decisions = []
            for owner in owners if prebalance else []:
                started = time.perf_counter()
                observation = client._policy_view(owner, compact=compact)
                decision = choose_transfers(observation, predictive=effective_predictive, message_delay=command_delay,
                    respect_service_forecasts=effective_forecasts, request_prefix=f"protocol:{current['next_tick']}")
                initial = decision
                # Evaluator-only instrumentation, never an input to the actor.
                # Called before any optional batch commitment; it may archive the
                # full replay prefix, but cannot replace the planner's decision.
                evaluator_ms = 0.
                if precommit_observer is not None:
                    evaluator_started = time.perf_counter()
                    precommit_observer(session=session, controller_state=current,
                        client_state=client.state, observation=observation,
                        decision=initial)
                    evaluator_ms = 1000*(time.perf_counter()-evaluator_started)
                attempts = []
                priority_error = False
                for _ in range(len(initial["intents"])):
                    if not decision["intents"]:
                        break
                    callback = getattr(stock_return_selector, "on_priority_submission", None)
                    if callback is None:
                        request_id, reply = client.submit(owner, "transfer", decision["intents"][0])
                    else:
                        joint = current.setdefault("joint_post_priority", {"selector_identity":
                            stock_return_selector_identity, "policy_state": {}, "phase": "priority"})
                        if joint["selector_identity"] != stock_return_selector_identity:
                            raise ValueError("protocol_control:stock_return_selector_state_identity_mismatch")
                        payload = decision["intents"][0]
                        request_id = client.next_id(owner, "transfer")
                        try:
                            request_id, reply = client.submit(owner, "transfer", payload, request_id=request_id)
                        except BaseException as error:
                            callback(policy_state=joint["policy_state"], payload=payload,
                                request_id=request_id, reply=None, exception_type=type(error).__name__)
                            raise
                        callback(policy_state=joint["policy_state"], payload=payload,
                            request_id=request_id, reply=reply, exception_type=None)
                    attempts.append({"request_id": request_id, "reply": reply})
                    if reply.get("status") != "pending":
                        priority_error = True
                        break
                    observation = client._policy_view(owner, compact=compact)
                    decision = choose_transfers(observation, predictive=effective_predictive, message_delay=command_delay,
                        respect_service_forecasts=effective_forecasts, request_prefix=f"protocol:{current['next_tick']}:residual")
                inventory_return = None
                if stock_return and target >= stock_return_activate_at:
                    inventory_return = _post_inventory_return(client, owner, current,
                        compact=compact, command_delay=command_delay, priority_error=priority_error,
                        precommit_observer=precommit_observer,
                        **({"stock_return_selector": stock_return_selector,
                            "stock_return_selector_identity": stock_return_selector_identity,
                            "post_decision_observer": post_decision_observer,
                            "pre_stock_return_observer": pre_stock_return_observer}
                            if stock_return_selector is not None or post_decision_observer is not None
                                or pre_stock_return_observer is not None else {}))
                    evaluator_ms += inventory_return.get("offline_evaluator_ms", 0.)
                decision_record = {"owner_id": owner, "decision": initial, "attempts": attempts,
                                   "compute_ms": 1000*(time.perf_counter()-started) - evaluator_ms}
                if inventory_return is not None:
                    decision_record["inventory_return"] = inventory_return
                if precommit_observer is not None:
                    decision_record["offline_evaluator_ms"] = evaluator_ms
                    decision_record["timing_scope"] = "owner_planning_and_submit_excluding_offline_prefix_archive"
                decisions.append(decision_record)
            records.append({"tick": current["next_tick"], "at": target, "refreshed": refreshed, "trace_sequence": trace_sequence,
                            "publications": publications, "service_actions": service_actions,
                            "preparation_compute_ms": preparation_ms, "owner_decisions": decisions})
            if inventory_snapshots:
                records[-1]["inventory_publications"] = inventory_publications
            if tick_start_observer is not None:
                records[-1]["offline_tick_start_observer_ms"] = tick_start_evaluator_ms
            trace_sequence += 1
            current["next_tick"] += 1
        if complete and not soft_stopped:
            complete = advance(horizon)
        # Do not insert a client observation at an arbitrary split horizon: that
        # would alter the controller history relative to uninterrupted execution.
        current["client"] = client.state if _consume_state else copy.deepcopy(client.state)
        # result_at itself advances and uses a separate native budget. It must
        # never silently execute the rest of a budget-truncated timestamp.
        snapshot_horizon = session.physical_time if soft_stopped else horizon
        # Keep the final real drain above even when exporting is deferred: a
        # submit after an earlier same-timestamp drain can schedule new work.
        # Only its reached + horizon_complete receipt certifies this boundary.
        should_export = complete and (not defer_intermediate_result or soft_stopped)
        result = session.result_at(snapshot_horizon) if should_export else None
        if should_export:
            complete = complete and result.get("advance", {}).get("status") == "reached" and result.get("advance", {}).get("horizon_complete", False)
        current["control_boundary_complete"] = complete
        status = "soft_deadline_reached" if soft_stopped and complete else "reached" if complete else "budget_exhausted"
        continuation = {"status": status, "timestamp_complete": complete,
                        "next_control_tick_pending": soft_stopped,
                        "requested_horizon": horizon, "physical_time": session.physical_time}
        if result is not None:
            result["control_continuation"] = continuation
        output = {"status": status, "result": result,
                "controller_state": current, "control_records": records, "client_calls": client.calls,
                "native_batches": native_batches, "control_continuation": continuation,
                "wall_seconds": time.perf_counter()-call_started,
                "complete_100ms_requirement_certified": False,
                "scope": "actual R1/R2 analytic baseline on public native protocol; no new-method or deployment claim"}
        if defer_intermediate_result:
            output["boundary_advance"] = last_advance
            output["result_export"] = ("exported_soft_stop" if result is not None else
                                       "deferred_complete_boundary" if complete else "not_exported_incomplete")
        if inventory_snapshots:
            output["inventory_snapshot_reads"] = client.inventory_snapshot_reads
        if tick_start_observer is not None:
            output["offline_tick_start_observer_seconds"] = sum(
                r["offline_tick_start_observer_ms"] for r in records) / 1000.
        return output

