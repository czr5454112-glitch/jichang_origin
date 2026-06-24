from __future__ import annotations

from pathlib import Path

import pytest

from czr005.io.legacy_map import parse_legacy_map
from czr005.io.legacy_tasks import (
    expand_tasks,
    group_tasks_by_start_java_order,
    parse_legacy_tasks,
    summarize_tasks,
)

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"


def test_map2_counts_and_schema() -> None:
    parsed = parse_legacy_map(LEGACY / "map2.txt")

    assert parsed.header.node_count == 54
    assert len(parsed.nodes) == 54
    assert len(parsed.heuristic_raw) == 54
    assert all(len(row) == 54 for row in parsed.heuristic_raw)
    assert len(parsed.edges) == 69
    assert parsed.start_nodes == (0, 1, 2, 3, 4, 5, 52, 53)
    assert parsed.end_nodes == (47, 48, 49, 50, 51)
    assert parsed.node_type_counts == {1: 8, 2: 5, 4: 19, 5: 22}

    as_dict = parsed.to_dict()
    assert as_dict["schema"] == "czr005.legacy_map.v1"
    assert as_dict["edges"][0]["travel_time"] == as_dict["edges"][0]["length"] / 2.5


def test_example1_requires_explicit_java_compatible_ragged_heuristic_mode() -> None:
    example_map = LEGACY / "example1" / "map.txt"

    with pytest.raises(ValueError, match="heuristic row"):
        parse_legacy_map(example_map)

    parsed = parse_legacy_map(example_map, allow_ragged_heuristic=True)

    assert parsed.header.node_count == 11
    assert len(parsed.nodes) == 11
    assert len(parsed.heuristic_raw) == 11
    assert all(len(row) == 11 for row in parsed.heuristic_raw)
    assert parsed.heuristic_raw[-1][-1] == 0.0
    assert len(parsed.edges) == 13
    assert parsed.start_nodes == (0, 10)
    assert parsed.end_nodes == (9,)
    assert parsed.node_type_counts == {0: 8, 1: 2, 2: 1}


def test_inputdata_counts_and_early_bag_split() -> None:
    header, raw_tasks = parse_legacy_tasks(LEGACY / "inputdata.txt")
    expanded = expand_tasks(raw_tasks)
    summary = summarize_tasks(raw_tasks, expanded)

    assert header == "ID EntryTime(s) STD(s) star end Unloader Loader"
    assert summary["raw_task_count"] == 28506
    assert summary["direct_raw_task_count"] == 13409
    assert summary["early_split_raw_task_count"] == 15097
    assert summary["expanded_task_count"] == 43603

    first_early = next(task for task in raw_tasks if task.std - task.entry_time >= 4800)
    legs = [task for task in expanded if task.task_id == first_early.task_id]
    assert [task.leg for task in legs] == ["storage_in", "storage_out"]
    assert legs[0].start == first_early.start
    assert legs[0].goal == 47
    assert legs[1].start == 52
    assert legs[1].goal == first_early.end
    assert legs[1].pass_time == first_early.std - 2700


def test_java_equivalent_grouping_contains_all_expanded_tasks() -> None:
    _, raw_tasks = parse_legacy_tasks(LEGACY / "inputdata.txt")
    expanded = expand_tasks(raw_tasks)
    grouped = group_tasks_by_start_java_order(expanded)

    assert sum(len(items) for items in grouped.values()) == len(expanded)
    assert set(grouped) == {0, 1, 2, 3, 4, 5, 52, 53}
    for task_list in grouped.values():
        for left, right in zip(task_list, task_list[1:]):
            assert int(left.pass_time - right.pass_time) <= 0
