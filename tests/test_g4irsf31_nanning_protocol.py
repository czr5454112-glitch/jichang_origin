from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
for bootstrap in (ROOT, ROOT / "src"):
    if str(bootstrap) not in sys.path:
        sys.path.insert(0, str(bootstrap))

from scripts.eval import run_g4irsf31_nanning_protocol as protocol


EXPECTED_SCENARIOS = (
    "single_1",
    "single_2",
    "single_3",
    "single_4",
    "single_5",
    "single_6",
    "single_7",
    "single_8",
    "pair_1_7",
    "pair_2_4",
    "pair_3_5",
    "pair_4_5",
    "pair_5_7",
    "triple_2_4_6",
    "triple_3_5_8",
    "triple_4_6_7",
)


def test_nanning_fault_matrix_keeps_the_paper_shape_without_old_map_override() -> None:
    assert tuple(name for name, _lines in protocol.TABLE_5_5_SHAPE) == (
        EXPECTED_SCENARIOS
    )
    assert dict(protocol.TABLE_5_5_SHAPE)["pair_5_7"] == (5, 7)
    assert [protocol.LINE_EDGES[value] for value in (5, 7)] == [
        (112, 113),
        (34, 55),
    ]


def _inputs_available() -> bool:
    paths = [
        protocol.DEFAULT_PROFILE,
        *(
            protocol.DEFAULT_TASK_DIR / f"nanning_{scale}x_manifest.json"
            for scale in (1, 2)
        ),
        *(
            protocol.DEFAULT_TASK_DIR / f"nanning_{scale}x_raw.txt"
            for scale in (1, 2)
        ),
    ]
    return all(path.is_file() for path in paths)


def test_real_nanning_protocol_is_topology_and_business_pre_registered() -> None:
    if not _inputs_available():
        pytest.skip("generated Nanning map/workloads are not in this checkout")

    profile = json.loads(protocol.DEFAULT_PROFILE.read_text(encoding="utf-8"))
    result = protocol.build_protocol(
        profile,
        {
            scale: protocol._workload(scale, protocol.DEFAULT_TASK_DIR)
            for scale in (1, 2)
        },
    )

    assert result["status"] == "COMPLETE_PROTOCOL_ONLY_NO_ALGORITHM_RUN"
    assert result["selection_inputs"]["algorithm_outcomes_consulted"] is False
    assert result["storage_proxy"] == {
        "storage_in_goal": 53,
        "storage_out_start": 53,
        "alias": "IDK1",
        "source_role": "EMPTY_PALLET_STORAGE_EBS_PROXY_CANDIDATE",
        "real_ebs_claimed": False,
    }
    assert [tuple(row["edge"]) for row in result["lines"]] == list(
        protocol.LINE_EDGES.values()
    )

    nodes = {int(row["location"]): row for row in profile["nodes"]}
    for line in result["lines"]:
        start, end = line["edge"]
        assert nodes[start]["node_type"] not in {1, 2, 7}
        assert nodes[end]["node_type"] not in {1, 2, 7}
        assert line["pallet_capacity"] > 0
        assert line["nominal_1x_shortest_path_leg_exposure_count"] > 0

    expected_1x = (
        28_506,
        25_886,
        28_506,
        27_813,
        23_669,
        28_506,
        28_506,
        27_839,
        28_506,
        25_193,
        12_186,
        22_976,
        23_669,
        25_193,
        12_115,
        27_813,
    )
    rows_1x = result["scales"]["1x"]["scenarios"]
    rows_2x = result["scales"]["2x"]["scenarios"]
    assert tuple(row["scenario"] for row in rows_1x) == EXPECTED_SCENARIOS
    assert tuple(row["topology_upper_raw_bags"] for row in rows_1x) == expected_1x
    assert tuple(row["topology_upper_raw_bags"] for row in rows_2x) == tuple(
        2 * value for value in expected_1x
    )
    assert all(row["topology_upper_raw_bags"] > 0 for row in rows_1x)
