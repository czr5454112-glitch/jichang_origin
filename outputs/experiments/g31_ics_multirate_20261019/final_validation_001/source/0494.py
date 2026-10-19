"""Diagnostic-only nested Python and accepted027 native spans.

All unclassified work is retained. This does not identify pure physics or
claim a complete per-business computation total.
"""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
import time

from . import probe_original_route_update_internal_deadline as policy
from .capture_native027_request_timing import Native027TimingCapture
from .native027_request_timing import analyze_candidate_partition, ABI027

CAPACITY = 1_000_000


def require(ok, reason):
    if not ok: raise ValueError("route_phase:" + reason)


class PythonSpans:
    def __init__(self, clock=time.perf_counter_ns):
        self.clock, self.rows, self.stack = clock, [], []

    @contextmanager
    def span(self, phase, **details):
        row = {"id": len(self.rows), "parent": self.stack[-1] if self.stack else None,
            "phase": phase, "start_ns": self.clock(), "end_ns": None, "exception": False, **details}
        self.rows.append(row); self.stack.append(row["id"])
        try: yield
        except BaseException:
            row["exception"] = True
            raise
        finally:
            row["end_ns"] = self.clock()
            require(self.stack.pop() == row["id"], "span_stack")


class ObservedIntent:
    """Delegate every policy attribute and method; only measure observe()."""
    def __init__(self, intent, spans): self._intent, self._spans = intent, spans
    def __getattr__(self, key): return getattr(self._intent, key)
    def observe(self, *args, **kwargs):
        with self._spans.span("candidate_and_intent_update"):
            return self._intent.observe(*args, **kwargs)


def measured_route_type(spans):
    class MeasuredRoute(policy.RouteUpdate):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.intent = ObservedIntent(self.intent, spans)
        def _step(self, *, initial):
            with spans.span("request_service_invocation", at=self.session.physical_time, initial=initial):
                return super()._step(initial=initial)
        def _view(self, initial):
            with spans.span("request_public_observation_and_filter"):
                return super()._view(initial)
    return MeasuredRoute


class PhaseTape(policy.ServiceTape):
    def __init__(self, native, *, native_module, reference, timed):
        super().__init__(native)
        self._actual_native, self._native_module = native, native_module
        self._reference, self._timed = deepcopy(reference), timed
        self.capture = None
        self.capture_setup = None
        self.capture_take = None
    def begin(self, path):
        require(self.capture is None, "capture_started_twice")
        if self._timed:
            start = time.perf_counter_ns()
            self.capture = Native027TimingCapture(self._actual_native,
                native_module=self._native_module, contract_reference=self._reference,
                session_identity=1, capacity=CAPACITY)
            self.capture_setup = {"start_ns": start, "end_ns": time.perf_counter_ns()}
            self.native = self.capture
        return super().begin(path)
    def close(self):
        super().close()
        if self.capture is not None and self.capture_take is None:
            start = time.perf_counter_ns()
            try: self.capture.take_completed()
            except BaseException as error:
                self.capture.errors.append("take_failed:"+repr(error))
                raise
            finally:
                self.capture_take = {"start_ns": start, "end_ns": time.perf_counter_ns()}
    def diagnostic(self, spans):
        return {"schema": "g31.original_route_native027_phase_capture.v1", "timed": self._timed,
            "capacity": CAPACITY, "capture_setup": self.capture_setup, "capture_take": self.capture_take,
            "python_spans": deepcopy(spans.rows),
            "native_batches": deepcopy(self.capture.batches) if self.capture is not None else [],
            "native_envelopes": deepcopy(self.capture.envelopes) if self.capture is not None else [],
            "capture_errors": deepcopy(self.capture.errors) if self.capture is not None else [],
            "complete_computation_available": False, "physics_subtracted_ns": 0}


def validate_python_spans(rows):
    children = {}; prior_start = -1
    phases = {"request_service_invocation", "request_public_observation_and_filter", "candidate_and_intent_update"}
    for index, row in enumerate(rows):
        require(type(row["id"]) is int and row["id"] == index and row["phase"] in phases and row["exception"] is False, "python_span_domain")
        require(all(type(row[k]) is int for k in ("start_ns", "end_ns")) and
            0 <= row["start_ns"] <= row["end_ns"] and prior_start <= row["start_ns"], "python_span_time")
        prior_start = row["start_ns"]
        parent = row["parent"]
        if parent is None:
            require(row["phase"] == "request_service_invocation", "python_outer_phase")
        else:
            require(type(parent) is int and 0 <= parent < index and
                rows[parent]["start_ns"] <= row["start_ns"] <= row["end_ns"] <= rows[parent]["end_ns"], "python_span_parent")
        children.setdefault(parent, []).append(row)
    for group in children.values():
        require(all(a["end_ns"] <= b["start_ns"] for a, b in zip(group, group[1:])), "python_span_overlap")
    return children



def root_native_phases(batches, envelopes):
    """Subset only after the complete trace passed the native validator."""
    selected={e["call_ordinal"] for e in envelopes}
    rows=[r for batch in batches for r in batch["rows"] if r["call_ordinal"] in selected]
    child_duration={}
    for row in rows:
        parent=row["parent_span_id"]
        child_duration[parent]=child_duration.get(parent,0)+row["end_ns"]-row["start_ns"]
    phases={}; inner=0
    for row in rows:
        phase=ABI027["RequestTimingPhase"][row["phase"]]
        duration=row["end_ns"]-row["start_ns"]
        exclusive=duration-child_duration.get(row["span_id"],0)
        require(exclusive>=0,"root_native_negative_exclusive")
        phases[phase]=phases.get(phase,0)+exclusive
        if row["parent_span_id"]==-1:inner+=duration
    envelope=sum(e["end_ns"]-e["start_ns"] for e in envelopes)
    require(sum(phases.values())==inner<=envelope,"root_native_phase_conservation")
    return {"exclusive_ns_by_phase":phases,"native_inner_total_ns":inner,
        "binding_and_wrapper_remainder_ns":envelope-inner,"whole_native_envelope_ns":envelope,
        "call_count":len(envelopes),"span_count":len(rows),"physics_subtracted_ns":0,
        "scope":"All native calls inside the actual root, including shared/background work, charged fully. Labels are broad bundles; physical_dispatch is not an exemption. No complete-computation attribution is inferred."}

def summarize(diagnostic, tape, root, events):
    """Conserve native envelopes, Python service intervals and all other gaps.

    Native enum labels describe broad bundles. Their exclusive totals are
    useful diagnostics, never a whitelist for subtracting physical work.
    """
    require(diagnostic["timed"] is True and diagnostic["capacity"] == CAPACITY and
        not diagnostic["capture_errors"], "capture_incomplete")
    partition = analyze_candidate_partition(diagnostic["native_batches"], diagnostic["native_envelopes"])
    require(partition["status"] == "structurally_valid_native027_candidate_partition", "native_partition_unknown")
    envelopes = diagnostic["native_envelopes"]
    require(len(envelopes) == len(tape), "native_tape_denominator")
    for env, row in zip(envelopes, tape, strict=True):
        require(env["api_endpoint"] == row["endpoint"] and
            row["start_ns"] <= env["start_ns"] <= env["end_ns"] <= row["end_ns"], "native_tape_binding")
        if row["endpoint"] in {"submit_protocol_transfer", "submit_protocol_command"}:
            require(env["protocol_request_id"] == row["args"][0]["request_id"], "native_submission_identity")
        if row["endpoint"] in {"protocol_request", "protocol_command"}:
            require(env["protocol_request_id"] == row["args"][1], "native_query_identity")
    rows = diagnostic["python_spans"]; children = validate_python_spans(rows)
    require(rows and len(children.get(None, [])) == len(root["steps"]), "python_invocation_denominator")
    start = root["started_ns"]; end = root["returned_ns"] if root["returned_ns"] is not None else root["censored_ns"]
    require(type(start) is int and type(end) is int and start <= end, "root_window")
    setup, take = diagnostic["capture_setup"], diagnostic["capture_take"]
    require(setup is not None and take is not None and 0 <= setup["start_ns"] <= setup["end_ns"] <= start
        and end <= take["start_ns"] <= take["end_ns"], "diagnostic_setup_take_scope")
    # _step records a tiny diagnostic tail after the root's final codec clock.
    # Keep that tail separately; never expand or silently trim the true root.
    service = [r for r in rows if r["parent"] is None]
    require(all(start <= r["start_ns"] <= end for r in service), "service_outside_root")
    native = [e for e in envelopes if start <= e["start_ns"] and e["end_ns"] <= end]
    require(not any(e["start_ns"] < edge < e["end_ns"] for e in envelopes for edge in (start,end)), "root_cuts_native_call")
    require(len(service)==len(events)==len(root["steps"]),"service_event_denominator")
    for measured,event,step in zip(service,events,root["steps"],strict=True):
        require(type(measured.get("initial")) is bool and measured["initial"] is event["initial"] is step["initial"]
            and measured.get("at")==event["at"]==step["at"],"service_event_identity")
        first,after=event["first_api"],event["after_api"]
        require(type(first) is int and type(after) is int and 0 <= first < after <=len(tape),"service_event_range")
        selected=tape[first:after]
        require(all(r["role"]=="request" for r in selected) and
            measured["start_ns"] <= selected[0]["start_ns"] <= selected[-1]["end_ns"] <= measured["end_ns"],
            "service_event_interval")
        require((first==0 or tape[first-1]["end_ns"]<=measured["start_ns"]) and
            (after==len(tape) or measured["end_ns"]<=tape[after]["start_ns"]),"service_event_coverage")
    native_ns = sum(e["end_ns"]-e["start_ns"] for e in native)
    service_native = sum(e["end_ns"]-e["start_ns"] for e in native
        if any(s["start_ns"] <= e["start_ns"] and e["end_ns"] <= s["end_ns"] for s in service))
    service_ns = sum(min(s["end_ns"], end)-s["start_ns"] for s in service)
    python_service = service_ns-service_native
    other = end-start-native_ns-python_service
    require(python_service >= 0 and other >= 0, "root_partition_negative")
    phases = {}
    for row in rows:
        value = row["end_ns"]-row["start_ns"]-sum(c["end_ns"]-c["start_ns"] for c in children.get(row["id"], []))
        phases[row["phase"]] = phases.get(row["phase"], 0)+value
    return {"status": "validated_partial_root_phase_diagnostics", "native_partition_all_warm_calls": partition,
        "root_total_ns": end-start, "root_native_envelope_ns": native_ns,
        "root_native_phase_bundles":root_native_phases(diagnostic["native_batches"],native),
        "root_python_request_service_remainder_ns": python_service, "root_other_unclassified_ns": other,
        "partition_exact": native_ns+python_service+other == end-start,
        "python_exclusive_bundles_including_nested_native_ns": phases,
        "max_request_service_invocation_ns": max(r["end_ns"]-r["start_ns"] for r in service),
        "diagnostic_step_tail_outside_root_ns": sum(max(0, r["end_ns"]-end) for r in service),
        "scope": "Service maximum is the measured request invocation, not the maximum of all background executor services. Python bundle table includes nested native envelopes and must not be added to native totals. All native/Python/shared remainder remains charged.",
        "complete_computation_available": False, "complete_100ms_certified": False, "physics_subtracted_ns": 0}
