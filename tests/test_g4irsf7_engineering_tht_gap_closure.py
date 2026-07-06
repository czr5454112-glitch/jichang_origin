from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.eval import run_g4irsf7_engineering_tht_gap_closure as g7


def test_java_source_queue_one_per_epoch_derivation() -> None:
    scratch = ROOT / ".pytest_cache" / "czr005_g4irsf7"
    scratch.mkdir(parents=True, exist_ok=True)
    source = scratch / "tasks.jsonl"
    rows = [
        {"task_id": 2, "segment_id": "2:a", "start": 52, "goal": 49, "pass_time": 19500.0},
        {"task_id": 1, "segment_id": "1:a", "start": 52, "goal": 48, "pass_time": 19500.0},
        {"task_id": 3, "segment_id": "3:a", "start": 3, "goal": 47, "pass_time": 8267.845},
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    out, meta = g7.derive_release_jsonl(source, "java_source_queue_one_per_epoch", scratch / "derived")
    derived = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    by_source = {}
    for row in derived:
        by_source.setdefault(row["start"], []).append(row["pass_time"])

    assert by_source[52] == [19500.0, 19501.0]
    assert by_source[3] == [8267.0]
    assert meta["max_source_queue_rank"] == 2


def test_promotion_status_requires_guardrails() -> None:
    row = {
        "complete_bags": 28506,
        "processed_segment_count": 43603,
        "planned_segments": 43603,
        "node_window_conflicts": 0,
        "runtime_full_astar_calls": 0,
        "gap_vs_original_min": 0.004,
        "mean_tht": 3.971,
    }

    assert g7.promotion_status(row) == "candidate_noastar_policy_v2"

    unsafe = dict(row, node_window_conflicts=1)
    assert g7.promotion_status(unsafe) == "reject_guardrail"


def test_cpp_reservation_semantics_parameter_smoke() -> None:
    from czr005 import cpp_backend

    if not cpp_backend.is_available():
        return

    import scripts.eval.g4i_runtime as g4i
    from scripts.eval import run_g4irsf5_original_protocol_comparative_validation as g5
    from scripts.eval import run_g4irsf6_paper_protocol_gap_closure as g6

    graph, _artifact = g6.derive_map_for_speed(2.5)
    node_records, edge_records, heuristic = g6.graph_records_from_map(graph)
    policy = json.loads(g5.MODEL_PATH.read_text(encoding="utf-8"))
    payload = cpp_backend.g4irsf4_no_astar_streaming_replay_from_jsonl(
        node_records=node_records,
        edge_records=edge_records,
        heuristic_time=heuristic,
        task_jsonl_path=g5.TASK_JSONL,
        w1=policy["w1"],
        b1=policy["b1"],
        w2=policy["w2"],
        b2=policy["b2"],
        risk_margin_threshold=float(policy.get("risk_margin_threshold", 1.0)),
        risk_historical_threshold=float(policy.get("risk_historical_threshold", 0.5)),
        risk_bottleneck_threshold=float(policy.get("risk_bottleneck_threshold", 5.0)),
        historical_risk_rules=g4i._historical_risk_rules(),
        fallback_rules=g4i._fallback_rules(policy),
        policy_name=g5._official_mode().policy_name,
        use_model=True,
        rule_only=False,
        risk_gated_rule=True,
        fallback_name=g5._official_mode().fallback_name,
        max_tasks=16,
        summary_only=True,
        reservation_semantics="reservation_open_end_boundary",
    )

    assert payload["summary"]["reservation_semantics"] == "reservation_open_end_boundary"
