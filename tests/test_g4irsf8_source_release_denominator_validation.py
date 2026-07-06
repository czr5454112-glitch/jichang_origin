from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.eval import run_g4irsf7_engineering_tht_gap_closure as g7
from scripts.eval import run_g4irsf8_source_release_denominator_validation as g8


def test_denominator_summary_exposes_source_release_delay() -> None:
    tasks = [
        {"task_id": 1, "segment_id": "1:a", "goal_reached": True, "attempt_time": 10.0, "finish_time": 40.0},
        {"task_id": 1, "segment_id": "1:b", "goal_reached": True, "attempt_time": 20.0, "finish_time": 50.0},
    ]
    expected = {1: 2}
    original = {"1:a": 0.0, "1:b": 5.0}
    release = {"1:a": 10.0, "1:b": 20.0}

    original_summary = g8.summarize_with_denominator(tasks, expected, "original_entry_time_tth", original, release)
    release_summary = g8.summarize_with_denominator(tasks, expected, "java_release_time_tth", original, release)
    processed_summary = g8.summarize_with_denominator(tasks, expected, "processed_segment_attempt_time_tth", original, release)

    assert original_summary.mean_minutes == (40.0 + 45.0) / 60.0
    assert release_summary.mean_minutes == 60.0 / 60.0
    assert processed_summary.mean_minutes == release_summary.mean_minutes


def test_release_derivation_test_fixture_does_not_touch_formal_artifact() -> None:
    scratch = ROOT / ".pytest_cache" / "czr005_g4irsf8"
    scratch.mkdir(parents=True, exist_ok=True)
    source = scratch / "tasks.jsonl"
    rows = [
        {"task_id": 1, "segment_id": "1:a", "start": 52, "goal": 49, "pass_time": 100.0},
        {"task_id": 2, "segment_id": "2:a", "start": 52, "goal": 49, "pass_time": 100.0},
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    formal = g8.FORMAL_SOURCE_QUEUE
    before = g8._sha256(formal) if formal.exists() else ""
    out, meta = g7.derive_release_jsonl(source, "java_source_queue_one_per_epoch", scratch / "derived")
    after = g8._sha256(formal) if formal.exists() else ""

    assert out.parent == scratch / "derived"
    assert meta["row_count"] == 2
    assert before == after


def test_claim_allowed_blocks_open_end_without_java_proof() -> None:
    allowed, note = g8.claim_allowed_for_denominator(
        "source_queue_plus_open_end",
        "java_release_time_tth",
        "release_denominator_supported",
        "engineering_reasonable_but_not_java_proven",
    )

    assert allowed is False
    assert "open-end" in note

