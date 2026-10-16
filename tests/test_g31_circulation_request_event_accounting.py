"""Counterexamples to diluted/shared/missing request-time accounting."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation import request_event_accounting as timing


MS = 1_000_000


def phases(required, measured=()):
    return {p: "measured" if p in measured else {"not_applicable": "No operation of this kind in this explicit test case."}
            for p in required}


def root(rid="r", status="no_action", end=100*MS):
    return {"request_id": rid, "opened_ns": 0, "closed_ns": end, "status": status,
            "business_job_ids": [], "phase_coverage": phases(timing.ROOT_PHASES, ("observe",))}


def span(sid, start, end, *, parent=None, deps=("r",), phase="observe", kind="control", **extra):
    return {"span_id": sid, "start_ns": start, "end_ns": end,
        "parent_span_id": parent, "root_request_ids": list(deps), "phase": phase,
        "work_class": kind, **extra}


def ledger():
    return {"schema": timing.SCHEMA, "clock": "monotonic_ns", "execution_lanes": 1,
        "request_scope": "owner_activation_updates", "coverage_complete": True,
        "service_windows": [{"start_ns": 0, "end_ns": 100*MS}],
        "requests": [root()], "messages": [], "spans": [span("outer", 0, 100*MS)]}


def test_no_action_is_a_full_root_and_exact_budget_is_allowed():
    raw = ledger()
    before = copy.deepcopy(raw)
    report = timing.analyze_ledger(raw)
    assert report["status"] == "complete_measured_accounting"
    assert report["request_count"] == 1
    assert report["status_counts"] == {"no_action": 1}
    assert report["requests"][0]["complete_request_compute_ns"] == 100*MS
    assert report["all_observed_requests_within_100ms"] is True
    assert report["complete_business_requirement_certified"] is False
    assert raw == before


def test_nested_submit_is_exclusive_and_shared_work_is_never_divided():
    raw = ledger()
    raw["requests"].append(root("other"))
    raw["spans"][0]["root_request_ids"].append("other")
    raw["spans"].append(span("nested", 20*MS, 90*MS, parent="outer", deps=(), phase="submit"))
    for r in raw["requests"]:
        r["phase_coverage"]["submit"] = "measured"
    report = timing.analyze_ledger(raw)
    assert report["status"] == "complete_measured_accounting"
    assert [r["complete_request_compute_ns"] for r in report["requests"]] == [100*MS, 100*MS]
    assert report["exclusive_work_ns_by_class"]["control"] == 100*MS


def test_accumulated_compute_and_continuous_segment_are_different_from_wait():
    raw = ledger()
    raw["spans"].append(span("wait", 30*MS, 70*MS, parent="outer", deps=(), kind="wait",
                             exclusion_reason="Measured wall-clock transport wait; no execution in this interval."))
    raw["requests"][0].update(logical_opened_at=5., logical_closed_at=105.)
    report = timing.analyze_ledger(raw)
    row = report["requests"][0]
    assert row["complete_request_compute_ns"] == 60*MS
    assert row["max_continuous_compute_ns"] == 30*MS
    assert row["root_wall_elapsed_ns"] == 100*MS
    assert row["logical_end_to_end_seconds"] == 100
    assert row["logical_queue_transport_split"] == "unmeasured"


def test_native_validation_is_counted_even_when_nested_inside_physics_envelope():
    raw = ledger()
    raw["spans"][0].update(work_class="physics", phase="advance", exclusion_reason="Instrumented physical event processing only.")
    raw["spans"] += [span("local", 0, 10*MS, parent="outer"),
        span("serialize", MS, 2*MS, parent="local", phase="serialize", protocol_request_id="m"),
        span("submit", 2*MS, 3*MS, parent="local", phase="submit", protocol_request_id="m"),
        span("ack", 3*MS, 4*MS, parent="local", phase="ack", protocol_request_id="m"),
        span("validate", 20*MS, 40*MS, parent="outer", phase="source_validate", protocol_request_id="m")]
    raw["requests"][0]["phase_coverage"].update(serialize="measured", submit="measured")
    raw["messages"] = [{"request_id": "m", "root_request_ids": ["r"], "status": "rejected",
        "phase_coverage": phases(timing.MESSAGE_PHASES, ("serialize", "submit", "source_validate", "ack"))}]
    report = timing.analyze_ledger(raw)
    assert report["status"] == "complete_measured_accounting"
    assert report["requests"][0]["complete_request_compute_ns"] == 30*MS
    assert report["exclusive_work_ns_by_class"]["physics"] == 70*MS


def test_each_child_message_needs_its_own_native_stage_measurements():
    raw = ledger()
    raw["messages"] = [{"request_id": mid, "root_request_ids": ["r"], "status": "received",
        "phase_coverage": phases(timing.MESSAGE_PHASES, ("receiver_validate",))} for mid in ("m1", "m2")]
    raw["spans"].append(span("validation", 1, 2, parent="outer", phase="receiver_validate", protocol_request_id="m1"))
    report = timing.analyze_ledger(raw)
    assert report["status"] == "unknown_incomplete_measurement"
    assert "declared_phase_not_measured:m2:receiver_validate" in report["errors"]
    assert report["all_observed_requests_within_100ms"] is None


def test_a_terminal_message_cannot_declare_every_operation_not_applicable():
    raw = ledger()
    raw["messages"] = [{"request_id": "m", "root_request_ids": ["r"], "status": "received",
        "phase_coverage": phases(timing.MESSAGE_PHASES)}]
    report = timing.analyze_ledger(raw)
    assert report["status"] == "unknown_incomplete_measurement"
    for phase in ("serialize", "submit", "ack"):
        assert "mandatory_message_phase_unmeasured:m:" + phase in report["errors"]


@pytest.mark.parametrize("defect", ["gap", "unclassified_native", "unattributed", "missing_phase",
    "false_measured_phase", "open_root", "open_message", "not_instrumented", "empty_roots"])
def test_missing_coverage_cannot_produce_a_pass(defect):
    raw = ledger()
    if defect == "gap":
        raw["spans"][0]["start_ns"] = 1
    elif defect == "unclassified_native":
        raw["spans"].append(span("native", 10*MS, 20*MS, parent="outer", kind="unclassified", phase="advance"))
    elif defect == "unattributed":
        raw["spans"][0]["root_request_ids"] = []
    elif defect == "missing_phase":
        raw["requests"][0]["phase_coverage"].pop("serialize")
    elif defect == "false_measured_phase":
        raw["requests"][0]["phase_coverage"]["serialize"] = "measured"
    elif defect == "open_root":
        raw["requests"][0].update(status="open", closed_ns=None)
    elif defect == "open_message":
        raw["messages"] = [{"request_id": "m", "root_request_ids": ["r"], "status": "pending",
            "phase_coverage": phases(timing.MESSAGE_PHASES)}]
    elif defect == "not_instrumented":
        raw["coverage_complete"] = False
    else:
        raw["requests"] = []
        raw["spans"][0]["root_request_ids"] = []
    report = timing.analyze_ledger(raw)
    assert report["status"].startswith("unknown")
    assert report["all_observed_requests_within_100ms"] is None


@pytest.mark.parametrize("defect", ["overlap", "cycle", "clock", "parallel", "out_of_lifetime", "bad_dependency"])
def test_invalid_interval_or_identity_never_looks_measured(defect):
    raw = ledger()
    if defect == "overlap":
        raw["spans"] += [span("a", 10*MS, 30*MS, parent="outer"), span("b", 20*MS, 40*MS, parent="outer")]
    elif defect == "cycle":
        raw["spans"][0]["parent_span_id"] = "outer"
    elif defect == "clock":
        raw["clock"] = "physical_simulation_seconds"
    elif defect == "parallel":
        raw["execution_lanes"] = 2
    elif defect == "out_of_lifetime":
        raw["requests"][0]["opened_ns"] = 1
    else:
        raw["spans"][0]["root_request_ids"] = ["missing"]
    report = timing.analyze_ledger(raw)
    assert report["status"] == "unknown_invalid_ledger"
    assert report["all_observed_requests_within_100ms"] is None


def test_one_nanosecond_exceedance_is_not_rounded_or_averaged_away():
    raw = ledger()
    raw["service_windows"][0]["end_ns"] += 1
    raw["spans"][0]["end_ns"] += 1
    raw["requests"][0]["closed_ns"] += 1
    report = timing.analyze_ledger(raw)
    assert report["status"] == "complete_measured_accounting"
    assert report["known_over_budget_count"] == 1
    assert report["all_observed_requests_within_100ms"] is False
