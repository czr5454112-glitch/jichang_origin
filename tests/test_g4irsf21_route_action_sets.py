from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from scripts.eval import run_g4irsf20_route_counterfactuals as g20
from scripts.eval import run_g4irsf21_route_action_sets as runner


def _scan_row(
    index: int = 0,
    *,
    wait_age: float = 5.0,
    legal: list[int] | None = None,
    baseline: int = 7,
) -> dict[str, Any]:
    return {
        "schema": "czr005.g4irsf15.causal_skeleton.v1",
        "skeleton_id": f"selection-{index}",
        "population_group_sha256": f"group-{index}",
        "skeleton_selection_sha256": f"selection-{index}",
        "kind": "I3",
        "event_ordinal": 10 + index,
        "runtime_bag_id": 100 + index,
        "wait_age_seconds": wait_age,
        "candidate_count": len(legal or [4, 7, 9]),
        "normal_flow": True,
        "baseline_next_node": baseline,
        "legal_next_edges": legal or [4, 7, 9],
        "wait_available": True,
    }


def _observation(selected: int) -> dict[str, Any]:
    nodes = [4, 7, 9]
    return {
        "schema": "czr005.g4irsf20.route_pre_action_observation_set.v1",
        "feature_names": ["event_time", "target_queue_length"],
        "candidate_observations": [
            {"event_time": 10.0, "target_queue_length": float(node)}
            for node in nodes
        ],
        "canonical_candidate_observations": [
            [10.0, float(node)] for node in nodes
        ],
        "candidate_next_nodes": nodes,
        "baseline_candidate_index": 1,
        "treatment_candidate_index": nodes.index(selected),
        "normal_flow": True,
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "runtime_full_astar_call_count": 0,
    }


class FakeNative:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        failed_action: tuple[str, int | None] | None = None,
    ) -> None:
        self.rows = rows
        self.failed_action = failed_action
        self.seen_targets: list[dict[str, Any]] = []
        self.profiles: list[str] = []

    def g4irsf15_scan_causal_skeletons_from_records(self, *args: Any) -> dict[str, Any]:
        self.profiles.append(str(args[-1]))
        return {"census_complete": True, "skeletons": self.rows}

    def g4irsf15_run_causal_target_pairs_from_records(self, *args: Any) -> dict[str, Any]:
        targets = [dict(row) for row in args[-2]]
        self.profiles.append(str(args[-1]))
        self.seen_targets = targets
        pairs: list[dict[str, Any]] = []
        delta = {("NEXT_EDGE", 4): -2.0, ("NEXT_EDGE", 9): 1.0, ("WAIT", None): -1.0}
        for target in targets:
            action = str(target["action_kind"])
            node = target.get("selected_next_node")
            key = (action, int(node) if type(node) is int else None)
            failed = key == self.failed_action
            source = next(
                row
                for row in self.rows
                if row["event_ordinal"] == target["event_ordinal"]
            )
            runtime_bag_id = int(source["runtime_bag_id"])
            task_id = 9000 + runtime_bag_id
            pair: dict[str, Any] = {
                "target_schema": target["schema"],
                "population_group_id": target["population_group_id"],
                "population_selection_id": target["population_selection_id"],
                "event_ordinal": target["event_ordinal"],
                "horizon": target["horizon"],
                "action_kind": action,
                "pair_status": (
                    "SCREENING_FALSE_POSITIVE"
                    if failed
                    else runner.COMPLETE_PAIR_STATUS
                ),
                "same_state_start": not failed,
                "action_changed": not failed,
                "pair_complete": not failed,
                "live_safety_pass": not failed,
                "affected_bag_deltas": [
                    {"completion_delta_seconds": delta[key]}
                ],
                "resolved_execution_descriptor": {
                    "runtime_bag_id": runtime_bag_id,
                },
                "baseline": {
                    "affected_bag_outcomes": [
                        {
                            "runtime_bag_id": runtime_bag_id,
                            "task_id": task_id,
                        }
                    ]
                },
                "route_observation": (
                    _observation(int(node)) if action == "NEXT_EDGE" else None
                ),
            }
            if action == "NEXT_EDGE":
                pair["selected_next_node"] = int(node)
            pairs.append(pair)
        return {"pairs": pairs}


def _run(
    tmp_path: Path,
    native: FakeNative,
    *,
    target_groups: int = 1,
) -> tuple[dict[str, Any], Path, Path, Path]:
    dataset = tmp_path / "action_sets.jsonl"
    table = tmp_path / "action_sets.json"
    report = tmp_path / "action_sets.md"
    summary = runner.run_campaign(
        root=runner.ROOT,
        target_groups=target_groups,
        long_wait_target=0,
        screening_multiplier=1.0,
        dataset_path=dataset,
        table_path=table,
        report_path=report,
        module=native,
        native_arguments=(),
    )
    return summary, dataset, table, report


def _nested_keys(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        return [str(key) for key in value] + [
            nested for child in value.values() for nested in _nested_keys(child)
        ]
    if isinstance(value, list):
        return [nested for child in value for nested in _nested_keys(child)]
    return []


def test_three_edges_plus_wait_form_one_complete_compact_group(tmp_path: Path) -> None:
    native = FakeNative([_scan_row()])
    summary, dataset, table, report = _run(tmp_path, native)

    assert native.profiles == [runner.RESEARCH_PROFILE, runner.RESEARCH_PROFILE]
    assert [target["action_kind"] for target in native.seen_targets] == [
        "NEXT_EDGE",
        "NEXT_EDGE",
        "WAIT",
    ]
    assert [target.get("selected_next_node") for target in native.seen_targets] == [
        4,
        9,
        None,
    ]
    assert "selected_next_node" not in native.seen_targets[-1]

    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    group = rows[0]
    assert group["full_legal_action_set_labeled"] is True
    assert group["split_group"] == 9100
    assert group["wait_action_labeled"] is True
    assert group["utility_unit"] == "seconds"
    assert (
        group["utility_semantics"]
        == "BASELINE_MINUS_TREATMENT_COMPLETION_SECONDS"
    )
    assert group["s4_index"] == 1
    assert [candidate["action_kind"] for candidate in group["candidates"]] == [
        "NEXT_EDGE",
        "NEXT_EDGE",
        "NEXT_EDGE",
        "WAIT",
    ]
    assert [candidate["utility"] for candidate in group["candidates"]] == [
        2.0,
        0.0,
        -1.0,
        1.0,
    ]
    assert group["candidates"][-1]["native_features"] is None
    assert summary["status"] == "COMPLETE_ACTION_SET_TARGET_MET"
    assert summary["counts"]["executed_treatments"] == 3
    assert table.is_file() and report.is_file()
    persisted = json.loads(table.read_text(encoding="utf-8"))
    assert persisted["design"]["utility_unit"] == group["utility_unit"]
    assert persisted["design"]["utility_semantics"] == group["utility_semantics"]
    forbidden = [
        key for key in _nested_keys([persisted, group])
        if "sha" in key.lower() or "hash" in key.lower() or "manifest" in key.lower()
    ]
    assert forbidden == []
    report_text = report.read_text(encoding="utf-8")
    assert "native pair rows" in report_text
    assert "positive values are better" in report_text
    assert "earliest eligible events" in report_text
    assert "grouped-even sampling by original task" in report_text


def test_one_false_positive_drops_the_entire_group(tmp_path: Path) -> None:
    native = FakeNative([_scan_row()], failed_action=("NEXT_EDGE", 9))
    summary, dataset, _table, _report = _run(tmp_path, native)

    assert dataset.read_text(encoding="utf-8") == ""
    assert summary["status"] == "ACTION_SET_SHORTFALL"
    assert summary["counts"]["fully_complete_groups"] == 0
    assert summary["counts"]["persisted_groups"] == 0
    assert summary["dropped_group_reason_counts"] == {
        "SCREENING_FALSE_POSITIVE": 1
    }


def test_screening_is_event_order_stratified_and_capped_at_one_point_five() -> None:
    scan = {
        "census_complete": True,
        "skeletons": [
            _scan_row(index, wait_age=40.0 if index % 2 else 5.0)
            for index in range(40)
        ],
    }
    selected = runner.select_screening_groups(
        scan,
        target_groups=16,
        long_wait_target=8,
        screening_multiplier=1.5,
    )
    assert len(selected) == 24
    assert sum(row["wait_age_seconds"] >= 30.0 for row in selected) >= 12
    assert [row["event_ordinal"] for row in selected] == sorted(
        row["event_ordinal"] for row in selected
    )


def test_g21_target_is_append_only_and_g20_v1_stays_five_fields() -> None:
    group = runner.normalize_i3_row(_scan_row())
    targets = runner.build_action_targets(group)
    assert all(target["schema"] == runner.TARGET_SCHEMA for target in targets)
    assert set(targets[-1]) == {
        "schema",
        "population_group_id",
        "population_selection_id",
        "event_ordinal",
        "horizon",
        "action_kind",
    }

    old_plan = [
        {
            "group_index": 0,
            "wait_age_seconds": 5.0,
            "planned_horizon": "H_bag",
            "selection": {
                "schema_id": "czr005.g4irsf15.causal_skeleton.v1",
                "descriptor_id": "selection-old",
                "skeleton_id": "selection-old",
                "population_group_id": "group-old",
                "population_selection_id": "selection-old",
                "kind": "I3_NEXT_EDGE",
                "event_ordinal": 10,
            },
        }
    ]
    old_target = g20.deferred_plan(old_plan)[0]["target"]
    assert old_target["schema"] == g20.DEFERRED_TARGET_SCHEMA
    assert set(old_target) == {
        "schema",
        "population_group_id",
        "population_selection_id",
        "event_ordinal",
        "horizon",
    }
