from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from czr005.datasets import decision_trace as dt
from scripts.eval import run_g4irsf11_decision_trace_sampling as runner


def _raw_decision(
    decision_id: str = "d-1",
    *,
    task_id: int = 1,
    segment_id: str = "1:direct",
    fallback: int | None = 2,
    selected: int = 2,
    scenario: str = "paper_repeat_01",
    source_queue: int = 1,
    runtime_bag_id: int | None = None,
    fault_mode: str = "no_fault",
) -> dict[str, object]:
    return {
        "decision_id": decision_id,
        "task_id": task_id,
        "segment_id": segment_id,
        "event_time": 12.0,
        "current_node": 0,
        "goal_node": 3,
        # Deliberately reversed; canonical ordering must keep features/scores
        # paired with the corresponding node.
        "candidate_records": [
            {
                "next_node": 2,
                "features": {"target_queue_length": 2, "static_potential": 0.2},
                "model_score": 1.5,
                "shield_allowed": True,
                "shield_reason": "",
            },
            {
                "next_node": 1,
                "features": {"target_queue_length": 1, "static_potential": 0.8},
                "model_score": 0.5,
                "shield_allowed": True,
                "shield_reason": "",
            },
        ],
        "model_prediction": 1,
        "model_margin": 1.0,
        "risk_gate_triggered": fallback is not None,
        "fallback_selected_next": fallback,
        "selected_next": selected,
        "decision_source": "local_shield" if fallback is not None else "model",
        "rule_reason": "queue_guard" if fallback is not None else "",
        "local_snapshot": {
            "junction_queue_length": source_queue,
            "next_available_time": 12.5,
            "faulted_outgoing_count": 0,
            "message_age_seconds": 0.25,
            "downstream_pressure": 1.0,
        },
        "short_history": [4, 0],
        "full_astar_used": False,
        "metadata": {
            "scenario": scenario,
            "scale": "2x",
            "fault_mode": fault_mode,
            "model_score_semantics": "lower_is_better_cost",
            "runtime_bag_id": task_id if runtime_bag_id is None else runtime_bag_id,
        },
    }


def _mapping_rows() -> list[dict[str, object]]:
    return [
        {
            "task_id": 1,
            "segment_id": "1:direct",
            "start": 4,
            "goal": 3,
            "g4irsf7_original_pass_time": 10.8,
            "pass_time": 12.0,
            "g4irsf7_source_queue_rank": 2,
        },
        {
            "task_id": 2,
            "segment_id": "2:direct",
            "start": 5,
            "goal": 3,
            "g4irsf7_original_pass_time": 10.1,
            "pass_time": 11.0,
            "g4irsf7_source_queue_rank": 1,
        },
    ]


def test_true_outgoing_candidates_are_canonical_and_actions_are_valid() -> None:
    row = dt.validate_decision_rows([_raw_decision()], {0: [2, 1]})[0]

    assert row["candidate_next_nodes"] == [1, 2]
    assert [record["next_node"] for record in row["candidate_records"]] == [1, 2]
    assert row["candidate_records"][0]["features"]["target_queue_length"] == 1
    assert row["selected_next"] in row["candidate_next_nodes"]
    assert row["model_prediction"] in row["candidate_next_nodes"]
    assert row["fallback_selected_next"] in row["candidate_next_nodes"]


def test_candidate_set_must_equal_graph_outgoing_neighbors() -> None:
    raw = _raw_decision()
    raw["candidate_records"] = [raw["candidate_records"][0]]  # type: ignore[index]
    raw["model_prediction"] = 2
    raw["selected_next"] = 2
    raw["fallback_selected_next"] = 2
    raw["model_margin"] = 999.0

    with pytest.raises(dt.DecisionTraceValidationError, match="true outgoing neighbors"):
        dt.validate_decision_rows([raw], {0: [1, 2]})


def test_selected_action_must_belong_to_candidates() -> None:
    raw = _raw_decision(selected=9)

    with pytest.raises(dt.DecisionTraceValidationError, match="selected_next must belong"):
        dt.canonicalise_decision_row(raw)


def test_disagreement_is_true_only_when_model_and_fallback_actions_differ() -> None:
    same = dt.canonicalise_decision_row(_raw_decision(fallback=1, selected=1))
    different = dt.canonicalise_decision_row(_raw_decision(fallback=2, selected=2))

    assert same["model_fallback_disagreement"] is False
    assert different["model_fallback_disagreement"] is True

    inconsistent = _raw_decision(fallback=1, selected=1)
    inconsistent["model_fallback_disagreement"] = True
    with pytest.raises(dt.DecisionTraceValidationError, match="exactly when"):
        dt.canonicalise_decision_row(inconsistent)


def test_margin_is_required_finite_and_non_null() -> None:
    missing = _raw_decision()
    missing["model_margin"] = None
    with pytest.raises(dt.DecisionTraceValidationError, match="model_margin"):
        dt.canonicalise_decision_row(missing)

    infinite = _raw_decision()
    infinite["model_margin"] = float("inf")
    with pytest.raises(dt.DecisionTraceValidationError, match="model_margin"):
        dt.canonicalise_decision_row(infinite)


def test_lower_is_better_score_contract_is_explicit_and_verified() -> None:
    row = dt.canonicalise_decision_row(_raw_decision())

    assert row["model_score_semantics"] == dt.MODEL_SCORE_SEMANTICS
    assert row["model_prediction"] == 1
    assert row["model_margin"] == 1.0

    missing = _raw_decision()
    del missing["metadata"]["model_score_semantics"]  # type: ignore[index]
    with pytest.raises(dt.DecisionTraceValidationError, match="model_score_semantics"):
        dt.canonicalise_decision_row(missing)

    wrong_prediction = _raw_decision()
    wrong_prediction["model_prediction"] = 2
    with pytest.raises(dt.DecisionTraceValidationError, match="minimum-cost"):
        dt.canonicalise_decision_row(wrong_prediction)

    wrong_margin = _raw_decision()
    wrong_margin["model_margin"] = 0.25
    with pytest.raises(dt.DecisionTraceValidationError, match="second_min_cost-min_cost"):
        dt.canonicalise_decision_row(wrong_margin)


def test_runtime_bag_id_is_required_non_negative_metadata() -> None:
    missing = _raw_decision()
    del missing["metadata"]["runtime_bag_id"]  # type: ignore[index]
    with pytest.raises(dt.DecisionTraceValidationError, match="runtime_bag_id"):
        dt.canonicalise_decision_row(missing)

    negative = _raw_decision(runtime_bag_id=-1)
    with pytest.raises(dt.DecisionTraceValidationError, match="cannot be negative"):
        dt.canonicalise_decision_row(negative)


@pytest.mark.parametrize(
    "leaking_field",
    ["future_path_suffix", "teacher_path", "path_history", "post_hoc_success", "reached_goal"],
)
def test_future_route_and_posthoc_fields_are_recursively_rejected(leaking_field: str) -> None:
    raw = _raw_decision()
    raw[leaking_field] = [0, 1, 2]

    with pytest.raises(dt.DecisionTraceValidationError, match="forbidden"):
        dt.canonicalise_decision_row(raw)


def test_candidate_feature_order_and_digest_are_reproducible() -> None:
    first = _raw_decision()
    second = _raw_decision()
    second["candidate_records"] = list(reversed(second["candidate_records"]))  # type: ignore[arg-type]

    row_a = dt.canonicalise_decision_row(first)
    row_b = dt.canonicalise_decision_row(second)

    assert row_a["candidate_records"] == row_b["candidate_records"]
    assert row_a["candidate_order_digest"] == row_b["candidate_order_digest"]
    assert row_a["candidate_ordering"] == dt.CANDIDATE_ORDERING


def test_unknown_candidate_feature_without_lineage_fails_closed() -> None:
    raw = _raw_decision()
    raw["candidate_records"][0]["features"]["future_route_quality_proxy"] = 1.0  # type: ignore[index]

    with pytest.raises(dt.DecisionTraceValidationError, match="forbidden|approved lineage"):
        dt.canonicalise_decision_row(raw)


def test_original_arrival_release_mapping_is_linked_to_every_decision() -> None:
    decisions = dt.validate_decision_rows([_raw_decision()], {0: [1, 2]})
    mappings = dt.source_release_mapping(_mapping_rows())
    links = dt.decision_source_links(decisions, mappings)

    assert links == [
        {
            "decision_id": "d-1",
            "runtime_bag_id": 1,
            "task_id": 1,
            "segment_id": "1:direct",
            "source_node": 4,
            "goal_node": 3,
            "original_arrival_time": 10.8,
            "java_arrival_epoch": 10,
            "release_time": 12.0,
            "source_queue_delay_seconds": 2.0,
            "raw_arrival_to_release_delta_seconds": pytest.approx(1.2),
            "source_queue_rank": 2,
            "mapping_source": "g4irsf7_original_pass_time->pass_time",
        }
    ]


def test_source_identity_audit_preserves_repeated_original_task_ids() -> None:
    audit = dt.source_identity_audit(
        [
            {"task_id": 7, "segment_id": "7:storage_in"},
            {"task_id": 7, "segment_id": "7:storage_out"},
            {"task_id": 8, "segment_id": "8:direct"},
        ]
    )

    assert audit == {
        "processed_segment_count": 3,
        "unique_original_task_id_count": 2,
        "repeated_original_task_id_count": 1,
        "extra_segments_sharing_original_task_id": 1,
        "max_segments_per_original_task_id": 2,
        "original_task_ids_rewritten": False,
        "runtime_internal_identity_required": True,
    }


def test_runtime_identity_is_unique_per_original_segment_without_rewriting_task_id() -> None:
    decisions = [
        dt.canonicalise_decision_row(
            _raw_decision("in-d", task_id=7, segment_id="7:storage_in", runtime_bag_id=100)
        ),
        dt.canonicalise_decision_row(
            _raw_decision("out-d", task_id=7, segment_id="7:storage_out", runtime_bag_id=101)
        ),
    ]

    audit = dt.validate_runtime_bag_identity(decisions)
    assert audit["status"] == "PASS"
    assert audit["runtime_identity_count"] == 2
    assert audit["original_segment_identity_count"] == 2
    assert {row["task_id"] for row in decisions} == {7}

    alias = [dict(row) for row in decisions]
    alias[1] = {**alias[1], "metadata": {**alias[1]["metadata"], "runtime_bag_id": 100}}
    with pytest.raises(dt.DecisionTraceValidationError, match="aliases original segments"):
        dt.validate_runtime_bag_identity(alias)


def test_complete_java_source_queue_identity_counts_are_locked() -> None:
    task_path = (
        ROOT
        / "artifacts"
        / "tasks"
        / "g4irsf7"
        / "java_source_queue_one_per_epoch.jsonl"
    )
    assert task_path.is_file(), "the paper source queue is required for the identity contract"

    audit = dt.source_identity_audit(dt.load_jsonl(task_path))
    assert audit["processed_segment_count"] == 43_603
    assert audit["unique_original_task_id_count"] == 28_506
    assert audit["repeated_original_task_id_count"] == 15_097
    assert audit["extra_segments_sharing_original_task_id"] == 15_097
    assert audit["max_segments_per_original_task_id"] == 2
    assert audit["original_task_ids_rewritten"] is False


def test_stratified_reservoir_deduplicates_repeats_and_is_order_independent() -> None:
    raw_rows = [
        _raw_decision("run-1-d", scenario="paper_repeat_01"),
        _raw_decision("run-2-d", scenario="paper_repeat_02"),
        _raw_decision("other", task_id=2, segment_id="2:direct", scenario="high_flow_2x"),
    ]
    decisions = dt.validate_decision_rows(raw_rows, {0: [1, 2]})
    mappings = dt.source_release_mapping(_mapping_rows())
    links = dt.decision_source_links(decisions, mappings)
    config = dt.SamplingConfig(limit=10, minimum_per_stratum=1, maximum_per_stratum=4, seed="fixed")

    forward = dt.stratified_reservoir_sample(decisions, links, config=config)
    reverse = dt.stratified_reservoir_sample(list(reversed(decisions)), list(reversed(links)), config=config)

    assert forward.statistics["eligible_hard_case_count_before_dedupe"] == 3
    assert forward.statistics["unique_hard_case_count_after_dedupe"] == 2
    assert forward.statistics["deterministic_repeat_count_removed"] == 1
    assert [row["semantic_fingerprint"] for row in forward.rows] == [
        row["semantic_fingerprint"] for row in reverse.rows
    ]
    repeated = next(row for row in forward.rows if row["deterministic_repeat_count"] == 2)
    assert repeated["scenario"] == "paper"
    assert repeated["sample_weight"] == 1.0
    assert "source_queue_delay" in repeated["why_hard"]


def test_quota_shortfall_is_explicit_when_global_limit_cannot_cover_minima() -> None:
    decisions = dt.validate_decision_rows(
        [
            _raw_decision("a", scenario="scenario_a"),
            _raw_decision("b", task_id=2, segment_id="2:direct", scenario="scenario_b"),
        ],
        {0: [1, 2]},
    )
    links = dt.decision_source_links(decisions, dt.source_release_mapping(_mapping_rows()))
    sample = dt.stratified_reservoir_sample(
        decisions,
        links,
        config=dt.SamplingConfig(limit=1, minimum_per_stratum=1, maximum_per_stratum=2, seed="fixed"),
    )

    assert sample.statistics["sample_count"] == 1
    assert sample.statistics["strata_below_requested_minimum"] == 1
    assert sum(not row["minimum_quota_satisfied"] for row in sample.balance_rows) == 1


def test_reservoir_retains_only_bounded_rows_per_stratum() -> None:
    raw_rows = []
    task_rows = []
    for task_id in range(1, 101):
        segment_id = f"{task_id}:direct"
        raw_rows.append(
            _raw_decision(
                f"d-{task_id}",
                task_id=task_id,
                segment_id=segment_id,
                scenario="high_flow_2x",
            )
        )
        task_rows.append(
            {
                "task_id": task_id,
                "segment_id": segment_id,
                "start": 4,
                "goal": 3,
                "g4irsf7_original_pass_time": 10.8,
                "pass_time": 12.0,
            }
        )
    decisions = dt.validate_decision_rows(raw_rows, {0: [1, 2]})
    links = dt.decision_source_links(decisions, dt.source_release_mapping(task_rows))
    sample = dt.stratified_reservoir_sample(
        decisions,
        links,
        config=dt.SamplingConfig(limit=3, minimum_per_stratum=1, maximum_per_stratum=4, seed="fixed"),
    )

    assert sample.statistics["unique_hard_case_count_after_dedupe"] == 100
    assert sample.statistics["maximum_retained_candidate_rows"] == 4
    assert sample.statistics["sample_count"] == 3
    assert all(row["sample_weight"] == pytest.approx(100 / 3) for row in sample.rows)


def test_feature_lineage_separates_runtime_metadata_and_labels() -> None:
    rows = dt.feature_lineage_rows()
    dt.validate_feature_lineage(rows)

    by_field = {row["field_path"]: row for row in rows}
    assert by_field["candidate_records[].features.*"]["lineage"] == "runtime"
    assert by_field["original_arrival_time"]["lineage"] == "metadata"
    assert by_field["tail_bucket"]["lineage"] == "label"
    assert by_field["tail_bucket"]["storage_boundary"] == "separate_outcome_table"
    assert by_field["tail_bucket"]["model_input_allowed"] is False


def test_feature_lineage_recursively_rejects_label_derived_runtime_feature() -> None:
    rows = dt.feature_lineage_rows()
    target = next(
        row for row in rows if row["field_path"] == "candidate_records[].features.static_potential"
    )
    target["sources"] = ["tail_bucket"]

    with pytest.raises(dt.DecisionTraceValidationError, match="post-hoc/label"):
        dt.validate_feature_lineage(rows)


def test_artifact_writer_keeps_runtime_trace_and_outcome_table_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    task_path = tmp_path / "tasks.jsonl"
    outcome_path = tmp_path / "outcomes.jsonl"
    map_path = tmp_path / "map.json"
    trace_path.write_text(
        json.dumps(_raw_decision(fault_mode="single_delayed_30s")) + "\n",
        encoding="utf-8",
    )
    task_path.write_text(json.dumps(_mapping_rows()[0]) + "\n", encoding="utf-8")
    outcome_path.write_text(
        json.dumps({"decision_id": "d-1", "reached_goal": True, "tail_bucket": "p99"}) + "\n",
        encoding="utf-8",
    )
    map_path.write_text(
        json.dumps({"nodes": [{"location": 0, "outgoing": [1, 2]}]}),
        encoding="utf-8",
    )

    for name in (
        "TRACE_SCHEMA",
        "TRACE_MANIFEST",
        "TRACE_SAMPLE",
        "OUTCOME_SAMPLE",
        "HARD_CASE_INDEX",
        "SAMPLING_BALANCE",
        "SAMPLING_REPORT",
        "LINEAGE_TABLE",
        "LINEAGE_REPORT",
        "SOURCE_RELEASE_TABLE",
        "SOURCE_IDENTITY_TABLE",
        "SOURCE_IDENTITY_REPORT",
    ):
        original = getattr(runner, name)
        monkeypatch.setattr(runner, name, tmp_path / original.name)
    monkeypatch.setattr(runner, "DATASET_DIR", tmp_path)
    monkeypatch.setattr(runner, "TABLE_DIR", tmp_path)
    monkeypatch.setattr(runner, "REPORT_DIR", tmp_path)

    manifest = runner.write_artifacts(
        trace_paths=[trace_path],
        task_path=task_path,
        map_path=map_path,
        outcome_path=outcome_path,
        scenario="paper_repeat_01",
        scale="2x",
        fault_mode="single_delayed_30s",
        config=dt.SamplingConfig(limit=10, minimum_per_stratum=1, maximum_per_stratum=2),
    )

    runtime_row = json.loads((tmp_path / runner.TRACE_SAMPLE.name).read_text(encoding="utf-8"))
    outcome_row = json.loads((tmp_path / runner.OUTCOME_SAMPLE.name).read_text(encoding="utf-8"))
    assert "reached_goal" not in runtime_row
    assert "tail_bucket" not in runtime_row
    assert outcome_row["reached_goal"] is True
    assert manifest["validation"]["candidate_equals_true_outgoing_set"] == "PASS"
    assert manifest["validation"]["runtime_bag_identity"]["status"] == "PASS"
    assert manifest["source_task"]["identity_audit"]["original_task_ids_rewritten"] is False
    assert manifest["sampling"]["sample_count"] == 1
    assert manifest["coverage"]["status"] == "PARTIAL_WITH_EXPLICIT_BLOCKER"
    assert manifest["coverage"]["fault_covered"] is False
    assert manifest["coverage"]["fault_coverage_requirement"] == (
        "at_least_one_fault_local_active_committed_decision"
    )
    assert manifest["coverage"]["fault_local_active_decision_count_before_dedupe"] == 0
    assert manifest["coverage"]["dimension_counts_before_dedupe"]["fault"] == {
        "fault_scenario_inactive_here": 1
    }
    assert "missing_fault_decisions" in manifest["coverage"]["blockers"]

    active_fault = _raw_decision(fault_mode="single_delayed_30s")
    active_fault["local_snapshot"]["faulted_outgoing_count"] = 1  # type: ignore[index]
    active_fault["candidate_records"][0]["features"]["advertised_fault"] = True  # type: ignore[index]
    trace_path.write_text(json.dumps(active_fault) + "\n", encoding="utf-8")
    active_manifest = runner.write_artifacts(
        trace_paths=[trace_path],
        task_path=task_path,
        map_path=map_path,
        outcome_path=outcome_path,
        scenario="paper_repeat_01",
        scale="2x",
        fault_mode="single_delayed_30s",
        config=dt.SamplingConfig(limit=10, minimum_per_stratum=1, maximum_per_stratum=2),
    )
    assert active_manifest["coverage"]["fault_covered"] is True
    assert active_manifest["coverage"]["fault_local_active_decision_count_before_dedupe"] == 1
    assert active_manifest["coverage"]["dimension_counts_before_dedupe"]["fault"] == {
        "fault_local_active": 1
    }
    assert "missing_fault_decisions" not in active_manifest["coverage"]["blockers"]


def test_runtime_payload_decisions_key_is_supported(tmp_path: Path) -> None:
    path = tmp_path / "payload.json"
    path.write_text(
        json.dumps({"decisions": [_raw_decision()], "summary": {"decision_count": 1}}),
        encoding="utf-8",
    )

    rows, context = runner._read_trace(path)

    assert len(rows) == 1
    assert rows[0]["decision_id"] == "d-1"
    assert context == {"_runtime_summary": {"decision_count": 1}}


def test_trace_shard_completeness_requires_every_untruncated_shard() -> None:
    shards = [
        {
            "path": "shard0.json",
            "decision_count": 6,
            "context": {"trace_shard_count": 2, "trace_shard_index": 0},
            "runtime_summary": {
                "decision_trace_seen_count": 10,
                "decision_trace_shard_seen_count": 6,
                "decision_trace_stored_count": 6,
                "hold_trace_stored_count": 0,
                "decision_trace_truncated": False,
            },
        },
        {
            "path": "shard1.json",
            "decision_count": 4,
            "context": {"trace_shard_count": 2, "trace_shard_index": 1},
            "runtime_summary": {
                "decision_trace_seen_count": 10,
                "decision_trace_shard_seen_count": 4,
                "decision_trace_stored_count": 4,
                "hold_trace_stored_count": 0,
                "decision_trace_truncated": False,
            },
        },
    ]

    complete = runner._trace_completeness(shards)
    missing = runner._trace_completeness([shards[0]])
    truncated_shards = [dict(shard) for shard in shards]
    truncated_shards[1] = {
        **truncated_shards[1],
        "runtime_summary": {**shards[1]["runtime_summary"], "decision_trace_truncated": True},
    }
    truncated = runner._trace_completeness(truncated_shards)
    lost_hold_shards = [dict(shard) for shard in shards]
    lost_hold_shards[0] = {
        **lost_hold_shards[0],
        "decision_count": 5,
        "runtime_summary": {
            **shards[0]["runtime_summary"],
            "decision_trace_stored_count": 5,
        },
    }
    lost_hold = runner._trace_completeness(lost_hold_shards)

    assert complete["status"] == "PASS"
    assert complete["stored_decision_count_sum"] == 10
    assert missing["status"] == "PARTIAL_WITH_EXPLICIT_BLOCKER"
    assert any("incomplete_trace_shard_indices" in blocker for blocker in missing["blockers"])
    assert truncated["status"] == "PARTIAL_WITH_EXPLICIT_BLOCKER"
    assert any("decision_trace_truncated" in blocker for blocker in truncated["blockers"])
    assert lost_hold["status"] == "PARTIAL_WITH_EXPLICIT_BLOCKER"
    assert any("stored_plus_hold_mismatch" in blocker for blocker in lost_hold["blockers"])


def test_trace_completeness_validates_independent_scenario_runs_separately() -> None:
    shards = []
    for scenario, seen in (("high_flow_2p5x", 11), ("high_flow_4x", 19), ("temporal_fault", 7)):
        shards.append(
            {
                "path": scenario + ".json",
                "decision_count": seen,
                "context": {
                    "scenario": scenario,
                    "trace_shard_count": 1,
                    "trace_shard_index": 0,
                },
                "runtime_summary": {
                    "decision_trace_seen_count": seen,
                    "decision_trace_shard_seen_count": seen,
                    "decision_trace_stored_count": seen,
                    "hold_trace_stored_count": 0,
                    "decision_trace_truncated": False,
                },
            }
        )

    result = runner._trace_completeness(shards)

    assert result["status"] == "PASS"
    assert result["run_group_count"] == 3
    assert result["global_decision_seen_count"] == 37
    assert result["stored_decision_count_sum"] == 37
    assert all(group["status"] == "PASS" for group in result["groups"])


def test_compiled_event_runtime_binding_matches_decision_contract() -> None:
    from czr005 import cpp_backend
    from scripts.eval.g4i_runtime import _graph_records

    if not cpp_backend.is_available():
        pytest.skip("C++ extension is not built in this environment")
    module = cpp_backend.load_cpp_module()
    if not hasattr(module, "g4irsf11_event_runtime_from_records"):
        pytest.skip("built C++ extension predates G4IRSF11 event runtime")
    node_records, edge_records, heuristic = _graph_records()
    payload = dict(
        module.g4irsf11_event_runtime_from_records(
            node_records=node_records,
            edge_records=edge_records,
            heuristic_time=heuristic,
            bag_records=[("binding:direct", 900001, 0.0, 1000.0, 3, 47, "3")],
            max_decisions_per_bag=32,
            max_events=20_000,
            trace_limit=256,
            scenario="binding_contract",
            scale=1.0,
        )
    )
    assert payload["decisions"]
    context = dict(payload["trace_context"])
    raw = [
        runner._merge_metadata(
            dict(row),
            {"scenario": "binding_contract", "scale": "1x", "fault_mode": "no_fault"},
            context,
            "binding_contract",
        )
        for row in payload["decisions"]
    ]
    decisions = dt.validate_decision_rows(raw, dt.load_adjacency(ROOT / "data" / "processed" / "maps" / "map2.json"))
    identity = dt.validate_runtime_bag_identity(decisions)

    assert all(row["model_score_semantics"] == dt.MODEL_SCORE_SEMANTICS for row in decisions)
    assert all(row["selected_next"] in row["candidate_next_nodes"] for row in decisions)
    assert all(row["full_astar_used"] is False for row in decisions)
    assert identity["status"] == "PASS"
    assert identity["runtime_identity_alias_count"] == 0


def test_real_map_java_source_queue_binding_contract_keeps_negative_outcomes() -> None:
    """Reproduce the real-map contract without requiring runtime completion."""

    from czr005 import cpp_backend
    from scripts.eval.g4i_runtime import _graph_records

    if not cpp_backend.is_available():
        pytest.skip("C++ extension is not built in this environment")
    module = cpp_backend.load_cpp_module()
    if not hasattr(module, "g4irsf11_event_runtime_from_records"):
        pytest.skip("built C++ extension predates G4IRSF11 event runtime")
    task_path = ROOT / "artifacts" / "tasks" / "g4irsf7" / "java_source_queue_one_per_epoch.jsonl"
    all_task_rows = dt.load_jsonl(task_path)
    task_rows = []
    seen_task_ids: set[int] = set()
    for row in all_task_rows:
        task_id = int(row["task_id"])
        if task_id in seen_task_ids:
            continue
        seen_task_ids.add(task_id)
        task_rows.append(row)
        if len(task_rows) == 8:
            break
    bag_records = [
        (
            str(row["segment_id"]),
            int(row["task_id"]),
            float(row["pass_time"]),
            float(row["std"]),
            int(row["start"]),
            int(row["goal"]),
            str(row["start"]),
        )
        for row in task_rows
    ]
    node_records, edge_records, heuristic = _graph_records()
    payload = dict(
        module.g4irsf11_event_runtime_from_records(
            node_records=node_records,
            edge_records=edge_records,
            heuristic_time=heuristic,
            bag_records=bag_records,
            fault_windows=[],
            queue_discipline="aging",
            retry_interval=0.25,
            minimum_service_seconds=0.001,
            dispatch_headway_seconds=0.001,
            history_limit=8,
            max_decisions_per_bag=512,
            max_events=2_000_000,
            max_simulation_time=-1.0,
            trace_limit=10_000,
            local_queue_capacity=0,
            deadlock_retry_threshold=8,
            diagnostic_hops=2,
            enable_source_admission=True,
            enable_backpressure=True,
            enable_pibt_lite=True,
            enable_deadlock_escape=True,
            scenario="real_map_contract",
            scale=1.0,
        )
    )
    raw = [
        runner._merge_metadata(
            dict(row),
            {"scenario": "real_map_contract", "scale": "1x", "fault_mode": "no_fault"},
            dict(payload["trace_context"]),
            "real_map_contract",
        )
        for row in payload["decisions"]
    ]
    decisions = dt.validate_decision_rows(
        raw, dt.load_adjacency(ROOT / "data" / "processed" / "maps" / "map2.json")
    )
    identity = dt.validate_runtime_bag_identity(decisions)
    links = dt.decision_source_links(decisions, dt.source_release_mapping(task_rows))
    sample = dt.stratified_reservoir_sample(
        decisions,
        links,
        config=dt.SamplingConfig(limit=100, minimum_per_stratum=1, maximum_per_stratum=8),
    )
    summary = payload["summary"]

    assert summary["requested_count"] == 8
    assert summary["completed_count"] + summary["failed_count"] == 8
    assert all(bool(row["failure_reason"]) for row in payload["bags"] if not row["completed"])
    assert summary["runtime_full_astar_calls"] == 0
    assert summary["reservation_conflicts"] == 0
    assert sample.statistics["input_decision_count"] == len(decisions)
    assert identity["status"] == "PASS"
    # Completion/failure remains an outcome, not a schema gate.  A future
    # negative regression is therefore retained instead of hidden by a forced
    # completion assertion.
