"""Static route screening never converts loops or absent receipts to success."""
from scripts.experiments.g31_ics_circulation import original_command_window_census as census


def test_unconstrained_continuation_loop_is_retained_not_repaired():
    graph = {0: [(1, 1.), (2, 2.)], 1: [(3, 1.)], 2: [(0, 1.)], 3: []}
    report = census.stage_candidates(graph, {n: 2. for n in graph}, 0, 3)
    row = report["candidates"][0]
    assert row["full_predicted_path"] == [0, 2, 0, 1, 3]
    assert row["topology_status"] == "prefix_revisited"
    assert row["window_status"] == "native_same_timestamp_tie_unknown"
    assert row["native_executable"] == "unknown"


def test_short_window_and_unreachable_tail_are_distinct_retained_negatives():
    graph = {0: [(1, 1.), (2, 2.)], 1: [], 2: []}
    row = census.stage_candidates(graph, {0: 1.5, 1: 2., 2: 2.}, 0, 1)["candidates"][0]
    assert row["topology_status"] == "no_continuation" and row["window_status"] == "too_short"
    assert row["additional_free_flow_seconds"] is None


def test_missing_receipts_never_infer_head_or_candidate_success():
    data = {"jobs": [{"business_bag_id": "a", "origin": 0, "storage_node": 1}]}
    report = {"jobs": [{"business_bag_id": "a", "unreachable_required_stage_cohort": True}], "stages": {}}
    result = {"receipts": [], "advance": {"horizon_complete": False}}
    diagnosis = census.offline_receipt_diagnosis(data, report, result)
    assert diagnosis["storage_heads"] == [] and diagnosis["actual_default_path_windows"] == []
    assert diagnosis["advance"]["horizon_complete"] is False


def test_no_strict_reordering_when_delay_only_equals_actual_gap():
    graph = {0: [(1, 1.), (2, 2.)], 1: [], 2: [(1, 1.)]}
    stage = census.stage_candidates(graph, {n: 2. for n in graph}, 0, 1)
    data = {"jobs": [{"business_bag_id": x, "origin": 0, "storage_node": 1} for x in ("a", "b")]}
    report = {"jobs": [{"business_bag_id": x, "unreachable_required_stage_cohort": x == "a"} for x in ("a", "b")],
              "stages": {"0:1": stage}}
    result = {"receipts": [{"event": "STORAGE_ENTER", "business_bag_id": x, "time": t} for x, t in (("a", 10.), ("b", 12.))]}
    row = census.offline_receipt_diagnosis(data, report, result)["storage_heads"][0]
    assert row["status"] == "no_single_simple_free_flow_candidate"
    assert row["single_deviation_candidates"][0]["free_flow_delay_suffices"] is False
