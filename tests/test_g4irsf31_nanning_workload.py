from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for bootstrap in (ROOT, ROOT / "src"):
    if str(bootstrap) not in sys.path:
        sys.path.insert(0, str(bootstrap))

from czr005.io.legacy_tasks import RawLegacyTask
from scripts.eval import run_g4irsf31_nanning_workload as workload


def _profile() -> dict:
    nodes = [
        {
            "location": node,
            "alias": f"N{node}",
            "node_type": 1 if node in (0, 1, 2) else 2 if node in (3, 4) else 7,
            "service_time": 0.0,
        }
        for node in range(6)
    ]
    edges = [
        {"start": start, "end": end, "length": length, "speed": 2.5}
        for start, end, length in (
            (0, 3, 1.0),
            (0, 5, 2.0),
            (1, 4, 1.0),
            (1, 5, 10.0),
            (2, 3, 1.0),
            (2, 4, 1.0),
            (5, 3, 1.0),
            (5, 4, 1.0),
        )
    ]
    return {
        "schema": "fixture",
        "status": "COMPLETE",
        "map_id": "fixture",
        "nodes": nodes,
        "edges": edges,
        "business_roles": {
            "standard_loader_nodes": [0, 1],
            "transfer_loader_nodes": [2],
            "unloader_nodes": [3, 4],
            "storage_pairs": [
                {
                    "storage_in_goal": 5,
                    "storage_out_start": 0,
                    "storage_alias": "N5",
                    "loader_alias": "N0",
                },
                {
                    "storage_in_goal": 5,
                    "storage_out_start": 1,
                    "storage_alias": "N5",
                    "loader_alias": "N1",
                },
            ],
        },
    }


def _task(
    task_id: int,
    *,
    entry: float,
    std: float,
    start: int,
    end: int,
    unloader: str,
    loader: str,
) -> RawLegacyTask:
    return RawLegacyTask(
        task_id=task_id,
        entry_time=entry,
        std=std,
        start=start,
        end=end,
        unloader=unloader,
        loader=loader,
        source_line=task_id + 2,
    )


def test_projection_keeps_lanes_and_flights_atomic() -> None:
    rows = (
        _task(0, entry=10, std=100, start=10, end=20, unloader="U1", loader="A"),
        _task(1, entry=11, std=100, start=10, end=20, unloader="U1", loader="A"),
        _task(2, entry=12, std=100, start=11, end=20, unloader="U1", loader="B"),
        _task(3, entry=13, std=200, start=99, end=21, unloader="U2", loader="T"),
        _task(4, entry=14, std=200, start=99, end=21, unloader="U2", loader="T"),
    )
    projection = workload.build_original_projection(rows, _profile())
    mapped = projection["task_projection"]

    assert mapped[0][0] == mapped[1][0]
    assert mapped[3][0] == mapped[4][0] == 2
    assert mapped[0][1] == mapped[1][1] == mapped[2][1]
    assert mapped[3][1] == mapped[4][1]
    assert set(projection["standard_loader_load"]) == {0, 1}
    assert set(projection["unloader_load"]) == {3, 4}


def test_inserted_manifest_reuses_original_physical_od() -> None:
    original = (
        _task(7, entry=10, std=100, start=10, end=20, unloader="U1", loader="A"),
        _task(9, entry=20, std=200, start=11, end=21, unloader="U2", loader="T"),
    )
    projection = workload.build_original_projection(original, _profile())
    inserted = (
        original[0],
        original[1],
        _task(10, entry=60, std=150, start=10, end=20, unloader="U1", loader="A"),
        _task(11, entry=70, std=250, start=11, end=21, unloader="U2", loader="T"),
    )
    projected = workload._project_generated_tasks(
        original,
        inserted,
        projection,
        _profile(),
        inserted_id_offset=10,
    )

    assert (projected[0].start, projected[0].end) == (
        projected[2].start,
        projected[2].end,
    )
    assert (projected[1].start, projected[1].end) == (
        projected[3].start,
        projected[3].end,
    )


def test_storage_pair_is_selected_once_from_projected_1x() -> None:
    rows = (
        _task(0, entry=0, std=10_000, start=0, end=3, unloader="N3", loader="N0"),
        _task(1, entry=0, std=10_000, start=0, end=4, unloader="N4", loader="N0"),
    )
    selected = workload.select_storage_pair(rows, _profile(), speed_mps=2.5)

    assert selected["storage_in_goal"] == 5
    assert selected["storage_out_start"] == 0
    assert selected["mean_free_flow_seconds"] < 2.0
