from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import g4irsf31_map_adapter as map_adapter
from scripts.eval import g4irsf32_portable_inputs as portable


def _profile_payload(*, storage_mode: str = "none") -> dict:
    pairs = []
    if storage_mode == "explicit_ebs":
        pairs = [
            {
                "pair_id": "main-ebs",
                "storage_in_goal": "ebs-in",
                "storage_out_start": "ebs-out",
            }
        ]
    return {
        "schema": map_adapter.PORTABLE_MAP_SCHEMA,
        "map_id": "portable-fixture",
        "name": "portable fixture",
        # Intentionally not lexical: dense IDs must not depend on row order.
        "nodes": [
            {
                "external_id": "sink-Z",
                "node_type": 2,
                "service_time": 0.0,
                "outgoing": [],
            },
            {
                "external_id": "src-A",
                "node_type": 1,
                "service_time": 0.0,
                "outgoing": ["merge-B"],
            },
            {
                "external_id": "ebs-out",
                "node_type": 7,
                "service_time": 0.0,
                "outgoing": ["sink-Z"],
            },
            {
                "external_id": "merge-B",
                "node_type": 4,
                "service_time": 1.0,
                "outgoing": ["sink-Z", "ebs-in"],
            },
            {
                "external_id": "ebs-in",
                "node_type": 7,
                "service_time": 0.0,
                "outgoing": [],
            },
        ],
        "edges": [
            {"start": "src-A", "end": "merge-B", "length": 2.0, "speed": 2.0},
            {"start": "merge-B", "end": "sink-Z", "length": 2.0, "speed": 2.0},
            {"start": "merge-B", "end": "ebs-in", "length": 1.0, "speed": 1.0},
            {"start": "ebs-out", "end": "sink-Z", "length": 1.0, "speed": 1.0},
        ],
        "roles": {
            "source_nodes": ["src-A"],
            "goal_nodes": ["sink-Z"],
            "storage": {"mode": storage_mode, "pairs": pairs},
        },
    }


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _load_profile(tmp_path: Path, *, storage_mode: str = "none"):
    return map_adapter.load_map_profile(
        _write_json(
            tmp_path / f"map-{storage_mode}.json",
            _profile_payload(storage_mode=storage_mode),
        )
    )


def _write_workload(
    tmp_path: Path,
    rows: list[dict],
    *,
    storage_pair_id: str | None = None,
) -> Path:
    segments_path = tmp_path / "segments.jsonl"
    segments_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return _write_json(
        tmp_path / "workload.json",
        {
            "schema": portable.PORTABLE_WORKLOAD_SCHEMA,
            "map_id": "portable-fixture",
            "segment_count": len(rows),
            "segments_path": segments_path.name,
            "storage_pair_id": storage_pair_id,
        },
    )


def test_portable_map_remap_is_stable_and_roles_are_explicit(tmp_path: Path) -> None:
    first_payload = _profile_payload()
    second_payload = _profile_payload()
    second_payload["nodes"] = list(reversed(second_payload["nodes"]))
    first = map_adapter.load_map_profile(
        _write_json(tmp_path / "first.json", first_payload)
    )
    second = map_adapter.load_map_profile(
        _write_json(tmp_path / "second.json", second_payload)
    )

    assert first.external_node_ids == tuple(sorted(first.external_node_ids))
    assert first.external_node_ids == second.external_node_ids
    assert first.node_records == second.node_records
    assert first.edge_records == second.edge_records
    assert first.explicit_roles is True
    assert first.storage_mode == "none"

    missing_roles = _profile_payload()
    missing_roles.pop("roles")
    with pytest.raises(map_adapter.MapProfileError, match="roles must be an object"):
        map_adapter.load_map_profile(
            _write_json(tmp_path / "missing-roles.json", missing_roles)
        )


def test_direct_workload_maps_external_ids_into_native_request(
    tmp_path: Path,
) -> None:
    profile = _load_profile(tmp_path)
    manifest = _write_workload(
        tmp_path,
        [
            {
                "segment_id": "bag-1:direct",
                "task_id": 1,
                "pass_time": 10.0,
                "std": 100.0,
                "start_external_id": "src-A",
                "goal_external_id": "sink-Z",
                "leg": "direct",
            }
        ],
    )
    workload = portable.load_portable_workload(manifest, profile)
    request, _contract = map_adapter.build_s4_request(profile, workload.rows)

    mapping = {
        external: dense for dense, external in enumerate(profile.external_node_ids)
    }
    assert request["bag_records"][0][4:6] == (
        mapping["src-A"],
        mapping["sink-Z"],
    )
    assert request["storage_source_nodes"] == []


def test_storage_lifecycle_requires_one_explicit_profile_pair(tmp_path: Path) -> None:
    storage_rows = [
        {
            "segment_id": "bag-2:storage_in",
            "task_id": 2,
            "pass_time": 10.0,
            "std": 100.0,
            "start_external_id": "src-A",
            "goal_external_id": "ebs-in",
            "leg": "storage_in",
        },
        {
            "segment_id": "bag-2:storage_out",
            "task_id": 2,
            "pass_time": 50.0,
            "std": 100.0,
            "start_external_id": "ebs-out",
            "goal_external_id": "sink-Z",
            "leg": "storage_out",
        },
    ]
    no_storage = _load_profile(tmp_path)
    no_storage_manifest = _write_workload(tmp_path, storage_rows)
    with pytest.raises(portable.PortableInputError, match="explicitly selected"):
        portable.load_portable_workload(no_storage_manifest, no_storage)

    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    explicit = _load_profile(explicit_dir, storage_mode="explicit_ebs")
    manifest = _write_workload(
        explicit_dir,
        storage_rows,
        storage_pair_id="main-ebs",
    )
    workload = portable.load_portable_workload(manifest, explicit)
    pair = explicit.storage_pairs[0]
    assert pair.pair_id == "main-ebs"
    assert explicit.storage_source_nodes == (pair.storage_out_start,)
    assert [(row["start"], row["goal"]) for row in workload.rows] == [
        (explicit.start_nodes[0], pair.storage_in_goal),
        (pair.storage_out_start, explicit.goal_nodes[0]),
    ]


def test_fault_schema_maps_only_registered_directed_edges(tmp_path: Path) -> None:
    profile = _load_profile(tmp_path)
    protocol = {
        "schema": portable.PORTABLE_FAULT_SCHEMA,
        "map_id": profile.map_id,
        "scenarios": [
            {
                "scenario_id": "merge-entry-outage",
                "windows": [
                    {
                        "start_external_id": "src-A",
                        "end_external_id": "merge-B",
                        "fault_time": 20.0,
                        "repair_time": 40.0,
                    }
                ],
            }
        ],
    }
    scenarios = portable.load_portable_fault_scenarios(
        _write_json(tmp_path / "faults.json", protocol), profile
    )
    mapping = {
        external: dense for dense, external in enumerate(profile.external_node_ids)
    }
    assert scenarios[0].fault_windows == (
        (mapping["src-A"], mapping["merge-B"], 20.0, 40.0, 0.0, False),
    )

    protocol["scenarios"][0]["windows"][0]["end_external_id"] = "sink-Z"
    with pytest.raises(portable.PortableInputError, match="not a directed map edge"):
        portable.load_portable_fault_scenarios(
            _write_json(tmp_path / "bad-faults.json", protocol), profile
        )


def test_legacy_map2_and_nanning_loading_remains_compatible() -> None:
    root = map_adapter.ROOT
    map2 = map_adapter.load_map_profile(root / "data/processed/maps/map2.json")
    nanning = map_adapter.load_map_profile(
        root / "data/processed/maps/nanning_airport_profile.json",
        storage_source_nodes=[53],
    )

    assert map2.explicit_roles is False
    assert map2.storage_source_nodes == (52,)
    assert nanning.explicit_roles is False
    assert nanning.storage_source_nodes == (53,)
