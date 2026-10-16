import copy

import pytest

from scripts.experiments.g31_ics_circulation.request_spans import summarize_request_spans


def trace():
    request = {"request_id": "r", "owner_id": "A"}
    return {"wall_seconds": .05, "controller_state": {"client": {"outbox": {"r": {"terminal": True}}}},
        "client_calls": [{"at": 0., "retry": False, "kind": "transfer", "request": request,
                          "submit_compute_ms": 999}],
        "control_records": [
            {"trace_sequence": 0, "at": 0., "owner_id": "A", "compute_wall_ms": 10.,
             "attempts": [{"request_id": "r", "reply": {"status": "pending"}}]},
            {"trace_sequence": 2, "at": 5., "owner_id": "A", "compute_wall_ms": 10.,
             "refreshed": [{"request_id": "r", "view": {"last_delivered_ack": {
                 "status": "received", "delivered_at": 4.5}}}]}],
        "native_batches": [{"trace_sequence": 1, "start_at": 0., "end_at": 5., "wall_ms": 20.}]}


def test_full_chain_exclusive_envelopes_do_not_double_bill_submit():
    result = summarize_request_spans(trace())
    assert result["status"] == "complete_conservative_accounting"
    row = result["requests"][0]
    assert row["compute_upper_ms"] == pytest.approx(50.)
    assert row["native_compute_upper_ms"] == 20.
    assert row["end_to_end_logical_seconds"] == 5.
    assert result["shared_scheduler_residual_upper_ms"] == pytest.approx(10.)
    assert not result["complete_100ms_requirement_certified"]


def test_shared_native_cost_is_not_divided_by_batch_and_failure_not_dropped():
    run = trace()
    request = {"request_id": "s", "owner_id": "B"}
    run["client_calls"].append({"at": 0., "retry": False, "kind": "route", "request": request})
    run["control_records"].insert(1, {"trace_sequence": 1, "at": 0., "owner_id": "B",
        "compute_wall_ms": 3., "attempts": [{"request_id": "s", "reply": {"status": "pending"}}]})
    run["native_batches"][0]["trace_sequence"] = 2
    run["control_records"][-1]["trace_sequence"] = 3
    run["control_records"].append({"trace_sequence": 4, "at": 5., "owner_id": "B",
        "compute_wall_ms": 2., "refreshed": [{"request_id": "s", "view": {
            "last_delivered_ack": {"status": "rejected", "delivered_at": 5.}}}]})
    result = summarize_request_spans(run)
    assert result["request_count"] == 2
    assert all(r["native_compute_upper_ms"] == 20. for r in result["requests"])
    assert result["terminal_status_counts"] == {"received": 1, "rejected": 1}


def test_open_requests_and_retries_remain_in_denominator():
    run = trace()
    run["controller_state"]["client"]["outbox"]["r"]["terminal"] = False
    run["control_records"][-1]["refreshed"] = []
    retry = copy.deepcopy(run["client_calls"][0]); retry["retry"] = True
    run["client_calls"].append(retry)
    result = summarize_request_spans(run)
    assert result["request_count"] == 1 and result["retry_count"] == 1
    assert result["open_request_count"] == 1
    assert result["requests"][0]["status"] == "unknown_open"
    assert result["requests"][0]["compute_upper_scope"] == "observed_prefix"
    assert result["requests"][0]["complete_request_compute_upper_ms"] is None
    assert result["max_complete_request_upper_ms"] is None


def test_missing_or_duplicate_order_cannot_certify():
    run = trace(); run["native_batches"][0].pop("trace_sequence")
    assert summarize_request_spans(run)["status"].startswith("unknown")
    run = trace(); run["native_batches"][0]["trace_sequence"] = 0
    assert summarize_request_spans(run)["status"].startswith("unknown")


def test_mutated_retry_is_rejected():
    run = trace()
    retry = copy.deepcopy(run["client_calls"][0]); retry["request"]["owner_id"] = "B"
    run["client_calls"].append(retry)
    with pytest.raises(ValueError, match="mutated_retry"):
        summarize_request_spans(run)


def test_missing_creation_or_negative_residual_is_unknown():
    run = trace(); run["control_records"][0]["attempts"] = []
    assert summarize_request_spans(run)["status"] == "unknown_incomplete_trace"


def test_resumed_or_truncated_trace_keeps_prior_outbox_denominator():
    run = trace(); run["client_calls"] = []
    result = summarize_request_spans(run)
    assert result["status"] == "unknown_missing_request_history"
    assert result["request_count"] == 1
    assert result["untraced_request_ids"] == ["r"]
    assert result["requests"][0]["compute_upper_ms"] is None


def test_trace_beginning_at_retry_cannot_certify_initial_computation():
    run = trace(); run["client_calls"][0]["retry"] = True
    result = summarize_request_spans(run)
    assert result["status"] == "unknown_incomplete_trace"
    assert {"request_id": "r", "reason": "missing_initial_submission"} in result["errors"]
    run = trace(); run["wall_seconds"] = .001
    assert summarize_request_spans(run)["status"] == "unknown_incomplete_trace"


def assert_unknown_with_full_denominator(run):
    result = summarize_request_spans(run)
    assert result["status"].startswith("unknown")
    assert result["request_count"] == 1
    assert result["requests"][0]["request_id"] == "r"
    assert result["requests"][0]["compute_upper_ms"] is None
    return result


def test_native_before_creation_cannot_silently_drop_request_compute():
    run = trace()
    run["control_records"][0]["trace_sequence"] = 1
    run["native_batches"][0]["trace_sequence"] = 0
    result = assert_unknown_with_full_denominator(run)
    assert any(e["reason"] == "invalid_or_reversed_physical_trace_time" for e in result["errors"])


@pytest.mark.parametrize("sequences", [(1, 2, 3), (0, 2, 3), (-1, 0, 1)])
def test_missing_prefix_and_sequence_gaps_keep_requests_unknown(sequences):
    run = trace()
    run["control_records"][0]["trace_sequence"], run["native_batches"][0]["trace_sequence"], run["control_records"][1]["trace_sequence"] = sequences
    result = assert_unknown_with_full_denominator(run)
    assert result["errors"] == [{"reason": "missing_trace_prefix_or_sequence_gap"}]


@pytest.mark.parametrize("problem", ["creation_time", "creation_owner", "native_reverse", "owner_nonfinite",
                                    "ack_future", "ack_before_creation", "ack_owner", "retry_time"])
def test_invalid_physical_call_or_ack_order_fails_closed(problem):
    run = trace()
    if problem == "creation_time":
        run["client_calls"][0]["at"] = .5
    elif problem == "creation_owner":
        run["control_records"][0]["owner_id"] = "B"
    elif problem == "native_reverse":
        run["native_batches"][0]["end_at"] = -.1
    elif problem == "owner_nonfinite":
        run["control_records"][1]["at"] = float("nan")
    elif problem == "ack_future":
        run["control_records"][1]["refreshed"][0]["view"]["last_delivered_ack"]["delivered_at"] = 20.
    elif problem == "ack_before_creation":
        run["control_records"][1]["refreshed"][0]["view"]["last_delivered_ack"]["delivered_at"] = -.1
    elif problem == "ack_owner":
        run["control_records"][1]["owner_id"] = "B"
    else:
        call = copy.deepcopy(run["client_calls"][0])
        call.update(retry=True, at=2.)
        run["client_calls"].append(call)
    assert_unknown_with_full_denominator(run)


def test_unknown_order_retains_union_of_call_record_and_outbox_ids():
    run = trace()
    run["controller_state"]["client"]["outbox"]["old"] = {"terminal": False}
    run["control_records"][0]["attempts"].append({"request_id": "untraced", "reply": {"status": "pending"}})
    run["native_batches"][0]["trace_sequence"] = 0
    result = summarize_request_spans(run)
    assert result["status"].startswith("unknown") and result["request_count"] == 3
    assert {r["request_id"] for r in result["requests"]} == {"r", "old", "untraced"}
    assert all(r["compute_upper_ms"] is None for r in result["requests"])


def test_duplicate_initial_submission_is_not_a_valid_retry_history():
    run = trace()
    run["client_calls"].append(copy.deepcopy(run["client_calls"][0]))
    result = assert_unknown_with_full_denominator(run)
    assert {"request_id": "r", "reason": "duplicate_initial_submission"} in result["errors"]
