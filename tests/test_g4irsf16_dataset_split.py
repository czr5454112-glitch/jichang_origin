from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from czr005.g4irsf16 import data
from czr005.g4irsf16.model import DEPLOYMENT_FEATURES


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def formal_build() -> data.ModelReadyBuild:
    return data.build_model_ready_data(ROOT)


def _primary_rows(build: data.ModelReadyBuild) -> list[dict[str, object]]:
    return [
        *build.rows_by_dataset["i3_route"],
        *build.rows_by_dataset["i4_hold"],
    ]


def test_real_formal_release_joins_to_separated_model_ready_rows(
    formal_build: data.ModelReadyBuild,
) -> None:
    assert {name: len(rows) for name, rows in formal_build.rows_by_dataset.items()} == {
        "i3_route": 1086,
        "i4_hold": 1086,
        "hsystem_externality": 256,
    }
    rows = _primary_rows(formal_build)
    assert len({row["descriptor_id"] for row in rows}) == 2172
    assert len({row["target_key"] for row in rows}) == 2172
    assert all(
        row["target_key"] == f"{row['descriptor_id']}:{row['horizon']}"
        for row in rows
    )
    assert Counter((row["kind"], row["signed_class"]) for row in rows) == Counter(
        {
            ("I3", "BENEFICIAL"): 23,
            ("I3", "NEUTRAL"): 30,
            ("I3", "HARMFUL"): 1033,
            ("I4", "BENEFICIAL"): 24,
            ("I4", "NEUTRAL"): 325,
            ("I4", "HARMFUL"): 737,
        }
    )
    assert all(
        math.isclose(
            float(row["direct_benefit_seconds"]),
            -float(row["h_bag_effect_seconds"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for row in rows
    )


def test_deployment_partition_exactly_matches_frozen_model_schema(
    formal_build: data.ModelReadyBuild,
) -> None:
    schema = data.model_ready_arrow_schema()
    deployable = tuple(
        field.name
        for field in schema
        if field.metadata[b"g4irsf16.column_partition"] == b"deployable_feature"
    )
    assert deployable == DEPLOYMENT_FEATURES
    assert tuple(schema.names[: len(DEPLOYMENT_FEATURES)]) == DEPLOYMENT_FEATURES
    assert data.COLUMN_PARTITIONS["deployable_feature"] == DEPLOYMENT_FEATURES
    assert not set(schema.names).intersection(data.FORBIDDEN_OUTPUT_COLUMNS)

    table = data.rows_to_arrow(formal_build.rows_by_dataset["i3_route"])
    assert table.schema == schema
    for name in data.STATIC_DEPLOYMENT_FEATURES:
        assert table.column(name).null_count == 0
        assert not schema.field(name).nullable
    for name in data.DYNAMIC_DEPLOYMENT_FEATURES:
        # No exact matched F2 feature cache was supplied to this build.  The
        # builder must preserve unknown as Arrow null rather than invent zero.
        assert table.column(name).null_count == table.num_rows
        assert schema.field(name).nullable


def test_hbag_externality_is_unknown_not_zero(
    formal_build: data.ModelReadyBuild,
) -> None:
    hbag = [
        row for row in _primary_rows(formal_build) if row["horizon"] == "H_bag"
    ]
    assert len(hbag) == 1916
    externality_fields = (
        "risk_adjusted_utility_seconds",
        "externality_nonempty",
        "external_affected_count",
        "realized_affected_count",
        "other_bag_mean_harm_seconds",
        "other_bag_max_harm_seconds",
        "other_bag_p95_harm_seconds",
        "other_bag_cvar95_harm_seconds",
        "extra_deadline_miss_count",
        "system_original_entry_delta_seconds",
    )
    assert all(row["h_system_available"] is False for row in hbag)
    assert all(row["externality_observed"] is False for row in hbag)
    assert all(row[name] is None for row in hbag for name in externality_fields)


def test_real_hsystem_sparse_positive_harm_tail_metrics(
    formal_build: data.ModelReadyBuild,
) -> None:
    rows = formal_build.rows_by_dataset["hsystem_externality"]
    assert sum(row["externality_nonempty"] is True for row in rows) == 144
    assert max(int(row["external_affected_count"]) for row in rows) == 365
    assert math.isclose(
        max(float(row["other_bag_max_harm_seconds"]) for row in rows),
        78.10009999999966,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert math.isclose(
        max(float(row["other_bag_cvar95_harm_seconds"]) for row in rows),
        54.03688499999771,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert {row["extra_deadline_miss_count"] for row in rows} == {0}
    assert all(row["risk_adjusted_utility_seconds"] is not None for row in rows)


def test_type7_and_cvar_use_external_ids_and_clipped_harm() -> None:
    def outcome(finish: float) -> dict[str, object]:
        return {"completed": True, "finish_time": finish, "deadline": 100.0}

    signed_harms = (-2.0, 0.0, 10.0, 20.0)
    delta_rows = []
    for runtime_id, signed_harm in zip(range(2, 6), signed_harms, strict=True):
        delta_rows.append(
            {
                "runtime_bag_id": runtime_id,
                "completion_delta_seconds": signed_harm,
                "baseline": outcome(90.0),
                "treatment": outcome(110.0 if runtime_id == 5 else 90.0),
            }
        )
    pair = {
        "horizon": "H_system",
        "direct_affected_runtime_bag_ids": [1],
        "externality_runtime_bag_ids": [2, 3, 4, 5],
        "realized_affected_runtime_bag_ids": [1, 2, 3, 4, 5],
        "realized_outcome_deltas": delta_rows,
    }
    metrics = data.hsystem_externality_metrics(pair)
    assert metrics == {
        "externality_nonempty": True,
        "external_affected_count": 4,
        "realized_affected_count": 5,
        "other_bag_mean_harm_seconds": 7.5,
        "other_bag_max_harm_seconds": 20.0,
        "other_bag_p95_harm_seconds": 18.499999999999996,
        "other_bag_cvar95_harm_seconds": 20.0,
        "extra_deadline_miss_count": 1,
    }


def test_component_hash_split_is_pure_deterministic_and_leakage_disjoint(
    formal_build: data.ModelReadyBuild,
) -> None:
    rows = _primary_rows(formal_build)
    assert formal_build.split_manifest["split_row_counts"] == {
        "train": 1332,
        "calibration": 318,
        "validation": 314,
        "final_audit": 208,
    }
    component_splits: dict[str, set[str]] = defaultdict(set)
    clone_splits: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        component_splits[str(row["component_id"])].add(str(row["split"]))
        clone_splits[str(row["clone_group_id"])].add(str(row["split"]))
        assert row["split"] == data.split_for_component(str(row["component_id"]))
    assert all(len(values) == 1 for values in component_splits.values())
    assert all(len(values) == 1 for values in clone_splits.values())
    assert formal_build.split_manifest["clone_group_cross_split_count"] == 0
    assert formal_build.split_manifest["raw_task_cross_split_count"] == 0
    assert formal_build.split_manifest["source_split_assignments_consumed"] is False


def test_final_audit_is_sealed_and_never_selection_eligible(
    formal_build: data.ModelReadyBuild,
) -> None:
    final_rows = [
        row for row in _primary_rows(formal_build) if row["split"] == "final_audit"
    ]
    assert len(final_rows) == 208
    assert {row["final_audit_status"] for row in final_rows} == {
        "SEALED_NOT_CONSUMED"
    }
    assert formal_build.split_manifest["final_audit"] == {
        "status": "SEALED",
        "row_count": 208,
        "row_level_results_consumed_for_selection": False,
        "model_training_allowed": False,
        "rule_or_threshold_selection_allowed": False,
        "support_census_only": True,
    }
    assert all(
        row["selection_allowed"] is False
        for row in formal_build.support_rows
        if row["split"] == "final_audit"
    )


def test_runtime_cache_cannot_override_static_or_global_proxy_fields(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "bad_runtime_cache.json"
    cache.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "descriptor_id": "descriptor",
                        "features": {"queued_bag_count": 99.0},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        data.ModelReadyDataError,
        match="RUNTIME_CACHE_NON_DYNAMIC_FEATURE:queued_bag_count",
    ):
        data._load_runtime_feature_cache(cache)

    static_override = tmp_path / "bad_static_override.json"
    static_override.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "descriptor_id": "descriptor",
                        "features": {"deadline_slack_seconds": 1.0},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        data.ModelReadyDataError,
        match="RUNTIME_CACHE_NON_DYNAMIC_FEATURE:deadline_slack_seconds",
    ):
        data._load_runtime_feature_cache(static_override)


def test_matched_live_trace_projects_only_exact_local_dynamic_features(
    tmp_path: Path,
) -> None:
    def candidate(next_node: int, queue: int, incoming: int, raw: float) -> dict[str, object]:
        return {
            "action_next_node": next_node,
            "features": {
                "target_queue_length": queue,
                "target_scheduled_incoming": incoming,
                "corridor_next_available": 105.0,
                "target_next_available": 108.0,
                "corridor_wait_seconds": 5.0,
                "target_calendar_delay_seconds": 4.0,
                "travel_time": 4.0,
                "static_potential": 20.0,
                "model_score": 1.0,
                "scorer_raw_score": raw,
                "scorer_raw_bottleneck": 0.0,
                "advertised_fault": next_node == 12,
                "shield_allowed": True,
                "shield_reason": "allowed",
            },
        }

    trace = {
        "schema": "czr005.g4irsf16.matched_local_features.v1",
        "target": {
            "target_key": "descriptor:H_system",
            "descriptor_id": "descriptor",
            "kind": "I3",
            "horizon": "H_system",
        },
        "runtime_match": {"decision_ordinal": 3},
        "action_context": {
            "current_node": 10,
            "goal_node": 20,
            "candidate_next_nodes": [11, 12],
            "f2_model_prediction": 0.0,
            "f2_selected_next": 11,
        },
        "features": {
            "current_local_queue_length": 7,
            "current_next_available_time": 102.0,
            "current_calendar_wait_seconds": 2.0,
            "short_history": [10, 12, 10, 12],
            "f2": {
                "model_margin": 0.25,
                "scorer_raw_margin": 0.5,
                "risk_gate_triggered": False,
                "scorer_risk_abstain": False,
            },
            "candidates": [
                candidate(11, 3, 4, 1.25),
                candidate(12, 8, 9, 2.25),
            ],
        },
    }
    cache = tmp_path / "matched.json"
    cache.write_text(json.dumps({"rows": [trace]}), encoding="utf-8")
    by_descriptor, by_target = data._load_runtime_feature_cache(cache)
    projected, matched = data._runtime_features_for_row(
        "descriptor",
        "descriptor:H_system",
        {
            "kind": "I3",
            "node": 10,
            "goal": 20,
            "baseline_next_node": 11,
            "selected_next_node": 12,
        },
        by_descriptor,
        by_target,
    )
    assert matched is True
    assert projected == {
        "current_queue_length": 7.0,
        "target_queue_length": 8.0,
        "target_scheduled_incoming": 9.0,
        "current_next_available_wait_seconds": 2.0,
        "target_next_available_wait_seconds": 4.0,
        "f2_model_margin": 0.25,
        "f2_raw_score": 1.25,
        "recent_visit_count": 2.0,
        "short_history_repeat_count": 2.0,
        "advertised_fault": 1.0,
    }


def test_committed_parquets_use_all_real_matched_cache_rows() -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    tables = [
        pq.read_table(ROOT / data.DATASET_OUTPUTS[name])
        for name in ("i3_route", "i4_hold")
    ]
    table = pa.concat_tables(tables)
    assert table.num_rows == 2172
    assert table.column("runtime_feature_cache_matched").to_pylist() == [True] * 2172
    assert all(
        table.column(name).null_count == 0
        for name in data.DYNAMIC_DEPLOYMENT_FEATURES
    )
    assert "downstream_pressure" not in table.column_names
    assert "has_physical_fault" not in table.column_names
    assert table.column("runtime_dynamic_feature_complete").to_pylist() == [True] * 2172

    manifest = json.loads(
        (ROOT / data.SPLIT_MANIFEST_OUTPUT).read_text(encoding="utf-8")
    )
    cache = manifest["runtime_feature_cache"]
    assert cache["matched_row_count"] == 2172
    assert cache["fully_complete_dynamic_row_count"] == 2172
    assert cache["fully_observed_dynamic_column_count"] == 10
    assert cache["dynamic_column_coverage"] == pytest.approx(1.0)
    assert cache["trace_mapped_feature_complete_row_count"] == 2172
    assert cache["dynamic_feature_null_counts"] == {
        name: 0
        for name in data.DYNAMIC_DEPLOYMENT_FEATURES
    }
    assert cache["path"] == (
        "outputs/runtime/g4irsf16/"
        "g4irsf16_f2_off_e4_m0_43603_shards4.matched_features.jsonl.zst"
    )
    pruning = cache["matched_live_trace_projection"][
        "feature_realizability_pruning"
    ]
    assert pruning["removed_from_deployment_schema"] == [
        "downstream_pressure",
        "has_physical_fault",
    ]
    assert pruning["has_physical_fault_owner"] == (
        "SUPERVISOR_PHYSICAL_SHIELD_STATE"
    )
    assert pruning["proxy_substitution_allowed"] is False
    with (ROOT / data.SPLIT_SUPPORT_OUTPUT).open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        support = list(csv.DictReader(handle))
    assert support
    assert all(
        row["runtime_trace_mapped_feature_complete_count"] == row["row_count"]
        for row in support
    )
    assert all(
        row["runtime_dynamic_feature_complete_count"] == row["row_count"]
        for row in support
    )
