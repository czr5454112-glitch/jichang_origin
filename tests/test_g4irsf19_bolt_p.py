from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.eval import run_g4irsf19_bolt_p as bolt_p


def _group(
    group_id: str,
    order: int,
    *,
    value: int = 1,
    delay_ms: int = 0,
    reads: list[str] | None = None,
    writes: list[str] | None = None,
    snapshot: dict[str, int] | None = None,
    operation: str = "scale",
    frontier: str = "f0",
) -> bolt_p.ProposalGroup:
    raw: dict[str, object] = {
        "group_id": group_id,
        "order": order,
        "frontier": frontier,
        "payload": {
            "operation": operation,
            "value": value,
            "factor": 3,
            "delay_ms": delay_ms,
            "tag": group_id,
        },
    }
    if reads is not None or writes is not None:
        raw["reads"] = reads or []
        raw["writes"] = writes or []
        raw["snapshot"] = snapshot or {}
    return bolt_p._group_from_mapping(raw, order)


def test_p1_replay_is_deterministic_and_outputs_are_compact(tmp_path: Path) -> None:
    groups = [_group(f"g{i}", i, value=i + 1) for i in range(4)]
    report = bolt_p.run_campaign(groups, {}, worker_counts=(1,))

    assert report["p1_deterministic_parity_pass"] is True
    assert report["all_parallel_runs_match_p1"] is True
    run = report["runs"][0]
    assert [row["group_id"] for row in run["groups"]] == [
        "g0",
        "g1",
        "g2",
        "g3",
    ]
    assert [row["proposal"]["value"] for row in run["groups"]] == [3, 6, 9, 12]
    assert run["evidence_commit_count"] == 4

    json_path = tmp_path / "bolt.json"
    csv_path = tmp_path / "bolt.csv"
    md_path = tmp_path / "bolt.md"
    bolt_p.write_outputs(
        report,
        json_path=json_path,
        csv_path=csv_path,
        markdown_path=md_path,
    )
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["simulator_internal_parallel_commit"] is False
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["workers"] == "1"
    assert "not parallel mutation" in md_path.read_text(encoding="utf-8")


def test_process_counts_preserve_canonical_result_despite_completion_order() -> None:
    groups = [
        _group(f"g{i}", i, value=i, delay_ms=(7 - i) * 2)
        for i in range(8)
    ]
    report = bolt_p.run_campaign(
        groups,
        {},
        worker_counts=(1, 2, 4, 8),
    )

    assert report["all_parallel_runs_match_p1"] is True
    assert [run["workers"] for run in report["runs"]] == [1, 2, 4, 8]
    for run in report["runs"]:
        assert run["serial_parity_pass"] is True
        assert [row["group_id"] for row in run["groups"]] == [
            f"g{i}" for i in range(8)
        ]
    assert all(
        run["worker_process_count_observed"] >= 2
        for run in report["runs"]
        if run["workers"] > 1
    )


def test_conflict_stale_and_failure_counters_are_explicit() -> None:
    groups = [
        _group("commit", 0, writes=["owner:1"], snapshot={"owner:1": 0}),
        _group(
            "conflict",
            1,
            reads=["owner:1"],
            snapshot={"owner:1": 0},
        ),
        _group(
            "stale",
            2,
            reads=["owner:2"],
            snapshot={"owner:2": 1},
        ),
        _group("failed", 3, operation="fail"),
    ]
    report = bolt_p.run_campaign(groups, {}, worker_counts=(1,))
    run = report["runs"][0]

    assert run["evidence_commit_count"] == 1
    assert run["conflict_rejection_count"] == 1
    assert run["stale_rejection_count"] == 2
    assert run["worker_failure_count"] == 1
    assert [row["aggregation_status"] for row in run["groups"]] == [
        "EVIDENCE_COMMITTED",
        "CONFLICT_STALE_REJECTED",
        "STALE_REJECTED",
        "WORKER_FAILED",
    ]
    assert report["p1_deterministic_parity_pass"] is True
    assert report["all_parallel_runs_match_p1"] is True
    assert report["all_runs_worker_failure_free"] is False
    assert report["status"] == "INCOMPLETE_OR_NONDETERMINISTIC"


def test_non_contiguous_frontier_reuse_retains_conflict_history() -> None:
    groups = [
        _group(
            "f0-first",
            0,
            frontier="f0",
            writes=["owner:1"],
            snapshot={"owner:1": 0},
        ),
        _group(
            "f1",
            1,
            frontier="f1",
            writes=["owner:2"],
            snapshot={"owner:2": 0},
        ),
        _group(
            "f0-later",
            2,
            frontier="f0",
            reads=["owner:1"],
            snapshot={"owner:1": 1},
        ),
    ]

    report = bolt_p.run_campaign(groups, {}, worker_counts=(1,))
    run = report["runs"][0]

    assert run["conflict_rejection_count"] == 1
    assert run["stale_rejection_count"] == 0
    assert run["evidence_commit_count"] == 2
    assert run["groups"][2]["conflict_keys"] == ["owner:1"]
    assert run["groups"][2]["aggregation_status"] == "CONFLICT_STALE_REJECTED"


def test_existing_g15_shards_become_disjoint_native_groups(tmp_path: Path) -> None:
    plan = {
        "schema": "czr005.g4irsf15.causal_campaign_plan.v1",
        "shards": [
            {"shard_index": 3, "targets": [{"descriptor_id": "a"}]},
            {"shard_index": 4, "targets": [{"descriptor_id": "b"}]},
        ],
    }
    path = tmp_path / "g15-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    groups, versions, source = bolt_p.load_plan(path)

    assert source == "G4IRSF15_CAUSAL_SHARD_PLAN"
    assert versions == {}
    assert [group.group_id for group in groups] == [
        "g15-shard-0003",
        "g15-shard-0004",
    ]
    assert groups[0].payload["targets"] == [{"descriptor_id": "a"}]
    assert set(groups[0].writes).isdisjoint(groups[1].writes)


def test_native_payload_is_reduced_to_action_and_gate_evidence() -> None:
    compact = bolt_p._compact_native_payload(
        {
            "schema": "pair-schema",
            "target_count": 1,
            "action_changing_pair_count": 1,
            "false_positive_pair_count": 0,
            "large_unused_field": [1, 2, 3],
            "pairs": [
                {
                    "descriptor_id": "d",
                    "kind": "I3",
                    "event_ordinal": 9,
                    "horizon": "H_bag",
                    "pair_status": "ACTION_CHANGED_HORIZON_COMPLETE",
                    "action_changed": True,
                    "pair_complete": True,
                    "live_safety_pass": True,
                    "formal_hard_gate_pass": False,
                    "hard_gate_fail_reasons": [],
                    "committed_action_certificate": {
                        "baseline_action": "EDGE:1",
                        "treatment_action": "EDGE:2",
                    },
                    "large_branch_dump": {"ignored": True},
                }
            ],
        }
    )

    assert compact["action_changing_pair_count"] == 1
    assert "large_unused_field" not in compact
    assert "large_branch_dump" not in compact["pairs"][0]
    assert compact["pairs"][0]["committed_action_certificate"][
        "treatment_action"
    ] == "EDGE:2"
