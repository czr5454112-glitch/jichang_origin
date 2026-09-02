from scripts.eval import cie_fixed_denominator_business as metrics


def test_incomplete_bags_remain_in_business_denominator() -> None:
    inputs = [
        {
            "segment_id": "1:a",
            "task_id": 1,
            "pass_time": 0.0,
            "original_entry_time": 0.0,
            "std": 8.0,
        },
        {
            "segment_id": "2:a",
            "task_id": 2,
            "pass_time": 1.0,
            "original_entry_time": 1.0,
            "std": 8.0,
        },
    ]
    results = [
        {
            "segment_id": "1:a",
            "completed": True,
            "release_time": 0.0,
            "admitted_time": 1.0,
            "finish_time": 6.0,
        },
        {
            "segment_id": "2:a",
            "completed": False,
            "release_time": 1.0,
            "admitted_time": -1.0,
            "finish_time": -1.0,
        },
    ]

    result = metrics.summarize(inputs, results, fixed_horizon=10.0)

    assert result["denominator_raw_bags"] == 2
    assert result["completed_raw_bag_count"] == 1
    assert result["on_time_raw_bag_count"] == 1
    assert result["missed_bag_count"] == 1
    assert (
        result["tardiness_seconds"]["fixed_horizon_all_population_lower_bound"][
            "sum"
        ]
        == 2.0
    )
    assert result["completion_targets"]["time_to_90_percent"]["reached"] is False
    assert result["backlog"]["raw_bag_total"]["end_backlog"] == 1
