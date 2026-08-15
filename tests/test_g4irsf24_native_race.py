from __future__ import annotations

import pytest

from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf24_native_race as race
from scripts.eval import run_g4irsf24_reporting as reporting


def _fresh_row(
    arm: str, repeat: int, *, mean: float, p95: float, p99: float, maximum: float
) -> dict[str, object]:
    return {
        "arm": arm,
        "repeat": repeat,
        "denominator": "processed_attempt",
        "mean_s": mean,
        "p95_s": p95,
        "p99_s": p99,
        "max_s": maximum,
        "completed_segments": 4,
        "completed_raw_bags": 2,
        "safety_pass": True,
    }


def test_three_denominators_share_one_complete_population() -> None:
    inputs = [
        {
            "segment_id": "a",
            "task_id": 1,
            "original_entry_time": 0.0,
            "pass_time": 2.0,
        },
        {
            "segment_id": "b",
            "task_id": 2,
            "original_entry_time": 10.0,
            "pass_time": 12.0,
        },
    ]
    bags = [
        {
            "segment_id": "a",
            "completed": True,
            "release_time": 2.0,
            "admitted_time": 5.0,
            "finish_time": 12.0,
        },
        {
            "segment_id": "b",
            "completed": True,
            "release_time": 12.0,
            "admitted_time": 13.0,
            "finish_time": 22.0,
        },
    ]

    metrics, raw = race.timing_distributions(inputs, bags)

    assert len(raw) == 2
    assert metrics["processed_attempt"]["mean_seconds"] == 8.0
    assert metrics["java_release"]["mean_seconds"] == 10.0
    assert metrics["original_entry"]["mean_seconds"] == 12.0


def test_compatible_safety_accepts_absent_newer_abi_counters() -> None:
    safety = race._safety_for_arm(
        "F2",
        {
            "completed_count": 2,
            "failed_count": 0,
            "reservation_conflicts": 0,
            "event_limit_reached": False,
            "time_limit_reached": False,
        },
        requested=2,
    )
    assert safety["pass"] is True


def test_strict_s4_safety_rejects_absent_current_abi_fields() -> None:
    safety = race._safety_for_arm(
        "S4",
        {
            "completed_count": 2,
            "failed_count": 0,
            "event_limit_reached": False,
            "time_limit_reached": False,
        },
        requested=2,
    )

    assert safety["pass"] is False
    assert "reservation_conflicts" in safety["missing_fields"]
    assert "full_cie_astar_runtime_fallback" in safety["missing_fields"]


def test_strict_s4_safety_accepts_complete_current_abi_fields() -> None:
    summary = {
        "completed_count": 2,
        **{name: 0 for name in race.HARD_SAFETY_ZERO_FIELDS},
        **{name: False for name in race.HARD_SAFETY_FALSE_FIELDS},
    }

    safety = race._safety_for_arm("S4", summary, requested=2)

    assert safety["pass"] is True
    assert safety["missing_fields"] == []


def test_exact_hca_release_trace_replaces_native_release(tmp_path) -> None:
    prefix = harness.InputPrefix(
        size_segments=1,
        rows=(
            {
                "segment_id": "a",
                "task_id": 1,
                "pass_time": 10.75,
                "original_entry_time": 10.75,
            },
        ),
        prefix_sha256="fixture",
        raw_bag_count=1,
        first_segment_id="a",
        last_segment_id="a",
    )
    lifecycle = tmp_path / "lifecycle.csv"
    lifecycle.write_text(
        "segment_id,release_epoch\na,12.0\n",
        encoding="utf-8",
    )

    adjusted, summary = race.apply_exact_hca_releases(prefix, lifecycle)

    assert adjusted.rows[0]["pass_time"] == 12.0
    assert adjusted.rows[0]["original_entry_time"] == 10.75
    assert summary["release_minus_canonical_pass_mean_seconds"] == 1.25


def test_release_evidence_same_source_is_validated_without_truncation(
    tmp_path, monkeypatch
) -> None:
    evidence = tmp_path / "release.csv"
    contents = (
        "segment_id,task_id,start,goal,release_epoch\n"
        "a,1,3,47,12.0\n"
        "b,2,4,47,13.0\n"
    )
    evidence.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(reporting, "RELEASE_EVIDENCE", evidence)

    assert reporting._release_evidence(evidence) == 2
    assert evidence.read_text(encoding="utf-8") == contents


@pytest.mark.parametrize(
    "contents, message",
    [
        ("segment_id,task_id,start,goal,release_epoch\n", "no data rows"),
        (
            "segment_id,task_id,start,goal,release_epoch\n"
            "a,1,3,47,12.0\n"
            "a,2,4,47,13.0\n",
            "duplicate segment_id",
        ),
        ("segment_id,task_id,start,goal\na,1,3,47\n", "fields mismatch"),
    ],
)
def test_release_evidence_same_source_rejects_invalid_compact_data(
    tmp_path, monkeypatch, contents: str, message: str
) -> None:
    evidence = tmp_path / "release.csv"
    evidence.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(reporting, "RELEASE_EVIDENCE", evidence)

    with pytest.raises(reporting.ReportingError, match=message):
        reporting._release_evidence(evidence)


def test_fresh_decision_requires_every_repeat_to_win() -> None:
    rows = [
        _fresh_row("HCA", repeat, mean=100.0, p95=120.0, p99=130.0, maximum=140.0)
        for repeat in (1, 2)
    ] + [
        _fresh_row("S4", 1, mean=90.0, p95=110.0, p99=120.0, maximum=150.0),
        _fresh_row("S4", 2, mean=110.0, p95=130.0, p99=140.0, maximum=160.0),
    ]

    decision = reporting._fresh_decision(rows)

    assert decision["FRESH_HCA_STRICT_WIN"] is False
    assert decision["status"] == "FRESH_HCA_NOT_BEATEN"


def test_fresh_decision_rejects_mismatched_repeat_sets() -> None:
    rows = [
        _fresh_row("HCA", 1, mean=100.0, p95=120.0, p99=130.0, maximum=140.0),
        _fresh_row("HCA", 2, mean=100.0, p95=120.0, p99=130.0, maximum=140.0),
        _fresh_row("S4", 1, mean=80.0, p95=100.0, p99=110.0, maximum=150.0),
    ]

    assert reporting._fresh_decision(rows)["status"] == reporting.NOT_MEASURED


def test_fresh_decision_aggregates_two_paired_clear_wins() -> None:
    rows = [
        _fresh_row("HCA", repeat, mean=100.0, p95=120.0, p99=130.0, maximum=140.0)
        for repeat in (1, 2)
    ] + [
        _fresh_row("S4", repeat, mean=80.0, p95=100.0, p99=110.0, maximum=150.0)
        for repeat in (1, 2)
    ]

    decision = reporting._fresh_decision(rows)

    assert decision["status"] == "FRESH_HCA_CLEAR_WIN"
    assert decision["repeat_count"] == 2
    assert decision["s4_safety_pass_all_repeats"] is True
