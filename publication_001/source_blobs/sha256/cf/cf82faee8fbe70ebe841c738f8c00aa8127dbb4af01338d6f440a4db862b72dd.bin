"""Pure admission/closure contract for a finite original-input operation probe.

Native owner notices do not carry a business ID. Accordingly the root admitted
before advance is a notification bundle, not a renamed business-task request.
Every eligible public job receives the whole bundle bound; empty/unknown scope
is retained. No native state, results, or future input jobs select a decision.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math


SCHEMA = "g31.original_notification_operation_contract.v1"
JOB_STATUSES = frozenset(("waiting_for_tray", "loading", "in_transit", "storage", "unloading", "handed_off", "failed", "completed"))
TERMINAL = frozenset(("received", "updated", "delivered", "withdrawn", "cancelled", "rejected", "failed", "expired"))
SUCCESS = {"route": frozenset(("updated",)), "transfer": frozenset(("received",)),
           "demand": frozenset(("delivered",)), "service_forecast": frozenset(("delivered",)),
           "withdraw_service_forecast": frozenset(("withdrawn", "delivered")),
           "cancel_transfer": frozenset(("cancelled",))}
RESULT_ONLY_MASK = 16 | 32
PUBLIC_UPDATE_MASK = 1 | 2 | 4 | 8 | 64 | 128


def require(condition, reason):
    if not condition: raise ValueError("original_notification:"+reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def contract():
    return {"schema": SCHEMA, "original_offered_jobs": 28506, "nodes": 151, "directed_edges": 227,
        "admitted_notification_boundaries": 12, "event_budget_per_call": 100000,
        "completion_tail_seconds": 120., "native_call_budget": 20000,
        "public_horizon": 86400., "retry_period_seconds": 60., "command_delay_seconds": 2.,
        "publication_delay_seconds": .5, "lease_seconds": 120.,
        "admission": "Batch admitted before each complete native notification advance; owner bundle before its first full public observation. The entire triggering advance is charged to every resulting owner bundle.",
        "job_scope": "All unique returned non-completed job contracts, including handed_off/failed, enrolled after the public read. Explicit completed status excluded and recorded. Missing/malformed/unrepresented carried contracts make scope unknown, never silently remove a job.",
        "joint_closure": "All enrolled children depend on every operation in the owner bundle, and close only after all actual terminal ACKs are handled, complete same-time drain and returned encoded output. R2 affected-job scope remains unverified.",
        "failures": "Delivered rejection/failed/expired can close explicit terminal_failure. A submission reply or forecast cannot close a root. Lost ACK stays open until an immutable retry receives a terminal ACK or the declared tail ends.",
        "new_updates": "ACK/timeout-only masks16/32 continue existing requests and create no new proposal root. Any public update bit1/2/4/8/64/128 creates a notification bundle while admission is open; mixed old-result/new-information scope remains conservative. Later bundles cannot close older bundles. After12 notification boundaries no new proposals are made; subsequent notices remain recorded and existing immutable requests continue within120 logical seconds/20000calls.",
        "setup": "Input rebuild/read/validation/native load/construction, diagnostic capture constructor and all public preprocessing are charged in full to every admitted root, never divided. Host/import startup additionally retains a whole-worker bound; no setup interval is subtracted from the authoritative bound.",
        "comparison": "Baseline preserves exact frozen full28506 input. Explicit ACK-loss variants are separate communication-contract factors; no R1 permission, graph, job, capacity or physical timing is changed.",
        "limits": ["Experimental notification bundle, not field business admission", "Original input has no suffix-reroute permission; no R1-install coverage claim", "Finite requests do not certify full-day business service/protection", "No unconditional100ms claim"]}


def eligible_jobs(view, owner):
    """Return a lossless public-scope classification; no silent row filtering."""
    require(view.get("schema") == "g31.owner_protocol_observation.v1" and view.get("owner_id") == owner,
            "full_owned_protocol_view_required")
    require(nonnegative(view.get("now")), "invalid_view_clock")
    require(isinstance(view.get("jobs"), list) and isinstance(view.get("trays"), list)
            and isinstance(view.get("node_contracts"), list), "missing_public_scope")
    nodes = {}
    for row in view["node_contracts"]:
        require(type(row.get("node")) is int and row["node"] not in nodes, "invalid_or_duplicate_node_contract")
        authority = row.get("resource_owner", row.get("zone"))
        require(isinstance(authority, str) and authority, "missing_node_authority")
        nodes[row["node"]] = authority
    carried = set()
    for tray in view["trays"]:
        require(isinstance(tray.get("business_bag_id"), str) and type(tray.get("node")) is int,
                "malformed_public_tray")
        require(nodes.get(tray["node"]) == owner, "foreign_tray")
        if tray["business_bag_id"]: carried.add(tray["business_bag_id"])
    included, excluded, classifications, seen = [], [], {}, set()
    for row in view["jobs"]:
        identity = row.get("business_bag_id")
        require(isinstance(identity, str) and identity and identity not in seen, "missing_or_duplicate_job")
        seen.add(identity)
        require(all(key in row for key in ("destination", "deadline", "storage_node", "storage_release_at",
                "storage_min_dwell", "load_seconds", "unload_seconds", "hold_seconds", "protected_service", "allow_suffix_reroute")),
                "incomplete_public_job_contract")
        require(all(type(row[key]) is int for key in ("origin", "destination", "storage_node"))
                and all(type(row[key]) in (int, float) and math.isfinite(row[key]) for key in
                    ("deadline", "storage_release_at", "storage_min_dwell", "load_seconds", "unload_seconds", "hold_seconds"))
                and type(row["protected_service"]) is bool and type(row["allow_suffix_reroute"]) is bool,
                "malformed_public_job_contract")
        require(row.get("status") in JOB_STATUSES and nonnegative(row.get("arrival"))
                and row["arrival"] <= view["now"] and type(row.get("origin")) is int,
                "unknown_or_future_job_scope")
        require(nodes.get(row["origin"]) == owner or identity in carried, "unowned_job_contract")
        if row["status"] == "completed":
            excluded.append(identity); classifications[identity] = "explicit_public_completed"
        else:
            included.append(identity)
            classifications[identity] = "remote_progress_unknown" if row["status"] == "handed_off" else "public_"+row["status"]
    require(carried <= seen, "carried_job_contract_missing")
    return {"eligible_job_ids": included, "excluded_completed_job_ids": excluded,
            "classification": classifications, "view_sha256": digest(view),
            "affected_job_scope_verified": False}


class NotificationLedger:
    """Clocked finite bundles; caller supplies actual returned native evidence.

    This pure API never authenticates caller-created evidence by itself. The
    eventual independent verifier must bind every reference to its service tape.
    """
    def __init__(self, owners):
        require(isinstance(owners, (list, tuple)) and owners and len(set(owners)) == len(owners)
                and all(isinstance(o, str) and o for o in owners), "invalid_owners")
        self.owners = list(owners); self.cursors = {o: 0 for o in owners}
        self.batches, self.roots, self.operations = {}, {}, {}

    def begin(self, identity, *, at, wall_ns):
        require(identity not in self.batches and nonnegative(at) and type(wall_ns) is int and wall_ns >= 0,
                "invalid_or_duplicate_batch")
        self.batches[identity] = {"accepted_at": at, "accepted_wall_ns": wall_ns,
            "returned": None, "roots": [], "status": "unknown_pending_boundary"}

    def notified(self, identity, response, *, wall_ns, call_ordinal, admit=True):
        batch = self.batches[identity]
        require(batch["returned"] is None and type(wall_ns) is int and wall_ns >= batch["accepted_wall_ns"]
                and type(call_ordinal) is int and call_ordinal > 0, "invalid_boundary_return")
        require(response.get("status") in {"notified", "horizon_reached"}
                and response.get("timestamp_complete") is True and nonnegative(response.get("physical_time"))
                and response["physical_time"] >= batch["accepted_at"], "incomplete_native_boundary")
        notices = response.get("notifications")
        require(isinstance(notices, dict) and set(notices) <= set(self.owners), "foreign_notification")
        require(response["status"] != "notified" or bool(notices), "notified_without_notice")
        require(type(admit) is bool, "explicit_admission_switch_required")
        for owner, row in notices.items():
            require(type(row.get("sequence")) is int and row["sequence"] > self.cursors[owner]
                    and nonnegative(row.get("observed_at")) and row["observed_at"] <= response["physical_time"]
                    and type(row.get("change_mask")) is int and row["change_mask"] > 0
                    and not row["change_mask"] & ~(RESULT_ONLY_MASK | PUBLIC_UPDATE_MASK), "invalid_notice")
        # Mutate only after every owner has passed; malformed later rows cannot
        # advance some cursors and make a partial response look complete.
        batch["returned"] = {"response": deepcopy(response), "wall_ns": wall_ns, "call_ordinal": call_ordinal}
        batch["status"] = "complete_notification_boundary"
        batch["admission_open"] = admit
        batch["continuation_only_owners"] = []
        batch["not_admitted_owners"] = []
        for owner in self.owners:
            if owner not in notices: continue
            self.cursors[owner] = notices[owner]["sequence"]
            if not notices[owner]["change_mask"] & PUBLIC_UPDATE_MASK:
                batch["continuation_only_owners"].append(owner); continue
            if not admit:
                batch["not_admitted_owners"].append(owner); continue
            root = identity+":"+owner
            self.roots[root] = {"owner": owner, "batch": identity, "notice": deepcopy(notices[owner]),
                "accepted_wall_ns": batch["accepted_wall_ns"], "observation": None, "operations": [],
                "output": None, "scope_errors": []}
            batch["roots"].append(root)
        return list(batch["roots"])

    def observe(self, root, view, *, start_ns, end_ns, call_ordinal):
        row = self.roots[root]; batch = self.batches[row["batch"]]
        require(row["observation"] is None and type(start_ns) is int and type(end_ns) is int
                and batch["returned"]["wall_ns"] <= start_ns <= end_ns
                and type(call_ordinal) is int and call_ordinal > batch["returned"]["call_ordinal"], "invalid_observation")
        require(view.get("now") == batch["returned"]["response"]["physical_time"], "observation_crossed_native_boundary")
        try: scope = eligible_jobs(view, row["owner"])
        except (ValueError, TypeError, KeyError) as error:
            row["scope_errors"].append(str(error)); raise
        row["observation"] = {"scope": scope, "start_ns": start_ns, "end_ns": end_ns, "call_ordinal": call_ordinal}

    def submit(self, root, request_id, kind, payload, *, at, wall_ns, retry=False):
        row = self.roots[root]
        require(row["observation"] is not None and row["output"] is None and not row["scope_errors"], "submission_outside_valid_open_scope")
        require(kind in SUCCESS and payload.get("owner_id") == row["owner"] and payload.get("request_id") == request_id
                and nonnegative(at) and at >= self.batches[row["batch"]]["returned"]["response"]["physical_time"]
                and type(wall_ns) is int and wall_ns >= row["observation"]["end_ns"], "invalid_operation")
        fingerprint = digest(payload)
        if retry:
            old = self.operations[request_id]
            require(old["root"] == root and old["kind"] == kind and old["payload_sha256"] == fingerprint
                    and old["ack"] is None and at >= old["attempts"][-1]["at"]
                    and wall_ns >= old["attempts"][-1]["wall_ns"], "mutated_or_terminal_retry")
            old["attempts"].append({"at": at, "wall_ns": wall_ns})
        else:
            require(request_id not in self.operations, "duplicate_immutable_identity")
            self.operations[request_id] = {"root": root, "kind": kind, "payload_sha256": fingerprint,
                "attempts": [{"at": at, "wall_ns": wall_ns}], "ack": None}
            row["operations"].append(request_id)

    def handle_ack(self, request_id, ack, *, at, wall_ns, query_ordinal):
        operation = self.operations[request_id]; root = self.roots[operation["root"]]
        require(root["output"] is None and operation["ack"] is None, "ack_after_closure_or_duplicate")
        require(ack.get("request_id") == request_id and ack.get("status") in TERMINAL
                and nonnegative(at) and at >= operation["attempts"][-1]["at"]
                and nonnegative(ack.get("delivered_at")) and ack["delivered_at"] <= at
                and type(ack.get("sequence")) is int and ack["sequence"] > 0
                and type(wall_ns) is int and wall_ns >= operation["attempts"][-1]["wall_ns"]
                and type(query_ordinal) is int and query_ordinal > 0, "actual_terminal_query_required")
        operation["ack"] = {"body": deepcopy(ack), "handled_wall_ns": wall_ns, "at": at, "query_ordinal": query_ordinal}

    def finish(self, root, *, drain, drain_start_ns, drain_end_ns, output_end_ns, encoded_output, drain_ordinal):
        row = self.roots[root]
        require(row["observation"] is not None and row["output"] is None and not row["scope_errors"], "invalid_closure_scope")
        require(all(self.operations[i]["ack"] is not None for i in row["operations"]), "pending_ack_keeps_all_children_open")
        earliest = max([row["observation"]["end_ns"]]+[self.operations[i]["ack"]["handled_wall_ns"] for i in row["operations"]])
        earliest_at = max([self.batches[row["batch"]]["returned"]["response"]["physical_time"]]+
            [self.operations[i]["ack"]["at"] for i in row["operations"]])
        require(all(type(t) is int for t in (drain_start_ns, drain_end_ns, output_end_ns))
                and earliest <= drain_start_ns <= drain_end_ns <= output_end_ns
                and drain.get("status") == "reached" and drain.get("horizon_complete") is True
                and nonnegative(drain.get("physical_time")) and drain["physical_time"] >= earliest_at
                and type(drain_ordinal) is int and drain_ordinal > 0,
                "complete_post_ack_drain_required")
        disposition = ("no_action" if not row["operations"] else "completed" if all(
            self.operations[i]["ack"]["body"]["status"] in SUCCESS[self.operations[i]["kind"]] for i in row["operations"]) else "terminal_failure")
        parsed = json.loads(encoded_output)
        require(parsed == {"root_id": root, "disposition": disposition, "operation_ids": row["operations"]}, "output_not_bound_to_actual_operations")
        row["output"] = {"wall_ns": output_end_ns, "drain_start_ns": drain_start_ns, "drain_end_ns": drain_end_ns,
            "drain": deepcopy(drain), "drain_ordinal": drain_ordinal, "encoded": encoded_output, "disposition": disposition}

    def accounting(self, *, mandatory_setup_ns, known_end_ns):
        require(type(mandatory_setup_ns) is int and mandatory_setup_ns >= 0 and type(known_end_ns) is int,
                "invalid_setup_or_end")
        report = {}
        for identity, row in self.roots.items():
            end = row["output"]["wall_ns"] if row["output"] else known_end_ns
            require(row["accepted_wall_ns"] <= end <= known_end_ns, "negative_root_lifetime")
            amount = end-row["accepted_wall_ns"]+mandatory_setup_ns
            scope = row["observation"]["scope"] if row["observation"] else {"eligible_job_ids": [], "affected_job_scope_verified": False}
            report[identity] = {"status": "complete_experimental_bundle_bound" if row["output"] else "unknown_open_or_scope",
                "complete_compute_upper_ns": amount if row["output"] else None, "known_prefix_upper_ns": amount,
                "job_children": {job: {"complete_compute_upper_ns": amount if row["output"] else None,
                    "affected_job_scope_verified": False} for job in scope["eligible_job_ids"]},
                "scope_errors": list(row["scope_errors"]), "original_business_request_100ms_certified": False}
        return {"roots": report, "bundle_denominator": len(self.roots),
            "pending_boundary_denominator": sum(b["returned"] is None for b in self.batches.values()),
            "job_child_denominator": sum(len(r["job_children"]) for r in report.values()),
            "original_offered_jobs": 28506, "original_business_request_100ms_certified": False}
