from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.eval import run_g4irsf9_v2_candidate_tiering_open_end_proof as g9


def test_java_closed_interval_treats_touching_endpoint_as_conflict() -> None:
    assert g9.java_closed_interval_conflict(0.0, 1.0, 1.0, 2.0) is True
    assert g9.open_end_interval_conflict(0.0, 1.0, 1.0, 2.0) is False
    assert g9.java_closed_interval_conflict(0.0, 1.0, 1.0001, 2.0) is False
    assert g9.java_closed_interval_conflict(0.0, 1.0, 0.5, 1.5) is True


def test_final_open_end_category_prefers_java_closed_evidence() -> None:
    assert (
        g9.final_open_end_category(
            "java_closed_interval_conflict",
            "original_output_inferred_open_end",
            "engineering_reasonable_but_unproven",
        )
        == "java_closed_interval_conflict"
    )


def test_candidate_tiering_keeps_open_enhancement_separate() -> None:
    tiers = {candidate.candidate: candidate for candidate in g9.candidates("java_closed_interval_conflict")}

    assert tiers[g9.SAFE_POLICY_ID].base_claim_level == "paper_protocol_engineering_candidate"
    assert tiers[g9.SAFE_POLICY_ID].reservation_semantics == "baseline"
    assert tiers[g9.OPEN_POLICY_ID].base_claim_level == "engineering_enhancement_not_paper_candidate"
    assert tiers[g9.OPEN_POLICY_ID].reservation_semantics == "reservation_open_end_boundary"


def test_source_queue_backlog_fixture(tmp_path: Path) -> None:
    original = tmp_path / "original.jsonl"
    release = tmp_path / "release.jsonl"
    original_rows = [
        {"task_id": 1, "segment_id": "1:a", "start": 52, "goal": 49, "pass_time": 100.0},
        {"task_id": 2, "segment_id": "2:a", "start": 52, "goal": 49, "pass_time": 100.0},
        {"task_id": 3, "segment_id": "3:a", "start": 52, "goal": 49, "pass_time": 100.0},
    ]
    release_rows = [
        {**original_rows[0], "pass_time": 100.0},
        {**original_rows[1], "pass_time": 101.0},
        {**original_rows[2], "pass_time": 102.0},
    ]
    original.write_text("\n".join(json.dumps(row) for row in original_rows) + "\n", encoding="utf-8")
    release.write_text("\n".join(json.dumps(row) for row in release_rows) + "\n", encoding="utf-8")

    original_map = {g9.g8.segment_key(row): row for row in g9.g8.load_jsonl(original)}
    grouped = {}
    for row in g9.g8.load_jsonl(release):
        key = g9.g8.segment_key(row)
        source = int(row["start"])
        grouped.setdefault(source, []).append((float(original_map[key]["pass_time"]), float(row["pass_time"]), key))

    items = grouped[52]
    assert len(items) == 3
    assert max(int(release_time) for _original, release_time, _key in items) == 102
    assert sum(max(0.0, release_time - int(original_time)) for original_time, release_time, _key in items) == 3.0

