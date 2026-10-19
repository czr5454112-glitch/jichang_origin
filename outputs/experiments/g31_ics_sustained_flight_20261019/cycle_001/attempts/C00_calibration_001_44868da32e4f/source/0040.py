"""Airport planner seam while preserving the byte-pinned historical controller.

The control loop is an explicit source copy of the registered v3 protocol loop
with only a callable planner and its continuation identity added. Native owner
observations, ProtocolClient submit, immutable retries and delivered ACKs still
use the historical implementation. C00 invokes that old entry point directly.
"""
from __future__ import annotations

import copy
import math
import time
from typing import Any

from .analytic_control import transfer_candidates
from .protocol_control import ProtocolClient, _publish_services, _cooldown_ready

def run_airport_protocol_control(session: Any, owners: list[str], *, horizon: float, control_period: float = .5,
                         predictive: bool = True, command_delay: float = .01, publication_delay: float = .02,
                         retry_period: float = .5, routes: bool = True, forecasts: bool = True,
                         prebalance: bool = True, compact: bool = True, lease_seconds: float = 5., forecast_validity: float = 120.,
                         forecast_refresh_period: float = 60., forecast_change_threshold: float = 1.,
                         rejection_cooldown: float = .2, state: dict | None = None,
                         event_budget: int = 100000, _use_policy_view: bool = True,
                         _use_recent_forecasts: bool = True, planner=None,
                         planner_identity: str | None = None) -> dict:
    """Advance common public ticks, including retries and both real control layers.

    Each call preserves the next unexecuted tick. Native + JSON client/controller
    state must be restored together; JSON alone cannot restore physical state.
    """
    call_started = time.perf_counter()
    if not owners or len(set(owners)) != len(owners):
        raise ValueError("protocol_control:invalid_owners")
    if not all(math.isfinite(v) and v >= 0 for v in (horizon, command_delay, publication_delay, lease_seconds)) or control_period <= 0 or not math.isfinite(control_period):
        raise ValueError("protocol_control:invalid_timing")
    if horizon < session.physical_time:
        raise ValueError("protocol_control:horizon_before_physical_time")
    if not all(math.isfinite(v) and v > 0 for v in (forecast_validity, forecast_refresh_period, forecast_change_threshold, rejection_cooldown)):
        raise ValueError("protocol_control:invalid_lifecycle_period")
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
    choose_transfers = transfer_candidates if planner is None else planner
    current = copy.deepcopy(state) if state is not None else {
        "schema": "g31.protocol_controller_state.v3", "config": config,
        "start": session.physical_time, "next_tick": 0, "published": {}, "routes": {}, "forecasts": {}}
    if current.get("schema") != "g31.protocol_controller_state.v3" or current["config"] != config:
        raise ValueError("protocol_control:state_configuration_mismatch")
    if current.get("control_boundary_complete") is False:
        raise ValueError("protocol_control:partial_tick_resume_not_supported")
    client = ProtocolClient(session, retry_period=retry_period, rejection_cooldown=rejection_cooldown,
        forecast_validity=forecast_validity, state=current.get("client"), _use_policy_view=_use_policy_view,
        _use_recent_forecasts=_use_recent_forecasts)
    records, native_batches = [], []
    trace_sequence = 0

    def advance(target):
        nonlocal trace_sequence
        start_at = session.physical_time
        started = time.perf_counter(); cpu = time.process_time()
        response = session.advance_to(target, max_events=event_budget)
        native_batches.append({"target": target, "status": response["status"],
                               "start_at": start_at, "end_at": session.physical_time, "trace_sequence": trace_sequence,
                               "wall_ms": 1000*(time.perf_counter()-started),
                               "cpu_ms": 1000*(time.process_time()-cpu)})
        trace_sequence += 1
        return response.get("status") == "reached" and response.get("horizon_complete", False)

    complete = True
    # An epsilon must never authorize executing an event after the requested
    # horizon; native time cannot then be rolled back to finish the call.
    while current["start"] + current["next_tick"] * control_period <= horizon:
        target = current["start"] + current["next_tick"] * control_period
        if target < session.physical_time:
            raise ValueError("protocol_control:missed_control_boundary")
        if not advance(target):
            complete = False; break
        started = time.perf_counter()
        refreshed = client.refresh()
        publications, service_actions = [], []
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
            service_actions.extend(_publish_services(client, owner, current, command_delay=command_delay,
                publication_delay=publication_delay, routes=routes, forecasts=forecasts, lease_seconds=lease_seconds,
                forecast_refresh_period=forecast_refresh_period, forecast_change_threshold=forecast_change_threshold))
        preparation_ms = 1000*(time.perf_counter()-started)
        if not advance(target):
            complete = False; break
        decisions = []
        for owner in owners if prebalance else []:
            started = time.perf_counter()
            observation = client._policy_view(owner, compact=compact)
            decision = choose_transfers(observation, predictive=predictive, message_delay=command_delay,
                respect_service_forecasts=forecasts, request_prefix=f"protocol:{current['next_tick']}")
            initial = decision
            attempts = []
            for _ in range(len(initial["intents"])):
                if not decision["intents"]:
                    break
                request_id, reply = client.submit(owner, "transfer", decision["intents"][0])
                attempts.append({"request_id": request_id, "reply": reply})
                if reply.get("status") != "pending":
                    break
                observation = client._policy_view(owner, compact=compact)
                decision = choose_transfers(observation, predictive=predictive, message_delay=command_delay,
                    respect_service_forecasts=forecasts, request_prefix=f"protocol:{current['next_tick']}:residual")
            decisions.append({"owner_id": owner, "decision": initial, "attempts": attempts,
                              "compute_ms": 1000*(time.perf_counter()-started)})
        records.append({"tick": current["next_tick"], "at": target, "refreshed": refreshed, "trace_sequence": trace_sequence,
                        "publications": publications, "service_actions": service_actions,
                        "preparation_compute_ms": preparation_ms, "owner_decisions": decisions})
        trace_sequence += 1
        current["next_tick"] += 1
    if complete:
        complete = advance(horizon)
    # Do not insert a client observation at an arbitrary split horizon: that
    # would alter the controller history relative to uninterrupted execution.
    current["client"] = copy.deepcopy(client.state)
    # result_at itself advances and uses a separate native budget. It must
    # never silently execute the rest of a budget-truncated timestamp.
    result = session.result_at(horizon) if complete else None
    complete = complete and result.get("advance", {}).get("status") == "reached" and result.get("advance", {}).get("horizon_complete", False)
    current["control_boundary_complete"] = complete
    continuation = {"status": "reached" if complete else "budget_exhausted",
                    "requested_horizon": horizon, "physical_time": session.physical_time}
    if result is not None:
        result["control_continuation"] = continuation
    return {"status": "reached" if complete else "budget_exhausted", "result": result,
            "controller_state": current, "control_records": records, "client_calls": client.calls,
            "native_batches": native_batches, "control_continuation": continuation,
            "wall_seconds": time.perf_counter()-call_started,
            "complete_100ms_requirement_certified": False,
            "scope": "actual R1/R2 analytic baseline on public native protocol; no new-method or deployment claim"}

