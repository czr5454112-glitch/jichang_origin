from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.eval import cie_backlog_area_correction as correction
from scripts.eval import cie_fixed_denominator_business as business_metrics
from scripts.eval import run_cie_random_robustness as random_runner


def _legacy_metric(
    *,
    arrivals: int,
    departures: int,
    end: int,
    area: float,
    drain: float,
) -> dict:
    return {
        "arrival_count": arrivals,
        "departure_count": departures,
        "end_backlog": end,
        "backlog_area_seconds": area,
        "drain_time_seconds": drain,
    }


def _legacy_business() -> dict:
    return {
        "fixed_horizon_seconds": 100.0,
        "backlog": {
            "raw_bag_total": _legacy_metric(
                arrivals=10, departures=8, end=2, area=100.0, drain=5.0
            ),
            "raw_bag_source_until_all_segments_admitted": _legacy_metric(
                arrivals=10, departures=9, end=1, area=60.0, drain=3.0
            ),
            "raw_bag_network_after_all_segments_admitted": _legacy_metric(
                arrivals=9, departures=8, end=1, area=40.0, drain=2.0
            ),
        },
    }


def test_legacy_raw_areas_receive_exact_fixed_horizon_tail() -> None:
    view = correction.correction_view(
        _legacy_business(), raw_last_arrival=80.0
    )

    groups = view["groups"]
    assert groups["raw_bag_total"]["derived_last_event_seconds"] == 85.0
    assert groups["raw_bag_total"]["legacy_area_seconds"] == 100.0
    assert groups["raw_bag_total"]["corrected_area_seconds"] == 130.0
    assert (
        groups["raw_bag_source_until_all_segments_admitted"][
            "corrected_area_seconds"
        ]
        == 77.0
    )
    assert (
        groups["raw_bag_network_after_all_segments_admitted"][
            "corrected_area_seconds"
        ]
        == 55.0
    )
    assert view["source_artifact_mutated"] is False


def test_ambiguous_legacy_network_tail_is_explicit_nm() -> None:
    payload = _legacy_business()
    payload["backlog"]["raw_bag_total"]["drain_time_seconds"] = 0.0
    payload["backlog"][
        "raw_bag_source_until_all_segments_admitted"
    ]["drain_time_seconds"] = 0.0

    view = correction.correction_view(payload, raw_last_arrival=80.0)
    network = view["groups"]["raw_bag_network_after_all_segments_admitted"]

    assert network["reportable"] is False
    assert network["corrected_area_seconds"] is None
    assert network["status"] == "N_M_LEGACY_LAST_EVENT_NOT_EXACTLY_RECOVERABLE"


def test_no_departures_uses_last_arrival_as_exact_total_endpoint() -> None:
    payload = _legacy_business()
    total = payload["backlog"]["raw_bag_total"]
    total.update(
        departure_count=0,
        end_backlog=10,
        drain_time_seconds="Infinity",
    )

    view = correction.correction_view(payload, raw_last_arrival=80.0)
    total_view = view["groups"]["raw_bag_total"]

    assert total_view["derived_last_event_seconds"] == 80.0
    assert total_view["corrected_area_seconds"] == 300.0


def test_inconsistent_legacy_end_counter_is_explicit_nm() -> None:
    payload = _legacy_business()
    payload["backlog"]["raw_bag_total"]["end_backlog"] = 1

    view = correction.correction_view(payload, raw_last_arrival=80.0)
    total = view["groups"]["raw_bag_total"]

    assert total["reportable"] is False
    assert total["status"] == "N_M_INVALID_OR_INCONSISTENT_LEGACY_COUNTERS"


def test_new_business_payload_is_used_without_second_correction() -> None:
    inputs = [
        {
            "segment_id": "1:a",
            "task_id": 1,
            "pass_time": 0.0,
            "original_entry_time": 0.0,
            "std": 5.0,
        }
    ]
    results = [
        {
            "segment_id": "1:a",
            "completed": False,
            "release_time": 0.0,
            "admitted_time": -1.0,
            "finish_time": -1.0,
        }
    ]
    payload = business_metrics.summarize(inputs, results, fixed_horizon=10.0)

    view = correction.correction_view(payload, raw_last_arrival=0.0)
    total = view["groups"]["raw_bag_total"]

    assert total["status"] == "EXACT_NATIVE_OBSERVATION_END_V2"
    assert total["corrected_area_seconds"] == 10.0
    assert total["correction_seconds"] == 0.0


def test_standalone_supplement_keeps_source_hash_and_legacy_value(
    tmp_path: Path,
) -> None:
    artifact = {
        "schema": "czr005.cie_targeted_ablation.run.v1",
        "status": "COMPLETE",
        "scale": 2,
        "fixed_denominator_business": {"detailed": _legacy_business()},
    }
    artifact["fixed_denominator_business"]["detailed"][
        "fixed_horizon_seconds"
    ] = 98_259.0
    source = tmp_path / "cell.json"
    source.write_text(json.dumps(artifact), encoding="utf-8")

    written = correction.write_supplements(
        [source], output_dir=tmp_path / "supplements"
    )
    supplement = json.loads(written[0].read_text(encoding="utf-8"))

    assert source.read_text(encoding="utf-8") == json.dumps(artifact)
    assert supplement["source"]["sha256"]
    assert (
        supplement["groups"]["raw_bag_total"]["legacy_area_seconds"]
        == 100.0
    )
    assert (
        supplement["groups"]["raw_bag_total"]["reported_method"]
        == "LEGACY_PLUS_EXACT_FIXED_HORIZON_TAIL_V1"
    )


def test_random_last_arrival_requires_reproduced_manifest_and_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = random_runner.REVISION_MANIFEST.resolve(strict=True)
    contract = random_runner.load_random_contract(manifest)
    workload_source = tmp_path / "random-workload.jsonl"
    workload_source.write_text("{}\n", encoding="utf-8")
    perturbation = {
        "pairing_key": {
            "map": "map2",
            "load_factor": 2.0,
            "seed": contract.seeds[0],
        },
        "arrival_jitter_seconds": {"realization_sha256": "arrival"},
        "base_arrival_schedule_sha256": "base-arrival",
        "randomized_arrival_schedule_sha256": "random-arrival",
        "combined_realization_sha256": "combined",
        "same_realization_required_for_both_arms": True,
        "arm_used_to_generate_randomness": False,
    }
    workload = SimpleNamespace(
        source_path=workload_source,
        rows=(
            {
                "segment_id": "1:a",
                "task_id": 1,
                "pass_time": 100.0,
                "original_entry_time": 90.0,
            },
            {
                "segment_id": "2:a",
                "task_id": 2,
                "pass_time": 210.0,
                "original_entry_time": 200.0,
            },
        ),
    )
    monkeypatch.setattr(
        random_runner,
        "prepare_randomized_cell",
        lambda _args, _contract: (
            "case",
            workload,
            {},
            {},
            {"perturbation": perturbation},
        ),
    )
    artifact = {
        "schema": random_runner.SCHEMA,
        "map": "map2",
        "load_factor": 2.0,
        "seed": contract.seeds[0],
        "arm": "P0D0",
        "random_contract": {"manifest_sha256": contract.manifest_sha256},
        "provenance": {
            "binary_path": str(tmp_path / "binary.pyd"),
            "workload_sha256": correction._sha256_file(workload_source),
        },
        "perturbation": perturbation,
    }

    last_arrival, identity = correction.regenerate_random_last_raw_arrival(
        artifact, manifest_path=manifest
    )

    assert last_arrival == 200.0
    assert identity["pass"] is True
    assert all(identity["gates"].values())


def test_random_regeneration_reuses_recorded_same_hca_source_root(
    tmp_path: Path,
) -> None:
    manifest = random_runner.REVISION_MANIFEST.resolve(strict=True)
    source_root = tmp_path / "frozen-hca"
    source_root.mkdir()
    artifact = {
        "map": "map2",
        "load_factor": 1.0,
        "seed": 104729,
        "arm": "P0D0",
        "provenance": {"binary_path": str(tmp_path / "binary.pyd")},
        "release_protocol": {
            "base_release_mode_before_random_jitter": "same_hca",
            "base_same_hca_release_trace_pass": True,
            "evidence": {
                "pass": True,
                "status": "ELIGIBLE_EXACT_HCA_RELEASE_TRACE",
                "source_root": str(source_root),
            },
        },
    }

    args = correction._random_args(artifact, manifest)

    assert args.map2_hca_case_root == source_root
    assert args.nanning_hca_root != source_root


def test_random_1x_regeneration_rejects_missing_release_evidence(
    tmp_path: Path,
) -> None:
    manifest = random_runner.REVISION_MANIFEST.resolve(strict=True)
    artifact = {
        "map": "map2",
        "load_factor": 1.0,
        "seed": 104729,
        "arm": "P0D0",
        "provenance": {"binary_path": str(tmp_path / "binary.pyd")},
        "release_protocol": {
            "base_release_mode_before_random_jitter": "same_hca",
            "base_same_hca_release_trace_pass": True,
        },
    }

    with pytest.raises(
        correction.BacklogAreaCorrectionError,
        match="recorded, eligible same-HCA release root",
    ):
        correction._random_args(artifact, manifest)


def test_random_regeneration_reuses_recorded_map2_2x_workload(
    tmp_path: Path,
) -> None:
    manifest = random_runner.REVISION_MANIFEST.resolve(strict=True)
    workload = tmp_path / "frozen-map2-2x.jsonl"
    artifact = {
        "map": "map2",
        "load_factor": 2.0,
        "seed": 104729,
        "arm": "P1D1",
        "provenance": {
            "binary_path": str(tmp_path / "binary.pyd"),
            "workload_path": str(workload),
        },
    }

    args = correction._random_args(artifact, manifest)

    assert args.map2_workload_2x == workload
    assert args.canonical_workload is None


def test_random_regeneration_reuses_recorded_nanning_workload_directory(
    tmp_path: Path,
) -> None:
    manifest = random_runner.REVISION_MANIFEST.resolve(strict=True)
    workload = tmp_path / "frozen-nanning" / "nanning_2x_canonical.jsonl"
    artifact = {
        "map": "nanning",
        "load_factor": 2.0,
        "seed": 104729,
        "arm": "P0D0",
        "provenance": {
            "binary_path": str(tmp_path / "binary.pyd"),
            "workload_path": str(workload),
        },
    }

    args = correction._random_args(artifact, manifest)

    assert args.nanning_task_dir == workload.parent
    assert args.canonical_workload is None
