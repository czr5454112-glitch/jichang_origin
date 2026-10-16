"""Partial native phase evidence never becomes a discounted complete total."""
import copy
from pathlib import Path
import re

import pytest

from scripts.experiments.g31_ics_circulation.native_request_timing import (
    analyze_native_timing, PHASES, METHODS, IDENTITIES)


def row(sid, parent, start, end, phase, *, method=0, kind=0, index=-1, related=0, related_index=-1):
    return {"span_id": sid, "parent_span_id": parent, "start_ns": start, "end_ns": end,
        "phase": phase, "method": method, "trace_epoch": 1, "call_ordinal": 1,
        "event_sequence": 0, "logical_time": 2., "attempt": 1,
        "identity_kind": kind, "identity_index": index,
        "related_identity_kind": related, "related_identity_index": related_index,
        "ended": True, "exception_exit": False}


def fixture():
    batch = {"schema": "g31.native_request_timing.v1", "clock": "steady_clock_relative_nanoseconds",
        "coverage": "known_control_phases_and_unclassified_remainder", "physics_subtraction_authorized": False,
        "session_identity": 15, "trace_epoch": 1, "errors": 0, "completed_outer_calls": 1, "emitted_span_count": 4,
        "rows": [row(0, -1, 0, 100, 0, method=11), row(1, 0, 10, 20, 5, kind=1, index=0),
                 row(2, 0, 20, 30, 6, kind=1, index=0), row(3, 0, 30, 40, 8, kind=1, index=0)],
        "transfer_identities": [{"index": 0, "request_id": "live:A:transfer:0"}],
        "command_identities": [], "leg_identities": [], "job_identities": []}
    envelope = {"session_identity": 15, "trace_epoch": 1, "call_ordinal": 1,
        "start_ns": 5000, "end_ns": 5105, "method": 11}
    return [batch], [envelope]


def test_exclusive_partition_keeps_all_native_and_binding_remainder():
    batches, envelopes = fixture()
    report = analyze_native_timing(batches, envelopes)
    assert report["status"] == "validated_partial_native_phase_partition", report
    assert report["identified_control_bundle_ns"] == 30
    assert report["unclassified_native_remainder_ns"] == 70
    assert report["python_binding_remainder_ns"] == 5
    assert report["unchanged_whole_native_envelope_ns"] == 105
    assert report["physics_subtracted_ns"] == 0
    assert report["complete_request_100ms_certified"] is False
    assert report["refined_per_request_totals_available"] is False


def test_rejected_submission_with_no_native_row_links_actual_call_argument():
    batches, envelopes = fixture()
    batches[0]["rows"] = [row(0, -1, 0, 50, 0, method=1, kind=5)]
    batches[0]["emitted_span_count"] = 1
    batches[0]["transfer_identities"] = []
    envelopes[0].update(method=1, protocol_request_id="invalid-request-is-still-counted")
    report = analyze_native_timing(batches, envelopes)
    assert report["status"] == "validated_partial_native_phase_partition"
    assert report["identified_control_bundle_ns"] == 50
    del envelopes[0]["protocol_request_id"]
    assert analyze_native_timing(batches, envelopes)["status"] == "unknown"


def test_nested_result_advance_is_not_double_counted():
    batches, envelopes = fixture()
    batches[0]["rows"] = [row(0, -1, 0, 100, 0, method=13), row(1, 0, 10, 80, 0, method=12),
                           row(2, 1, 20, 60, 1), row(3, 2, 30, 40, 8, kind=1, index=0)]
    envelopes[0]["method"] = 13
    report = analyze_native_timing(batches, envelopes)
    assert report["status"] == "validated_partial_native_phase_partition"
    assert report["identified_control_bundle_ns"] == 10
    assert sum(report["exclusive_ns_by_phase"].values()) == 100
    assert report["unchanged_whole_native_envelope_ns"] == 105


@pytest.mark.parametrize("defect", ["overflow", "missing_end", "exception", "missing_call", "missing_span",
    "unknown_phase", "overlap", "duplicate_span", "native_longer_than_outer", "negative_time",
    "missing_identity", "wrong_epoch", "bool_time", "method_mismatch", "nan_logical",
    "deleted_middle_leaf", "deleted_final_leaf", "reordered_rows"])
def test_incomplete_or_tampered_trace_fails_closed(defect):
    batches, envelopes = fixture(); batch = batches[0]
    if defect == "overflow": batch["errors"] = 1
    elif defect == "missing_end": batch["rows"][1]["ended"] = False
    elif defect == "exception": batch["rows"][1]["exception_exit"] = True
    elif defect == "missing_call": batch["completed_outer_calls"] = 2
    elif defect == "missing_span": batch["rows"].pop(0)
    elif defect == "unknown_phase": batch["rows"][1]["phase"] = 999
    elif defect == "overlap": batch["rows"][2]["start_ns"] = 19
    elif defect == "duplicate_span": batch["rows"].append(copy.deepcopy(batch["rows"][1]))
    elif defect == "native_longer_than_outer": envelopes[0]["end_ns"] = 5099
    elif defect == "negative_time": batch["rows"][1]["start_ns"] = -1
    elif defect == "missing_identity": batch["transfer_identities"] = []
    elif defect == "wrong_epoch": batch["trace_epoch"] = 2
    elif defect == "bool_time": batch["rows"][1]["start_ns"] = True
    elif defect == "method_mismatch": envelopes[0]["method"] = 12
    elif defect == "nan_logical": batch["rows"][1]["logical_time"] = float("nan")
    elif defect == "deleted_middle_leaf": batch["rows"].pop(2)
    elif defect == "deleted_final_leaf": batch["rows"].pop()
    elif defect == "reordered_rows": batch["rows"][1:3] = reversed(batch["rows"][1:3])
    report = analyze_native_timing(batches, envelopes)
    assert report["status"] == "unknown", (defect, report)
    assert report["errors"] and not report["complete_request_100ms_certified"]


def test_old_leg_immutable_transfer_relation_survives_later_tray_reuse():
    batches, envelopes = fixture()
    batches[0]["leg_identities"] = [{"index": 4, "transport_leg_id": "opaque-name", "job_index": -1,
                                     "tray_index": 0, "kind": "empty_return"}]
    batches[0]["rows"][1] = row(1, 0, 10, 20, 23, kind=3, index=4, related=1, related_index=0)
    batches[0]["rows"][2] = row(2, 0, 20, 30, 11, kind=3, index=4)
    assert analyze_native_timing(batches, envelopes)["status"] == "validated_partial_native_phase_partition"
    batches[0]["rows"][2].update(related_identity_kind=1, related_identity_index=7)
    assert analyze_native_timing(batches, envelopes)["errors"] == ["conflicting_immutable_leg_relation"]


def test_unmapped_completed_empty_leg_is_unknown_not_guessed_from_text():
    batches, envelopes = fixture()
    batches[0]["leg_identities"] = [{"index": 4, "transport_leg_id": "live:A:transfer:0:empty_return:4",
                                     "job_index": -1, "tray_index": 0, "kind": "empty_return"}]
    batches[0]["rows"][1].update(identity_kind=3, identity_index=4)
    assert analyze_native_timing(batches, envelopes)["errors"] == ["missing_immutable_leg_relation"]


def test_sequential_takes_keep_counter_and_identity_continuity():
    batches, envelopes = fixture()
    second = copy.deepcopy(batches[0]); second["completed_outer_calls"] = 2; second["emitted_span_count"] = 8
    for r in second["rows"]:
        r["span_id"] += 4
        if r["parent_span_id"] >= 0: r["parent_span_id"] += 4
        r["call_ordinal"] = 2; r["start_ns"] += 200; r["end_ns"] += 200
    batches.append(second)
    envelopes.append({**envelopes[0], "call_ordinal": 2, "start_ns": 6000, "end_ns": 6105})
    assert analyze_native_timing(batches, envelopes)["unchanged_whole_native_envelope_ns"] == 210
    second["transfer_identities"][0]["request_id"] = "silently-changed"
    assert analyze_native_timing(batches, envelopes)["errors"] == ["mutated_native_identity"]


def test_cpp_python_enum_abi_is_exact():
    from scripts.experiments.g31_ics_circulation.native025_request_timing import exact_header_abi, ABI025
    header = Path("cpp/ics_core/runtime/request_timing_recorder.hpp").read_text(encoding="utf-8")
    version, actual = exact_header_abi(header)
    assert actual["RequestTimingPhase"] == PHASES
    assert actual["RequestTimingMethod"] == METHODS
    assert actual["RequestTimingIdentity"][:len(IDENTITIES)] == IDENTITIES
    assert actual["RequestTimingIdentity"] == (IDENTITIES if version == "native022" else ABI025["RequestTimingIdentity"])


def test_proxy_preserves_recent_capability_and_forwards_exact_response():
    from scripts.experiments.g31_ics_circulation.capture_native_request_timing import capture_session
    class Session:
        physical_time = 3.
        def offline_request_timing_start(self, capacity, identity): self.start = (capacity, identity)
        def offline_request_timing_take(self):
            return {"rows": [], "errors": 0, "completed_outer_calls": 0, "trace_epoch": 7, "session_identity": 9}
        def observe_protocol_control_policy_recent(self, owner, forecast_validity):
            self.args = (owner, forecast_validity)
            return response
    response = {"sentinel": object()}
    session = Session(); proxy = capture_session(session, capacity=3, session_identity=9)
    assert hasattr(type(proxy), "observe_protocol_control_policy_recent")
    assert proxy.observe_protocol_control_policy_recent("A", 120.) is response
    assert session.args == ("A", 120.) and proxy.physical_time == 3.
    assert proxy.envelopes[0]["trace_epoch"] == 7 and proxy.envelopes[0]["method"] == 8
    with pytest.raises(ValueError, match="unclassified_endpoint"):
        proxy.owner_notifications(["A"])


def test_proxy_exceptions_retain_failed_call_without_dropping_denominator():
    from scripts.experiments.g31_ics_circulation.capture_native_request_timing import capture_session
    class Session:
        def offline_request_timing_start(self, capacity, identity): pass
        def offline_request_timing_take(self):
            return {"rows": [], "errors": 0, "completed_outer_calls": 0, "trace_epoch": 1, "session_identity": 1}
        def submit_protocol_command(self, payload): raise ValueError("bad actual payload")
    proxy = capture_session(Session(), session_identity=1)
    assert not hasattr(type(proxy), "observe_protocol_control_policy_recent")
    assert not hasattr(type(proxy), "observe_protocol_control_policy")
    with pytest.raises(ValueError, match="bad actual payload"):
        proxy.submit_protocol_command({"request_id": "bad-id"})
    assert len(proxy.envelopes) == 1 and proxy.envelopes[0]["protocol_request_id"] == "bad-id"
    assert proxy.errors == ["ValueError:bad actual payload"]


def test_capture_requires_explicit_namespace_before_touching_native():
    from scripts.experiments.g31_ics_circulation.capture_native_request_timing import capture_session
    with pytest.raises(TypeError, match="session_identity"):
        capture_session(object())
    for invalid in (0, -1, True, 1.5, 2**64):
        with pytest.raises(ValueError, match="invalid_session_identity"):
            capture_session(object(), session_identity=invalid)


def test_campaign_namespaces_keep_parent_and_fork_distinct():
    from scripts.experiments.g31_ics_circulation.capture_native_request_timing import CaptureNamespaces
    parent, child = object(), object()
    registry = CaptureNamespaces()
    assert registry.identity_for(parent) == 1
    assert registry.identity_for(child) == 2
    assert registry.identity_for(parent) == 1


def test_capture_rejects_native_namespace_mismatch():
    from scripts.experiments.g31_ics_circulation.capture_native_request_timing import capture_session
    class Session:
        def offline_request_timing_start(self, capacity, identity): pass
        def offline_request_timing_take(self):
            return {"rows": [], "errors": 0, "completed_outer_calls": 0, "trace_epoch": 1, "session_identity": 2}
    with pytest.raises(ValueError, match="session_identity_mismatch"):
        capture_session(Session(), session_identity=1)
