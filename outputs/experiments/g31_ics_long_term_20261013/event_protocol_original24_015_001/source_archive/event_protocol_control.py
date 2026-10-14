"""Owner-local event activation of the same public analytic R1/R2 policies.

Native G31 alone advances physics and delivers notifications. A notification
activates only its owner; other owners' private events are not polling ticks.
The JSON scheduler keeps complete owner actions and can continue after a
native event-budget cut without observing a partial physical timestamp.
"""
from __future__ import annotations

import copy
import math
import time
from typing import Any

from .analytic_control import transfer_candidates
from .protocol_control import ProtocolClient, _publish_services


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
            elif client.session.physical_time < previous["next_retry"]:
                continue
        request_id, reply = client.submit(owner, "demand", {
            "target_owner": recipient, "message_delay": command_delay,
            "publication_delay": publication_delay})
        channels[recipient] = request_id
        records.append({"request_id": request_id, "reply": reply})
    return records


def _retry_time(client: ProtocolClient) -> float:
    return min((row["next_retry"] for row in client.state["outbox"].values()
                if not row["terminal"]), default=math.inf)


def _activate_owner(client: ProtocolClient, owner: str, current: dict, causes: dict) -> dict:
    config = current["config"]
    started = time.perf_counter(); cpu = time.process_time()
    refreshed = client.refresh(owner_id=owner)
    publications = _publish_owner_demand(client, owner, config["owners"], current,
        config["command_delay"], config["publication_delay"])
    services = _publish_services(client, owner, current, command_delay=config["command_delay"],
        publication_delay=config["publication_delay"], routes=config["routes"],
        forecasts=config["forecasts"], lease_seconds=config["lease_seconds"])
    decision, attempts = None, []
    epoch = current["owner_epochs"].get(owner, 0)
    if config["prebalance"]:
        observation = client.view(owner, compact=config["compact"])
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
            observation = client.view(owner, compact=config["compact"])
            decision = transfer_candidates(observation, predictive=config["predictive"],
                message_delay=config["command_delay"], respect_service_forecasts=config["forecasts"],
                request_prefix=f"event:{owner}:{epoch}:residual")
        decision = initial
    current["owner_epochs"][owner] = epoch + 1
    return {"owner_id": owner, "owner_epoch": epoch, "at": client.session.physical_time,
        "causes": causes, "refreshed": refreshed, "publications": publications,
        "service_actions": services, "decision": decision, "attempts": attempts,
        "compute_wall_ms": 1000*(time.perf_counter()-started),
        "compute_cpu_ms": 1000*(time.process_time()-cpu)}


def run_event_protocol_control(session: Any, owners: list[str], *, horizon: float,
        control_period: float = 60., predictive: bool = True, command_delay: float = 2.,
        publication_delay: float = .5, retry_period: float = 60., routes: bool = True,
        forecasts: bool = True, prebalance: bool = True, compact: bool = True,
        lease_seconds: float = 120., state: dict | None = None, event_budget: int = 100000,
        max_activations: int = 10000) -> dict:
    """Continue actual owner notifications and declared public timers.

    Computation counters and intermediate native budget stops are diagnostic,
    not inputs to an owner policy. JSON state must be paired with the native
    checkpoint. Only completed native timestamps authorize policy activation.
    """
    if not owners or len(set(owners)) != len(owners):
        raise ValueError("event_control:invalid_owners")
    if not all(math.isfinite(v) and v >= 0 for v in (horizon, command_delay, publication_delay, lease_seconds)):
        raise ValueError("event_control:invalid_timing")
    if not all(math.isfinite(v) and v > 0 for v in (control_period, retry_period)):
        raise ValueError("event_control:invalid_period")
    if horizon < session.physical_time or event_budget <= 0 or max_activations <= 0:
        raise ValueError("event_control:invalid_horizon_or_budget")
    config = {"owners": owners, "control_period": control_period, "predictive": predictive,
        "command_delay": command_delay, "publication_delay": publication_delay,
        "retry_period": retry_period, "routes": routes, "forecasts": forecasts,
        "prebalance": prebalance, "compact": compact, "lease_seconds": lease_seconds}
    current = copy.deepcopy(state) if state is not None else {
        "schema": "g31.event_protocol_controller.v1", "config": copy.deepcopy(config),
        "start": session.physical_time, "next_tick": 0, "after_sequences": {o: 0 for o in owners},
        "pending_owners": [], "pending_causes": {}, "owner_epochs": {},
        "published": {}, "routes": {}, "forecasts": {}}
    if current.get("schema") != "g31.event_protocol_controller.v1" or current.get("config") != config:
        raise ValueError("event_control:state_configuration_mismatch")
    client = ProtocolClient(session, retry_period=retry_period, state=current.get("client"))
    records, native_batches = [], []
    status, complete = "running", False
    while True:
        while current["pending_owners"]:
            if len(records) >= max_activations:
                status = "control_budget_exhausted"
                break
            owner = current["pending_owners"][0]
            records.append(_activate_owner(client, owner, current, current["pending_causes"][owner]))
            current["pending_owners"].pop(0)
            del current["pending_causes"][owner]
        if status == "control_budget_exhausted":
            break
        tick_time = current["start"] + current["next_tick"] * control_period
        deadline = min(horizon, tick_time, _retry_time(client))
        if deadline < session.physical_time:
            raise ValueError("event_control:missed_public_timer")
        started = time.perf_counter(); cpu = time.process_time()
        response = session.advance_until_owner_notification(
            owners, current["after_sequences"], deadline, max_events=event_budget)
        native_batches.append({"requested_public_deadline": deadline, "status": response["status"],
            "timestamp_complete": response.get("timestamp_complete", False),
            "wall_ms": 1000*(time.perf_counter()-started), "cpu_ms": 1000*(time.process_time()-cpu)})
        if response["status"] == "budget_exhausted":
            status = "native_budget_exhausted"
            break
        if response["status"] not in {"notified", "horizon_reached"} or not response.get("timestamp_complete", False):
            raise ValueError("event_control:invalid_native_notification_boundary")
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
        for row in client.state["outbox"].values():
            if not row["terminal"] and row["next_retry"] <= now:
                causes.setdefault(row["payload"]["owner_id"], {})["retry_timer"] = True
        current["pending_owners"] = [owner for owner in owners if owner in causes]
        current["pending_causes"] = causes
        if not causes and response["status"] == "horizon_reached" and now == horizon:
            status, complete = "reached", True
            break
    current["client"] = copy.deepcopy(client.state)
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
        "control_continuation": continuation, "complete_100ms_requirement_certified": False,
        "scope": "same public analytic policies with lawful owner notifications; not new-method or deployment certification"}
