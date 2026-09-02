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


def _activation_artifact(
    *,
    map_name: str,
    factor: float,
    manifest_sha256: str,
    summary: dict[str, object] | None = None,
) -> dict[str, object]:
    label = runner._factor_label(factor)
    raw_count, segment_count = runner.REGISTERED_POPULATION_BY_FACTOR[label]
    binary_sha256 = "b" * 64
    native_summary = {
        "loaded_cpp_binary_sha256": binary_sha256,
        **(summary or {}),
    }
    return {
        "schema": runner.SCHEMA_RUN,
        "status": "COMPLETE",
        "native_execution_started": True,
        "map": map_name,
        "nominal_load_factor": factor,
        "population": {
            "raw_bag_denominator": raw_count,
            "segment_count": segment_count,
            "whole_population": True,
        },
        "execution_integrity": {"pass": True},
        "provenance": {
            "git_commit": "a" * 40,
            "binary_sha256": binary_sha256,
            "revision_manifest_sha256": manifest_sha256,
            "canonical_sha256": runner._json_sha256(
                ["canonical", map_name, label]
            ),
            "request_sha256": runner._json_sha256(
                ["request", map_name, label]
            ),
            "load_manifest_sha256": (
                "c" * 64 if factor in {1.25, 1.5, 1.75} else None
            ),
        },
        "runtime": {"summary": native_summary},
    }


def _write_activation_campaign(
    root: Path,
    manifest: Path,
    *,
    nanning_two_x_summary: dict[str, object] | None = None,
) -> list[Path]:
    manifest_sha256 = runner._file_sha256(manifest)
    paths: list[Path] = []
    for map_name in runner.MAPS:
        for factor in runner.SCAN_FACTORS:
            summary = (
                nanning_two_x_summary
                if map_name == "nanning" and factor == 2.0
                else None
            )
            path = root / f"{map_name}_{factor:.2f}x.json"
            path.write_text(
                json.dumps(
                    _activation_artifact(
                        map_name=map_name,
                        factor=factor,
                        manifest_sha256=manifest_sha256,
                        summary=summary,
                    )
                ),
                encoding="utf-8",
            )
            paths.append(path)
    return paths


def test_j2_mutation_uses_multi_candidate_denominator_and_is_precommit(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "revision.yaml"
    manifest.write_text(
        "action_change_rate_lt: 0.5\naction_change_count_lt: 100\n",
        encoding="utf-8",
    )
    paths = _write_activation_campaign(
        tmp_path,
        manifest,
        nanning_two_x_summary={
            "merge_grant_service_opportunity_count": 584_213,
            "merge_grant_multi_candidate_opportunity_count": 66,
            "merge_grant_true_competition_count": 5,
            "merge_grant_order_mutation_count": 15,
        },
    )

    aggregate = runner.aggregate_results(
        result_paths=paths, revision_manifest_path=manifest
    )
    row = next(
        row
        for row in aggregate["activation_rows"]
        if row["map"] == "nanning" and row["nominal_load_factor"] == "2.00"
    )

    assert row["merge_grant_precommit_order_mutation_opportunity_count"] == 66
    assert row["merge_grant_exact_slot_overlap_opportunity_count"] == 5
    assert row["merge_grant_precommit_order_mutation_count"] == 15
    assert row["merge_grant_precommit_order_mutation_rate"] == pytest.approx(15 / 66)
    assert row["merge_grant_precommit_order_mutation_is_final_action"] is False
    assert row["merge_grant_exact_slot_overlap_used_as_mutation_denominator"] is False
    # With the frozen test threshold, 15/66 is rare while 15/5 would be active.
    assert row["j2_m3_classification"] == "RARELY_ACTIVATED"
    report = runner._report_text(aggregate)
    assert "PRE_COMMIT_ORDER_MUTATION" in report
    assert "not a final executed action" in report
    assert "| nanning | 2.00 | 584213 | 66 | 5 | 15 | 0.227273 |" in report


def test_activation_aggregate_rejects_failed_or_extra_cells(tmp_path: Path) -> None:
    manifest = tmp_path / "revision.yaml"
    manifest.write_text(
        "action_change_rate_lt: 0.001\naction_change_count_lt: 100\n",
        encoding="utf-8",
    )
    paths = _write_activation_campaign(tmp_path, manifest)
    failed = json.loads(paths[0].read_text(encoding="utf-8"))
    failed["status"] = "FAILED_INTEGRITY"
    failed["execution_integrity"] = {"pass": False}
    paths[0].write_text(json.dumps(failed), encoding="utf-8")

    with pytest.raises(runner.ActivationError, match="failed execution integrity"):
        runner.aggregate_results(
            result_paths=paths, revision_manifest_path=manifest
        )

    paths = _write_activation_campaign(tmp_path, manifest)
    extra = tmp_path / "map2_3.00x.json"
    extra.write_text(
        json.dumps(
            _activation_artifact(
                map_name="map2",
                factor=2.0,
                manifest_sha256=runner._file_sha256(manifest),
            )
            | {"nominal_load_factor": 3.0}
        ),
        encoding="utf-8",
    )
    with pytest.raises(runner.ActivationError, match="unregistered"):
        runner.aggregate_results(
            result_paths=[*paths, extra], revision_manifest_path=manifest
        )

    with pytest.raises(runner.ActivationError, match="duplicate"):
        runner.aggregate_results(
            result_paths=[*paths, paths[0]], revision_manifest_path=manifest
        )


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("git_commit", "d" * 40, "git identity mismatch"),
        ("binary_sha256", "d" * 64, "binary identity mismatch"),
        (
            "revision_manifest_sha256",
            "d" * 64,
            "revision-manifest identity mismatch",
        ),
    ),
)
def test_activation_aggregate_rejects_mixed_global_identity(
    tmp_path: Path,
    field: str,
    replacement: str,
    message: str,
) -> None:
    manifest = tmp_path / "revision.yaml"
    manifest.write_text(
        "action_change_rate_lt: 0.001\naction_change_count_lt: 100\n",
        encoding="utf-8",
    )
    paths = _write_activation_campaign(tmp_path, manifest)
    changed = json.loads(paths[-1].read_text(encoding="utf-8"))
    changed["provenance"][field] = replacement
    if field == "binary_sha256":
        changed["runtime"]["summary"]["loaded_cpp_binary_sha256"] = replacement
    paths[-1].write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(runner.ActivationError, match=message):
        runner.aggregate_results(
            result_paths=paths, revision_manifest_path=manifest
        )


def test_activation_aggregate_rejects_bad_workload_identity(tmp_path: Path) -> None:
    manifest = tmp_path / "revision.yaml"
    manifest.write_text(
        "action_change_rate_lt: 0.001\naction_change_count_lt: 100\n",
        encoding="utf-8",
    )
    paths = _write_activation_campaign(tmp_path, manifest)
    changed = json.loads(paths[-1].read_text(encoding="utf-8"))
    changed["population"]["raw_bag_denominator"] -= 1
    paths[-1].write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(runner.ActivationError, match="workload population mismatch"):
        runner.aggregate_results(
            result_paths=paths, revision_manifest_path=manifest
        )

    paths = _write_activation_campaign(tmp_path, manifest)
    first = json.loads(paths[0].read_text(encoding="utf-8"))
    changed = json.loads(paths[-1].read_text(encoding="utf-8"))
    changed["provenance"]["canonical_sha256"] = first["provenance"][
        "canonical_sha256"
    ]
    paths[-1].write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(runner.ActivationError, match="reused a canonical workload"):
        runner.aggregate_results(
            result_paths=paths, revision_manifest_path=manifest
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
