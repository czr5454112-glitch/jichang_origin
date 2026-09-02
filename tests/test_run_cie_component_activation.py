from __future__ import annotations

import json
from pathlib import Path

import pytest

from czr005.io.legacy_tasks import RawLegacyTask
from scripts.eval import g4irsf31_map_adapter as map_adapter
from scripts.eval import run_cie_component_activation as runner


def _synthetic_flights() -> tuple[RawLegacyTask, ...]:
    rows: list[RawLegacyTask] = []
    task_id = 0
    for stream in range(13):
        for flight_index in range(4):
            std = 10_000.0 + flight_index * 1_000.0 + stream
            for bag in range(2):
                rows.append(
                    RawLegacyTask(
                        task_id=task_id,
                        entry_time=std - 1_000.0 + bag,
                        std=std,
                        start=0,
                        end=stream,
                        unloader=f"U{stream:02d}",
                        loader="L",
                        source_line=task_id + 2,
                    )
                )
                task_id += 1
    return tuple(rows)


def test_intermediate_selection_uses_whole_flights_and_largest_remainder() -> None:
    source = _synthetic_flights()

    generated, selection, offset = runner.build_factor_raw_tasks(source, 1.25)

    assert selection["stream_count"] == 13
    assert selection["source_flight_count"] == 52
    assert selection["selected_inserted_flight_count"] == 13
    assert all(value["quota"] == 1 for value in selection["per_stream"].values())
    assert selection["whole_flight_manifest_invariant"] is True
    assert selection["expanded_segment_sampling_or_duplication"] is False

    inserted = [row for row in generated if row.task_id >= offset]
    assert len(generated) == len(source) + 13 * 2
    assert len(inserted) == 13 * 2
    assert all(
        sum(row.std == candidate.std for row in inserted) == 2
        for candidate in inserted
    )
    records = selection["selected_flight_keys"]
    assert selection["selected_flight_keys_sha256"] == runner._json_sha256(records)


def test_same_flight_selection_is_reusable_for_both_map_projections() -> None:
    source = _synthetic_flights()
    generated, selection, offset = runner.build_factor_raw_tasks(source, 1.50)

    # A map projection may replace only physical start/end/loader aliases.  It
    # must retain exactly the selected raw IDs and hence the same flight key hash.
    projected_ids = {row.task_id for row in generated}
    independently_generated, second, second_offset = runner.build_factor_raw_tasks(
        source, 1.50
    )
    assert second_offset == offset
    assert {row.task_id for row in independently_generated} == projected_ids
    assert second["selected_flight_keys_sha256"] == selection[
        "selected_flight_keys_sha256"
    ]


def test_dry_request_is_full_g31_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    canonical = tmp_path / "tasks.jsonl"
    canonical.write_text(
        json.dumps(
            {
                "segment_id": "1:direct",
                "task_id": 1,
                "pallet_id": 1,
                "pass_time": 10.0,
                "std": 100.0,
                "start": 0,
                "goal": 2,
                "original_start": 0,
                "original_goal": 2,
                "original_entry_time": 10.0,
                "leg": "direct",
                "early_bag_split": False,
                "source_line": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    binary = tmp_path / "czr005_cpp.pyd"
    binary.write_bytes(b"test")
    profile = map_adapter.RuntimeMapProfile(
        name="tiny",
        source_path=tmp_path / "map.json",
        node_records=(
            (0, 1, 0.1, 0, 0, (1,)),
            (1, 0, 2.0, 1, 0, (2,)),
            (2, 2, 0.1, 2, 0, ()),
        ),
        edge_records=((0, 1, 1.0, 2.5), (1, 2, 1.0, 2.5)),
        start_nodes=(0,),
        goal_nodes=(2,),
        storage_source_nodes=(),
    )
    monkeypatch.setattr(runner, "_profile_for_map", lambda *_args: profile)

    rows, request, contract = runner.prepare_runtime_request(
        map_name="map2", canonical_path=canonical, binary=binary
    )

    assert len(rows) == 1
    assert contract["identity_gates"] == {
        key: True for key in contract["identity_gates"]
    }
    assert request["scorer_mode"] == "S4_queue_aware_rule_only"
    assert request["merge_grant_rule"] == "M3"
    assert request["merge_grant_timing_mode"] == "jit_fair_aging_deadline"
    assert request["enable_s4_local_potential_descent_guard"] is True
    assert request["enable_s4_direct_neighbor_merge_calendar_visibility"] is True
    assert request["complete_on_goal_arrival"] is True
    assert request["enable_cie_component_activation"] is True
    assert request["max_simulation_time"] == 98_259.0
    assert request["max_events"] == 60_000_000
    assert contract["static_potential"] == "H_SA"


def test_activation_classification_uses_frozen_dual_rare_threshold() -> None:
    thresholds = {
        "action_change_rate_lt": 0.001,
        "action_change_count_lt": 100,
    }
    assert runner.classify_component(0, 0, thresholds) == "NOT_ACTIVATED"
    assert runner.classify_component(10_000, 5, thresholds) == "RARELY_ACTIVATED"
    assert (
        runner.classify_component(10_000, 100, thresholds)
        == "ACTIVATED_NO_CLEAR_OUTCOME_EFFECT"
    )
    assert (
        runner.classify_component(100, 1, thresholds)
        == "ACTIVATED_NO_CLEAR_OUTCOME_EFFECT"
    )


def test_two_x_timing_is_na_even_if_population_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner.g24,
        "timing_distributions",
        lambda *_args: pytest.fail("2x protocol attempted to compute THT"),
    )

    timing = runner._timing_payload([], [], complete=True, factor=2.0)

    assert timing["status"] == "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
    assert timing["distributions"] is None
    assert timing["survivor_or_common_cohort_used"] is False
