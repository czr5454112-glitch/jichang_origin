from copy import deepcopy
import json

import pytest

from scripts.experiments.g31_ics_circulation.original_notification_contract import NotificationLedger, eligible_jobs


def view():
    jobs = []
    for identity, status in (("waiting", "waiting_for_tray"), ("remote", "handed_off"), ("done", "completed")):
        jobs.append({"business_bag_id": identity, "origin": 0, "destination": 1, "arrival": 1., "status": status,
            "deadline": 100., "storage_node": -1, "storage_release_at": 0., "storage_min_dwell": 0.,
            "load_seconds": 0., "unload_seconds": 0., "hold_seconds": 0., "protected_service": True,
            "allow_suffix_reroute": False})
    return {"schema": "g31.owner_protocol_observation.v1", "owner_id": "A", "now": 2., "jobs": jobs,
            "trays": [], "node_contracts": [{"node": 0, "resource_owner": "A"}, {"node": 1, "resource_owner": "B"}]}


def setup(observation=None):
    ledger = NotificationLedger(["A", "B"])
    ledger.begin("batch0", at=0., wall_ns=10)
    response = {"status": "notified", "timestamp_complete": True, "physical_time": 2.,
                "notifications": {"A": {"sequence": 4, "observed_at": 2., "change_mask": 3}}}
    roots = ledger.notified("batch0", response, wall_ns=20, call_ordinal=1)
    ledger.observe(roots[0], observation or view(), start_ns=21, end_ns=30, call_ordinal=2)
    return ledger, roots[0]


def submit(ledger, root, identity="request0", kind="transfer"):
    payload = {"request_id": identity, "owner_id": "A", "tray_id": "T"}
    ledger.submit(root, identity, kind, payload, at=2., wall_ns=40)
    return payload


def ack(ledger, identity="request0", status="received"):
    ledger.handle_ack(identity, {"request_id": identity, "sequence": 1, "status": status, "delivered_at": 3.},
                      at=3., wall_ns=60, query_ordinal=5)


def finish(ledger, root, disposition, *, at=3.):
    ledger.finish(root, drain={"status": "reached", "horizon_complete": True, "physical_time": at},
        drain_start_ns=70, drain_end_ns=80, output_end_ns=90, drain_ordinal=6,
        encoded_output=json.dumps({"root_id": root, "disposition": disposition,
                                   "operation_ids": ledger.roots[root]["operations"]}))


def test_handed_off_is_retained_and_completed_explicitly_excluded():
    result = eligible_jobs(view(), "A")
    assert result["eligible_job_ids"] == ["waiting", "remote"]
    assert result["excluded_completed_job_ids"] == ["done"]
    assert result["classification"]["remote"] == "remote_progress_unknown"
    assert result["affected_job_scope_verified"] is False


@pytest.mark.parametrize("change", [
    lambda v: v["jobs"].append(deepcopy(v["jobs"][0])),
    lambda v: v["jobs"][0].pop("destination"),
    lambda v: v["jobs"][0].update(status="invented"),
    lambda v: v["jobs"][0].update(arrival=3.),
    lambda v: v["jobs"][0].update(origin=1),
    lambda v: v["trays"].append({"node": 0, "business_bag_id": "missing"}),
    lambda v: v["trays"].append({"node": 1, "business_bag_id": "waiting"}),
    lambda v: v.update(schema="compact_or_invented"),
])
def test_malformed_unowned_or_missing_contract_never_dropped(change):
    data = view(); change(data)
    with pytest.raises(ValueError): eligible_jobs(data, "A")


def test_whole_shared_trigger_setup_and_completion_to_every_child():
    ledger, root = setup(); submit(ledger, root); ack(ledger); finish(ledger, root, "completed")
    report = ledger.accounting(mandatory_setup_ns=1000, known_end_ns=100)
    row = report["roots"][root]
    assert row["complete_compute_upper_ns"] == 1080
    assert [x["complete_compute_upper_ns"] for x in row["job_children"].values()] == [1080, 1080]
    assert report["job_child_denominator"] == 2
    assert report["original_offered_jobs"] == 28506
    assert report["original_business_request_100ms_certified"] is False


def test_lost_ack_and_immutable_retry_keeps_all_children_open():
    ledger, root = setup(); payload = submit(ledger, root)
    ledger.submit(root, "request0", "transfer", payload, at=62., wall_ns=65, retry=True)
    with pytest.raises(ValueError, match="pending_ack"): finish(ledger, root, "completed", at=63.)
    row = ledger.accounting(mandatory_setup_ns=1000, known_end_ns=100)["roots"][root]
    assert row["complete_compute_upper_ns"] is None
    assert all(x["complete_compute_upper_ns"] is None for x in row["job_children"].values())
    assert len(ledger.operations["request0"]["attempts"]) == 2


def test_rejection_closes_explicit_terminal_failure_without_success_promotion():
    ledger, root = setup(); submit(ledger, root); ack(ledger, status="rejected")
    with pytest.raises(ValueError, match="output_not_bound"): finish(ledger, root, "completed")
    finish(ledger, root, "terminal_failure")
    assert ledger.roots[root]["output"]["disposition"] == "terminal_failure"


def test_no_job_no_action_still_has_bundle_denominator():
    observation = view(); observation["jobs"] = []
    ledger, root = setup(observation); finish(ledger, root, "no_action")
    report = ledger.accounting(mandatory_setup_ns=1000, known_end_ns=100)
    assert report["bundle_denominator"] == 1 and report["job_child_denominator"] == 0
    assert report["roots"][root]["complete_compute_upper_ns"] == 1080


def test_later_independent_notice_does_not_close_prior_pending_bundle():
    ledger, old = setup(); submit(ledger, old)
    ledger.begin("batch1", at=2., wall_ns=45)
    roots = ledger.notified("batch1", {"status": "notified", "timestamp_complete": True, "physical_time": 3.,
        "notifications": {"B": {"sequence": 1, "observed_at": 3., "change_mask": 1}}}, wall_ns=50, call_ordinal=3)
    data = view(); data.update(owner_id="B", now=3., jobs=[])
    ledger.observe(roots[0], data, start_ns=51, end_ns=52, call_ordinal=4)
    finish(ledger, roots[0], "no_action")
    report = ledger.accounting(mandatory_setup_ns=0, known_end_ns=100)
    assert report["roots"][old]["complete_compute_upper_ns"] is None
    assert report["roots"][roots[0]]["complete_compute_upper_ns"] == 45


def test_partial_native_timestamp_retains_unresolved_boundary():
    ledger = NotificationLedger(["A"]); ledger.begin("batch0", at=0., wall_ns=10)
    with pytest.raises(ValueError, match="incomplete_native"):
        ledger.notified("batch0", {"status": "budget_exhausted", "timestamp_complete": False}, wall_ns=20, call_ordinal=1)
    assert ledger.accounting(mandatory_setup_ns=0, known_end_ns=100)["pending_boundary_denominator"] == 1


def test_malformed_second_notice_does_not_partly_commit_cursors():
    ledger = NotificationLedger(["A", "B"]); ledger.begin("batch0", at=0., wall_ns=10)
    with pytest.raises(ValueError, match="invalid_notice"):
        ledger.notified("batch0", {"status": "notified", "timestamp_complete": True, "physical_time": 2.,
            "notifications": {"A": {"sequence": 2, "observed_at": 2., "change_mask": 1},
                              "B": {"sequence": 1, "observed_at": 3., "change_mask": 1}}}, wall_ns=20, call_ordinal=1)
    assert ledger.cursors == {"A": 0, "B": 0} and not ledger.roots


def test_changed_retry_and_future_ack_and_incomplete_drain_are_rejected():
    ledger, root = setup(); payload = submit(ledger, root)
    with pytest.raises(ValueError): ledger.submit(root, "request0", "transfer", {**payload, "tray_id": "other"}, at=3., wall_ns=50, retry=True)
    with pytest.raises(ValueError): ledger.handle_ack("request0", {"request_id": "request0", "sequence": 1, "status": "received", "delivered_at": 4.}, at=3., wall_ns=60, query_ordinal=5)
    ack(ledger)
    with pytest.raises(ValueError): finish(ledger, root, "completed", at=2.)
    finish(ledger, root, "completed")
    with pytest.raises(ValueError): ack(ledger)


@pytest.mark.parametrize("mask", [16, 32, 48])
def test_result_only_notice_is_continuation_not_new_independent_proposal(mask):
    ledger = NotificationLedger(["A"]); ledger.begin("batch0", at=0., wall_ns=10)
    roots = ledger.notified("batch0", {"status": "notified", "timestamp_complete": True, "physical_time": 2.,
        "notifications": {"A": {"sequence": 1, "observed_at": 2., "change_mask": mask}}}, wall_ns=20, call_ordinal=1)
    assert roots == [] and ledger.batches["batch0"]["continuation_only_owners"] == ["A"]


def test_admission_stop_preserves_notice_and_cursor_without_new_roots():
    ledger = NotificationLedger(["A"]); ledger.begin("batch0", at=0., wall_ns=10)
    roots = ledger.notified("batch0", {"status": "notified", "timestamp_complete": True, "physical_time": 2.,
        "notifications": {"A": {"sequence": 1, "observed_at": 2., "change_mask": 1}}}, wall_ns=20, call_ordinal=1, admit=False)
    assert roots == [] and ledger.cursors["A"] == 1
    assert ledger.batches["batch0"]["not_admitted_owners"] == ["A"]
