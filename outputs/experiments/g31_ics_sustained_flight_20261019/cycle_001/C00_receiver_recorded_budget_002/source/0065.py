"""External wrappers for complete conservative serial controller bundles.

No controller/native source edits. Full native calls are charged, including
physics; stage-isolated validation is never claimed. Diagnostic IDs are sidecar
state and never enter the actual controller or native observations.
"""
from __future__ import annotations

import copy
import bisect
from collections import Counter
import hashlib
import json
import math
import time

from . import event_protocol_control as event
from .protocol_control import TERMINAL


SCHEMA = "g31.request_bundle_ledger.v1"
BUDGET_NS = 100_000_000
NATIVE_OWNER_CALLS = {"observe_protocol", "observe_protocol_control", "observe_protocol_control_policy", "protocol_demand_signature",
    "protocol_request", "protocol_command", "submit_protocol_transfer", "submit_protocol_command"}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class BundleRecorder:
    def __init__(self, session, *, clock=time.perf_counter_ns):
        self.session, self.clock = session, clock
        self.roots, self.messages, self.bundles, self.windows = {}, {}, [], []
        self.current_root = None
        self.current_owner_messages = set()
        self.active = set()
        self.last_native = None
        self.last_execution_bundle = None
        self.notification_bundles = {}
        self.cause_bundles = {}
        self.native_methods = {}
        self.error = None
        self._call_roots = set()

    def _bundle(self, kind, start, end, roots, **extra):
        row = {"bundle_id": len(self.bundles), "kind": kind, "start_ns": start, "end_ns": end,
               "root_request_ids": set(roots), **extra}
        self.bundles.append(row)
        return row

    def _new_root(self, owner, start, logical, epoch, *, maintenance=False):
        rid = f"measured:{len(self.roots)}:{owner}:{epoch}"
        self.roots[rid] = {"request_id": rid, "owner_id": owner, "owner_epoch": epoch,
            "accepted_ns": start, "logical_opened_at": logical, "status": "open",
            "message_ids": [], "business_job_ids": [], "maintenance_only": maintenance}
        self._call_roots.add(rid)
        return rid

    def _message_send(self, name, payload):
        if self.current_root is None:
            raise ValueError("request_bundles:submission_outside_owner_activation")
        mid = payload["request_id"]
        signature = _hash(payload)
        if mid not in self.messages:
            root = self.roots[self.current_root]
            self.messages[mid] = {"request_id": mid, "root_request_id": self.current_root,
                "owner_id": payload["owner_id"], "payload_sha256": signature,
                "opened_ns": self.clock(), "closed_ns": None, "status": "open", "attempts": 0,
                "kind": "transfer" if name == "submit_protocol_transfer" else payload["kind"]}
            root["message_ids"].append(mid)
            if payload.get("business_bag_id") and payload["business_bag_id"] not in root["business_job_ids"]:
                root["business_job_ids"].append(payload["business_bag_id"])
            self.active.add(self.current_root)
        message = self.messages[mid]
        if message["payload_sha256"] != signature:
            raise ValueError("request_bundles:mutated_retry")
        message["attempts"] += 1
        self.current_owner_messages.add(mid)

    def _settle_roots(self, root_ids):
        for rid in root_ids:
            root = self.roots[rid]
            children = [self.messages[m] for m in root["message_ids"]]
            complete = (root.get("drain_complete_bundle_id") is not None and
                        all(m["closed_ns"] is not None for m in children))
            root["status"] = ("completed" if children else "no_action") if complete else "open"
            if complete:
                root["logical_closed_at"] = self.session.physical_time
                self.active.discard(rid)
            else:
                root.pop("logical_closed_at", None)
                self.active.add(rid)

    @staticmethod
    def _cause_keys(owner, causes):
        keys = []
        if "periodic_tick" in causes:
            keys.append(json.dumps([owner, "periodic_tick", causes["periodic_tick"]]))
        keys.extend(json.dumps([owner, "timer", timer["key"], timer["generation"], timer["deadline"]])
                    for timer in causes.get("timers", []))
        return keys

    def due_timers(self, original, current, now):
        result = original(current, now)
        # This hook runs immediately after native boundary validation and tick
        # generation, before any owner is dispatched. Capture causal identity
        # here, not from whichever native drain happens to precede dispatch.
        if self.last_native is None:
            raise ValueError("request_bundles:timer_without_native_origin")
        tick = current["next_tick"]-1
        for owner in current["config"]["owners"]:
            causes = {"timers": result.get(owner, [])}
            if tick >= 0:
                causes["periodic_tick"] = tick
            for key in self._cause_keys(owner, causes):
                self.cause_bundles.setdefault(key, self.last_native)
        return result

    def _link_trigger(self, rid, trigger):
        native = self.bundles[trigger]
        native["root_request_ids"].add(rid)
        # A pending cause can survive a returned controller checkpoint. Its
        # originating native call, notification/timer processing and mandatory
        # checkpoint output still belong to the eventual activation root.
        for window in self.windows:
            if window["start_ns"] <= native["start_ns"] and native["end_ns"] <= window["end_ns"]:
                window["root_request_ids"] = sorted(set(window["root_request_ids"]) | {rid})
                for bundle in self.bundles:
                    if not window["start_ns"] <= bundle["start_ns"] <= bundle["end_ns"] <= window["end_ns"]:
                        continue
                    if (bundle["kind"] in {"scheduler_output_full", "native_result_full"} or
                            (bundle["kind"] == "scheduler_gap_full" and
                             (bundle["start_ns"] == window["start_ns"] or bundle["start_ns"] == native["end_ns"]))):
                        bundle["root_request_ids"].add(rid)

    def owner(self, original, client, owner, current, causes, **kwargs):
        start = self.clock()
        rid = self._new_root(owner, start, self.session.physical_time, current["owner_epochs"].get(owner, 0))
        deps = {rid} | {r for r in self.active if self.roots[r]["owner_id"] == owner}
        self._call_roots.update(deps)
        # The native call producing a notification/timer boundary is an upper
        # bundle for the update it triggers, even if its earlier physics was
        # unrelated. No truth fields are passed back to the policy.
        trigger_ids = set()
        notice = causes.get("notification")
        if notice is not None:
            trigger = self.notification_bundles.get((owner, notice["sequence"]))
            if trigger is None:
                raise ValueError("request_bundles:notification_without_measured_native_origin")
            trigger_ids.add(trigger)
        cause_keys = self._cause_keys(owner, causes)
        for key in cause_keys:
            if key not in self.cause_bundles:
                raise ValueError("request_bundles:unmeasured_timer_origin")
            trigger_ids.add(self.cause_bundles[key])
        for trigger in trigger_ids:
            self._link_trigger(rid, trigger)
        self.roots[rid]["trigger_bundle_ids"] = sorted(trigger_ids)
        self.roots[rid]["trigger_keys"] = cause_keys
        self.roots[rid]["activation_causes"] = copy.deepcopy(causes)
        self.current_root = rid
        self.current_owner_messages = {m for m, row in self.messages.items()
                                       if row["closed_ns"] is None and row["owner_id"] == owner}
        try:
            record = original(client, owner, current, causes, **kwargs)
        finally:
            self.current_root = None
        end = self.clock()
        touched = set(self.current_owner_messages)
        deps.update(self.messages[m]["root_request_id"] for m in touched)
        self._call_roots.update(deps)
        bundle = self._bundle("owner_activation", start, end, deps, owner_id=owner,
                              protocol_request_ids=sorted(touched), activation_root_id=rid)
        self.last_execution_bundle = bundle["bundle_id"]
        self.roots[rid]["activation_bundle_id"] = bundle["bundle_id"]
        for mid in touched:
            row = client.state["outbox"][mid]
            message = self.messages[mid]
            ack = row.get("client_view", {}).get("last_delivered_ack", {})
            status = ack.get("status", row.get("submission_reply", {}).get("status"))
            if row["terminal"]:
                if status not in TERMINAL:
                    raise ValueError("request_bundles:terminal_without_observed_outcome")
                message.update(status=status, closed_ns=end, terminal_owner_bundle_id=bundle["bundle_id"],
                               logical_closed_at=self.session.physical_time)
        # Every activation requires the controller's following timestamp drain,
        # even after a terminal ACK or a no-action decision. A budget cut must
        # leave these roots open until that actual native boundary is complete.
        for root_id in deps:
            self.roots[root_id]["required_drain_after_bundle_id"] = bundle["bundle_id"]
            self.roots[root_id]["drain_complete_bundle_id"] = None
        self._settle_roots(deps)
        return record

    def invoke(self, name, method, *args, **kwargs):
        self.native_methods[name] = self.native_methods.get(name, 0) + 1
        if name in NATIVE_OWNER_CALLS:
            if self.current_root is None:
                raise ValueError("request_bundles:owner_native_call_outside_activation:" + name)
            if name.startswith("submit_protocol_"):
                self._message_send(name, args[0])
            return method(*args, **kwargs)
        if name not in {"advance_until_owner_notification", "result_at"}:
            raise ValueError("request_bundles:unclassified_native_method:" + name)
        if self.current_root is not None:
            raise ValueError("request_bundles:native_advance_nested_in_owner")
        start = self.clock()
        deps = set(self.active)
        if self.last_execution_bundle is not None:
            previous = self.bundles[self.last_execution_bundle]
            if previous["kind"] == "owner_activation":
                # The controller requires a native drain after every owner
                # activation, including no-action and already-ACKed updates.
                deps.update(previous["root_request_ids"])
        mids = sorted(m for m, row in self.messages.items() if row["closed_ns"] is None)
        response = method(*args, **kwargs)
        end = self.clock()
        kind = "native_advance_full" if name == "advance_until_owner_notification" else "native_result_full"
        bundle = self._bundle(kind, start, end, deps, protocol_request_ids=mids)
        self.last_execution_bundle = bundle["bundle_id"]
        self._call_roots.update(deps)
        if name == "advance_until_owner_notification":
            bundle["native_status"] = response.get("status")
            bundle["timestamp_complete"] = response.get("timestamp_complete") is True
            bundle["physical_time"] = self.session.physical_time
            bundle["notification_sequences"] = {owner: notice["sequence"] for owner, notice in response.get("notifications", {}).items()}
            if bundle["timestamp_complete"] and bundle["native_status"] in {"notified", "horizon_reached"}:
                for rid in deps:
                    root = self.roots[rid]
                    if root.get("required_drain_after_bundle_id") is not None and root.get("drain_complete_bundle_id") is None:
                        root["drain_complete_bundle_id"] = bundle["bundle_id"]
                self._settle_roots(deps)
            self.last_native = bundle["bundle_id"]
            for owner, notice in response.get("notifications", {}).items():
                self.notification_bundles[(owner, notice["sequence"])] = bundle["bundle_id"]
        return response

    def run(self, owners, **kwargs):
        """One unchanged controller call; all gaps get located full charges."""
        original = event._activate_owner
        original_due = event._due_timers
        if not self.windows and kwargs.get("state") is not None:
            raise ValueError("request_bundles:initial_unmeasured_controller_restore")
        self._call_roots = set(self.active)
        first = len(self.bundles)
        start = self.clock()
        event._activate_owner = lambda *a, **kw: self.owner(original, *a, **kw)
        event._due_timers = lambda *a, **kw: self.due_timers(original_due, *a, **kw)
        try:
            proxy_type = _PolicySessionProxy if hasattr(type(self.session), "observe_protocol_control_policy") else _SessionProxy
            part = event.run_event_protocol_control(proxy_type(self), owners, **kwargs)
        except BaseException as exc:
            self.error = type(exc).__name__ + ":" + str(exc)
            raise
        finally:
            event._activate_owner = original
            event._due_timers = original_due
        end = self.clock()
        emitted = self.bundles[first:]
        cohort = set(self._call_roots)
        if not cohort:
            rid = self._new_root("scheduler", start, self.session.physical_time, len(self.windows), maintenance=True)
            self.roots[rid].update(status="completed", logical_closed_at=self.session.physical_time)
            cohort = {rid}
        # Result construction is required by this controller-call interface;
        # charge it to this call's cohort, never every historical root.
        for row in emitted:
            if row["kind"] == "native_result_full":
                row["root_request_ids"].update(cohort)
        cursor = start
        previous = None
        for row in emitted:
            if row["start_ns"] < cursor:
                raise ValueError("request_bundles:overlapping_wrappers")
            if row["start_ns"] > cursor:
                deps = cohort if previous is None else previous["root_request_ids"] | row["root_request_ids"]
                self._bundle("scheduler_gap_full", cursor, row["start_ns"], deps or cohort)
            if not row["root_request_ids"]:
                # A background native interval is retained and charged to this
                # call's cohort; it is not silently called free simulation.
                row["root_request_ids"].update(cohort)
            cursor, previous = row["end_ns"], row
        if cursor < end:
            self._bundle("scheduler_output_full", cursor, end, cohort)
        self.windows.append({"start_ns": start, "end_ns": end, "root_request_ids": sorted(cohort),
                             "status": part["status"], "physical_time": self.session.physical_time})
        return part

    def ledger(self):
        bundles = [{**row, "root_request_ids": sorted(row["root_request_ids"])} for row in self.bundles]
        return {"schema": SCHEMA, "clock": "monotonic_ns", "execution_lanes": 1,
            "request_scope": "owner_activation_updates", "coverage": "whole_controller_calls_and_all_native_calls",
            "native_physics_subtracted": False, "native_stage_times_isolated": False,
            "runtime_error": self.error, "service_windows": copy.deepcopy(self.windows),
            "requests": copy.deepcopy(list(self.roots.values())), "messages": copy.deepcopy(list(self.messages.values())),
            "bundles": bundles, "native_method_counts": dict(self.native_methods),
            "cause_origins": dict(self.cause_bundles)}


class _SessionProxy:
    def __init__(self, recorder):
        self._recorder = recorder

    @property
    def physical_time(self):
        return self._recorder.session.physical_time

    def __getattr__(self, name):
        value = getattr(self._recorder.session, name)
        if callable(value):
            return lambda *a, **kw: self._recorder.invoke(name, value, *a, **kw)
        raise ValueError("request_bundles:unclassified_native_attribute:" + name)


class _PolicySessionProxy(_SessionProxy):
    # ProtocolClient intentionally checks this method on the session TYPE;
    # defining it only for capable natives preserves the old fallback path.
    def observe_protocol_control_policy(self, owner):
        return self._recorder.invoke("observe_protocol_control_policy",
                                     self._recorder.session.observe_protocol_control_policy, owner)


def analyze_bundles(ledger):
    """Complete located upper bounds, never isolated native-stage durations."""
    report = {"schema": "g31.request_bundle_accounting.v1", "status": "unknown", "requests": [],
        "complete_100ms_requirement_certified": False, "native_stage_times_isolated": False,
        "all_captured_roots_complete_upper_within_100ms": None, "errors": []}
    try:
        if (ledger["schema"] != SCHEMA or ledger["clock"] != "monotonic_ns" or ledger["execution_lanes"] != 1
                or ledger["coverage"] != "whole_controller_calls_and_all_native_calls"
                or ledger["native_physics_subtracted"] is not False or ledger.get("runtime_error")):
            raise ValueError("invalid_or_incomplete_capture_contract")
        roots = {r["request_id"]: r for r in ledger["requests"]}
        messages = {m["request_id"]: m for m in ledger["messages"]}
        bundles = {b["bundle_id"]: b for b in ledger["bundles"]}
        report["request_count"] = len(ledger["requests"])
        report["protocol_request_count"] = len(ledger["messages"])
        if not roots or len(roots) != len(ledger["requests"]) or len(messages) != len(ledger["messages"]) or len(bundles) != len(ledger["bundles"]):
            raise ValueError("empty_or_duplicate_identity")
        def ns(x):
            return isinstance(x, int) and not isinstance(x, bool) and x >= 0
        def logical(x):
            return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0
        for b in bundles.values():
            if not ns(b["start_ns"]) or not ns(b["end_ns"]) or b["end_ns"] < b["start_ns"]:
                raise ValueError("invalid_bundle_interval")
            if not b["root_request_ids"] or not set(b["root_request_ids"]) <= set(roots):
                raise ValueError("unattributed_or_unknown_dependency")
            if b["kind"] not in {"owner_activation", "native_advance_full", "native_result_full", "scheduler_gap_full", "scheduler_output_full"}:
                raise ValueError("unclassified_bundle")
        ordered = sorted(bundles.values(), key=lambda b: (b["start_ns"], b["end_ns"]))
        if any(b["start_ns"] < a["end_ns"] for a, b in zip(ordered, ordered[1:])):
            raise ValueError("overlapping_exclusive_bundles")
        covered = set()
        trigger_shared = {}
        for window in ledger["service_windows"]:
            if not ns(window["start_ns"]) or not ns(window["end_ns"]) or window["end_ns"] < window["start_ns"]:
                raise ValueError("invalid_service_window")
            cursor = window["start_ns"]
            local = [b for b in ordered if window["start_ns"] <= b["start_ns"] and b["end_ns"] <= window["end_ns"]]
            for b in local:
                if b["start_ns"] != cursor or b["bundle_id"] in covered:
                    raise ValueError("service_window_gap_or_duplicate")
                cursor = b["end_ns"]
                covered.add(b["bundle_id"])
            if cursor != window["end_ns"]:
                raise ValueError("service_window_incomplete")
            shared = [b for b in local if b["kind"] in {"scheduler_output_full", "native_result_full"} or
                      (b["kind"] == "scheduler_gap_full" and b["start_ns"] == window["start_ns"])]
            gaps = {b["start_ns"]: b for b in local if b["kind"] == "scheduler_gap_full"}
            for b in local:
                if b["kind"] == "native_advance_full":
                    following = gaps.get(b["end_ns"])
                    trigger_shared[b["bundle_id"]] = shared + ([] if following is None else [following])
        if covered != set(bundles):
            raise ValueError("bundle_outside_service_windows")
        native_bundles = [b for b in ordered if b["kind"] == "native_advance_full"]
        native_starts = [b["start_ns"] for b in native_bundles]
        root_bundles = {rid: [] for rid in roots}
        for b in ordered:
            for rid in b["root_request_ids"]:
                root_bundles[rid].append(b)
        for mid, m in messages.items():
            parent = m["root_request_id"]
            if parent not in roots or mid not in roots[parent]["message_ids"]:
                raise ValueError("unlinked_message")
            if not ns(m["opened_ns"]) or not isinstance(m["attempts"], int) or isinstance(m["attempts"], bool) or m["attempts"] < 1:
                raise ValueError("invalid_message_lifecycle")
            created = bundles[roots[parent]["activation_bundle_id"]]
            if not created["start_ns"] <= m["opened_ns"] <= created["end_ns"] or mid not in created["protocol_request_ids"]:
                raise ValueError("message_creation_uncovered")
            closed = m["closed_ns"]
            if closed is not None:
                if not ns(closed) or closed < m["opened_ns"] or m["status"] not in TERMINAL:
                    raise ValueError("invalid_terminal_message")
                terminal = bundles[m["terminal_owner_bundle_id"]]
                if terminal["kind"] != "owner_activation" or terminal["end_ns"] != closed or parent not in terminal["root_request_ids"] or mid not in terminal["protocol_request_ids"]:
                    raise ValueError("terminal_message_processing_uncovered")
            lo = bisect.bisect_left(native_starts, m["opened_ns"])
            hi = len(native_bundles) if closed is None else bisect.bisect_right(native_starts, closed)
            for b in native_bundles[lo:hi]:
                if closed is None or b["end_ns"] <= closed:
                    if parent not in b["root_request_ids"] or mid not in b.get("protocol_request_ids", []):
                        raise ValueError("native_lifetime_bundle_omitted")
        for rid, root in roots.items():
            if root["status"] not in {"open", "completed", "no_action"}:
                raise ValueError("unrecognized_root_outcome")
            if not ns(root["accepted_ns"]) or not logical(root["logical_opened_at"]):
                raise ValueError("invalid_root_opening")
            if "logical_closed_at" in root and (not logical(root["logical_closed_at"]) or root["logical_closed_at"] < root["logical_opened_at"]):
                raise ValueError("invalid_root_closing")
            charged = root_bundles[rid]
            if not charged:
                raise ValueError("unmeasured_root")
            if not root.get("maintenance_only"):
                activation = bundles[root["activation_bundle_id"]]
                if activation["kind"] != "owner_activation" or activation["activation_root_id"] != rid or rid not in activation["root_request_ids"]:
                    raise ValueError("activation_root_uncovered")
                if root["accepted_ns"] != activation["start_ns"]:
                    raise ValueError("root_accepted_after_preprocessing")
                if BundleRecorder._cause_keys(root["owner_id"], root["activation_causes"]) != root["trigger_keys"]:
                    raise ValueError("root_cause_identity_mismatch")
                for key in root["trigger_keys"]:
                    if ledger["cause_origins"][key] not in root["trigger_bundle_ids"]:
                        raise ValueError("root_cause_origin_mismatch")
                notice = root["activation_causes"].get("notification")
                if notice is not None and not any(bundles[t].get("notification_sequences", {}).get(root["owner_id"]) == notice["sequence"]
                                                  for t in root["trigger_bundle_ids"]):
                    raise ValueError("root_notification_origin_mismatch")
                for trigger_id in root["trigger_bundle_ids"]:
                    trigger = bundles[trigger_id]
                    if trigger["kind"] != "native_advance_full" or rid not in trigger["root_request_ids"]:
                        raise ValueError("root_trigger_native_uncovered")
                    if any(rid not in b["root_request_ids"] for b in trigger_shared[trigger_id]):
                        raise ValueError("trigger_scheduler_or_checkpoint_uncovered")
                owner_bundles = [b for b in charged if b["kind"] == "owner_activation"]
                required = root["required_drain_after_bundle_id"]
                if required != owner_bundles[-1]["bundle_id"]:
                    raise ValueError("required_post_owner_drain_mismatch")
                drained = root.get("drain_complete_bundle_id")
                if drained is not None:
                    drain = bundles[drained]
                    if (drain["kind"] != "native_advance_full" or drain.get("timestamp_complete") is not True or
                            drain.get("native_status") not in {"notified", "horizon_reached"} or
                            drain["start_ns"] < bundles[required]["end_ns"] or rid not in drain["root_request_ids"]):
                        raise ValueError("required_native_drain_uncovered")
                elif root["status"] != "open":
                    raise ValueError("root_completed_before_required_native_drain")
            if any(mid not in messages or messages[mid]["root_request_id"] != rid for mid in root["message_ids"]):
                raise ValueError("root_child_identity_mismatch")
            complete = root["status"] != "open" and all(messages[mid]["closed_ns"] is not None for mid in root["message_ids"])
            if root["status"] != "open" and not complete:
                raise ValueError("root_completed_with_open_message")
            total = sum(b["end_ns"]-b["start_ns"] for b in charged)
            by_kind = Counter()
            for b in charged:
                by_kind[b["kind"]] += b["end_ns"]-b["start_ns"]
            continuous, maximum, last = 0, 0, None
            for b in charged:
                continuous = continuous + b["end_ns"]-b["start_ns"] if last == b["start_ns"] else b["end_ns"]-b["start_ns"]
                maximum, last = max(maximum, continuous), b["end_ns"]
            report["requests"].append({"request_id": rid, "owner_id": root["owner_id"], "status": root["status"],
                "maintenance_only": root["maintenance_only"], "message_count": len(root["message_ids"]),
                "message_outcomes": [messages[mid]["status"] for mid in root["message_ids"]],
                "upper_ns_by_bundle_kind": dict(by_kind),
                "known_prefix_compute_upper_ns": total, "complete_compute_upper_ns": total if complete else None,
                "max_continuous_bundle_upper_ns": maximum, "upper_bound_exceeds_100ms": total > BUDGET_NS,
                "earliest_charged_ns": charged[0]["start_ns"], "latest_charged_ns": charged[-1]["end_ns"],
                "logical_end_to_end_seconds": (root["logical_closed_at"]-root["logical_opened_at"] if "logical_closed_at" in root else None)})
        report.update(status="complete_conservative_bundle_accounting", request_scope=ledger["request_scope"],
            open_root_count=sum(r["complete_compute_upper_ns"] is None for r in report["requests"]),
            exclusive_controller_wall_ns=sum(b["end_ns"]-b["start_ns"] for b in ordered),
            upper_bound_over_100ms_count=sum(r["upper_bound_exceeds_100ms"] for r in report["requests"]))
        report["message_outcome_counts"] = dict(Counter(m["status"] for m in messages.values()))
        report["root_status_counts"] = dict(Counter(r["status"] for r in roots.values()))
        report["max_complete_compute_upper_ns"] = max((r["complete_compute_upper_ns"] for r in report["requests"]
            if r["complete_compute_upper_ns"] is not None), default=None)
        report["max_owner_activation_wall_ns"] = max((b["end_ns"]-b["start_ns"] for b in ordered
            if b["kind"] == "owner_activation"), default=None)
        report["owner_activation_wall_over_100ms_count"] = sum(b["end_ns"]-b["start_ns"] > BUDGET_NS for b in ordered
            if b["kind"] == "owner_activation")
        if report["open_root_count"] == 0:
            report["all_captured_roots_complete_upper_within_100ms"] = report["upper_bound_over_100ms_count"] == 0
        report["scope"] = "Whole native work including physics and full local shared bundles. An upper bound above 100ms is not an isolated request overrun; passing complete bounds applies only to this declared captured owner-update cohort. Queue/transport stage split is unmeasured."
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        report["status"] = "unknown_invalid_bundle_capture"
        report["errors"].append(str(exc))
        report["all_captured_roots_complete_upper_within_100ms"] = None
    return report
