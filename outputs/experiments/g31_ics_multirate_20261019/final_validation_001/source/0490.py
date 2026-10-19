"""Explicit causal request ancestry for a future rolling controller.

This records declared request boundaries; it does not infer them afterward from
nearby timestamps or shared reservation reads. Existing experiments are not
retroactively certified. This module has no compute-span/apportionment ledger;
its duration is an elapsed envelope, including any waits between recorded calls.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math

TERMINAL = {"received", "updated", "delivered", "withdrawn", "rejected", "failed", "expired", "cancelled"}
RELATIONS = {"independent_offer", "result_handling", "fallback", "cancellation", "lease_failure", "replacement_replan", "mixed_offer_and_continuation"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class RequestLineage:
    def __init__(self):
        self.roots = {}
        self.protocol = {}
        self.sequence = 0
        self.last_wall_ns = -1
        self.last_at = -1.

    def _stamp(self, at, wall_ns):
        if not isinstance(at, (int, float)) or isinstance(at, bool) or not math.isfinite(at) or at < 0 or at < self.last_at or type(wall_ns) is not int or wall_ns < 0 or wall_ns < self.last_wall_ns:
            raise ValueError("rolling_lineage:noncausal_clock")
        self.last_wall_ns = wall_ns; self.last_at = at; self.sequence += 1
        return {"sequence": self.sequence, "at": at, "wall_ns": wall_ns}

    def accept(self, root_id, *, scope, completion_contract, owner, trigger_id, trigger_kind, relation, parents=(), predecessor_protocol_id=None,
               jobs=(), trays=(), at, wall_ns):
        if (not all(isinstance(v, str) and v for v in (root_id, owner, trigger_id, trigger_kind)) or
                root_id in self.roots or relation not in RELATIONS):
            raise ValueError("rolling_lineage:invalid_root_or_classification")
        if scope not in {"business_task_update", "owner_activation_proxy", "maintenance_update"}:
            raise ValueError("rolling_lineage:explicit_admission_scope_required")
        if (not isinstance(completion_contract, dict) or
                set(completion_contract) != {"kind", "goal_id", "terminal_failure_allowed"} or
                completion_contract["kind"] != "one_shot_update" or
                not isinstance(completion_contract["goal_id"], str) or not completion_contract["goal_id"] or
                type(completion_contract["terminal_failure_allowed"]) is not bool):
            raise ValueError("rolling_lineage:explicit_supported_finite_contract_required")
        if (any(not isinstance(v, str) or not v for v in (*jobs, *trays)) or
                len(set(jobs)) != len(jobs) or len(set(trays)) != len(trays) or
                (scope == "business_task_update" and len(jobs) != 1)):
            raise ValueError("rolling_lineage:invalid_declared_task_scope")
        parents = tuple(parents)
        if len(set(parents)) != len(parents) or any(p not in self.roots for p in parents):
            raise ValueError("rolling_lineage:missing_or_duplicate_parent")
        if any(self.roots[p]["decision_seal"] is not None for p in parents):
            raise ValueError("rolling_lineage:continuation_after_final_disposition")
        continuation = relation != "independent_offer"
        if continuation != bool(parents):
            raise ValueError("rolling_lineage:explicit_continuation_parent_required")
        if predecessor_protocol_id is not None:
            old = self.protocol.get(predecessor_protocol_id)
            if old is None or not set(old["parent_roots"]) <= set(parents):
                raise ValueError("rolling_lineage:predecessor_parent_mismatch")
        root = {"root_id": root_id, "scope": scope, "completion_contract": copy.deepcopy(completion_contract),
            "owner": owner, "trigger_id": trigger_id, "trigger_kind": trigger_kind,
            "relation": relation, "continuation_parent_roots": list(parents), "predecessor_protocol_id": predecessor_protocol_id,
            "jobs": sorted(set(jobs)), "trays": sorted(set(trays)), "accepted": self._stamp(at, wall_ns),
            "observation": None, "input_references": [], "protocol_ids": [], "mandatory_drain": None,
            "output_returned": None, "decision_seal": None, "unclassified": False}
        self.roots[root_id] = root
        return copy.deepcopy(root)

    def observe(self, root_id, *, references, at, wall_ns):
        root = self.roots[root_id]
        if root["observation"] is not None: raise ValueError("rolling_lineage:root_observation_already_started")
        for reference in references:
            for field in ("delivered_at", "observed_at"):
                value = reference.get(field, at)
                if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                        not math.isfinite(value) or not 0 <= value <= at):
                    raise ValueError("rolling_lineage:future_input_reference_or_invalid_time")
        root["observation"] = self._stamp(at, wall_ns)
        root["input_references"] = copy.deepcopy(references)

    def submit(self, root_id, request_id, payload, *, required_terminal_statuses,
               continuation_parent_roots=(), retry=False, at, wall_ns):
        root = self.roots[root_id]
        if root["observation"] is None or root["decision_seal"] is not None or root["output_returned"] is not None:
            raise ValueError("rolling_lineage:submission_outside_open_observed_root")
        if not set(continuation_parent_roots) <= set(root["continuation_parent_roots"]):
            raise ValueError("rolling_lineage:undeclared_continuation_parent")
        parents = tuple(dict.fromkeys((root_id, *root["continuation_parent_roots"], *continuation_parent_roots)))
        if any(p not in self.roots for p in parents): raise ValueError("rolling_lineage:unknown_protocol_parent")
        required = list(required_terminal_statuses)
        if not required or len(set(required)) != len(required) or not set(required) <= TERMINAL:
            raise ValueError("rolling_lineage:explicit_terminal_operation_contract_required")
        required = sorted(required)
        payload_hash = _digest(payload)
        if retry:
            previous = self.protocol.get(request_id)
            if (previous is None or previous["payload_sha256"] != payload_hash or previous["parent_roots"] != list(parents)
                    or previous["required_terminal_statuses"] != required):
                raise ValueError("rolling_lineage:retry_identity_payload_or_parent_changed")
            if previous["terminal_delivered_ack"] is not None: raise ValueError("rolling_lineage:retry_after_terminal_handling")
            previous["attempts"].append(self._stamp(at, wall_ns))
            return
        if request_id in self.protocol: raise ValueError("rolling_lineage:new_request_reuses_identity")
        stamp = self._stamp(at, wall_ns)
        self.protocol[request_id] = {"request_id": request_id, "payload_sha256": payload_hash,
            "required_terminal_statuses": required,
            "parent_roots": list(parents), "attempts": [stamp], "terminal_delivered_ack": None,
            "handled": None, "handling_events": []}
        for parent in parents: self.roots[parent]["protocol_ids"].append(request_id)

    def handle_ack(self, request_id, ack, *, at, wall_ns):
        request = self.protocol[request_id]
        if (ack.get("request_id") != request_id or type(ack.get("sequence")) is not int or ack["sequence"] < 1 or
                ack.get("status") not in TERMINAL or not (0 <= ack.get("delivered_at", math.inf) <= at)):
            raise ValueError("rolling_lineage:terminal_delivered_ack_required")
        if any(self.roots[p]["decision_seal"] is not None for p in request["parent_roots"]):
            raise ValueError("rolling_lineage:ack_processing_after_final_disposition_requires_new_update")
        if request["terminal_delivered_ack"] is not None:
            if _digest(request["terminal_delivered_ack"]) != _digest(ack):
                raise ValueError("rolling_lineage:terminal_ack_identity_or_outcome_changed")
            stamp = self._stamp(at, wall_ns)
            request["handling_events"].append({**stamp, "duplicate": True})
            request["handled"] = stamp
            return
        stamp = self._stamp(at, wall_ns)
        request["terminal_delivered_ack"] = copy.deepcopy(ack)
        request["handled"] = stamp
        request["handling_events"].append({**request["handled"], "duplicate": False})

    def seal(self, root_id, *, disposition, classification_complete, at, wall_ns):
        """Final decision: all mandatory children must already be known/completed.

        This limited API deliberately has no deferred child-slot mechanism.
        Register continuations before sealing; a missing fallback keeps it open.
        """
        root = self.roots[root_id]
        if root["observation"] is None or root["decision_seal"] is not None:
            raise ValueError("rolling_lineage:seal_requires_open_observed_root")
        if disposition not in {"completed", "terminal_failure", "no_action"}:
            raise ValueError("rolling_lineage:explicit_disposition_required")
        if disposition == "terminal_failure" and not root["completion_contract"]["terminal_failure_allowed"]:
            raise ValueError("rolling_lineage:terminal_failure_not_allowed_by_contract")
        if disposition == "no_action" and root["protocol_ids"]:
            raise ValueError("rolling_lineage:no_action_with_submitted_operations")
        if any(self.protocol[p]["handled"] is None for p in root["protocol_ids"]):
            raise ValueError("rolling_lineage:seal_before_terminal_handling")
        if any(self.summary(key)["status"] != "complete_declared_lineage" for key, child in self.roots.items()
               if root_id in child["continuation_parent_roots"]):
            raise ValueError("rolling_lineage:seal_before_required_child_completion")
        if disposition == "completed":
            for identity in root["protocol_ids"]:
                if self.protocol[identity]["terminal_delivered_ack"]["status"] not in self.protocol[identity]["required_terminal_statuses"]:
                    if not any(root_id in child["continuation_parent_roots"] and
                               child["predecessor_protocol_id"] == identity and
                               child["decision_seal"]["disposition"] == "completed"
                               for child in self.roots.values() if child["decision_seal"] is not None):
                        raise ValueError("rolling_lineage:failed_operation_without_completed_replacement")
        root["unclassified"] = classification_complete is not True
        root["decision_seal"] = {**self._stamp(at, wall_ns), "disposition": disposition}

    def drain(self, root_id, *, timestamp_complete, at, wall_ns):
        if timestamp_complete is not True: raise ValueError("rolling_lineage:mandatory_native_drain_incomplete")
        root = self.roots[root_id]
        if root["decision_seal"] is None or root["output_returned"] is not None:
            raise ValueError("rolling_lineage:drain_requires_final_disposition")
        root["mandatory_drain"] = self._stamp(at, wall_ns)

    def output(self, root_id, *, at, wall_ns):
        root = self.roots[root_id]
        if root["observation"] is None: raise ValueError("rolling_lineage:output_without_observation")
        if root["output_returned"] is not None: raise ValueError("rolling_lineage:final_output_already_returned")
        if root["decision_seal"] is None or root["mandatory_drain"] is None:
            raise ValueError("rolling_lineage:output_before_disposition_and_drain")
        root["output_returned"] = self._stamp(at, wall_ns)

    def summary(self, root_id):
        # New independent requests reading an old reservation are not descendants;
        # only explicit continuation parents create this closure.
        closure = {root_id}
        while True:
            expanded = closure | {key for key, root in self.roots.items() if set(root["continuation_parent_roots"]) & closure}
            if expanded == closure: break
            closure = expanded
        pending = []
        endpoints = []
        for key in sorted(closure):
            root = self.roots[key]
            if root["unclassified"]: pending.append(key + ":unclassified")
            if root["decision_seal"] is None: pending.append(key + ":final_disposition_missing")
            if root["output_returned"] is None: pending.append(key + ":output_missing")
            else: endpoints.append(root["output_returned"]["wall_ns"])
            drain = root["mandatory_drain"]
            handled = []
            for identity in root["protocol_ids"]:
                request = self.protocol[identity]
                if request["terminal_delivered_ack"] is None or request["handled"] is None:
                    pending.append(identity + ":terminal_ack_or_handling_missing")
                else:
                    handled.append(request["handled"]["wall_ns"])
            required = root["decision_seal"] or root["accepted"]
            if drain is None or drain["sequence"] < required["sequence"] or drain["wall_ns"] < max(handled + [required["wall_ns"]]):
                pending.append(key + ":mandatory_drain_missing_or_before_handling")
            else: endpoints.append(drain["wall_ns"])
            if root["output_returned"] and drain and root["output_returned"]["wall_ns"] < drain["wall_ns"]:
                pending.append(key + ":output_precedes_drain")
        start = self.roots[root_id]["accepted"]["wall_ns"]
        return {"schema": "g31.rolling_request_lineage.v1", "root_id": root_id, "closure": sorted(closure),
            "status": "unknown_incomplete_lineage" if pending else "complete_declared_lineage",
            "pending": sorted(set(pending)), "elapsed_envelope_ms": (max(endpoints) - start) / 1e6 if not pending else None,
            "duration_scope": "Elapsed acceptance-to-return envelope, including waits; not measured exclusive computation.",
            "compute_time_measured": False, "shared_work_apportionment_measured": False,
            "retroactive_certification": False,
            "automatic_lineage_inference": False, "exhaustive_runtime_instrumentation_certified": False}
