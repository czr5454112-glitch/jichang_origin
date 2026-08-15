from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import g4irsf24_dlp_learning as dlp
from scripts.eval import run_g4irsf24_dlp_campaign as campaign


def _decision(
    *,
    bag: int,
    decision: str,
    time: float,
    current: int,
    selected: int,
    goal: int = 4,
    travel: float = 3.0,
    tail: float = 5.0,
) -> dict[str, object]:
    return {
        "schema_id": "czr005.g4irsf11.decision_trace.v1",
        "decision_id": decision,
        "task_id": 999,
        "event_time": time,
        "current_node": current,
        "selected_next": selected,
        "goal_node": goal,
        "metadata": {"runtime_bag_id": bag},
        "candidate_records": [
            {
                "next_node": selected,
                "features": {
                    "travel_time": travel,
                    "static_potential": tail,
                },
            },
            {
                "next_node": selected + 10,
                "features": {
                    "travel_time": travel + 1.0,
                    "static_potential": tail + 4.0,
                },
            },
        ],
    }


def _outcome(
    decision: str,
    bag: int,
    *,
    safe: bool = True,
    finish_time: float | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "decision_id": decision,
        "runtime_bag_id": bag,
        "reached_goal": safe,
        "loop_or_dead_end": not safe,
    }
    if finish_time is not None:
        row["finish_time"] = finish_time
    return row


def _transition(
    t0: float,
    current: int,
    selected: int,
    *,
    goal: int = 9,
    duration: float = 5.0,
    travel: float = 3.0,
    static_current: float = 8.0,
    static_selected: float = 5.0,
) -> dict[str, object]:
    return {
        "schema": dlp.TRANSITION_SCHEMA,
        "t0": t0,
        "t1": t0 + duration,
        "current": current,
        "selected": selected,
        "goal": goal,
        "duration": duration,
        "travel_time": travel,
        "static_potential_current": static_current,
        "static_potential_selected": static_selected,
    }


def _diamond_transitions(repeats: int = 2) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for repeat in range(repeats):
        offset = float(repeat * 20)
        rows.extend(
            [
                _transition(offset, 1, 2, duration=4.0, travel=1.0),
                _transition(offset + 5.0, 2, 4, duration=5.0, travel=2.0),
                _transition(offset + 10.0, 1, 3, duration=2.0, travel=1.0),
                _transition(offset + 15.0, 3, 4, duration=3.0, travel=2.0),
                _transition(offset + 19.0, 4, 5, duration=1.0, travel=1.0),
            ]
        )
    return rows


def test_build_transitions_joins_only_observed_safe_physical_moves() -> None:
    decisions = [
        _decision(bag=7, decision="d2", time=15.0, current=2, selected=4),
        _decision(bag=7, decision="d1", time=10.0, current=1, selected=2),
        _decision(bag=8, decision="u1", time=10.0, current=1, selected=2),
        _decision(bag=8, decision="u2", time=14.0, current=2, selected=4),
        _decision(bag=9, decision="m1", time=10.0, current=1, selected=2),
        _decision(bag=9, decision="m2", time=14.0, current=3, selected=4),
    ]
    outcomes = [
        _outcome("d1", 7),
        _outcome("d2", 7),
        _outcome("u1", 8, safe=False),
        _outcome("u2", 8, safe=False),
        _outcome("m1", 9),
        _outcome("m2", 9),
    ]

    rows = dlp.build_transitions(decisions, outcomes)

    assert rows == [
        {
            "schema": dlp.TRANSITION_SCHEMA,
            "t0": 10.0,
            "current": 1,
            "selected": 2,
            "goal": 4,
            "t1": 15.0,
            "duration": 5.0,
            "travel_time": 3.0,
            "static_potential_current": 8.0,
            "static_potential_selected": 5.0,
        }
    ]
    assert not ({"task_id", "runtime_bag_id", "decision_id"} & rows[0].keys())


def test_build_transitions_retains_last_observed_edge_to_goal() -> None:
    decisions = [
        _decision(bag=7, decision="d1", time=10.0, current=1, selected=2),
        _decision(
            bag=7,
            decision="d2",
            time=15.0,
            current=2,
            selected=4,
            travel=2.0,
            tail=0.0,
        ),
    ]
    outcomes = [
        _outcome("d1", 7, finish_time=18.0),
        _outcome("d2", 7, finish_time=18.0),
    ]

    rows = dlp.build_transitions(decisions, outcomes)

    assert [(row["current"], row["selected"]) for row in rows] == [(1, 2), (2, 4)]
    assert rows[-1] == {
        "schema": dlp.TRANSITION_SCHEMA,
        "t0": 15.0,
        "current": 2,
        "selected": 4,
        "goal": 4,
        "t1": 18.0,
        "duration": 3.0,
        "travel_time": 2.0,
        "static_potential_current": 2.0,
        "static_potential_selected": 0.0,
    }
    assert not ({"task_id", "runtime_bag_id", "decision_id"} & rows[-1].keys())


def test_chronological_split_is_contiguous_and_deterministic() -> None:
    rows = [_transition(float(value), value, value + 1) for value in range(10, 0, -1)]
    split = dlp.chronological_split(
        rows, train_fraction=0.6, validation_fraction=0.2
    )

    assert [len(split[name]) for name in ("train", "validation", "test")] == [6, 2, 2]
    assert max(row["t0"] for row in split["train"]) < min(
        row["t0"] for row in split["validation"]
    )
    assert max(row["t0"] for row in split["validation"]) < min(
        row["t0"] for row in split["test"]
    )


def test_chronological_split_keeps_equal_time_events_together() -> None:
    rows = [
        _transition(time, index, index + 1)
        for index, time in enumerate((1.0, 1.0, 2.0, 2.0, 3.0, 4.0))
    ]

    split = dlp.chronological_split(
        rows, train_fraction=0.45, validation_fraction=0.25
    )

    owners = {
        row["t0"]: name
        for name, partition in split.items()
        for row in partition
    }
    assert sum(len(partition) for partition in split.values()) == len(rows)
    for time in {row["t0"] for row in rows}:
        assert {
            name
            for name, partition in split.items()
            if any(row["t0"] == time for row in partition)
        } == {owners[time]}


def test_p1_edge_ewma_is_a_small_supported_residual_table() -> None:
    rows = [
        _transition(0.0, 1, 2, duration=5.0, travel=3.0),
        _transition(10.0, 1, 2, duration=9.0, travel=3.0),
        _transition(20.0, 2, 3, duration=4.0, travel=4.0),
    ]

    fitted = dlp.fit_edge_ewma(rows, alpha=0.5, min_support=2)

    assert fitted == [
        {"from": 1, "to": 2, "residual_seconds": 4.0, "support": 2}
    ]


def test_reconvergent_corridor_projects_only_supported_first_edges() -> None:
    rows = _diamond_transitions()

    corridors = dlp.fit_reconvergent_corridors(
        list(reversed(rows)), max_hops=3, min_support=2
    )

    assert corridors == [
        {
            "from": 1,
            "to": 2,
            "reconvergence": 4,
            "path": [1, 2, 4],
            "hops": 2,
            "dynamic_duration_seconds": 9.0,
            "static_duration_seconds": 3.0,
            "residual_seconds": 6.0,
            "support": 2,
            "participating_successor_count": 2,
        },
        {
            "from": 1,
            "to": 3,
            "reconvergence": 4,
            "path": [1, 3, 4],
            "hops": 2,
            "dynamic_duration_seconds": 5.0,
            "static_duration_seconds": 3.0,
            "residual_seconds": 2.0,
            "support": 2,
            "participating_successor_count": 2,
        },
    ]
    assert corridors == dlp.fit_reconvergent_corridors(
        rows, max_hops=3, min_support=2
    )
    assert dlp.fit_reconvergent_corridors(
        rows, max_hops=3, min_support=3
    ) == []

    artifact = dlp.build_reconvergent_corridor_artifact(
        rows,
        max_hops=3,
        min_support=2,
        beta=1.0,
        margin_seconds=0.5,
        detour_allowance_seconds=2.0,
    )
    assert artifact == {
        "schema": dlp.ARTIFACT_SCHEMA,
        "mode": "ewma",
        "beta": 1.0,
        "min_support": 2,
        "margin_seconds": 0.5,
        "detour_allowance_seconds": 2.0,
        "edge_residuals": [
            {"from": 1, "to": 2, "residual_seconds": 6.0, "support": 2},
            {"from": 1, "to": 3, "residual_seconds": 2.0, "support": 2},
        ],
        "value_residuals": [],
    }
    encoded = json.dumps({"corridors": corridors, "artifact": artifact})
    for forbidden in ("task_id", "runtime_bag_id", "decision_id", "event_time", "t0", "t1"):
        assert forbidden not in encoded


def test_reconvergent_corridor_rejects_a_one_hop_search() -> None:
    with pytest.raises(dlp.DLPLearningError, match="at least 2"):
        dlp.fit_reconvergent_corridors(
            _diamond_transitions(), max_hops=1, min_support=1
        )


def test_p2_td_bootstraps_node_goal_residuals_without_identity_features() -> None:
    rows = [
        _transition(
            0.0,
            1,
            2,
            goal=3,
            duration=6.0,
            travel=4.0,
            static_current=8.0,
            static_selected=4.0,
        ),
        _transition(
            6.0,
            2,
            3,
            goal=3,
            duration=4.0,
            travel=4.0,
            static_current=4.0,
            static_selected=0.0,
        ),
    ]

    fitted = dlp.fit_td_value_residuals(rows, alpha=1.0, min_support=1)

    assert fitted == [
        {"node": 1, "goal": 3, "residual_seconds": 2.0, "support": 1},
        {"node": 2, "goal": 3, "residual_seconds": 0.0, "support": 1},
    ]


@pytest.mark.parametrize("mode", dlp.MODES)
def test_artifact_has_exact_compact_runtime_contract(mode: str) -> None:
    rows = [
        _transition(0.0, 1, 2),
        _transition(10.0, 1, 2, duration=7.0),
        _transition(20.0, 2, 9, static_current=5.0, static_selected=0.0),
    ]

    artifact = dlp.build_artifact(
        rows,
        mode=mode,
        alpha=0.5,
        beta=1.0,
        min_support=1,
        margin_seconds=2.0,
        detour_allowance_seconds=3.0,
    )

    assert artifact["schema"] == dlp.ARTIFACT_SCHEMA
    assert artifact["mode"] == mode
    assert artifact["beta"] == 1.0
    assert artifact["min_support"] == 1
    assert artifact["margin_seconds"] == 2.0
    assert artifact["detour_allowance_seconds"] == 3.0
    assert artifact["edge_residuals"]
    assert bool(artifact["value_residuals"]) is (mode == "td")
    encoded = json.dumps(artifact)
    for forbidden in ("task_id", "runtime_bag_id", "event_time", "decision_id", "t0", "t1"):
        assert forbidden not in encoded


def test_cli_writes_artifact_and_optional_compact_transitions(tmp_path: Path) -> None:
    decisions_path = tmp_path / "decisions.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    artifact_path = tmp_path / "artifact.json"
    transitions_path = tmp_path / "transitions.jsonl"
    decisions = [
        _decision(bag=bag, decision=f"{bag}-a", time=float(bag), current=1, selected=2)
        for bag in range(3)
    ] + [
        _decision(
            bag=bag,
            decision=f"{bag}-b",
            time=float(bag) + 5.0,
            current=2,
            selected=4,
        )
        for bag in range(3)
    ]
    outcomes = [
        _outcome(f"{bag}-{suffix}", bag)
        for bag in range(3)
        for suffix in ("a", "b")
    ]
    decisions_path.write_text(
        "".join(json.dumps(row) + "\n" for row in decisions), encoding="utf-8"
    )
    outcomes_path.write_text(
        "".join(json.dumps(row) + "\n" for row in outcomes), encoding="utf-8"
    )

    code = dlp.main(
        [
            "--decisions",
            str(decisions_path),
            "--bag-results",
            str(outcomes_path),
            "--output",
            str(artifact_path),
            "--transitions-output",
            str(transitions_path),
            "--mode",
            "td",
            "--min-support",
            "1",
            "--train-fraction",
            "0.34",
            "--validation-fraction",
            "0.33",
        ]
    )

    assert code == 0
    assert json.loads(artifact_path.read_text(encoding="utf-8"))["schema"] == dlp.ARTIFACT_SCHEMA
    assert len(transitions_path.read_text(encoding="utf-8").splitlines()) == 3


def test_cli_writes_reconvergent_corridor_artifact_and_report(tmp_path: Path) -> None:
    transitions_path = tmp_path / "transitions.jsonl"
    artifact_path = tmp_path / "corridor_artifact.json"
    report_path = tmp_path / "corridors.json"
    transitions_path.write_text(
        "".join(json.dumps(row) + "\n" for row in _diamond_transitions(repeats=3)),
        encoding="utf-8",
    )

    code = dlp.main(
        [
            "--transitions-input",
            str(transitions_path),
            "--output",
            str(artifact_path),
            "--strategy",
            "corridor",
            "--max-hops",
            "2",
            "--min-support",
            "2",
            "--corridor-report-output",
            str(report_path),
        ]
    )

    assert code == 0
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert artifact["mode"] == "ewma"
    assert [(row["from"], row["to"]) for row in artifact["edge_residuals"]] == [
        (1, 2),
        (1, 3),
    ]
    assert artifact["value_residuals"] == []
    assert report["schema"] == dlp.CORRIDOR_SCHEMA
    assert report["corridor_count"] == 2


def test_cli_rejects_mixed_transition_sources(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        "".join(json.dumps(row) + "\n" for row in _diamond_transitions()),
        encoding="utf-8",
    )

    code = dlp.main(
        [
            "--transitions-input",
            str(rows_path),
            "--decisions",
            str(rows_path),
            "--bag-results",
            str(rows_path),
            "--output",
            str(tmp_path / "artifact.json"),
        ]
    )

    assert code == 2
    assert not (tmp_path / "artifact.json").exists()


def test_td_offline_ranking_uses_zero_terminal_value_without_goal_row(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "td.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema": dlp.ARTIFACT_SCHEMA,
                "mode": "td",
                "beta": 1.0,
                "min_support": 1,
                "margin_seconds": 0.0,
                "detour_allowance_seconds": 0.0,
                "edge_residuals": [
                    {"from": 1, "to": 2, "residual_seconds": 2.0, "support": 1}
                ],
                "value_residuals": [
                    {"node": 1, "goal": 2, "residual_seconds": -3.0, "support": 1}
                ],
            }
        ),
        encoding="utf-8",
    )
    transitions = [
        {
            "current": 1,
            "selected": 2,
            "goal": 2,
            "duration": 5.0,
            "travel_time": 3.0,
            "static_potential_current": 8.0,
            "static_potential_selected": 0.0,
        }
    ]

    result = campaign._offline_residual_ranking(
        transitions,
        [{"id": "TD", "mode": "td"}],
        {"TD": str(artifact_path)},
    )[0]

    assert result["runtime_lookup_coverage"] == 1.0
    assert result["td_bellman_coverage"] == 1.0
    assert result["td_bellman_mae_seconds"] == 0.0
