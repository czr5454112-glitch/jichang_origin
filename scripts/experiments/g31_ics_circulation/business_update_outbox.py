"""Opt-in experimental one-job admission bridge to the actual ProtocolClient.

No production controller uses this helper. The caller explicitly declares its
finite update and causal parents before observation; this is not retrospective
classification or acceptance of a replacement for the user's task contract.
Only elapsed envelopes are recorded, never exclusive compute or a100ms proof.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time

from .protocol_control import ProtocolClient, TERMINAL
from .rolling_request_lineage import RequestLineage


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


class BusinessUpdateOutbox:
    """Fresh exclusive client, one owner, explicit finite per-job updates.

    Direct client mutation and restored histories are unsupported and fail
    closed. Query results/ACKs come from this client's real returned refresh;
    row['terminal'] or a predicted/submission status can never close a root.
    """
    def __init__(self, client, owner, *, clock=time.perf_counter_ns):
        if not isinstance(client, ProtocolClient) or client.state["outbox"] or client.calls:
            raise ValueError("business_update:fresh_exclusive_protocol_client_required")
        if not isinstance(owner, str) or not owner:
            raise ValueError("business_update:owner_required")
        self.client, self.owner, self.clock = client, owner, clock
        self.lineage = RequestLineage()
        self.operations, self.observations, self.errors = {}, {}, []
        self.call_cursor = 0
        self.last_ack = {}

    def _at(self):
        return self.client.session.physical_time

    def _guard(self):
        if set(self.client.state["outbox"]) != set(self.operations) or len(self.client.calls) != self.call_cursor:
            self.errors.append("unclassified_external_client_activity")
            raise ValueError("business_update:unclassified_external_client_activity")
        for identity, operation in self.operations.items():
            row = self.client.state["outbox"][identity]
            if _digest(row["payload"]) != operation["payload_sha256"] or row["payload"]["owner_id"] != self.owner:
                self.errors.append("immutable_outbox_changed")
                raise ValueError("business_update:immutable_outbox_changed")

    def admit(self, root_id, *, business_job_id, trigger_id, trigger_kind, completion_contract,
              relation="independent_offer", parents=(), predecessor_protocol_id=None):
        self._guard()
        parents = tuple(parents)
        if any(self.lineage.roots[parent]["jobs"] != [business_job_id] for parent in parents):
            raise ValueError("business_update:continuation_job_scope_changed")
        return self.lineage.accept(root_id, scope="business_task_update", completion_contract=completion_contract,
            owner=self.owner, trigger_id=trigger_id, trigger_kind=trigger_kind, relation=relation,
            parents=parents, predecessor_protocol_id=predecessor_protocol_id,
            jobs=(business_job_id,), at=self._at(), wall_ns=self.clock())

    def observe(self, root_id, *, compact=True):
        self._guard()
        # Admission and observation-start stamps precede the actual public read.
        # Returned-view provenance/hash is retained separately after the read.
        self.lineage.observe(root_id, references=[], at=self._at(), wall_ns=self.clock())
        try:
            view = self.client.view(self.owner, compact=compact)
        except BaseException as error:
            self.errors.append("observation:"+type(error).__name__+":"+str(error))
            raise
        self.observations[root_id] = {"source": "ProtocolClient.view", "owner": self.owner,
            "returned_at": self._at(), "returned_wall_ns": self.clock(), "view_sha256": _digest(view),
            "observed_job_ids": sorted({row["business_bag_id"] for row in view.get("jobs", [])
                if isinstance(row, dict) and isinstance(row.get("business_bag_id"), str)} |
                {tray["job_contract"]["business_bag_id"] for tray in view.get("trays", [])
                 if isinstance(tray.get("job_contract"), dict) and
                 isinstance(tray["job_contract"].get("business_bag_id"), str)})}
        return view

    def submit(self, root_id, kind, payload, *, required_terminal_statuses):
        self._guard()
        root = self.lineage.roots[root_id]
        if root_id not in self.observations or root["observation"] is None or root["decision_seal"] is not None:
            raise ValueError("business_update:submission_requires_open_observed_update")
        # Validate before a side effect; the actual canonical payload is then
        # taken from the outbox, not reconstructed from a hypothetical request.
        required = tuple(required_terminal_statuses)
        if not required or len(set(required)) != len(required) or not set(required) <= TERMINAL:
            raise ValueError("business_update:explicit_required_terminal_statuses")
        admitted_job = root["jobs"][0]
        scope_verified = False
        if kind == "route":
            if payload.get("business_bag_id") != admitted_job:
                raise ValueError("business_update:route_job_does_not_match_admission")
            if admitted_job not in self.observations[root_id]["observed_job_ids"]:
                raise ValueError("business_update:admitted_route_job_not_observed")
            scope_verified = True
        # A transfer's empty tray/destination does not prove which job it serves.
        # Cancellation may refer to a preexisting operation absent from this
        # fresh client. Such operation lineage is retained as declared-label-only.
        identity = self.client.next_id(self.owner, kind)
        at, wall = self._at(), self.clock()
        before = len(self.client.calls)
        try:
            response = self.client.submit(self.owner, kind, payload, request_id=identity)
        except BaseException as error:
            self.errors.append(type(error).__name__+":"+str(error))
            raise
        finally:
            row = self.client.state["outbox"].get(identity)
            if row is not None:
                actual = row["payload"]
                self.operations[identity] = {"root_id": root_id, "kind": kind,
                    "required_terminal_statuses": required, "payload_sha256": _digest(actual),
                    "job_scope_verified": scope_verified}
                self.lineage.submit(root_id, identity, actual, required_terminal_statuses=required, at=at, wall_ns=wall)
            if len(self.client.calls) != before+1:
                self.errors.append("submission_call_not_fully_returned")
            self.call_cursor = len(self.client.calls)
        return response

    def refresh(self, *, retry=True):
        self._guard()
        before = self.call_cursor
        try:
            views = self.client.refresh(retry=retry, owner_id=self.owner)
        except BaseException as error:
            self.errors.append("refresh:"+type(error).__name__+":"+str(error))
            raise
        # Actual resend records identify the original immutable operation/root.
        # A new independent update reading that operation is not its parent.
        for call in self.client.calls[before:]:
            identity = call["request"]["request_id"]
            operation = self.operations.get(identity)
            if operation is None or call["retry"] is not True or _digest(call["request"]) != operation["payload_sha256"]:
                raise ValueError("business_update:unclassified_or_mutated_resend")
            self.lineage.submit(operation["root_id"], identity, call["request"], retry=True,
                required_terminal_statuses=operation["required_terminal_statuses"],
                at=call["at"], wall_ns=self.clock())
        self.call_cursor = len(self.client.calls)
        for returned in views:
            identity, view = returned["request_id"], returned["view"]
            if identity not in self.operations or view.get("request_id") != identity:
                raise ValueError("business_update:query_identity_mismatch")
            ack = view.get("last_delivered_ack")
            if ack and ack.get("status") in TERMINAL:
                # Native ACK body lacks request_id; bind it from the actual
                # query response identity. No hidden execution status is used.
                bound = {**copy.deepcopy(ack), "request_id": identity}
                if self.last_ack.get(identity) != bound:
                    self.lineage.handle_ack(identity, bound, at=self._at(), wall_ns=self.clock())
                    self.last_ack[identity] = bound
        return views

    def finish(self, root_id, output_payload, *, disposition, classification_complete, event_budget):
        """Require actual same-timestamp drain, then serialize and return output.

        A budget cut keeps the root incomplete; callers may retry this exact
        disposition at the same public clock. No extra horizon is invented.
        """
        self._guard()
        if self.errors:
            raise ValueError("business_update:prior_unresolved_capture_error")
        if type(event_budget) is not int or event_budget <= 0:
            raise ValueError("business_update:positive_drain_budget_required")
        root = self.lineage.roots[root_id]
        if root["decision_seal"] is None:
            self.lineage.seal(root_id, disposition=disposition, classification_complete=classification_complete,
                at=self._at(), wall_ns=self.clock())
        elif root["decision_seal"]["disposition"] != disposition or root["output_returned"] is not None:
            raise ValueError("business_update:sealed_disposition_changed_or_already_returned")
        now = self._at()
        drain = self.client.session.advance_to(now, max_events=event_budget)
        if (drain.get("status") != "reached" or drain.get("horizon_complete") is not True or
                drain.get("physical_time") != now or self._at() != now):
            return {"status": "mandatory_drain_incomplete", "drain": drain, "output": None}
        self.lineage.drain(root_id, timestamp_complete=True, at=now, wall_ns=self.clock())
        encoded = json.dumps(output_payload, allow_nan=False, separators=(",", ":"))
        self.lineage.output(root_id, at=now, wall_ns=self.clock())
        return {"status": "returned", "drain": drain, "output": encoded}

    def report(self, root_id):
        report = self.lineage.summary(root_id)
        root = self.lineage.roots[root_id]
        scope_verified = (all(self.lineage.roots[child]["jobs"] == root["jobs"] and root["jobs"][0] in
            self.observations.get(child, {}).get("observed_job_ids", []) for child in report["closure"]) and all(
            op["job_scope_verified"] for op in self.operations.values() if op["root_id"] in report["closure"]))
        report.update(experimental_contract=True, original_user_contract_accepted=False,
            production_controller_integrated=False, compute_time_measured=False,
            complete_request_100ms_certified=False, observation=self.observations.get(root_id),
            capture_errors=list(self.errors), job_scope_verified=scope_verified,
            job_scope="observed_job_and_route_identity" if scope_verified else "declared_label_only")
        if not scope_verified and report["status"] == "complete_declared_lineage":
            report["status"] = "complete_declared_operation_lineage_job_scope_unverified"
        if self.errors:
            report["status"] = "unknown_incomplete_lineage"
            report["elapsed_envelope_ms"] = None
        return report
