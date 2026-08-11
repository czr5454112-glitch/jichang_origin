from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.eval import run_g4irsf22_local_oracle as screen


def _summary(cost: float) -> dict:
    return {
        "observation_node": 7,
        "horizons": [
            {
                "horizon_seconds": horizon,
                "coverage_complete": True,
                "queue_area_bag_seconds": cost * horizon,
                "scheduled_incoming_area_bag_seconds": 0.0,
                "next_service_deficit_area_seconds_squared": 0.0,
                "queued_wait_seconds_at_horizon": 0.0,
                "incoming_reservation_count": 0,
                "service_completion_count": 0,
            }
            for horizon in screen.HORIZONS
        ],
    }


def _group() -> dict:
    return {
        "choice_group_id": "g22-1",
        "s4_index": 0,
        "candidates": [
            {
                "action_kind": "NEXT_EDGE",
                "selected_next_node": 7,
                "utility": 0.0,
                "local_future_summary": _summary(2.0),
            },
            {
                "action_kind": "NEXT_EDGE",
                "selected_next_node": 9,
                "utility": 3.0,
                "local_future_summary": _summary(1.0),
            },
            {
                "action_kind": "WAIT",
                "selected_next_node": None,
                "utility": -1.0,
                "local_future_summary": _summary(4.0),
            },
        ],
    }


def test_heuristic_selects_consistent_local_winner_and_reports_realized_gain() -> None:
    row = screen.rank_group(_group())
    assert row["selected_index"] == 1
    assert row["selected_action"] == ("NEXT_EDGE", 9)
    assert row["realized_utility_gain_vs_s4_seconds"] == 3.0
    assert row["perfect_action_gain_vs_s4_seconds"] == 3.0


def test_heuristic_ranking_does_not_read_realized_utility() -> None:
    original = screen.rank_group(_group())
    poisoned = _group()
    poisoned["candidates"][0]["utility"] = 1_000_000.0
    poisoned["candidates"][1]["utility"] = -1_000_000.0
    changed = screen.rank_group(poisoned)
    assert changed["selected_index"] == original["selected_index"]
    assert changed["horizon_scores"] == original["horizon_scores"]


def test_heuristic_does_not_treat_reservations_as_completed_service() -> None:
    original = screen.rank_group(_group())
    changed = _group()
    for candidate in changed["candidates"]:
        for row in candidate["local_future_summary"]["horizons"]:
            row["incoming_reservation_count"] = 1_000_000
            row["service_completion_count"] = 1_000_000
    reranked = screen.rank_group(changed)
    assert reranked["selected_index"] == original["selected_index"]
    assert reranked["horizon_scores"] == original["horizon_scores"]


def test_ties_fall_back_to_s4() -> None:
    group = _group()
    for candidate in group["candidates"]:
        candidate["local_future_summary"] = _summary(1.0)
    assert screen.rank_group(group)["selected_index"] == group["s4_index"]


def test_incomplete_or_negative_future_summary_is_rejected() -> None:
    incomplete = deepcopy(_summary(1.0))
    incomplete["horizons"][0]["coverage_complete"] = False
    with pytest.raises(ValueError, match="coverage is incomplete"):
        screen.local_information_cost(incomplete, 5)

    negative = deepcopy(_summary(1.0))
    negative["horizons"][0]["queue_area_bag_seconds"] = -1.0
    with pytest.raises(ValueError, match="must be non-negative"):
        screen.local_information_cost(negative, 5)


def test_summary_separates_heuristic_result_from_perfect_action_ceiling() -> None:
    result = screen.summarize([_group()])
    assert result["not_a_perfect_information_upper_bound"] is True
    assert result["held_out_validation"] is False
    assert result["screen_kind"] == "FIXED_LOCAL_COST_PLUS_THREE_OF_FOUR_CONSENSUS"
    assert result["consensus_non_s4_count"] == 1
    assert result["beneficial_count"] == 1
    assert result["minimum_positive_mean_horizon_seconds"] == 5
    assert [row["horizon_seconds"] for row in result["per_horizon"]] == [
        5,
        15,
        30,
        60,
    ]
    assert all(row["beneficial_precision_when_non_s4"] == 1.0 for row in result["per_horizon"])
    assert result["heuristic_inputs"] == list(screen.SUMMARY_FIELDS)
    assert result["perfect_action_ceiling_is_not_a_heuristic_input"] is True
    assert all("oracle" not in key for key in result)
