from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.eval import run_cie_external_baseline_robustness as external


ROOT = Path(__file__).resolve().parents[1]


def test_integer_jitter_is_frozen_bounded_and_repeatable() -> None:
    task_ids = [9, 2, 7, 2]
    first = external.integer_jitter(external.SEEDS[0], task_ids)
    second = external.integer_jitter(external.SEEDS[0], reversed(task_ids))
    assert first == second
    assert sorted(first) == [2, 7, 9]
    assert all(isinstance(value, int) and -5 <= value <= 5 for value in first.values())
    assert external.integer_jitter(external.SEEDS[1], task_ids) != first


def test_raw_jitter_naturally_crosses_direct_ebs_boundary_when_sampled() -> None:
    tasks = tuple(
        external.RawLegacyTask(
            task_id=task_id,
            entry_time=100.0,
            std=4900.0 if task_id == 5 else 1000.0,
            start=3,
            end=49,
            unloader="1",
            loader="C2",
            source_line=task_id + 2,
        )
        for task_id in range(6)
    )
    shifted, offsets = external.jitter_raw_tasks(tasks, seed=external.SEEDS[0])
    assert offsets[5] == 1
    assert tasks[5].slack_at_entry == 4800.0
    assert shifted[5].slack_at_entry == 4799.0
    assert len(external.expand_tasks(tasks)) == 7
    assert len(external.expand_tasks(shifted)) == 6


def test_one_point_seven_five_uses_same_flight_mask_on_each_maps_own_raw() -> None:
    map2 = tuple(
        external.RawLegacyTask(
            task_id=task_id,
            entry_time=100.0 + task_id,
            std=1000.0 + 1000.0 * task_id,
            start=3,
            end=49,
            unloader="1",
            loader="C2",
            source_line=task_id + 2,
        )
        for task_id in range(6)
    )
    nanning = tuple(
        external.RawLegacyTask(
            task_id=task.task_id,
            entry_time=task.entry_time,
            std=task.std,
            start=101,
            end=16,
            unloader=task.unloader,
            loader=task.loader,
            source_line=task.source_line,
        )
        for task in map2
    )
    map2_generated, map2_identity = external.build_base_raw_tasks(map2, 1.75)
    nanning_generated, nanning_identity = external.build_base_raw_tasks(
        nanning,
        1.75,
        selection_source_tasks=map2,
    )

    assert {task.task_id for task in map2_generated} == {
        task.task_id for task in nanning_generated
    }
    assert map2_identity["selection_sha256"] == nanning_identity["selection_sha256"]
    assert nanning_identity["cross_map_schedule_projection_by_raw_task_id"] is True
    assert {task.start for task in nanning_generated} == {101}
    assert {task.end for task in nanning_generated} == {16}
    assert {task.end for task in map2_generated} == {49}

    map2_two_x, _ = external.build_base_raw_tasks(map2, 2.0)
    nanning_two_x, nanning_two_x_identity = external.build_base_raw_tasks(
        nanning,
        2.0,
        selection_source_tasks=map2,
    )
    assert {
        task.task_id: (task.entry_time, task.std) for task in map2_two_x
    } == {
        task.task_id: (task.entry_time, task.std) for task in nanning_two_x
    }
    assert {task.start for task in nanning_two_x} == {101}
    assert {task.end for task in nanning_two_x} == {16}
    assert nanning_two_x_identity[
        "cross_map_schedule_projection_by_raw_task_id"
    ] is True


def test_one_generated_raw_file_is_authority_for_all_three_methods(tmp_path: Path) -> None:
    source = tmp_path / "inputdata.txt"
    source.write_text(
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "0 100 1000 3 49 1 C2\n"
        "1 200 6000 4 48 2 C1\n",
        encoding="utf-8",
    )
    identity = external.generate_cell(
        source_path=source,
        output_root=tmp_path / "workloads",
        load_factor=1.0,
        seed=external.SEEDS[0],
    )
    audit = external.audit_cell(Path(identity["raw_path"]).parent / "identity.json")
    assert audit["pass"] is True
    assert identity["raw_bag_count"] == 2
    assert identity["segment_count"] == 3
    assert identity["map"] == "map2"
    assert identity["map_sha256"] == external._sha256_file(external.DEFAULT_MAP)
    assert identity["storage_in_goal"] == 47
    assert identity["storage_out_start"] == 52
    assert identity["segment_population_policy"].startswith("DERIVE_FROM_JITTERED_RAW")
    consumers = identity["consumer_contract"]
    assert consumers["FENG_NATIVE_HCA"] == "raw_path"
    assert consumers["FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"] == "raw_path"
    assert consumers["G31_S4_NATIVE_SYSTEM"].startswith("canonical_path")
    assert Path(identity["raw_path"]).read_bytes()
    assert Path(identity["canonical_path"]).read_bytes()


def test_missing_nanning_frozen_source_is_materialized_and_sha_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.eval import run_g4irsf31_nanning_workload as nanning_workload

    task_dir = tmp_path / "nanning_tasks"
    source = task_dir / "nanning_1x_raw.txt"
    map_path = tmp_path / "nanning_map.txt"
    map_path.write_text("2 0.5 0.5 1.0 1.0\n", encoding="utf-8")
    raw_text = (
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "0 100 1000 3 4 1 C2\n"
    )
    calls: list[Path] = []

    def fake_build_workload(**kwargs: object) -> dict[str, object]:
        output_dir = Path(str(kwargs["output_dir"]))
        output_dir.mkdir(parents=True)
        (output_dir / "nanning_1x_raw.txt").write_bytes(raw_text.encode("utf-8"))
        calls.append(output_dir)
        return {
            "status": "COMPLETE",
            "raw_task_count": external.EXPECTED_POPULATIONS[1.0][0],
            "lifecycle": {"storage_in_goal": 53, "storage_out_start": 53},
        }

    protocol = external.MapProtocol(
        name="nanning",
        map_path=map_path,
        source_path=source,
        expected_map_sha256=external._sha256_file(map_path),
        expected_source_sha256=external.hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        storage_in_goal=53,
        storage_out_start=53,
        source_protocol="TEST_FROZEN_NANNING_1X",
    )
    monkeypatch.setitem(external.MAP_PROTOCOLS, "nanning", protocol)
    monkeypatch.setattr(external, "DEFAULT_NANNING_TASK_DIR", task_dir)
    monkeypatch.setattr(nanning_workload, "build_workload", fake_build_workload)

    assert external.prepare_frozen_source("nanning") == source.resolve()
    assert calls == [task_dir]
    assert external.prepare_frozen_source("nanning") == source.resolve()
    assert calls == [task_dir]

    source.write_bytes((raw_text + "1 200 1000 3 4 1 C2\n").encode("utf-8"))
    with pytest.raises(external.ExternalBaselineError, match="source identity drift"):
        external.prepare_frozen_source("nanning")


def test_map2_and_nanning_cells_use_distinct_raw_maps_and_storage_projection(
    tmp_path: Path,
) -> None:
    map2_map = tmp_path / "map2.txt"
    nanning_map = tmp_path / "nanning.txt"
    map2_map.write_text("60 0.5 0.5 1.0 1.0\n", encoding="utf-8")
    nanning_map.write_text("156 0.5 0.5 1.0 1.0\n", encoding="utf-8")
    map2_source = tmp_path / "map2_raw.txt"
    nanning_source = tmp_path / "nanning_raw.txt"
    header = "ID EntryTime(s) STD(s) star end Unloader Loader\n"
    map2_source.write_text(
        header
        + "0 100 1000 3 49 1 C2\n"
        + "1 200 6000 4 48 2 C1\n"
        + "2 300 2000 3 49 1 C2\n"
        + "3 400 7000 4 48 2 C1\n",
        encoding="utf-8",
    )
    nanning_source.write_text(
        header
        + "0 100 1000 101 16 1 C2\n"
        + "1 200 6000 103 17 2 C1\n"
        + "2 300 2000 101 16 1 C2\n"
        + "3 400 7000 103 17 2 C1\n",
        encoding="utf-8",
    )
    root = tmp_path / "workloads"
    map2 = external.generate_cell(
        source_path=map2_source,
        map_path=map2_map,
        map_name="map2",
        output_root=root,
        load_factor=1.0,
        seed=external.SEEDS[0],
    )
    nanning = external.generate_cell(
        source_path=nanning_source,
        map_path=nanning_map,
        map_name="nanning",
        output_root=root,
        load_factor=1.0,
        seed=external.SEEDS[0],
    )

    assert map2["raw_sha256"] != nanning["raw_sha256"]
    assert map2["canonical_sha256"] != nanning["canonical_sha256"]
    assert (map2["storage_in_goal"], map2["storage_out_start"]) == (47, 52)
    assert (nanning["storage_in_goal"], nanning["storage_out_start"]) == (53, 53)
    nanning_rows = [
        json.loads(line)
        for line in Path(nanning["canonical_path"]).read_text(encoding="utf-8").splitlines()
    ]
    early_rows = [row for row in nanning_rows if row["task_id"] == 1]
    assert [(row["start"], row["goal"]) for row in early_rows] == [
        (103, 53),
        (53, 17),
    ]
    for identity in (map2, nanning):
        path = Path(identity["raw_path"]).parent / "identity.json"
        assert external.audit_cell(path)["pass"] is True

    map2_scaled = external.generate_cell(
        source_path=map2_source,
        map_path=map2_map,
        map_name="map2",
        output_root=root,
        load_factor=1.75,
        seed=external.SEEDS[0],
    )
    nanning_scaled = external.generate_cell(
        source_path=nanning_source,
        map_path=nanning_map,
        map_name="nanning",
        output_root=root,
        load_factor=1.75,
        seed=external.SEEDS[0],
        selection_source_path=map2_source,
    )
    _header, map2_scaled_raw = external.parse_legacy_tasks(
        Path(map2_scaled["raw_path"])
    )
    _header, nanning_scaled_raw = external.parse_legacy_tasks(
        Path(nanning_scaled["raw_path"])
    )
    assert {
        task.task_id: (task.entry_time, task.std) for task in map2_scaled_raw
    } == {
        task.task_id: (task.entry_time, task.std) for task in nanning_scaled_raw
    }
    assert nanning_scaled["load_construction"]["selection_authority"][
        "sha256"
    ] == external._sha256_file(map2_source)
    assert external.audit_cell(
        Path(nanning_scaled["raw_path"]).parent / "identity.json"
    )["pass"] is True

    nanning_map.write_text("156 0.5 0.5 2.0 1.0\n", encoding="utf-8")
    nanning_identity_path = Path(nanning["raw_path"]).parent / "identity.json"
    with pytest.raises(external.ExternalBaselineError, match="map identity drift"):
        external.audit_cell(nanning_identity_path)
    nanning_map.write_text("156 0.5 0.5 1.0 1.0\n", encoding="utf-8")
    drifted_identity = json.loads(nanning_identity_path.read_text(encoding="utf-8"))
    drifted_identity["storage_out_start"] = 52
    nanning_identity_path.write_text(json.dumps(drifted_identity), encoding="utf-8")
    with pytest.raises(external.ExternalBaselineError, match="identity audit failed"):
        external.audit_cell(nanning_identity_path)


def test_dry_run_plan_has_180_commands_and_map_bound_workload_identity(
    tmp_path: Path,
) -> None:
    plan = external.build_dry_run_plan(
        workload_root=tmp_path / "workloads",
        result_root=tmp_path / "results",
        python="python",
        java="java",
        javac="javac",
        binary=tmp_path / "czr005_cpp.pyd",
    )
    assert plan["execution_started"] is False
    assert plan["maps"] == ["map2", "nanning"]
    assert plan["command_count"] == 180
    assert len(plan["entries"]) == 60
    for entry in plan["entries"]:
        protocol = external.map_protocol(entry["map"])
        assert set(entry["commands"]) == set(external.METHODS)
        hca = entry["commands"]["FENG_NATIVE_HCA"]
        dh = entry["commands"]["FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"]
        assert hca[hca.index("--map-path") + 1] == str(protocol.map_path)
        assert int(hca[hca.index("--storage-in-goal") + 1]) == protocol.storage_in_goal
        assert int(hca[hca.index("--storage-out-start") + 1]) == protocol.storage_out_start
        assert hca[hca.index("--input-path") + 1] == entry["raw_workload"]
        assert dh[dh.index("--map-path") + 1] == str(protocol.map_path)
        assert dh[dh.index("--input-path") + 1] == entry["raw_workload"]
        assert "--allow-external-workload" in dh
        assert dh[dh.index("--external-workload-identity") + 1] == entry["identity"]
        assert int(dh[dh.index("--seed") + 1]) == entry["seed"]
        assert float(dh[dh.index("--horizon-seconds") + 1]) == external.FIXED_HORIZON_SECONDS
        assert dh[dh.index("--classes-dir") + 1] == str(external.DEFAULT_DH_CLASSES_DIR)
        assert "--skip-compile" in dh
        g31 = entry["commands"]["G31_S4_NATIVE_SYSTEM"]
        assert g31[g31.index("--map") + 1] == entry["map"]
        assert g31[g31.index("--canonical") + 1] == entry["canonical_projection"]


def _normalized_result(
    *,
    tmp_path: Path,
    load: float,
    seed: int,
    method: str,
    value: float,
    full: bool,
    map_name: str = "map2",
) -> Path:
    protocol = external.map_protocol(map_name)
    identity_dir = tmp_path / "identities" / map_name / f"{load}_{seed}"
    identity_dir.mkdir(parents=True, exist_ok=True)
    identity_path = identity_dir / "identity.json"
    if not identity_path.exists():
        identity_path.write_text(
            json.dumps(
                {
                    "schema": external.WORKLOAD_SCHEMA,
                    "map": map_name,
                    "map_sha256": protocol.expected_map_sha256,
                    "storage_in_goal": protocol.storage_in_goal,
                    "storage_out_start": protocol.storage_out_start,
                    "seed": seed,
                    "load_factor": load,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    metrics = {
        "completed_raw_bag_count": value,
        "population_latency_mean_seconds": value if load != 2.0 and full else None,
    }
    payload = {
        "schema": external.RESULT_SCHEMA,
        "method": method,
        "map": map_name,
        "seed": seed,
        "load_factor": load,
        "workload_identity_path": str(identity_path),
        "workload_identity_sha256": external._sha256_file(identity_path),
        "workload_map_sha256": protocol.expected_map_sha256,
        "storage_in_goal": protocol.storage_in_goal,
        "storage_out_start": protocol.storage_out_start,
        "survivor_timing_used": False,
        "full_population_complete": full,
        "normalization_contract": (
            {
                "native_binary_sha256": external.EXPECTED_G31_BINARY_SHA256,
            }
            if method == external.REFERENCE_METHOD
            else (
                {
                    "reconstruction_java_source_sha256": (
                        external.EXPECTED_DH_SOURCE_SHA256
                    ),
                    "compiled_java_class_sha256": external.EXPECTED_DH_CLASS_SHA256,
                }
                if method == "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"
                else {}
            )
        ),
        "metrics": metrics,
    }
    path = tmp_path / "results" / f"{map_name}_{load}_{seed}_{method}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize("map_name", ["map2", "nanning"])
def test_broken_dh_port_is_rejected_but_map2_evidence_remains_reusable(
    tmp_path: Path, map_name: str
) -> None:
    path = _normalized_result(
        tmp_path=tmp_path,
        load=1.0,
        seed=external.SEEDS[0],
        method="FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION",
        value=1.0,
        full=True,
        map_name=map_name,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["normalization_contract"].update(
        reconstruction_java_source_sha256=external.LEGACY_DH_SOURCE_SHA256,
        compiled_java_class_sha256=external.LEGACY_DH_CLASS_SHA256,
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    if map_name == "nanning":
        with pytest.raises(external.ExternalBaselineError, match=external.INVALIDATED_DH_STATUS):
            external.aggregate_results([path], bootstrap_replicates=2)
    else:
        assert external.load_normalized_result(path)["map"] == "map2"
        payload["normalization_contract"]["compiled_java_class_sha256"] = "0" * 64
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(external.ExternalBaselineError, match="compiled class identity"):
            external.load_normalized_result(path)


def test_two_x_timing_is_rejected_even_if_full_population(tmp_path: Path) -> None:
    path = _normalized_result(
        tmp_path=tmp_path,
        load=2.0,
        seed=external.SEEDS[0],
        method=external.REFERENCE_METHOD,
        value=1.0,
        full=True,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metrics"]["population_latency_mean_seconds"] = 100.0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(external.ExternalBaselineError, match="2x timing"):
        external.load_normalized_result(path)


def test_result_map_coordinate_cannot_alias_another_map(tmp_path: Path) -> None:
    path = _normalized_result(
        tmp_path=tmp_path,
        load=1.0,
        seed=external.SEEDS[0],
        method=external.REFERENCE_METHOD,
        value=1.0,
        full=True,
        map_name="map2",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["map"] = "nanning"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(external.ExternalBaselineError, match="coordinates mismatch"):
        external.load_normalized_result(path)


@pytest.mark.parametrize(
    ("method", "contract_key", "stale_value", "message"),
    [
        (
            external.REFERENCE_METHOD,
            "native_binary_sha256",
            "not-final-b00",
            "final b00",
        ),
        (
            "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION",
            "reconstruction_java_source_sha256",
            "9ac97a4773706661bb981dfaa469886f74da4cebff62cabbc9490d40ca6bc461",
            "DH source is not final",
        ),
    ],
)
def test_stale_executor_identities_are_rejected_before_resume_or_aggregate(
    tmp_path: Path,
    method: str,
    contract_key: str,
    stale_value: str,
    message: str,
) -> None:
    path = _normalized_result(
        tmp_path=tmp_path,
        load=1.0,
        seed=external.SEEDS[0],
        method=method,
        value=1.0,
        full=True,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["normalization_contract"][contract_key] = stale_value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(external.ExternalBaselineError, match=message):
        external.load_normalized_result(path)


def test_aggregate_emits_formal_two_x_timing_na(tmp_path: Path) -> None:
    paths: list[Path] = []
    for map_name in external.MAPS:
        for seed in external.SEEDS:
            for method_index, method in enumerate(external.METHODS):
                paths.append(
                    _normalized_result(
                        tmp_path=tmp_path,
                        load=2.0,
                        seed=seed,
                        method=method,
                        value=100.0 + method_index,
                        full=True,
                        map_name=map_name,
                    )
                )
    aggregate = external.aggregate_results(paths, bootstrap_replicates=100)
    assert aggregate["observed_result_count"] == 60
    timing = [
        row
        for row in aggregate["rows"]
        if row["load_factor"] == 2.0
        and row["metric"] == "population_latency_mean_seconds"
    ]
    assert len(timing) == 4
    assert {row["map"] for row in timing} == set(external.MAPS)
    assert all(row["status"] == "FORMAL_2X_TIMING_NA_BY_PROTOCOL" for row in timing)
    assert all(row["paired_seed_count"] == 0 for row in timing)


def test_nanning_dh_uses_ported_reporting_alias_without_changing_runtime_id(
    tmp_path: Path,
) -> None:
    paths: list[Path] = []
    for seed in external.SEEDS:
        for method_index, method in enumerate(external.METHODS):
            paths.append(
                _normalized_result(
                    tmp_path=tmp_path,
                    load=1.0,
                    seed=seed,
                    method=method,
                    value=100.0 + method_index,
                    full=True,
                    map_name="nanning",
                )
            )

    aggregate = external.aggregate_results(paths, bootstrap_replicates=100)
    dh_rows = [
        row
        for row in aggregate["rows"]
        if row["map"] == "nanning"
        and row["runtime_comparison"]
        == "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"
    ]
    assert dh_rows
    assert {row["comparison"] for row in dh_rows} == {
        external.NANNING_DH_REPORTING_METHOD
    }
    assert external.reporting_method(
        "map2", "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"
    ) == "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _tiny_native_identity(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    source = tmp_path / "source.txt"
    source.write_text(
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "0 100 1000 3 49 1 C2\n",
        encoding="utf-8",
    )
    external.generate_cell(
        source_path=source,
        output_root=tmp_path / "workloads",
        load_factor=1.0,
        seed=external.SEEDS[0],
    )
    identity_path = external.cell_dir(
        tmp_path / "workloads", 1.0, external.SEEDS[0]
    ) / "identity.json"
    return identity_path, json.loads(identity_path.read_text(encoding="utf-8"))


def test_three_native_formats_normalize_to_one_strict_result_schema(
    tmp_path: Path,
) -> None:
    identity_path, identity = _tiny_native_identity(tmp_path)
    result_dir = external.cell_dir(tmp_path / "results", 1.0, external.SEEDS[0])
    entry = float(
        Path(str(identity["raw_path"])).read_text(encoding="utf-8").splitlines()[1].split()[1]
    )
    segment_id = json.loads(
        Path(str(identity["canonical_path"])).read_text(encoding="utf-8").splitlines()[0]
    )["segment_id"]
    finish = entry + 20.0

    # Fresh HCA campaign evidence.
    hca_run = result_dir / "hca_native" / "run_01"
    hca_run.mkdir(parents=True)
    (result_dir / "hca_native" / "fresh_hca_summary.json").write_text(
        json.dumps(
            {
                "schema": "g4irsf24.fresh_hca.campaign.v1",
                "runs": [
                    {
                        "comparison_eligible": True,
                        "status": "complete",
                        "run_id": "run_01",
                        "canonical_raw_bag_count": 1,
                        "canonical_segment_count": 1,
                        "benchmark_summary": {
                            "last_epoch": str(external.FIXED_HORIZON_SECONDS)
                        },
                        "denominators": {
                            "processed_attempt": {
                                "seconds": {
                                    "count": 1,
                                    "mean": 20.0,
                                    "p95": 20.0,
                                    "p99": 20.0,
                                    "max": 20.0,
                                }
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (hca_run / "run_status.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "returncode": 0,
                "command": [
                    "java",
                    str(Path(str(identity["map_path"])).resolve()),
                    str(Path(str(identity["raw_path"])).resolve()),
                ],
            }
        ),
        encoding="utf-8",
    )
    _write_csv(
        hca_run / "segment_lifecycle.csv",
        [
            {
                "task_id": 0,
                "segment_id": segment_id,
                "processed_attempt_epoch": entry + 1.0,
                "finish_epoch": finish,
                "complete": True,
            }
        ],
    )
    (hca_run / "metrics.json").write_text("{}\n", encoding="utf-8")
    (hca_run / "raw_bag_timings.csv").write_text("task_id\n0\n", encoding="utf-8")

    # Feng-paper-environment DH evidence.
    dh_dir = result_dir / "feng_env_dh"
    dh_dir.mkdir(parents=True)
    (dh_dir / "runner_status.json").write_text(
        json.dumps(
            {
                "schema": "czr005.feng_paper_env_cie_dh.run.v1",
                "status": "complete",
                "returncode": 0,
                "identity": {
                    "method": "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION",
                    "map_sha256": identity["map_sha256"],
                    "input_sha256": identity["raw_sha256"],
                    "horizon_seconds": external.FIXED_HORIZON_SECONDS,
                    "external_workload_identity": {
                        "sha256": external._sha256_file(identity_path)
                    },
                    "reconstruction_java_source_aggregate_sha256": (
                        external.EXPECTED_DH_SOURCE_SHA256
                    ),
                    "compiled_java_class_aggregate_sha256": (
                        external.EXPECTED_DH_CLASS_SHA256
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    _write_csv(
        dh_dir / "summary.csv",
        [
            {
                "status": "COMPLETE",
                "raw_bag_count": 1,
                "completed_raw_bags": 1,
                "segment_count": 1,
                "full_population_timing_eligible": True,
                "diagnostic_first_admission_to_completion_mean_seconds": 19.0,
                "diagnostic_first_admission_to_completion_p95_seconds": 19.0,
                "diagnostic_first_admission_to_completion_p99_seconds": 19.0,
                "diagnostic_first_admission_to_completion_max_seconds": 19.0,
                "simulation_end_seconds": finish,
                "reproduction_level": "TEST_RECONSTRUCTION",
            }
        ],
    )
    _write_csv(
        dh_dir / "segments.csv",
        [
            {
                "source_raw_bag_id": 0,
                "admission_time_seconds": entry + 1.0,
                "completion_time_seconds": finish,
                "status": "COMPLETED",
            }
        ],
    )
    (dh_dir / "bags.csv").write_text("task_id\n0\n", encoding="utf-8")

    # G31 native result evidence.
    g31_path = result_dir / "g31_native.json"
    g31_path.write_text(
        json.dumps(
            {
                "schema": "test.g31.native",
                "status": "COMPLETE",
                "map": identity["map"],
                "execution_integrity": {"pass": True},
                "population": {"raw_bag_denominator": 1, "segment_count": 1},
                "provenance": {
                    "canonical_sha256": identity["canonical_sha256"],
                    "executor_identity": "COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE",
                    "binary_sha256": external.EXPECTED_G31_BINARY_SHA256,
                },
                "request_contract": {
                    "fixed_end_epoch": external.FIXED_HORIZON_SECONDS
                },
                "fixed_denominator_business": {
                    "detailed": {
                        "completed_raw_bag_count": 1,
                        "completion_rate": 1.0,
                        "on_time_raw_bag_count": 1,
                        "on_time_rate": 1.0,
                        "missed_bag_count": 0,
                        "missed_bag_rate": 0.0,
                        "tardiness_seconds": {
                            "fixed_horizon_all_population_lower_bound": {
                                "sum": 0.0,
                                "mean": 0.0,
                                "p95": 0.0,
                                "p99": 0.0,
                                "max": 0.0,
                            }
                        },
                        "backlog": {
                            "raw_bag_source_until_all_segments_admitted": {
                                "backlog_area_seconds": 1.0
                            },
                            "raw_bag_network_after_all_segments_admitted": {
                                "backlog_area_seconds": 19.0
                            },
                            "raw_bag_total": {"backlog_area_seconds": 20.0},
                        },
                        "completion_targets": {
                            f"time_to_{p}_percent": {
                                "reached": True,
                                "elapsed_from_first_arrival_seconds": 20.0,
                            }
                            for p in (90, 95, 99)
                        },
                    }
                },
                "full_population_timing": {
                    "distributions": {
                        "processed_attempt": {
                            "count": 1,
                            "mean": 18.0,
                            "p95": 18.0,
                            "p99": 18.0,
                            "max": 18.0,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    normalized = [
        external.normalize_native_result(
            method=method,
            identity_path=identity_path,
            result_dir=result_dir,
        )
        for method in external.METHODS
    ]
    assert {result["schema"] for result in normalized} == {external.RESULT_SCHEMA}
    assert {result["workload_identity_sha256"] for result in normalized} == {
        external._sha256_file(identity_path)
    }
    assert [
        result["metrics"]["population_latency_mean_seconds"]
        for result in normalized
    ] == [20.0, 19.0, 18.0]
    assert all(result["full_population_complete"] for result in normalized)
    for method in external.METHODS:
        external.load_normalized_result(result_dir / f"{method}.json")


def test_normalized_native_evidence_hash_drift_is_rejected(tmp_path: Path) -> None:
    identity_path, identity = _tiny_native_identity(tmp_path)
    result_dir = external.cell_dir(tmp_path / "results", 1.0, external.SEEDS[0])
    result_dir.mkdir(parents=True)
    evidence = result_dir / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    payload = {
        "schema": external.RESULT_SCHEMA,
        "method": external.REFERENCE_METHOD,
        "map": identity["map"],
        "seed": external.SEEDS[0],
        "load_factor": 1.0,
        "workload_identity_path": str(identity_path),
        "workload_identity_sha256": external._sha256_file(identity_path),
        "workload_map_sha256": identity["map_sha256"],
        "storage_in_goal": identity["storage_in_goal"],
        "storage_out_start": identity["storage_out_start"],
        "survivor_timing_used": False,
        "full_population_complete": False,
        "normalization_contract": {
            "native_binary_sha256": external.EXPECTED_G31_BINARY_SHA256,
        },
        "native_evidence": [
            {
                "path": str(evidence),
                "sha256": external._sha256_file(evidence),
            }
        ],
        "metrics": {"completed_raw_bag_count": 0},
    }
    normalized = result_dir / "normalized.json"
    normalized.write_text(json.dumps(payload), encoding="utf-8")
    external.load_normalized_result(normalized)
    evidence.write_text('{"drift": true}\n', encoding="utf-8")
    with pytest.raises(external.ExternalBaselineError, match="native evidence hash"):
        external.load_normalized_result(normalized)


def test_g31_two_x_null_full_population_timing_stays_na(tmp_path: Path) -> None:
    native_path = tmp_path / "g31_native.json"
    native_path.write_text(
        json.dumps(
            {
                "schema": "test.g31.native",
                "status": "COMPLETE",
                "map": "map2",
                "execution_integrity": {"pass": True},
                "population": {"raw_bag_denominator": 2, "segment_count": 2},
                "provenance": {
                    "canonical_sha256": "canonical-sha",
                    "executor_identity": "COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE",
                    "binary_sha256": external.EXPECTED_G31_BINARY_SHA256,
                },
                "request_contract": {
                    "fixed_end_epoch": external.FIXED_HORIZON_SECONDS
                },
                "fixed_denominator_business": {
                    "detailed": {
                        "completed_raw_bag_count": 1,
                        "completion_rate": 0.5,
                        "on_time_raw_bag_count": 1,
                        "on_time_rate": 0.5,
                        "missed_bag_count": 1,
                        "missed_bag_rate": 0.5,
                        "tardiness_seconds": {
                            "fixed_horizon_all_population_lower_bound": {
                                "sum": 1.0,
                                "mean": 0.5,
                                "p95": 0.95,
                                "p99": 0.99,
                                "max": 1.0,
                            }
                        },
                        "backlog": {},
                        "completion_targets": None,
                    }
                },
                "full_population_timing": None,
            }
        ),
        encoding="utf-8",
    )
    metrics, full, evidence, _contract = external._normalize_g31(
        {
            "map": "map2",
            "load_factor": 2.0,
            "raw_bag_count": 2,
            "segment_count": 2,
            "canonical_sha256": "canonical-sha",
        },
        native_path,
    )
    assert full is False
    assert evidence == [native_path]
    assert metrics["completed_raw_bag_count"] == 1
    assert metrics["population_latency_mean_seconds"] is None
    assert metrics["population_latency_p95_seconds"] is None
    assert metrics["population_latency_p99_seconds"] is None
    assert metrics["population_latency_max_seconds"] is None


def test_g31_two_x_null_distributions_stays_na(tmp_path: Path) -> None:
    native_path = tmp_path / "g31_native.json"
    native_path.write_text(
        json.dumps(
            {
                "schema": "test.g31.native",
                "status": "COMPLETE",
                "map": "map2",
                "execution_integrity": {"pass": True},
                "population": {"raw_bag_denominator": 2, "segment_count": 2},
                "provenance": {
                    "canonical_sha256": "canonical-sha",
                    "executor_identity": "COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE",
                    "binary_sha256": external.EXPECTED_G31_BINARY_SHA256,
                },
                "request_contract": {
                    "fixed_end_epoch": external.FIXED_HORIZON_SECONDS
                },
                "fixed_denominator_business": {
                    "detailed": {
                        "completed_raw_bag_count": 1,
                        "completion_rate": 0.5,
                        "on_time_raw_bag_count": 1,
                        "on_time_rate": 0.5,
                        "missed_bag_count": 1,
                        "missed_bag_rate": 0.5,
                        "tardiness_seconds": {
                            "fixed_horizon_all_population_lower_bound": {}
                        },
                        "backlog": {},
                        "completion_targets": {},
                    }
                },
                "full_population_timing": {"distributions": None},
            }
        ),
        encoding="utf-8",
    )

    metrics, full, _evidence, _contract = external._normalize_g31(
        {
            "map": "map2",
            "load_factor": 2.0,
            "raw_bag_count": 2,
            "segment_count": 2,
            "canonical_sha256": "canonical-sha",
        },
        native_path,
    )

    assert full is False
    assert metrics["population_latency_mean_seconds"] is None
    assert metrics["population_latency_p95_seconds"] is None
    assert metrics["population_latency_p99_seconds"] is None
    assert metrics["population_latency_max_seconds"] is None


def test_execute_resume_skips_success_and_records_missing_native_failure(
    tmp_path: Path,
) -> None:
    identity_path, identity = _tiny_native_identity(tmp_path)
    result_root = tmp_path / "results"
    result_dir = external.cell_dir(result_root, 1.0, external.SEEDS[0])
    result_dir.mkdir(parents=True)
    normalized_path = result_dir / f"{external.METHODS[0]}.json"
    normalized_path.write_text(
        json.dumps(
            {
                "schema": external.RESULT_SCHEMA,
                "method": external.METHODS[0],
                "map": identity["map"],
                "seed": external.SEEDS[0],
                "load_factor": 1.0,
                "workload_identity_path": str(identity_path),
                "workload_identity_sha256": external._sha256_file(identity_path),
                "workload_map_sha256": identity["map_sha256"],
                "storage_in_goal": identity["storage_in_goal"],
                "storage_out_start": identity["storage_out_start"],
                "survivor_timing_used": False,
                "full_population_complete": False,
                "normalization_contract": {},
                "metrics": {"completed_raw_bag_count": 0},
            }
        ),
        encoding="utf-8",
    )
    skipped = external.execute_campaign(
        workload_root=tmp_path / "workloads",
        result_root=result_root,
        python="python",
        java="java",
        javac="javac",
        binary=tmp_path / "unused.pyd",
        methods=[external.METHODS[0]],
        load_factors=[1.0],
        seeds=[external.SEEDS[0]],
        normalize_only=True,
    )
    assert skipped["failure_count"] == 0
    assert skipped["records"][0]["status"] == "SKIPPED_SUCCESS"

    failed = external.execute_campaign(
        workload_root=tmp_path / "workloads",
        result_root=result_root,
        python="python",
        java="java",
        javac="javac",
        binary=tmp_path / "unused.pyd",
        methods=[external.METHODS[1]],
        load_factors=[1.0],
        seeds=[external.SEEDS[0]],
        normalize_only=True,
    )
    assert failed["failure_count"] == 1
    failure_path = result_dir / f"{external.METHODS[1]}.failure.json"
    assert json.loads(failure_path.read_text(encoding="utf-8"))["status"].startswith(
        "FAILED_"
    )


def test_missing_lifecycle_rows_remain_in_fixed_denominator_without_timing(
    tmp_path: Path,
) -> None:
    _identity_path, identity = _tiny_native_identity(tmp_path)
    completion, admission = external._group_lifecycle(
        [],
        identity,
        task_key="task_id",
        admission_key="admitted",
        completion_key="finish",
        complete_key="complete",
        allow_missing=True,
    )
    metrics, full = external._raw_business_metrics(
        identity,
        completion_by_task=completion,
        admission_by_task=admission,
    )
    assert full is False
    assert metrics["completed_raw_bag_count"] == 0
    assert metrics["completion_rate"] == 0.0
    assert metrics["population_latency_mean_seconds"] is None
    assert metrics["total_backlog_area_seconds"] > 0.0


def test_dh_na_lifecycle_cells_remain_missing_not_parse_errors(tmp_path: Path) -> None:
    _identity_path, identity = _tiny_native_identity(tmp_path)
    completion, admission = external._group_lifecycle(
        [
            {
                "source_raw_bag_id": "0",
                "admission_time_seconds": "N/A",
                "completion_time_seconds": "N/A",
                "status": "NOT_RELEASED",
            }
        ],
        identity,
        task_key="source_raw_bag_id",
        admission_key="admission_time_seconds",
        completion_key="completion_time_seconds",
        complete_key="status",
        complete_value="COMPLETED",
    )
    assert completion == {0: None}
    assert admission == {0: None}
