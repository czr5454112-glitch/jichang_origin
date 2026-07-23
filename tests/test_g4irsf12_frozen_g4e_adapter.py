from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import g4irsf12_frozen_g4e_adapter as adapter


@pytest.fixture(scope="module")
def evidence() -> dict[str, Any]:
    return adapter.collect_evidence(adapter.ROOT)


def test_frozen_identities_dimensions_and_complete_lineage(
    evidence: dict[str, Any],
) -> None:
    assert adapter.validate_evidence(evidence) == []
    model = evidence["model"]
    context = evidence["context"]
    assert model.raw_sha256 == adapter.MODEL_RAW_SHA256
    assert len(model.w1) == len(adapter.FEATURE_NAMES) == 22
    assert all(len(row) == 22 for row in model.w1)
    assert len(model.b1) == len(model.w2) == 22
    assert model.learned_rule_count == 16
    assert context.raw_sha256 == adapter.MAP_RAW_SHA256
    assert context.semantic_sha256 == adapter.MAP_SEMANTIC_SHA256
    assert len(context.nodes) == 54
    assert len(context.edge_travel_time) == 69

    lineage = evidence["lineage_rows"]
    assert [row["feature_name"] for row in lineage] == list(
        adapter.FEATURE_NAMES
    )
    s1_defaults = {
        int(row["feature_index"])
        for row in lineage
        if row["s1_resolution"].startswith("EXPLICIT_DEFAULT")
    }
    assert s1_defaults == {6, 11, 12, 13, 14, 19, 20, 21}
    s2_defaults = {
        int(row["feature_index"])
        for row in lineage
        if row["s2_resolution"].startswith("EXPLICIT_DEFAULT")
    }
    assert s2_defaults == s1_defaults | {7, 8}


def test_s1_defaults_non_equivalent_fields_and_s2_only_removes_node_ids(
    evidence: dict[str, Any],
) -> None:
    row = evidence["trace_rows"][0]
    s1 = adapter.feature_vectors(row, evidence["context"], "S1")
    s2 = adapter.feature_vectors(row, evidence["context"], "S2")
    assert len(s1) == len(row["candidate_next_nodes"])
    assert all(len(vector) == 22 for vector in s1)

    explicit_s1_defaults = {6, 11, 12, 13, 14, 19, 20, 21}
    for s1_vector, s2_vector in zip(s1, s2):
        assert all(s1_vector[index] == 0.0 for index in explicit_s1_defaults)
        assert s1_vector[7] != 0.0
        assert s1_vector[8] != 0.0
        assert s2_vector[7] == 0.0
        assert s2_vector[8] == 0.0
        assert all(
            s1_vector[index] == s2_vector[index]
            for index in range(22)
            if index not in {7, 8}
        )

    # A similarly named two-hop queue field is intentionally not smuggled
    # into the legacy reservation-overlap feature.
    changed = copy.deepcopy(row)
    changed["candidate_records"][0]["features"]["two_hop_queue_pressure"] = 999
    changed_s1 = adapter.feature_vectors(changed, evidence["context"], "S1")
    assert changed_s1[0][13] == 0.0
    assert changed_s1 == s1


def test_metadata_and_recorded_outputs_are_not_model_inputs(
    evidence: dict[str, Any],
) -> None:
    row = evidence["trace_rows"][0]
    baseline = adapter.feature_vectors(row, evidence["context"], "S1")

    changed = copy.deepcopy(row)
    changed["metadata"]["scenario"] = "deliberately_changed_non_model_metadata"
    changed["model_prediction"] = int(row["candidate_next_nodes"][-1])
    changed["selected_next"] = int(row["candidate_next_nodes"][-1])
    assert adapter.feature_vectors(changed, evidence["context"], "S1") == baseline

    top_level_scenario = copy.deepcopy(row)
    top_level_scenario["scenario"] = "forbidden_model_surface"
    with pytest.raises(ValueError, match="unapproved top-level"):
        adapter.feature_vectors(
            top_level_scenario, evidence["context"], "S1"
        )


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "teacher_next_node",
        "future_schedule",
        "post_hoc_success",
        "route_finish_time",
    ],
)
def test_teacher_future_and_posthoc_inputs_fail_closed(
    evidence: dict[str, Any],
    forbidden_key: str,
) -> None:
    row = copy.deepcopy(evidence["trace_rows"][0])
    row[forbidden_key] = 1
    with pytest.raises(ValueError, match="forbidden"):
        adapter.feature_vectors(row, evidence["context"], "S1")


def test_all_four_replayed_scorers_are_deterministic_candidate_local(
    evidence: dict[str, Any],
) -> None:
    row = evidence["trace_rows"][0]
    context = evidence["context"]
    model = evidence["model"]
    results = [
        adapter.score_frozen_g4e(row, context, model, "S1"),
        adapter.score_frozen_g4e(row, context, model, "S2"),
        adapter.score_rule(row, context, "S3"),
        adapter.score_rule(row, context, "S4"),
    ]
    candidates = set(row["candidate_next_nodes"])
    assert all(result.prediction in candidates for result in results)
    assert all(result.margin >= 0.0 for result in results)
    assert results == [
        adapter.score_frozen_g4e(row, context, model, "S1"),
        adapter.score_frozen_g4e(row, context, model, "S2"),
        adapter.score_rule(row, context, "S3"),
        adapter.score_rule(row, context, "S4"),
    ]

    expected_s3 = tuple(
        float(record["features"]["travel_time"])
        + float(record["features"]["static_potential"])
        for record in row["candidate_records"]
    )
    assert results[2].candidate_scores == expected_s3


def test_offline_replay_and_committed_outputs_keep_closed_loop_metrics_blank(
    evidence: dict[str, Any],
) -> None:
    replay = evidence["replay"]
    assert replay["decision_count"] == adapter.TRACE_EXPECTED_ROWS
    assert replay["candidate_score_count"] == 14_544
    assert len(replay["isolation_rows"]) == 5
    for row in replay["isolation_rows"]:
        assert row["evaluation_scope"] == adapter.DIAGNOSTIC_SCOPE
        assert row["closed_loop_run"] == "false"
        assert row["completion_rate"] == ""
        assert row["original_entry_time_tth"] == ""
    assert adapter.validate_committed_outputs(evidence, adapter.ROOT) == []

    with (adapter.ROOT / adapter.ISOLATION_TABLE_PATH).open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        committed_rows = list(csv.DictReader(handle))
    assert len(committed_rows) == 5
    assert all(row["completion_rate"] == "" for row in committed_rows)
    assert all(row["original_entry_time_tth"] == "" for row in committed_rows)

    bundle = json.loads(
        (adapter.ROOT / adapter.BUNDLE_PATH).read_text(encoding="utf-8")
    )
    assert bundle["status"] == adapter.CLAIM_STATUS
    assert bundle["claim_boundary"]["closed_loop_validated"] is False
    assert bundle["claim_boundary"]["promotion_eligible"] is False
    assert bundle["offline_trace"]["outcome_table_read"] is False
    assert bundle["input_contract"]["metadata_is_model_input"] is False
    assert len(bundle["feature_lineage"]) == 22

    report = (adapter.ROOT / adapter.REPORT_PATH).read_text(encoding="utf-8")
    assert "required closed-loop S0-S4 A/B" in report
    assert "leaves `completion_rate`" in report
    assert "No S1/S2 result here may be promoted" in report
