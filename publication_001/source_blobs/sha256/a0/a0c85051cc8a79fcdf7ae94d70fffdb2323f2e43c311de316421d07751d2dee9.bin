"""Owner-local event activation of the same public analytic R1/R2 policies.

Native G31 alone advances physics and delivers notifications. A notification
activates only its owner; other owners' private events are not polling ticks.
The JSON scheduler keeps complete owner actions and can continue after a
native event-budget cut without observing a partial physical timestamp.
"""
from __future__ import annotations

import copy
import heapq
import math
import time
from typing import Any

from .analytic_control import transfer_candidates
from .protocol_control import ProtocolClient, _publish_services, _cooldown_ready, _request_status


def _publish_owner_demand(client: ProtocolClient, owner: str, owners: list[str], state: dict,
                          command_delay: float, publication_delay: float) -> list[dict]:
    signature = client.session.protocol_demand_signature(owner)
    channels = state["published"].setdefault(owner, {})
    records = []
    for recipient in owners:
        if recipient == owner:
            continue
        previous = client.state["outbox"].get(channels.get(recipient))
        if previous:
            if not previous["terminal"]:
                continue
            ack = previous.get("client_view", {}).get("last_delivered_ack", {})
            if ack.get("status") == "delivered":
                captured = ack.get("captured_demand_signature")
                if captured is None:
                    raise ValueError("event_control:captured_demand_signature_required")
                if captured == signature:
                    continue
            elif not _cooldown_ready(previous, client.session.physical_time):
                continue
        request_id, reply = client.submit(owner, "demand", {
            "target_owner": recipient, "message_delay": command_delay,
            "publication_delay": publication_delay})
        channels[recipient] = request_id
        records.append({"request_id": request_id, "reply": reply})
    return records


def _retry_time(client: ProtocolClient) -> float:
    """Transport retries and one-shot rejection cooldown are different clocks."""
    return min((row["next_retry"] if not row["terminal"] else row.get("cooldown_until", math.inf)
                for row in client.state["outbox"].values() if not row.get("cooldown_consumed")), default=math.inf)


def _sync_owner_timers(client: ProtocolClient, owner: str, current: dict) -> None:
    desired = {}
    for request_id, row in client._active_rows(owner):
        if not row["terminal"]:
            desired["retry:" + request_id] = (row["next_retry"], "transport_retry")
        elif "cooldown_until" in row and not row.get("cooldown_consumed"):
            desired["cooldown:" + request_id] = (row["cooldown_until"], "rejection_cooldown")
    for key, row in current.get("active_routes", {}).items():
        original = client.state["outbox"][row["request_id"]]
        if row.get("owner") == owner and original["terminal"] and _request_status(original) == "updated":
            desired["route:" + key] = (original["payload"]["expiry"], "route_lease")
    for key, row in current["forecasts"].items():
        if row["owner"] != owner or row.get("retired_without_publication"):
            continue
        if row.get("withdrawn"):
            if "replace_at" in row:
                desired["replace:" + key] = (row["replace_at"], "forecast_replacement")
        elif not row.get("retire_reason"):
            desired["refresh:" + key] = (min(row["refresh_at"], row["valid_until"]), "forecast_refresh_or_expiry")
    for identity, deadline in current.get("forecast_expirations", {}).get(owner, {}).items():
        desired["received:" + owner + ":" + identity] = (deadline, "received_forecast_expiry")
    live = current.setdefault("timer_live", {})
    generations = current.setdefault("timer_generations", {})
    heap = current.setdefault("timer_heap", [])
    for key in list(live):
        if live[key][2] == owner and key not in desired:
            del live[key]
    for key, (deadline, kind) in desired.items():
        if key in live and live[key][0] == deadline:
            continue
        generation = generations.get(key, 0) + 1
        generations[key] = generation
        live[key] = [deadline, generation, owner, kind]
        heapq.heappush(heap, [deadline, key, generation, owner, kind])
    if len(heap) > max(32, 2*len(live)):
        heap[:] = [[row[0], key, *row[1:]] for key, row in live.items()]
        heapq.heapify(heap)


def _timer_time(current: dict) -> float:
    heap, live = current.setdefault("timer_heap", []), current.setdefault("timer_live", {})
    while heap and live.get(heap[0][1]) != [heap[0][0], *heap[0][2:]]:
        heapq.heappop(heap)
    return heap[0][0] if heap else math.inf


def _due_timers(current: dict, now: float) -> dict:
    causes = {}
    while _timer_time(current) <= now:
        deadline, key, generation, owner, kind = heapq.heappop(current["timer_heap"])
        del current["timer_live"][key]
        causes.setdefault(owner, []).append({"kind": kind, "key": key, "generation": generation, "deadline": deadline})
    return causes


def _activate_owner(client: ProtocolClient, owner: str, current: dict, causes: dict, *,
                    reuse_service_observation: bool = True) -> dict:
    config = current["config"]
    started = time.perf_counter(); cpu = time.process_time()
    refreshed = client.refresh(owner_id=owner)
    publications = _publish_owner_demand(client, owner, config["owners"], current,
        config["command_delay"], config["publication_delay"])
    service_observation = client._policy_view(owner)
    submissions_before_services = len(client.calls)
    services = _publish_services(client, owner, current, command_delay=config["command_delay"],
        publication_delay=config["publication_delay"], routes=config["routes"],
        forecasts=config["forecasts"], lease_seconds=config["lease_seconds"],
        forecast_refresh_period=config["forecast_refresh_period"],
        forecast_change_threshold=config["forecast_change_threshold"], observation=service_observation)
    decision, attempts = None, []
    observation_reused = False
    epoch = current["owner_epochs"].get(owner, 0)
    if config["prebalance"]:
        # Both consumers only read this activation-local snapshot. Reuse is
        # invalid after even a rejected submit because the client ledger may
        # change. It never escapes as a public cached view, crosses a native
        # drain, or introduces aliases between separate client.view calls.
        observation_reused = (reuse_service_observation and config["compact"] and
                              len(client.calls) == submissions_before_services)
        observation = service_observation if observation_reused else client._policy_view(owner, compact=config["compact"])
        decision = transfer_candidates(observation, predictive=config["predictive"],
            message_delay=config["command_delay"], respect_service_forecasts=config["forecasts"],
            request_prefix=f"event:{owner}:{epoch}")
        initial = decision
        for _ in range(len(initial["intents"])):
            if not decision["intents"]:
                break
            request_id, reply = client.submit(owner, "transfer", decision["intents"][0])
            attempts.append({"request_id": request_id, "reply": reply})
            if reply.get("status") != "pending":
                break
            observation = client._policy_view(owner, compact=config["compact"])
            decision = transfer_candidates(observation, predictive=config["predictive"],
                message_delay=config["command_delay"], respect_service_forecasts=config["forecasts"],
                request_prefix=f"event:{owner}:{epoch}:residual")
        decision = initial
    _sync_owner_timers(client, owner, current)
    current["owner_epochs"][owner] = epoch + 1
    return {"owner_id": owner, "owner_epoch": epoch, "at": client.session.physical_time,
        "causes": causes, "refreshed": refreshed, "publications": publications,
        "observation_reused": observation_reused,
        "service_actions": services, "decision": decision, "attempts": attempts,
        "compute_wall_ms": 1000*(time.perf_counter()-started),
        "compute_cpu_ms": 1000*(time.process_time()-cpu)}


def _bounded_public_deadline(existing, now, callback):
    """A caller-declared public wakeup; no response rewriting or hidden reads."""
    if callback is None:
        return existing
    due = callback(now)
    if due is None:
        return existing
    if type(due) not in (int, float) or not math.isfinite(due) or due < now:
        raise ValueError("event_control:invalid_caller_public_deadline")
    return min(existing, due)


def run_event_protocol_control(session: Any, owners: list[str], *, horizon: float,
        control_period: float = 60., predictive: bool = True, command_delay: float = 2.,
        publication_delay: float = .5, retry_period: float = 60., routes: bool = True,
        forecasts: bool = True, prebalance: bool = True, compact: bool = True,
        lease_seconds: float = 120., forecast_validity: float = 120., forecast_refresh_period: float = 60.,
        forecast_change_threshold: float = 1., rejection_cooldown: float = .2,
        state: dict | None = None, event_budget: int = 100000,
        max_activations: int = 10000, _reuse_service_observation: bool = True,
        _use_active_request_index: bool = True, _use_policy_view: bool = True,
        _use_recent_forecasts: bool = True, _consume_state: bool = False,
        _public_deadline=None) -> dict:
    """Continue actual owner notifications and declared public timers.

    Computation counters and intermediate native budget stops are diagnostic,
    not inputs to an owner policy. JSON state must be paired with the native
    checkpoint. Only completed native timestamps authorize policy activation.
    Private _consume_state transfers exclusive ownership of state to this
    call. Retained aliases are invalid; on failure discard/reconstruct the
    mutated state instead of treating it as a pre-call checkpoint.
    """
    call_started = time.perf_counter()
    if not owners or len(set(owners)) != len(owners):
        raise ValueError("event_control:invalid_owners")
    if not all(math.isfinite(v) and v >= 0 for v in (horizon, command_delay, publication_delay, lease_seconds)):
        raise ValueError("event_control:invalid_timing")
    if not all(math.isfinite(v) and v > 0 for v in (control_period, retry_period, lease_seconds, forecast_validity,
            forecast_refresh_period, forecast_change_threshold, rejection_cooldown)):
        raise ValueError("event_control:invalid_period")
    if horizon < session.physical_time or event_budget <= 0 or max_activations <= 0:
        raise ValueError("event_control:invalid_horizon_or_budget")
    config = {"owners": owners, "control_period": control_period, "predictive": predictive,
        "command_delay": command_delay, "publication_delay": publication_delay,
        "retry_period": retry_period, "routes": routes, "forecasts": forecasts,
        "prebalance": prebalance, "compact": compact, "lease_seconds": lease_seconds,
        "forecast_validity": forecast_validity, "forecast_refresh_period": forecast_refresh_period,
        "forecast_change_threshold": forecast_change_threshold, "rejection_cooldown": rejection_cooldown}
    current = (state if _consume_state else copy.deepcopy(state)) if state is not None else {
        "schema": "g31.event_protocol_controller.v2", "config": copy.deepcopy(config),
        "start": session.physical_time, "next_tick": 0, "after_sequences": {o: 0 for o in owners},
        "pending_owners": [], "pending_causes": {}, "owner_epochs": {},
        "published": {}, "routes": {}, "forecasts": {}, "needs_native_drain": False,
        "timer_heap": [], "timer_live": {}, "timer_generations": {}}
    if current.get("schema") != "g31.event_protocol_controller.v2" or current.get("config") != config:
        raise ValueError("event_control:state_configuration_mismatch")
    client = ProtocolClient(session, retry_period=retry_period, rejection_cooldown=rejection_cooldown,
        forecast_validity=forecast_validity, state=current.get("client"),
        _use_active_request_index=_use_active_request_index, _use_policy_view=_use_policy_view,
        _use_recent_forecasts=_use_recent_forecasts, _consume_state=_consume_state)
    records, native_batches = [], []
    status, complete = "running", False
    trace_sequence = 0
    while True:
        if current["pending_owners"] and not current["needs_native_drain"]:
            if len(records) >= max_activations:
                status = "control_budget_exhausted"
                break
            owner = current["pending_owners"].pop(0)
            cause = current["pending_causes"].pop(owner)
            record = _activate_owner(client, owner, current, cause,
                reuse_service_observation=_reuse_service_observation)
            record["trace_sequence"] = trace_sequence
            trace_sequence += 1
            records.append(record)
            current["needs_native_drain"] = True
            # Preserve a budget cut immediately after an action, including
            # its pending round and zero-delay work, for checkpoint recovery.
            if len(records) >= max_activations and current["pending_owners"]:
                status = "control_budget_exhausted"
                break
            continue
        tick_time = current["start"] + current["next_tick"] * control_period
        deadline = (session.physical_time if current["needs_native_drain"] or current["pending_owners"] else
                    min(horizon, tick_time, _timer_time(current)))
        deadline = _bounded_public_deadline(deadline, session.physical_time, _public_deadline)
        if deadline < session.physical_time:
            raise ValueError("event_control:missed_public_timer")
        start_at = session.physical_time
        started = time.perf_counter(); cpu = time.process_time()
        response = session.advance_until_owner_notification(
            owners, current["after_sequences"], deadline, max_events=event_budget)
        native_batches.append({"requested_public_deadline": deadline, "status": response["status"],
            "start_at": start_at, "end_at": session.physical_time, "trace_sequence": trace_sequence,
            "timestamp_complete": response.get("timestamp_complete", False),
            "wall_ms": 1000*(time.perf_counter()-started), "cpu_ms": 1000*(time.process_time()-cpu)})
        trace_sequence += 1
        if response["status"] == "budget_exhausted":
            status = "native_budget_exhausted"
            break
        if response["status"] not in {"notified", "horizon_reached"} or not response.get("timestamp_complete", False):
            raise ValueError("event_control:invalid_native_notification_boundary")
        current["needs_native_drain"] = False
        now = session.physical_time
        notices = response.get("notifications", {})
        if any(o not in owners for o in notices):
            raise ValueError("event_control:unsubscribed_notification")
        causes = {}
        for owner, notice in notices.items():
            sequence = notice["sequence"]
            if sequence <= current["after_sequences"][owner] or notice["observed_at"] > now:
                raise ValueError("event_control:invalid_notification_identity")
            current["after_sequences"][owner] = sequence
            causes[owner] = {"notification": copy.deepcopy(notice)}
        if tick_time <= now:
            for owner in owners:
                causes.setdefault(owner, {})["periodic_tick"] = current["next_tick"]
            current["next_tick"] += 1
        for owner, timers in _due_timers(current, now).items():
            causes.setdefault(owner, {})["timers"] = timers
        for owner in owners:
            if owner not in causes:
                continue
            if owner not in current["pending_owners"]:
                current["pending_owners"].append(owner)
            previous = current["pending_causes"].setdefault(owner, {})
            for kind, detail in causes[owner].items():
                if kind == "timers":
                    previous.setdefault(kind, []).extend(detail)
                else:
                    previous[kind] = detail
        if not current["pending_owners"] and not causes and response["status"] == "horizon_reached" and now == horizon:
            status, complete = "reached", True
            break
    current["client"] = client.state if _consume_state else copy.deepcopy(client.state)
    # Owner actions can enqueue zero-delay commands after the last complete
    # native boundary. An interrupted submission round is not proof that the
    # current native timestamp is still complete; certify only after draining.
    current["native_timestamp_complete"] = complete
    # This call is safe only after an already verified complete H and no
    # pending owner action. Never execute a diagnostic result on a budget cut.
    result = session.result_at(horizon) if complete else None
    if result is not None and (result["advance"]["status"] != "reached" or not result["advance"]["horizon_complete"]):
        raise ValueError("event_control:verified_horizon_was_not_complete")
    continuation = {"status": status, "requested_horizon": horizon,
        "physical_time": session.physical_time, "scope": "scheduler diagnostic; not an owner policy input"}
    if result is not None:
        result["control_continuation"] = continuation
    return {"status": status, "result": result, "controller_state": current,
        "control_records": records, "client_calls": client.calls, "native_batches": native_batches,
        "control_continuation": continuation, "wall_seconds": time.perf_counter()-call_started,
        "complete_100ms_requirement_certified": False,
        "scope": "same public analytic policies with lawful owner notifications; not new-method or deployment certification"}
