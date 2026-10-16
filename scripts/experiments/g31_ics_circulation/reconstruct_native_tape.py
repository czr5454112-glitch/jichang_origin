"""Offline reconstruction by exact API replay, never restoration from JSON.

Saved owner records identify submissions and retry eligibility; native records
preserve every advance boundary. Policy calculations are not rerun. A native
seal must match before this object releases a session/checkpoint for profiling.
The saved tape lacks complete advance responses: we check every recorded field,
notifications through owner causes/pending causes, and final cursor values.
"""
from __future__ import annotations

import copy
import json
import math
import re
from typing import Any

TERMINAL = frozenset({"received", "rejected", "cancelled", "failed", "expired",
                      "updated", "delivered", "withdrawn"})
SERVICE_KINDS = frozenset({"route", "service_forecast", "withdraw_service_forecast"})


class TapeMismatch(ValueError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise TapeMismatch("native_tape:" + reason)


def _time(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _equal(actual: Any, expected: Any, reason: str) -> None:
    # Preserve dictionary insertion order and exact floating representations.
    _require(json.dumps(actual, ensure_ascii=False, allow_nan=False, separators=(",", ":")) ==
             json.dumps(expected, ensure_ascii=False, allow_nan=False, separators=(",", ":")), reason)


def _result_without_timing(result: dict) -> dict:
    result = copy.deepcopy(result)
    result.pop("native_event_ms", None)
    result.get("native_summary", {}).pop("runtime_seconds", None)
    result.get("advance", {}).pop("wall_seconds", None)
    return result


def validate_call_assignment(parts: Any) -> dict:
    """Pure preflight: map every saved call to exactly one owner activation.

    This validates recorded attribution only. It does not validate physics,
    native replies, notifications, checkpoints or a native seal.
    """
    sent = {}
    config = None
    next_trace = owners = boundaries = calls_total = retries = part_count = 0
    now = 0.
    for part in parts:
        current_config = part["controller_state"]["config"]
        if config is None:
            config = copy.deepcopy(current_config)
            _require(_time(config["retry_period"]) and config["retry_period"] > 0, "retry_period")
        _equal(config, current_config, "config_changed")
        records = [(r["trace_sequence"], "owner", r) for r in part["control_records"]]
        records += [(r["trace_sequence"], "native", r) for r in part["native_batches"]]
        _require(all(type(sequence) is int for sequence, _, _ in records), "trace_sequence_type")
        records.sort(key=lambda r: r[0])
        _require([r[0] for r in records] == list(range(next_trace, next_trace + len(records))),
                 "trace_gap_duplicate_or_reset")
        position = 0
        for _, kind, row in records:
            if kind == "native":
                _require(row["start_at"] == now and _time(row["end_at"]) and
                         now <= row["end_at"] <= row["requested_public_deadline"], "native_boundary_time")
                now = row["end_at"]
                boundaries += 1
                continue
            _require(row["owner_id"] in config["owners"] and row["at"] == now, "owner_boundary")
            expected = []
            seen = set()
            for refresh in row["refreshed"]:
                identity = refresh["request_id"]
                _require(identity in sent and identity not in seen, "unknown_or_duplicate_refresh")
                seen.add(identity)
                known = sent[identity]
                _require(known["request"]["owner_id"] == row["owner_id"] and
                         known["kind"] == refresh["kind"], "refresh_owner_kind")
                terminal = refresh["view"].get("last_delivered_ack", {}).get("status") in TERMINAL
                if not terminal and now >= known["at"] + config["retry_period"]:
                    expected.append((identity, refresh["kind"], True, None))
            expected += [(r["request_id"], "demand", False, r["reply"]) for r in row["publications"]]
            for action in row["service_actions"]:
                if action["kind"] == "route_not_proposed":
                    _require("request_id" not in action and "reply" not in action, "non_submission_has_identity")
                    continue
                _require(action["kind"] in SERVICE_KINDS, "unknown_service_action")
                expected.append((action["request_id"], action["kind"], False, action["reply"]))
            expected += [(r["request_id"], "transfer", False, r["reply"]) for r in row["attempts"]]
            for identity, call_kind, retry, reply in expected:
                _require(position < len(part["client_calls"]), "missing_submission")
                call = part["client_calls"][position]
                _require(call["at"] == now and call["retry"] is retry and call["kind"] == call_kind and
                         call["request"]["request_id"] == identity and
                         call["request"]["owner_id"] == row["owner_id"], "submission_order_or_owner")
                if retry:
                    _equal(call["request"], sent[identity]["request"], "mutated_retry_payload")
                else:
                    _require(identity not in sent, "duplicate_new_identity")
                if reply is not None:
                    _equal(reply, call["reply"], "owner_submission_reply")
                sent[identity] = copy.deepcopy(call)
                position += 1
                retries += retry
            owners += 1
        _require(position == len(part["client_calls"]), "unassigned_submission")
        _require(set(sent) == set(part["controller_state"]["client"]["outbox"]), "outbox_identity_set")
        calls_total += position
        next_trace += len(records)
        part_count += 1
    return {"schema": "g31.native_tape_assignment.v1", "status": "recorded_call_assignment_validated",
            "parts": part_count, "owner_records": owners, "native_boundaries": boundaries,
            "submissions": calls_total, "immutable_ids": len(sent), "retry_attempts": retries,
            "trace_records": next_trace, "physical_time_from_tape": now,
            "native_executed": False, "native_state_equivalence_verified": False}


class NativeTapeReconstructor:
    """Single fresh native session, append-only saved shards, required seal gate.

    All saved artifacts and this API are offline capabilities. Callers must bind
    the exact input, binary, shard order and event_budget in their receipt. An
    error makes this reconstructor permanently unusable; discard that session.
    """

    def __init__(self, session: Any, *, event_budget: int):
        _require(isinstance(event_budget, int) and not isinstance(event_budget, bool) and event_budget > 0,
                 "explicit_event_budget_required")
        _require(session.physical_time == 0, "fresh_session_required")
        self._session = session
        self.event_budget = event_budget
        self.config = None
        self.after = {}
        self.pending_notices = {}
        self.sent = {}
        self.last_views = {}
        self.next_trace = 0
        self.parts = self.owner_count = self.boundary_count = self.call_count = self.query_count = 0
        self.failed = self.verified = False
        self._cut_checkpoints = {}

    def _send(self, calls: list[dict], position: int, *, owner: str, at: float,
              request_id: str, kind: str, retry: bool, expected_reply: dict | None = None) -> int:
        _require(position < len(calls), "missing_submission")
        call = calls[position]
        payload = call["request"]
        _require(call["at"] == at == self._session.physical_time and call["retry"] is retry and
                 call["kind"] == kind and payload["request_id"] == request_id and
                 payload["owner_id"] == owner, "submission_order_or_owner")
        if retry:
            _require(request_id in self.sent, "retry_without_origin")
            _equal(payload, self.sent[request_id]["payload"], "mutated_retry_payload")
            _require(self.sent[request_id]["kind"] == kind, "retry_kind_changed")
        else:
            _require(request_id not in self.sent, "duplicate_new_identity")
        if expected_reply is not None:
            _equal(call["reply"], expected_reply, "owner_submission_reply")
        endpoint = (self._session.submit_protocol_transfer if kind == "transfer"
                    else self._session.submit_protocol_command)
        reply = endpoint(copy.deepcopy(payload))
        _equal(reply, call["reply"], "native_submission_reply")
        _require(self._session.physical_time == at, "submit_advanced_physics")
        created = self.sent[request_id]["created_at"] if retry else at
        self.sent[request_id] = {"payload": copy.deepcopy(payload), "kind": kind,
                                "at": at, "created_at": created, "reply": copy.deepcopy(reply)}
        self.call_count += 1
        return position + 1

    def _owner(self, row: dict, calls: list[dict], position: int) -> int:
        owner, at = row["owner_id"], row["at"]
        _require(owner in self.after and _time(at) and at == self._session.physical_time, "owner_boundary")
        expected_notice = row["causes"].get("notification")
        notice = self.pending_notices.pop(owner, None)
        _equal(notice, expected_notice, "owner_notification_cause")
        seen = set()
        for refreshed in row["refreshed"]:
            request_id, kind = refreshed["request_id"], refreshed["kind"]
            _require(request_id in self.sent and request_id not in seen, "unknown_or_duplicate_refresh")
            seen.add(request_id)
            known = self.sent[request_id]
            _require(known["kind"] == kind and known["payload"]["owner_id"] == owner, "refresh_owner_kind")
            endpoint = self._session.protocol_request if kind == "transfer" else self._session.protocol_command
            view = endpoint(owner, request_id)
            _equal(view, refreshed["view"], "delivered_query_view")
            _require(self._session.physical_time == at, "query_advanced_physics")
            self.last_views[request_id] = copy.deepcopy(view)
            self.query_count += 1
            terminal = view.get("last_delivered_ack", {}).get("status") in TERMINAL
            if not terminal and at >= known["at"] + self.config["retry_period"]:
                position = self._send(calls, position, owner=owner, at=at, request_id=request_id,
                                      kind=kind, retry=True)
        for publication in row["publications"]:
            position = self._send(calls, position, owner=owner, at=at,
                                  request_id=publication["request_id"], kind="demand", retry=False,
                                  expected_reply=publication["reply"])
        for action in row["service_actions"]:
            if action["kind"] == "route_not_proposed":
                _require("request_id" not in action and "reply" not in action, "non_submission_has_identity")
                continue
            _require(action["kind"] in SERVICE_KINDS, "unknown_service_action")
            position = self._send(calls, position, owner=owner, at=at, request_id=action["request_id"],
                                  kind=action["kind"], retry=False, expected_reply=action["reply"])
        for attempt in row["attempts"]:
            position = self._send(calls, position, owner=owner, at=at, request_id=attempt["request_id"],
                                  kind="transfer", retry=False, expected_reply=attempt["reply"])
        self.owner_count += 1
        return position

    def _advance(self, row: dict) -> None:
        start, end, deadline = row["start_at"], row["end_at"], row["requested_public_deadline"]
        _require(all(_time(x) for x in (start, end, deadline)) and
                 start == self._session.physical_time and start <= end <= deadline, "native_boundary_time")
        response = self._session.advance_until_owner_notification(
            self.config["owners"], copy.deepcopy(self.after), deadline, max_events=self.event_budget)
        _require(response["status"] == row["status"] and
                 response["timestamp_complete"] is row["timestamp_complete"] and
                 response["physical_time"] == self._session.physical_time == end, "native_boundary_response")
        if row["status"] == "budget_exhausted":
            _require(not response.get("notifications"), "partial_boundary_notifications")
        else:
            _require(row["status"] in ("notified", "horizon_reached") and row["timestamp_complete"] is True,
                     "invalid_completed_boundary")
            for owner, notice in response["notifications"].items():
                _require(owner in self.after and type(notice["sequence"]) is int and
                         notice["sequence"] > self.after[owner] and
                         _time(notice["observed_at"]) and notice["observed_at"] <= end, "notification_identity")
                self.after[owner] = notice["sequence"]
                self.pending_notices[owner] = copy.deepcopy(notice)
        self.boundary_count += 1

    def replay_part(self, part: dict, *, retain_checkpoint: str | None = None) -> dict:
        _require(not self.failed and not self.verified, "closed_reconstructor")
        try:
            config = part["controller_state"]["config"]
            if self.config is None:
                _require(config["owners"] and len(set(config["owners"])) == len(config["owners"]), "owners")
                _require(_time(config["retry_period"]) and config["retry_period"] > 0, "retry_period")
                self.config = copy.deepcopy(config)
                self.after = {owner: 0 for owner in config["owners"]}
            _equal(config, self.config, "config_changed")
            records = [(row["trace_sequence"], "owner", row) for row in part["control_records"]]
            records.extend((row["trace_sequence"], "native", row) for row in part["native_batches"])
            _require(all(type(sequence) is int for sequence, _, _ in records), "trace_sequence_type")
            records.sort(key=lambda item: item[0])
            _require([x[0] for x in records] == list(range(self.next_trace, self.next_trace + len(records))),
                     "trace_gap_duplicate_or_reset")
            position = 0
            for _, kind, row in records:
                if kind == "owner":
                    position = self._owner(row, part["client_calls"], position)
                else:
                    self._advance(row)
            _require(position == len(part["client_calls"]), "unassigned_submission")
            state = part["controller_state"]
            _equal(self.after, state["after_sequences"], "final_notification_cursors")
            pending = {owner: cause["notification"] for owner, cause in state["pending_causes"].items()
                       if "notification" in cause}
            _equal(self.pending_notices, pending, "pending_notification_causes")
            _require(set(state["client"]["outbox"]) == set(self.sent), "outbox_identity_set")
            for identity, outbox in state["client"]["outbox"].items():
                known = self.sent[identity]
                _equal(outbox["payload"], known["payload"], "checkpoint_payload")
                _equal(outbox["submission_reply"], known["reply"], "checkpoint_submission_reply")
                _require(outbox["kind"] == known["kind"] and outbox["created_at"] == known["created_at"] and
                         outbox["next_retry"] == known["at"] + config["retry_period"], "checkpoint_attempt_state")
                _equal(outbox.get("client_view"), self.last_views.get(identity), "checkpoint_query_view")
            continuation = part["control_continuation"]
            _require(continuation["physical_time"] == self._session.physical_time and
                     continuation["status"] == part["status"], "continuation_boundary")
            if part["result"] is not None:
                _require(part["status"] == "reached" and state["native_timestamp_complete"] is True,
                         "result_before_complete_timestamp")
                actual = self._session.result_at(continuation["requested_horizon"])
                actual["control_continuation"] = copy.deepcopy(continuation)
                _equal(_result_without_timing(actual), _result_without_timing(part["result"]), "saved_physical_result")
                _require(self._session.physical_time == continuation["physical_time"], "result_advanced_physics")
            if retain_checkpoint is not None:
                _require(isinstance(retain_checkpoint, str) and retain_checkpoint and
                         retain_checkpoint not in self._cut_checkpoints, "checkpoint_label")
                self._cut_checkpoints[retain_checkpoint] = self._session.checkpoint()
            self.next_trace += len(records)
            self.parts += 1
            return self.report()
        except Exception:
            self.failed = True
            raise

    def finish(self, expected_native_sha256: str) -> dict:
        _require(not self.failed and not self.verified and self.parts > 0, "closed_or_empty_reconstructor")
        try:
            _require(isinstance(expected_native_sha256, str) and
                     re.fullmatch(r"[0-9a-f]{64}", expected_native_sha256) is not None, "known_seal_required")
            actual = self._session.offline_state_sha256()
            _require(actual == expected_native_sha256, "native_seal_mismatch")
            self.verified = True
            return dict(self.report(), native_state_sha256=actual)
        except Exception:
            self.failed = True
            raise

    def verified_session(self) -> Any:
        _require(self.verified and not self.failed, "unverified_session")
        return self._session

    def verified_checkpoint(self, label: str) -> Any:
        _require(self.verified and not self.failed, "unverified_checkpoint")
        return self._cut_checkpoints[label]

    def report(self) -> dict:
        return {"schema": "g31.native_tape_reconstruction.v1",
                "status": "failed" if self.failed else ("verified_against_known_native_seal" if self.verified
                                                        else "recorded_contracts_replayed_seal_pending"),
                "parts": self.parts, "owners": self.owner_count, "native_boundaries": self.boundary_count,
                "submissions": self.call_count, "queries": self.query_count, "trace_records": self.next_trace,
                "physical_time": self._session.physical_time,
                "full_advance_responses_in_source": False, "native_json_restore": False,
                "policy_reexecuted": False, "complete_100ms_requirement_certified": False}
