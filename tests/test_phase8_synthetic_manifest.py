from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

from phase8_synthetic_replay_cases import (  # noqa: E402
    MANIFEST_PATH,
    case_plan,
    graph_from_case,
    load_manifest_cases,
    make_replay_case,
    tasks_from_case,
)


def test_phase8_synthetic_replay_manifest_matches_generator() -> None:
    cases = load_manifest_cases(MANIFEST_PATH)
    regenerated = tuple(make_replay_case(spec) for spec in case_plan())

    assert tuple(case.spec.name for case in cases) == tuple(case.spec.name for case in regenerated)
    assert sum(case.spec.task_count for case in cases) == 110
    merge_buffer_case = next(case for case in cases if case.spec.name == "synthetic_seed31_merge_buffer")
    assert merge_buffer_case.spec.node_capacities == ((8, 2), (9, 2))
    assert merge_buffer_case.spec.merge_groups == ((4, 7, 7), (4, 8, 7), (5, 8, 8), (6, 8, 8))
    for loaded, expected in zip(cases, regenerated, strict=True):
        assert loaded.spec == expected.spec
        assert loaded.node_records == expected.node_records
        assert loaded.edge_records == expected.edge_records
        assert loaded.heuristic_time == expected.heuristic_time
        assert loaded.task_records == expected.task_records
        assert graph_from_case(loaded).node_count == len(loaded.node_records)
        assert len(tasks_from_case(loaded)) == loaded.spec.task_count
