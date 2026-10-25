"""Paired service accounting across STD and the separate STD-2700 cutoff."""
from copy import deepcopy
import math

import pytest

from scripts.experiments.g31_deadline_research.compare import business_rows, paired


def population():
    canonical, baseline, candidate = [], [], []

    def segment(task, leg, old_finish, new_finish, *, release=100, admitted=100):
        start, goal = (0, 53) if leg == "storage_in" else (53, 2) if leg == "storage_out" else (0, 2)
        source = {"segment_id": f"{task}:{leg}", "task_id": task, "leg": leg,
                  "start": start, "goal": goal, "pass_time": release,
                  "original_entry_time": 100, "std": 5000}
        canonical.append(source)
        for output, finish in ((baseline, old_finish), (candidate, new_finish)):
            output.append({"segment_id": source["segment_id"], "task_id": task,
                           "start": start, "goal": goal, "deadline": 5000,
                           "release_time": release, "admitted_time": admitted,
                           "completed": finish is not None,
                           "finish_time": finish if finish is not None else -1})

    segment(1, "direct", 5100, 4900)  # Rescue STD only; both miss 45-minute cutoff.
    segment(2, "direct", 2200, 2400)  # Harm early cutoff only; both meet STD.
    segment(3, "direct", 2400, 2200)  # Rescue early cutoff only.
    segment(4, "direct", 4900, 5100)  # Harm STD only.
    segment(5, "storage_in", 2000, 2400)
    segment(5, "storage_out", 2200, 2200, release=2100, admitted=2100)
    segment(6, "direct", None, 2100)  # Unfinished baseline remains denominator.
    segment(7, "storage_in", 2400, 2000)
    segment(7, "storage_out", 2200, 2200, release=2100, admitted=2100)
    segment(8, "direct", None, None)
    return canonical, baseline, candidate


def test_same_population_has_different_rescues_and_harms_for_two_cutoffs():
    result = paired(*population())
    standard = result["service"]["strict_on_time"]
    early = result["service"]["strict_early_2700"]
    assert standard["rescued_task_ids"] == [1, 6, 7]
    assert standard["harmed_task_ids"] == [4, 5]
    assert early["rescued_task_ids"] == [3, 6, 7]
    assert early["harmed_task_ids"] == [2, 5]
    assert standard["net_change_count"] == early["net_change_count"] == 1
    assert result["offered_business_bags"] == 8
    for outcome in result["service"].values():
        assert sum(outcome["counts"].values()) == 8
        assert sum(sum(group.values()) for group in outcome["by_final_leg"].values()) == 8
        assert outcome["candidate_count"] - outcome["baseline_count"] == outcome["net_change_count"]


def test_ebs_causality_cannot_be_hidden_by_early_final_finish():
    canonical, baseline, candidate = population()
    observed = business_rows(canonical, candidate)
    assert observed[5]["observed_on_time"]
    assert observed[5]["observed_early_2700"]
    assert not observed[5]["strict_on_time"]
    assert not observed[5]["strict_early_2700"]
    assert observed[5]["old_max_segment_on_time"]  # Every leg < STD; causality still invalid.
    assert not observed[5]["old_max_segment_early_2700"]
    result = paired(canonical, baseline, candidate)
    assert result["service"]["observed_on_time"]["rescued_task_ids"] == [1, 6]
    assert result["service"]["observed_early_2700"]["rescued_task_ids"] == [3, 6]
    assert result["ebs"]["transition_counts"] == {"valid_to_invalid": 1, "invalid_to_valid": 1}
    assert result["ebs"]["valid_to_invalid_task_ids"] == [5]
    assert result["ebs"]["invalid_to_valid_task_ids"] == [7]
    assert result["observed_final_finish_delta_candidate_minus_baseline_completed_subset"]["count"] == 6
    assert result["causal_both_final_finish_delta_completed_subset"]["count"] == 4


def test_unfinished_never_counts_as_on_time_and_is_not_filtered():
    canonical, baseline, candidate = population()
    rows = business_rows(canonical, baseline)
    for task in (6, 8):
        assert rows[task]["finish"] is None
        for field in ("observed_on_time", "strict_on_time", "old_max_segment_on_time",
                      "observed_early_2700", "strict_early_2700", "old_max_segment_early_2700"):
            assert not rows[task][field]
    result = paired(canonical, baseline, candidate)
    assert result["service"]["strict_early_2700"]["counts"]["neither_on_time"] == 3


def test_exact_deadline_equality_passes_and_next_float_fails():
    canonical, baseline, _ = population()
    canonical = [r for r in canonical if r["task_id"] in (1, 2)]
    baseline = [r for r in baseline if r["task_id"] in (1, 2)]
    baseline[0]["finish_time"] = 5000.0
    baseline[1]["finish_time"] = 2300.0
    candidate = deepcopy(baseline)
    candidate[0]["finish_time"] = math.nextafter(5000.0, math.inf)
    candidate[1]["finish_time"] = math.nextafter(2300.0, math.inf)
    result = paired(canonical, baseline, candidate)
    assert result["service"]["strict_on_time"]["harmed_task_ids"] == [1]
    assert result["service"]["strict_early_2700"]["harmed_task_ids"] == [2]


@pytest.mark.parametrize("corruption", ("missing", "duplicate", "deadline", "identity", "nan_finish"))
def test_pair_population_identity_and_timing_fail_closed(corruption):
    canonical, baseline, candidate = population()
    if corruption == "missing":
        candidate.pop()
    elif corruption == "duplicate":
        candidate.append(deepcopy(candidate[0]))
    elif corruption == "deadline":
        candidate[0]["deadline"] += 1
    elif corruption == "identity":
        candidate[0]["goal"] += 1
    else:
        candidate[0]["finish_time"] = math.nan
    with pytest.raises(ValueError):
        paired(canonical, baseline, candidate)
