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
from .regional_control import decode_route, encode_route, make_route_packet, public_astar, _ObservationRouting


TERMINAL = {"received", "rejected", "cancelled", "failed", "expired", "updated", "delivered", "withdrawn"}


class ProtocolClient:
    """Serializable client outbox. No unacknowledged server truth is inspected."""

    def __init__(self, session: Any, *, retry_period: float = 1., rejection_cooldown: float = .2,
                 forecast_validity: float = 120., state: dict | None = None,
                 _use_active_request_index: bool = True, _use_policy_view: bool = True,
                 _use_recent_forecasts: bool = True, _consume_state: bool = False):
        if not math.isfinite(retry_period) or retry_period <= 0:
            raise ValueError("protocol_client:invalid_retry_period")
        if not all(math.isfinite(v) and v > 0 for v in (rejection_cooldown, forecast_validity)):
            raise ValueError("protocol_client:invalid_lifecycle_period")
        self.session = session
        # Private ownership transfer: callers must relinquish all state aliases.
        # After an exception this owned state may be partially mutated.
        self.state = (state if _consume_state else copy.deepcopy(state)) if state is not None else {
            "schema": "g31.protocol_client_state.v1", "retry_period": retry_period,
            "rejection_cooldown": rejection_cooldown, "forecast_validity": forecast_validity,
            "sequences": {}, "outbox": {}}
        if self.state.get("schema") != "g31.protocol_client_state.v1" or self.state["retry_period"] != retry_period:
            raise ValueError("protocol_client:state_configuration_mismatch")
        for key, value in (("rejection_cooldown", rejection_cooldown), ("forecast_validity", forecast_validity)):
            if self.state.setdefault(key, value) != value:
                raise ValueError("protocol_client:state_configuration_mismatch")
        self.calls: list[dict] = []
        self._use_policy_view = _use_policy_view
        self._use_recent_forecasts = _use_recent_forecasts
        # Derived iteration indexes only: the full insertion-ordered outbox is
        # still the checkpoint and audit history. Rebuild after JSON/native
        # restore, and never include this runtime optimization in policy state.
        self._use_active_request_index = _use_active_request_index
        self._active_requests: dict[str, None] = {}
        self._owner_active_requests: dict[str, dict[str, None]] = {}
        for request_id, row in self.state["outbox"].items():
            self._index_request(request_id, row)

    def _index_request(self, request_id: str, row: dict) -> None:
        if not self._use_active_request_index:
            return
        owner = row["payload"]["owner_id"]
        active = not row["terminal"] or ("cooldown_until" in row and not row.get("cooldown_consumed"))
        if active:
            self._active_requests.setdefault(request_id, None)
            self._owner_active_requests.setdefault(owner, {}).setdefault(request_id, None)
        else:
            self._active_requests.pop(request_id, None)
            self._owner_active_requests.get(owner, {}).pop(request_id, None)

    def _active_rows(self, owner_id: str | None = None):
        if not self._use_active_request_index:
            for request_id, row in self.state["outbox"].items():
                if owner_id is None or row["payload"]["owner_id"] == owner_id:
                    yield request_id, row
            return
        ids = self._active_requests if owner_id is None else self._owner_active_requests.get(owner_id, {})
        # Refresh can retire the current row; snapshot identities rather than
        # copy historical payloads, while preserving original outbox order.
        for request_id in tuple(ids):
            yield request_id, self.state["outbox"][request_id]

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
            row["cooldown_until"] = self.session.physical_time + self.state["rejection_cooldown"]
        self._index_request(payload["request_id"], row)
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

    def refresh(self, *, retry: bool = True, owner_id: str | None = None) -> list[dict]:
        views = []
        for request_id, row in self._active_rows(owner_id):
            if row["terminal"]:
                if self.session.physical_time >= row.get("cooldown_until", math.inf):
                    row["cooldown_consumed"] = True
                self._index_request(request_id, row)
                continue
            owner = row["payload"]["owner_id"]
            view = (self.session.protocol_request(owner, request_id) if row["kind"] == "transfer"
                    else self.session.protocol_command(owner, request_id))
            row["client_view"] = copy.deepcopy(view)
            ack = view.get("last_delivered_ack", {})
            row["terminal"] = ack.get("status") in TERMINAL
            if ack.get("status") in {"rejected", "failed", "expired"}:
                row["cooldown_until"] = ack.get("delivered_at", self.session.physical_time) + self.state["rejection_cooldown"]
                if self.session.physical_time >= row["cooldown_until"]:
                    row["cooldown_consumed"] = True
            views.append({"request_id": request_id, "kind": row["kind"], "view": copy.deepcopy(view)})
            # acknowledged pending/granted is a snapshot, not final receipt.
            # Poll it with the same immutable payload, never a second order.
            if retry and not row["terminal"] and self.session.physical_time >= row["next_retry"]:
                self._send(row, retry=True)
            else:
                self._index_request(request_id, row)
        return views

    def view(self, owner: str, *, compact: bool = True) -> dict:
        result = (self.session.observe_protocol_control(owner) if compact else self.session.observe_protocol(owner))
        return self._annotate_view(result)

    def _policy_view(self, owner: str, *, compact: bool = True) -> dict:
        """Internal policy projection; public views retain their complete history.

        A forwarding proxy must explicitly implement the new endpoint. Merely
        exposing it through __getattr__ could bypass its old compact-view hook.
        Every call still reads a fresh native observation; no view is cached.
        """
        recent = getattr(type(self.session), "observe_protocol_control_policy_recent", None)
        if compact and self._use_policy_view and self._use_recent_forecasts and recent is not None:
            return self._annotate_view(self.session.observe_protocol_control_policy_recent(
                owner, self.state["forecast_validity"]))
        endpoint = getattr(type(self.session), "observe_protocol_control_policy", None)
        if not compact or not self._use_policy_view or endpoint is None:
            return self.view(owner, compact=compact)
        return self._annotate_view(self.session.observe_protocol_control_policy(owner))

    def _annotate_view(self, result: dict) -> dict:
        # This ledger is explicitly derived by native from this client's own
        # payloads and delivered ACKs. It must not be the legacy truth ledger.
        result["transfers"] = result["client_transfer_ledger"]
        # A common controller contract bounds soft-estimate age at receivers.
        # Keep expired identities in the view: filtering them could resurrect
        # an older publication when a newer one has expired or was withdrawn.
        for message in result.get("delivered_messages", []):
            if message.get("kind") == "service_forecast" and message.get("status", "conditional") == "conditional":
                message["valid_until"] = message["observed_at"] + self.state["forecast_validity"]
                if result["now"] >= message["valid_until"]:
                    message["status"] = "expired"
        return result


def route_payload(observation: dict, tray_id: str, *, message_delay: float, lease_seconds: float,
                  _routing: _ObservationRouting | None = None) -> tuple[dict, str]:
    packet = make_route_packet(observation, tray_id, _routing=_routing)
    encoded = encode_route(packet)
    decoded = decode_route(encoded)
    return {"business_bag_id": decoded.business_bag_id, "tray_id": tray_id,
            "from": decoded.replaceable_suffix[0], "next": decoded.replaceable_suffix[1],
            "expected_generation": decoded.generation, "expected_traversal": decoded.traversal_id,
            "expiry": observation["now"] + lease_seconds, "message_delay": message_delay}, encoded


def _request_status(row: dict | None) -> str:
    if not row:
        return ""
    return row.get("client_view", {}).get("last_delivered_ack", {}).get("status", row.get("submission_reply", {}).get("status", ""))


def _cooldown_ready(row: dict | None, now: float) -> bool:
    return row is None or now >= row.get("cooldown_until", -math.inf)


def _publish_services(client: ProtocolClient, owner: str, state: dict, *, command_delay: float,
                      publication_delay: float, routes: bool, forecasts: bool, lease_seconds: float,
                      forecast_refresh_period: float = 60., forecast_change_threshold: float = 1.,
                      observation: dict | None = None,
                      _reuse_route_work: bool = True) -> list[dict]:
    """Coalesce one active intent per locally observed service stage.

    Refresh replaces a publication only after its exact withdrawal is known.
    Transport retry repeats the immutable request; rejection cooldown creates
    a new request. Neither duration is used as a forecast or route lifetime.
    """
    observation = client._policy_view(owner) if observation is None else observation
    # One immutable view already feeds both route and forecast production.
    # Submissions may change native/client state but do not mutate that view;
    # reuse exactly its calculations until this invocation returns.
    routing = _ObservationRouting(observation) if _reuse_route_work else None
    now = observation["now"]
    state.setdefault("forecast_expirations", {})[owner] = {m["message_id"]: m["valid_until"]
        for m in observation.get("delivered_messages", [])
        if m.get("kind") == "service_forecast" and m.get("status") == "conditional" and m.get("valid_until", -1.) > now}
    nodes = {int(row["node"]): row for row in observation["node_contracts"]}
    jobs = {row["business_bag_id"]: row for row in observation.get("jobs", [])}
    alive, route_alive = set(), set()
    records = []
    active_routes = state.setdefault("active_routes", {})
    for tray in observation.get("trays", []):
        job = jobs.get(tray.get("business_bag_id")) or tray.get("job_contract")
        if not job or tray["mode"] not in ("loading", "loaded") or tray.get("edge_to", -1) >= 0:
            continue
        key = json.dumps([owner, tray["tray_id"], job["business_bag_id"], tray["generation"],
                          tray["traversal_id"], tray["node"]], separators=(",", ":"))
        if routes and tray["mode"] == "loaded" and job.get("allow_suffix_reroute", False):
            try:
                payload, encoded = route_payload(observation, tray["tray_id"], message_delay=command_delay,
                                                 lease_seconds=lease_seconds, _routing=routing)
            except ValueError as exc:
                records.append({"kind": "route_not_proposed", "reason": str(exc), "key": key})
            else:
                route_alive.add(key)
                route_key = key + ":" + json.dumps([decode_route(encoded).replaceable_suffix,
                    observation.get("known_faults", [])], sort_keys=True, separators=(",", ":"))
                active = active_routes.get(key)
                old_row = client.state["outbox"].get((active or {}).get("request_id"))
                needs_request = old_row is None or (old_row["terminal"] and _cooldown_ready(old_row, now) and
                    ((active or {}).get("route_key") != route_key or _request_status(old_row) != "updated" or
                     now >= old_row["payload"]["expiry"]))
                if needs_request:
                    request_id, reply = client.submit(owner, "route", payload)
                    state["routes"][route_key] = request_id
                    active_routes[key] = {"owner": owner, "route_key": route_key, "request_id": request_id}
                    records.append({"kind": "route", "request_id": request_id, "encoded_route": encoded, "reply": reply})
        if not forecasts:
            continue
        storage = int(job.get("storage_node", -1))
        goal = storage if storage >= 0 and job.get("storage_released_at", -1) < 0 else int(job["destination"])
        path = public_astar(observation, int(tray["node"]), goal, _routing=routing)
        if len(path) < 2:
            continue
        next_node = path[1]
        forecast_key = key + ":" + str(next_node)
        alive.add(forecast_key)
        old = state["forecasts"].get(forecast_key)
        old_request = client.state["outbox"].get((old or {}).get("request_id"))
        # These inputs are local observations, not an estimate from the native
        # future heap. Small numeric drift cannot cause a message per tick.
        condition = [tray["mode"], list(path), [[f["from"], f["to"], f["active"]]
            for f in observation.get("known_faults", [])]]
        estimate = float(tray.get("available_at", now))
        if old and not old.get("withdrawn") and not old.get("retired_without_publication"):
            changed = old.get("condition") != condition or abs(estimate-old.get("estimate", estimate)) >= forecast_change_threshold
            if changed or now >= old["refresh_at"] or now >= old["valid_until"]:
                old["retire_reason"] = "condition_changed" if changed else ("expired" if now >= old["valid_until"] else "refresh_due")
        rejected = bool(old_request and old_request["terminal"] and _request_status(old_request) in {"rejected", "failed", "expired"})
        if rejected and not old_request.get("client_view", {}).get("last_delivered_ack", {}).get("result_id"):
            old["retired_without_publication"] = True
        needs_publication = old is None or old.get("withdrawn") or old.get("retired_without_publication")
        if needs_publication and _cooldown_ready(old_request, now):
            if old:
                state.setdefault("forecast_history", []).append(copy.deepcopy(old))
            target = nodes[next_node].get("resource_owner", nodes[next_node]["zone"])
            request_id, reply = client.submit(owner, "service_forecast", {
                "target_owner": target, "tray_id": tray["tray_id"], "next": next_node,
                "message_delay": command_delay, "publication_delay": publication_delay})
            state["forecasts"][forecast_key] = {"owner": owner, "request_id": request_id, "withdrawn": False,
                "condition": condition, "estimate": estimate, "created_at": now,
                "refresh_at": now + forecast_refresh_period,
                "valid_until": now + command_delay + client.state["forecast_validity"]}
            records.append({"kind": "service_forecast", "request_id": request_id, "reply": reply})
    for key in list(active_routes):
        if active_routes[key].get("owner") == owner and key not in route_alive:
            del active_routes[key]
    for key, old in state["forecasts"].items():
        if old["owner"] == owner and key not in alive:
            old.pop("replace_at", None)
        if old["owner"] != owner or old["withdrawn"] or old.get("retired_without_publication"):
            continue
        if key not in alive:
            old["retire_reason"] = "stage_or_route_changed"
        if not old.get("retire_reason"):
            continue
        original = client.state["outbox"][old["request_id"]]
        original_ack = original.get("client_view", {}).get("last_delivered_ack", {})
        if original["terminal"] and _request_status(original) in {"rejected", "failed", "expired"} and not original_ack.get("result_id"):
            old["retired_without_publication"] = True
            continue
        previous = client.state["outbox"].get(old.get("withdraw_request_id"))
        if previous:
            if not previous["terminal"]:
                continue
            if _request_status(previous) in {"delivered", "withdrawn", "cancelled"}:
                old["withdrawn"] = True
                # Reactivate immediately once to publish the coalesced latest
                # condition. No recursive owner action or duplicate command.
                old["replace_at"] = now
                continue
            old["withdrawal_failure"] = copy.deepcopy(previous.get("client_view", {}).get("last_delivered_ack", {}) or previous["submission_reply"])
            if not _cooldown_ready(previous, now):
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
                         prebalance: bool = True, compact: bool = True, lease_seconds: float = 5., forecast_validity: float = 120.,
                         forecast_refresh_period: float = 60., forecast_change_threshold: float = 1.,
                         rejection_cooldown: float = .2, state: dict | None = None,
                         event_budget: int = 100000, _use_policy_view: bool = True,
                         _use_recent_forecasts: bool = True) -> dict:
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
                observation = client._policy_view(owner, compact=compact)
                decision = transfer_candidates(observation, predictive=predictive, message_delay=command_delay,
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
