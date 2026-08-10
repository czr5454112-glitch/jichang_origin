from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import run_g4irsf20_route_learning as route_learning


def _native_candidate(
    group_index: int,
    candidate_index: int,
    service_signal: float,
) -> dict[str, object]:
    event_time = 10.0 + group_index * 0.1
    travel_time = 1.0 + 0.05 * candidate_index
    return {
        "event_time": event_time,
        "target_queue_length": 0,
        "target_scheduled_incoming": 0,
        "corridor_next_available": event_time,
        "target_next_available": event_time + travel_time,
        "travel_time": travel_time,
        "static_potential": 5.0,
        "priority_slack_seconds": 60.0 - group_index * 0.01,
        "priority_age_seconds": 5.0 + group_index * 0.02,
        "recent_visit_count": candidate_index,
        "junction_queue_length": group_index % 5,
        "junction_next_available_time": event_time + group_index % 3,
        "priority_local_contention": group_index % 7,
        "current_goal_queue_length": group_index % 4,
        "target_goal_queue_length": candidate_index + group_index % 3,
        "target_goal_scheduled_incoming": group_index % 2,
        "current_goal_max_wait": float(group_index % 6),
        "goal_conditioned_differential": service_signal - 0.5,
        "estimated_service_rate": service_signal,
        "service_weighted_pressure": 2.0 * service_signal,
        "advertised_fault": False,
        "fault_message_age_seconds": 0.5 + 0.1 * candidate_index,
        "two_hop_queue_pressure": int(4 * service_signal),
    }


def _write_fake_compact(
    path: Path,
    *,
    learnable: bool,
    group_count: int = 90,
) -> None:
    rows: list[dict[str, Any]] = []
    for group_index in range(group_count):
        # Two exact-state rows share every split key, proving that the campaign
        # groups rather than randomly splitting individual rows.
        split_bucket = group_index // 2
        alternate_is_better = learnable and split_bucket % 3 != 0
        signals = (0.0, 1.0) if alternate_is_better else (1.0, 0.0)
        candidates: list[dict[str, Any]] = []
        for candidate_index, signal in enumerate(signals):
            native = _native_candidate(group_index, candidate_index, signal)
            s4_cost = (
                float(native["travel_time"])
                + float(native["static_potential"])
            )
            utility = (
                -s4_cost + 2.0 * signal
                if learnable
                else -s4_cost
            )
            candidates.append(
                {
                    "legal": True,
                    "native_features": native,
                    "utility": utility,
                }
            )
        rows.append(
            {
                "schema_id": route_learning.COMPACT_SCHEMA,
                "choice_group_id": f"choice-{group_index}",
                "clone_group_id": f"clone-{split_bucket}",
                "request_group": f"request-{split_bucket % 11}",
                "normal_flow": group_index % 5 != 0,
                "primary_pair_labeled": True,
                "full_legal_action_set_labeled": True,
                "wait_action_labeled": True,
                "label_scope": "COMPLETE_LEGAL_CHOICE_SET",
                "s4_index": 0,
                "candidates": candidates,
            }
        )
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _all_keys(value: object) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value] + [
            nested for child in value.values() for nested in _all_keys(child)
        ]
    if isinstance(value, list):
        return [nested for child in value for nested in _all_keys(child)]
    return []


def test_fake_compact_campaign_compares_all_groups_and_exports_only_a_go(
    tmp_path: Path,
) -> None:
    compact = tmp_path / "route_compact.jsonl"
    report_path = tmp_path / "route_report.json"
    policy_path = tmp_path / "route_policy.json"
    _write_fake_compact(compact, learnable=True)

    report = route_learning.run_campaign(
        input_path=compact,
        report_path=report_path,
        policy_path=policy_path,
        epochs=100,
        seed=20,
    )

    assert report["status"] == "OFFLINE_GO"
    assert report["data"]["group_split_contamination_count"] == 0
    assert all(report["data"]["checks"].values())
    assert len(report["comparisons"]) == 6 * 3
    assert {row["model_family"] for row in report["comparisons"]} == set(
        route_learning.MODEL_FAMILIES
    )
    assert {row["feature_group"] for row in report["comparisons"]} == {
        "F0",
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
    }
    evaluated = [row for row in report["comparisons"] if row["status"] == "EVALUATED"]
    assert evaluated
    for row in evaluated:
        assert "top1_accuracy" in row["audit"]["raw"]
        assert "pairwise_accuracy" in row["audit"]["raw"]
        assert "pairwise_auc" in row["audit"]["raw"]
        assert "mean_regret" in row["audit"]["selective"]
        assert "coverage" in row["audit"]
        assert "abstention_rate" in row["audit"]["coverage"]
        assert "normal_flow_mutation_potential" in row["audit"]

    promoted = [row for row in evaluated if row["promotion_pass"]]
    assert promoted
    for row in promoted:
        normal_flow = row["audit"]["normal_flow_mutation_potential"]
        assert normal_flow["applied_mutation_count"] >= 1
        assert normal_flow["beneficial_precision"] >= 0.80
        assert row["promotion_checks"]["audit_normal_flow_mutation"] is True

    assert report_path.is_file()
    assert policy_path.is_file()
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    assert policy["active"] is False
    assert policy["status"] == "OFFLINE_CANDIDATE"
    assert policy["native_closed_loop_validated"] is False
    assert policy["fallback"] == "S4"
    assert policy["feature_group"] in {"F3", "F4", "F5"}
    assert policy["model_family"] in route_learning.MODEL_FAMILIES
    assert policy["promotion_checks"]
    assert all(policy["promotion_checks"].values())
    lowered_keys = [key.lower() for key in _all_keys(policy)]
    assert not any("sha256" in key or "hash" in key for key in lowered_keys)
    assert not any(
        forbidden in feature_name.lower()
        for feature_name in policy["feature_names"]
        for forbidden in ("_id", "future", "outcome", "global", "oracle")
    )
    assert policy["model"]["identity_features_used"] is False
    assert policy["model"]["outcome_features_used"] is False


def test_no_improvement_is_explicit_no_go_without_active_policy(
    tmp_path: Path,
) -> None:
    compact = tmp_path / "route_no_go.jsonl"
    report_path = tmp_path / "route_no_go_report.json"
    policy_path = tmp_path / "must_not_exist.json"
    _write_fake_compact(compact, learnable=False, group_count=60)
    policy_path.write_text(
        json.dumps({"status": "ACTIVE_RESEARCH_POLICY", "active": True}),
        encoding="utf-8",
    )

    report = route_learning.run_campaign(
        input_path=compact,
        report_path=report_path,
        policy_path=policy_path,
        epochs=60,
        seed=20,
    )

    assert report["status"] == "NO_GO"
    assert report["selection"] == {
        "status": "NO_GO",
        "reason": "no model improved S4 while passing all offline gates",
        "selected_feature_group": None,
        "selected_model_family": None,
        "policy_exported": False,
    }
    assert report_path.is_file()
    assert not policy_path.exists()
    assert report["data"]["support"]["beneficial_alternative_count"] == 0


def test_primary_pair_only_data_is_an_explicit_contract_no_go(
    tmp_path: Path,
) -> None:
    compact = tmp_path / "route_primary_pair_only.jsonl"
    report_path = tmp_path / "route_primary_pair_only_report.json"
    policy_path = tmp_path / "must_not_exist.json"
    _write_fake_compact(compact, learnable=True, group_count=60)
    rows = [
        json.loads(line)
        for line in compact.read_text(encoding="utf-8").splitlines()
    ]
    for row in rows:
        row["full_legal_action_set_labeled"] = False
        row["wait_action_labeled"] = False
    compact.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    report = route_learning.run_campaign(
        input_path=compact,
        report_path=report_path,
        policy_path=policy_path,
        epochs=60,
        seed=20,
    )

    assert report["status"] == "NO_GO"
    assert report["selection"]["reason"] == (
        "promotion blocked: exact labels cover S4 versus one primary "
        "alternative, not every legal edge and WAIT"
    )
    assert report["data"]["checks"]["primary_pair_complete"] is True
    assert report["data"]["checks"]["full_legal_action_set_labeled"] is False
    assert report["data"]["checks"]["wait_action_labeled"] is False
    assert not policy_path.exists()


def test_candidate_feature_leakage_fails_before_training(tmp_path: Path) -> None:
    compact = tmp_path / "route_leak.jsonl"
    _write_fake_compact(compact, learnable=True, group_count=18)
    rows = [json.loads(line) for line in compact.read_text(encoding="utf-8").splitlines()]
    rows[0]["candidates"][0]["native_features"]["future_route_cost"] = 3.0
    compact.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    with pytest.raises(
        route_learning.RouteLearningCampaignError,
        match="FEATURE_LEAKAGE_OR_SCHEMA_ERROR.*FORBIDDEN_FEATURE",
    ):
        route_learning.run_campaign(
            input_path=compact,
            report_path=tmp_path / "unused_report.json",
            policy_path=tmp_path / "unused_policy.json",
            epochs=20,
        )
