"""Public-state R1/R2 controller over native delivered-ACK message endpoints.

The controller owns request identities, immutable payloads, retries and its
control phase. It does not read offline results to make a decision. Physical
time, messages, owner authorization and tray motion remain in the G31 host.
"""
from __future__ import annotations

import copy
import json
import math
import time
from typing import Any

from .analytic_control import transfer_candidates
from .regional_control import decode_route, encode_route, make_route_packet, public_astar


TERMINAL = {"received", "rejected", "cancelled", "failed", "expired", "updated", "delivered", "withdrawn"}


class ProtocolClient:
    """Serializable client outbox. No unacknowledged server truth is inspected."""

    def __init__(self, session: Any, *, retry_period: float = 1., state: dict | None = None):
        if not math.isfinite(retry_period) or retry_period <= 0:
            raise ValueError("protocol_client:invalid_retry_period")
        self.session = session
        self.state = copy.deepcopy(state) if state is not None else {
            "schema": "g31.protocol_client_state.v1", "retry_period": retry_period,
            "sequences": {}, "outbox": {}}
        if self.state.get("schema") != "g31.protocol_client_state.v1" or self.state["retry_period"] != retry_period:
            raise ValueError("protocol_client:state_configuration_mismatch")
        self.calls: list[dict] = []

    def next_id(self, owner: str, kind: str) -> str:
        n = self.state["sequences"].get(owner, 0)
        self.state["sequences"][owner] = n + 1
        return f"live:{len(owner.encode('utf-8'))}:{owner}:{kind}:{n}"

    def _send(self, row: dict, *, retry: bool) -> dict:
        payload = copy.deepcopy(row["payload"])
        started = time.perf_counter()
        reply = (self.session.submit_protocol_transfer(payload) if row["kind"] == "transfer"
                 else self.session.submit_protocol_command(payload))
        self.calls.append({"at": self.session.physical_time, "retry": retry,
                           "kind": row["kind"], "request": payload, "reply": copy.deepcopy(reply),
                           "submit_compute_ms": 1000*(time.perf_counter()-started)})
        row["next_retry"] = self.session.physical_time + self.state["retry_period"]
        row["submission_reply"] = copy.deepcopy(reply)
        if reply.get("status") == "rejected":
            row["terminal"] = True
        return reply

    def submit(self, owner: str, kind: str, payload: dict, *, request_id: str | None = None) -> tuple[str, dict]:
        request = copy.deepcopy(payload)
        # The protocol validates physical/owner dependencies on delivery. The
        # legacy truth-derived owner_version is deliberately unavailable here.
        request.pop("expected_version", None)
        request["request_id"] = request_id if request_id is not None else self.next_id(owner, kind)
        if request["request_id"] in self.state["outbox"]:
            raise ValueError("protocol_client:duplicate_id_use_saved_payload_retry")
        request["owner_id"] = owner
        if kind != "transfer":
            request["kind"] = kind
        row = {"kind": kind, "payload": request, "terminal": False,
               "created_at": self.session.physical_time}
        self.state["outbox"][request["request_id"]] = row
        return request["request_id"], self._send(row, retry=False)

    def refresh(self, *, retry: bool = True) -> list[dict]:
        views = []
        for request_id, row in self.state["outbox"].items():
            if row["terminal"]:
                continue
            owner = row["payload"]["owner_id"]
            view = (self.session.protocol_request(owner, request_id) if row["kind"] == "transfer"
                    else self.session.protocol_command(owner, request_id))
            row["client_view"] = copy.deepcopy(view)
            ack = view.get("last_delivered_ack", {})
            row["terminal"] = ack.get("status") in TERMINAL
            views.append({"request_id": request_id, "kind": row["kind"], "view": copy.deepcopy(view)})
            # acknowledged pending/granted is a snapshot, not final receipt.
            # Poll it with the same immutable payload, never a second order.
            if retry and not row["terminal"] and self.session.physical_time >= row["next_retry"]:
                self._send(row, retry=True)
        return views

    def view(self, owner: str, *, compact: bool = True) -> dict:
        result = (self.session.observe_protocol_control(owner) if compact else self.session.observe_protocol(owner))
        # This ledger is explicitly derived by native from this client's own
        # payloads and delivered ACKs. It must not be the legacy truth ledger.
        result["transfers"] = result["client_transfer_ledger"]
        return result


def route_payload(observation: dict, tray_id: str, *, message_delay: float, lease_seconds: float) -> tuple[dict, str]:
    packet = make_route_packet(observation, tray_id)
    encoded = encode_route(packet)
    decoded = decode_route(encoded)
    return {"business_bag_id": decoded.business_bag_id, "tray_id": tray_id,
            "from": decoded.replaceable_suffix[0], "next": decoded.replaceable_suffix[1],
            "expected_generation": decoded.generation, "expected_traversal": decoded.traversal_id,
            "expiry": observation["now"] + lease_seconds, "message_delay": message_delay}, encoded


def _publish_services(client: ProtocolClient, owner: str, state: dict, *, command_delay: float,
                      publication_delay: float, routes: bool, forecasts: bool, lease_seconds: float) -> list[dict]:
    observation = client.view(owner)
    nodes = {int(row["node"]): row for row in observation["node_contracts"]}
    jobs = {row["business_bag_id"]: row for row in observation.get("jobs", [])}
    alive = set()
    records = []
    for tray in observation.get("trays", []):
        job = jobs.get(tray.get("business_bag_id")) or tray.get("job_contract")
        if not job or tray["mode"] not in ("loading", "loaded") or tray.get("edge_to", -1) >= 0:
            continue
        key = json.dumps([owner, tray["tray_id"], job["business_bag_id"], tray["generation"],
                          tray["traversal_id"], tray["node"]], separators=(",", ":"))
        if routes and tray["mode"] == "loaded" and job.get("allow_suffix_reroute", False):
            try:
                payload, encoded = route_payload(observation, tray["tray_id"], message_delay=command_delay,
                                                 lease_seconds=lease_seconds)
            except ValueError as exc:
                records.append({"kind": "route_not_proposed", "reason": str(exc), "key": key})
            else:
                # Timestamp/expiry alone is not a new routing need. A changed
                # public path/fault readset or a rejected/expired request is.
                route_key = key + ":" + json.dumps([decode_route(encoded).replaceable_suffix,
                    observation.get("known_faults", [])], sort_keys=True, separators=(",", ":"))
                # An old successful ACK is historical evidence, not proof
                # that its route is still installed after a different intent.
                # Serialize this stage's updates until the prior result is
                # known so a late retry cannot reinstall a superseded route.
                active = state.setdefault("active_routes", {}).get(key)
                old_id = (active or {}).get("request_id")
                old_row = client.state["outbox"].get(old_id)
                old_ack = (old_row or {}).get("client_view", {}).get("last_delivered_ack", {})
                accepted_until = (old_row or {}).get("payload", {}).get("expiry", -1.)
                needs_request = (old_row is None or
                    (old_row["terminal"] and ((active or {}).get("route_key") != route_key or
                     old_ack.get("status") != "updated" or observation["now"] >= accepted_until)
                     and observation["now"] >= old_row["next_retry"]))
                if needs_request:
                    request_id, reply = client.submit(owner, "route", payload)
                    state["routes"][route_key] = request_id
                    state["active_routes"][key] = {"route_key": route_key, "request_id": request_id}
                    records.append({"kind": "route", "request_id": request_id, "encoded_route": encoded, "reply": reply})
        if forecasts:
            storage = int(job.get("storage_node", -1))
            goal = storage if storage >= 0 and job.get("storage_released_at", -1) < 0 else int(job["destination"])
            path = public_astar(observation, int(tray["node"]), goal)
            if len(path) < 2:
                continue
            next_node = path[1]
            forecast_key = key + ":" + str(next_node)
            alive.add(forecast_key)
            old = state["forecasts"].get(forecast_key)
            old_request = client.state["outbox"].get((old or {}).get("request_id"))
            old_ack = (old_request or {}).get("client_view", {}).get("last_delivered_ack", {})
            withdrew = client.state["outbox"].get((old or {}).get("withdraw_request_id"))
            withdraw_ack = (withdrew or {}).get("client_view", {}).get("last_delivered_ack", {})
            withdrawal_delivered = withdraw_ack.get("status") in {"delivered", "withdrawn", "cancelled"}
            rejected = bool(old_request and old_request["terminal"] and
                (old_ack.get("status") == "rejected" or old_request["submission_reply"].get("status") == "rejected"))
            needs_publication = old is None or old.get("withdrawn") or old.get("retired_without_publication") or withdrawal_delivered or rejected
            if needs_publication and (old_request is None or observation["now"] >= old_request["next_retry"]):
                if old:
                    state.setdefault("forecast_history", []).append(copy.deepcopy(old))
                target = nodes[next_node].get("resource_owner", nodes[next_node]["zone"])
                request_id, reply = client.submit(owner, "service_forecast", {
                    "target_owner": target, "tray_id": tray["tray_id"], "next": next_node,
                    "message_delay": command_delay, "publication_delay": publication_delay})
                state["forecasts"][forecast_key] = {"owner": owner, "request_id": request_id, "withdrawn": False}
                records.append({"kind": "service_forecast", "request_id": request_id, "reply": reply})
    for key, old in state["forecasts"].items():
        if old["owner"] != owner or key in alive or old["withdrawn"] or old.get("retired_without_publication"):
            continue
        original = client.state["outbox"][old["request_id"]]
        original_ack = original.get("client_view", {}).get("last_delivered_ack", {})
        if original["terminal"] and (original["submission_reply"].get("status") == "rejected" or
                (original_ack.get("status") == "rejected" and not original_ack.get("result_id"))):
            old["retired_without_publication"] = True
            continue
        previous = client.state["outbox"].get(old.get("withdraw_request_id"))
        if previous:
            if not previous["terminal"]:
                continue
            ack = previous.get("client_view", {}).get("last_delivered_ack", {})
            if ack.get("status") in {"delivered", "withdrawn", "cancelled"}:
                old["withdrawn"] = True
                continue
            # Rejected before the referenced publication existed is not a
            # withdrawal. Preserve it and try a new intent at a later tick.
            old["withdrawal_failure"] = copy.deepcopy(ack or previous["submission_reply"])
            if observation["now"] < previous["next_retry"]:
                continue
        request_id, reply = client.submit(owner, "withdraw_service_forecast", {
            "forecast_request_id": old["request_id"], "message_delay": command_delay,
            "publication_delay": publication_delay})
        old["withdraw_request_id"] = request_id
        records.append({"kind": "withdraw_service_forecast", "request_id": request_id, "reply": reply})
    return records


def run_protocol_control(session: Any, owners: list[str], *, horizon: float, control_period: float = .5,
                         predictive: bool = True, command_delay: float = .01, publication_delay: float = .02,
                         retry_period: float = .5, routes: bool = True, forecasts: bool = True,
                         prebalance: bool = True, compact: bool = True, lease_seconds: float = 5., state: dict | None = None,
                         event_budget: int = 100000) -> dict:
    """Advance common public ticks, including retries and both real control layers.

    Each call preserves the next unexecuted tick. Native + JSON client/controller
    state must be restored together; JSON alone cannot restore physical state.
    """
    if not owners or len(set(owners)) != len(owners):
        raise ValueError("protocol_control:invalid_owners")
    if not all(math.isfinite(v) and v >= 0 for v in (horizon, command_delay, publication_delay, lease_seconds)) or control_period <= 0 or not math.isfinite(control_period):
        raise ValueError("protocol_control:invalid_timing")
    if horizon < session.physical_time:
        raise ValueError("protocol_control:horizon_before_physical_time")
    config = {"owners": owners, "control_period": control_period, "predictive": predictive,
              "command_delay": command_delay, "publication_delay": publication_delay,
              "retry_period": retry_period, "routes": routes, "forecasts": forecasts,
              "prebalance": prebalance, "compact": compact, "lease_seconds": lease_seconds}
    current = copy.deepcopy(state) if state is not None else {
        "schema": "g31.protocol_controller_state.v2", "config": config,
        "start": session.physical_time, "next_tick": 0, "published": {}, "routes": {}, "forecasts": {}}
    if current.get("schema") != "g31.protocol_controller_state.v2" or current["config"] != config:
        raise ValueError("protocol_control:state_configuration_mismatch")
    if current.get("control_boundary_complete") is False:
        raise ValueError("protocol_control:partial_tick_resume_not_supported")
    client = ProtocolClient(session, retry_period=retry_period, state=current.get("client"))
    records, native_batches = [], []

    def advance(target):
        started = time.perf_counter(); cpu = time.process_time()
        response = session.advance_to(target, max_events=event_budget)
        native_batches.append({"target": target, "status": response["status"],
                               "wall_ms": 1000*(time.perf_counter()-started),
                               "cpu_ms": 1000*(time.process_time()-cpu)})
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
                    elif target < previous["next_retry"]:
                        continue
                request_id, reply = client.submit(owner, "demand", {
                    "target_owner": recipient, "message_delay": command_delay,
                    "publication_delay": publication_delay})
                channels[recipient] = request_id
                publications.append({"request_id": request_id, "reply": reply})
            service_actions.extend(_publish_services(client, owner, current, command_delay=command_delay,
                publication_delay=publication_delay, routes=routes, forecasts=forecasts, lease_seconds=lease_seconds))
        preparation_ms = 1000*(time.perf_counter()-started)
        if not advance(target):
            complete = False; break
        decisions = []
        for owner in owners if prebalance else []:
            started = time.perf_counter()
            observation = client.view(owner, compact=compact)
            decision = transfer_candidates(observation, predictive=predictive, message_delay=command_delay,
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
                observation = client.view(owner, compact=compact)
                decision = transfer_candidates(observation, predictive=predictive, message_delay=command_delay,
                    respect_service_forecasts=forecasts, request_prefix=f"protocol:{current['next_tick']}:residual")
            decisions.append({"owner_id": owner, "decision": initial, "attempts": attempts,
                              "compute_ms": 1000*(time.perf_counter()-started)})
        records.append({"tick": current["next_tick"], "at": target, "refreshed": refreshed,
                        "publications": publications, "service_actions": service_actions,
                        "preparation_compute_ms": preparation_ms, "owner_decisions": decisions})
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
            "complete_100ms_requirement_certified": False,
            "scope": "actual R1/R2 analytic baseline on public native protocol; no new-method or deployment claim"}


def complete_protocol_route(session: Any, owner: str, tray: str, request_id: str, *, command_delay: float = .01,
                            lease_seconds: float = 2., confirmation_window: float = 1.,
                            poll_period: float = .05, retry_period: float = .2, event_budget: int = 100000) -> dict:
    """Charge one whole simulated request, including all intervening native work."""
    if not all(math.isfinite(v) and v >= 0 for v in (command_delay, lease_seconds, confirmation_window)) or poll_period <= 0 or not math.isfinite(poll_period):
        raise ValueError("protocol_route:invalid_timing")
    started = time.perf_counter(); cpu = time.process_time(); begin = session.physical_time
    client = ProtocolClient(session, retry_period=retry_period)
    progress = None
    try:
        payload, encoded = route_payload(client.view(owner), tray, message_delay=command_delay, lease_seconds=lease_seconds)
    except ValueError as exc:
        response = {"status": "rejected", "reason": str(exc)}; encoded = None
    else:
        request_id, response = client.submit(owner, "route", payload, request_id=request_id)
        tick = 0
        while response["status"] == "pending":
            target = min(begin + confirmation_window, begin + tick*poll_period)
            progress = session.advance_to(target, max_events=event_budget)
            if progress["status"] != "reached" or not progress.get("horizon_complete", False):
                response = {"status": "timeout_unknown", "reason": "native_budget_exhausted"}; break
            client.refresh()
            known = client.state["outbox"][request_id]
            ack = known.get("client_view", {}).get("last_delivered_ack")
            if ack and ack["status"] in TERMINAL:
                response = copy.deepcopy(ack); break
            if target >= begin + confirmation_window:
                response = {"status": "timeout_unknown", "reason": "no_terminal_delivered_ack_in_public_window"}; break
            tick += 1
    response = json.loads(json.dumps(response, allow_nan=False))
    wall = 1000*(time.perf_counter()-started)
    return {"request_id": request_id, "encoded_route": encoded, "response": response, "advance": progress,
            "client_state": client.state, "client_calls": client.calls,
            "compute_wall_ms": wall, "compute_cpu_ms": 1000*(time.process_time()-cpu),
            "meets_measured_100ms": wall <= 100., "physical_started_at": begin,
            "physical_finished_at": session.physical_time, "complete_100ms_requirement_certified": False,
            "timing_scope": "observation+conversion+A*+codec+submit+all intervening native events/revalidation/ACK+client retry/response codec; logical wait is simulated, no deployment SLA"}
