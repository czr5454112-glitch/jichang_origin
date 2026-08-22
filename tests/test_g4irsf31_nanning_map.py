from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
for bootstrap in (ROOT, ROOT / "src"):
    if str(bootstrap) not in sys.path:
        sys.path.insert(0, str(bootstrap))

from czr005.io.legacy_map import parse_legacy_map
from scripts.eval import run_g4irsf31_nanning_map as g31


def _node(
    workbook_key: str,
    row: int,
    alias: str,
    raw_id: str,
    node_type: int,
    service: float | None,
) -> g31.SourceNode:
    return g31.SourceNode(
        workbook_key=workbook_key,
        workbook_name=f"{workbook_key}.xlsx",
        row_number=row,
        alias=alias,
        raw_id=raw_id,
        system=workbook_key,
        node_type=node_type,
        source_service=service,
        empty_pallet_storage_id=None,
    )


def _edge(
    workbook_key: str,
    row: int,
    start: str,
    end: str,
) -> g31.SourceEdge:
    return g31.SourceEdge(
        workbook_key=workbook_key,
        workbook_name=f"{workbook_key}.xlsx",
        row_number=row,
        raw_start=start,
        raw_end=end,
        length_m=4.0,
        speed_mps=2.0,
        system=workbook_key,
        pallet_capacity=2,
    )


def _synthetic_sources() -> tuple[g31.SourceWorkbook, ...]:
    international = g31.SourceWorkbook(
        key="international",
        name="international.xlsx",
        nodes=(
            _node("international", 2, "INL1", "ICS1", 1, 0.0),
            _node("international", 3, "INU1", "ICS2", 2, 1.0),
            _node("international", 4, "EPS1", "ICS7", 7, None),
            _node("international", 5, "IUMES", "ICS9", 11, None),
        ),
        edges=(
            _edge("international", 2, "ICS1", "ICS2"),
            _edge("international", 3, "ICS2", "ICS7"),
            _edge("international", 4, "ICS7", "ICS9"),
            _edge("international", 5, "ICS9", "ICS3"),
        ),
        node_range="A1:G5",
        edge_range="A1:F5",
    )
    domestic = g31.SourceWorkbook(
        key="domestic",
        name="domestic.xlsx",
        nodes=(
            _node("domestic", 2, "GTC1", "ICS3", 1, 0.0),
            _node("domestic", 3, "DU1", "ICS4", 2, 3.0),
            _node("domestic", 4, "DD37", "ICS9", 4, 1.5),
        ),
        edges=(
            _edge("domestic", 2, "ICS3", "ICS4"),
            _edge("domestic", 3, "ICS4", "ICS9"),
            _edge("domestic", 4, "ICS9", "ICS1"),
        ),
        node_range="A1:G4",
        edge_range="A1:F4",
    )
    return international, domestic


def test_namespace_split_and_same_node_storage_proxy(tmp_path: Path) -> None:
    profile = g31.build_profile_from_sources(_synthetic_sources())

    assert profile["counts"] == {
        "source_node_rows": 7,
        "dense_node_count": 7,
        "directed_edge_count": 7,
        "cross_system_edge_count": 2,
        "external_reference_edge_count": 2,
        "weak_component_count": 1,
        "strong_component_count": 1,
        "max_outdegree": 1,
        "max_indegree": 1,
        "imputed_service_node_count": 2,
    }
    collision = profile["duplicate_raw_id_policy"]["collisions"]
    assert [row["key"] for row in collision[0]["rows"]] == [
        "international:ICS9",
        "domestic:ICS9",
    ]
    assert profile["source_resolution"]["ics156_split"]["merged"] is False

    nodes = profile["nodes"]
    intl_ics9 = next(
        node for node in nodes
        if node["system_key"] == "international" and node["external_id"] == "ICS9"
    )
    domestic_ics9 = next(
        node for node in nodes
        if node["system_key"] == "domestic" and node["external_id"] == "ICS9"
    )
    # An ID found in the current workbook wins over the duplicate in the other
    # workbook; only ICS3 and ICS1 are resolved externally in this fixture.
    assert intl_ics9["location"] in nodes[2]["outgoing"]
    assert domestic_ics9["location"] in nodes[5]["outgoing"]

    roles = profile["business_roles"]
    assert roles["standard_loader_nodes"] == [0]
    assert roles["transfer_loader_nodes"] == [4]
    assert roles["unloader_nodes"] == [1, 5]
    assert roles["storage_pairs"] == [
        {
            "storage_in_goal": 2,
            "storage_out_start": 2,
            "storage_external_id": "ICS7",
            "storage_alias": "EPS1",
            "system_key": "international",
            "role_status": "EMPTY_PALLET_STORAGE_EBS_PROXY_CANDIDATE",
        }
    ]
    assert roles["ebs"]["status"] == "NOT_IDENTIFIED_IN_SOURCE_WORKBOOKS"

    profile_path = tmp_path / "profile.json"
    legacy_path = tmp_path / "map.txt"
    g31.write_outputs(
        profile,
        profile_output=profile_path,
        legacy_map_output=legacy_path,
    )
    parsed = parse_legacy_map(legacy_path, edge_speed=2.5)
    assert parsed.header.node_count == 7
    assert len(parsed.edges) == 7
    # Every synthetic edge is 4 m.  Map.read performs the historical /2.5
    # conversion, so the file itself must retain raw shortest-distance metres.
    assert parsed.heuristic_raw[0][1] == pytest.approx(4.0)
    assert profile["assumptions"]["legacy_header"]["hcost_file_semantics"] == (
        "DIRECTED_SHORTEST_DISTANCE_METRES_BEFORE_JAVA_2P5_MPS_NORMALIZATION"
    )
    assert len(legacy_path.read_text(encoding="utf-8").splitlines()) == 22


def _real_sources_available(source_dir: Path) -> bool:
    return all((source_dir / filename).is_file() for _key, filename in g31.WORKBOOK_NAMES)


def test_real_nanning_workbooks_form_one_auditable_dense_graph(
    tmp_path: Path,
) -> None:
    source_dir = g31.default_source_dir()
    if not _real_sources_available(source_dir):
        pytest.skip("the user-supplied Nanning workbooks are not in this checkout")

    profile = g31.build_profile(source_dir)
    counts = profile["counts"]
    assert profile["schema"] == g31.SCHEMA
    assert profile["status"] == g31.STATUS
    assert profile["map_id"] == "nanning_topology_examples_1_2_namespaced_ics156"
    assert counts["source_node_rows"] == counts["dense_node_count"] == 151
    assert counts["directed_edge_count"] == 227
    assert counts["cross_system_edge_count"] == 5
    assert counts["external_reference_edge_count"] == 5
    assert counts["weak_component_count"] == 1
    assert counts["strong_component_count"] == 1
    assert counts["max_outdegree"] == 4
    assert counts["max_indegree"] == 5
    assert counts["imputed_service_node_count"] == 6
    assert profile["node_type_counts"] == {
        "1": 11,
        "2": 42,
        "4": 76,
        "5": 2,
        "7": 10,
        "10": 1,
        "11": 4,
        "12": 5,
    }
    assert profile["topology_contract"]["strongly_connected"] is True
    assert profile["topology_contract"][
        "pallet_capacity_equals_floor_distance_over_2m"
    ] is True
    assert profile["topology_contract"]["zero_capacity_edge_count"] == 1

    collision = profile["duplicate_raw_id_policy"]["collisions"]
    assert len(collision) == 1
    assert collision[0]["raw_id"] == "ICS156"
    assert [(row["key"], row["alias"]) for row in collision[0]["rows"]] == [
        ("international:ICS156", "IUMES"),
        ("domestic:ICS156", "DD37"),
    ]
    assert profile["source_resolution"]["ics156_split"] == {
        "international_key": "international:ICS156",
        "domestic_key": "domestic:ICS156",
        "merged": False,
    }

    roles = profile["business_roles"]
    assert len(roles["standard_loader_nodes"]) == 8
    assert len(roles["transfer_loader_nodes"]) == 3
    assert len(roles["unloader_nodes"]) == 42
    assert roles["storage_pair_status"] == (
        "EMPTY_PALLET_STORAGE_EBS_PROXY_CANDIDATE"
    )
    assert len(roles["storage_pairs"]) == 10
    assert {
        pair["storage_in_goal"] for pair in roles["storage_pairs"]
    } == set(roles["empty_pallet_storage_ids"])
    assert all(
        pair["storage_in_goal"] == pair["storage_out_start"]
        and pair["role_status"]
        == "EMPTY_PALLET_STORAGE_EBS_PROXY_CANDIDATE"
        for pair in roles["storage_pairs"]
    )
    assert roles["ebs"]["status"] == "NOT_IDENTIFIED_IN_SOURCE_WORKBOOKS"
    assert roles["ebs"]["proxy_candidate_pair_count"] == 10

    external = {
        (row["raw_start"], row["raw_end"])
        for row in profile["external_reference_edges"]
    }
    assert external == {
        ("ICS100", "ICS26"),
        ("ICS118", "ICS54"),
        ("ICS26", "ICS100"),
        ("ICS30", "ICS118"),
        ("ICS30", "ICS152"),
    }

    profile_path = tmp_path / "nanning.json"
    legacy_path = tmp_path / "nanning.txt"
    g31.write_outputs(
        profile,
        profile_output=profile_path,
        legacy_map_output=legacy_path,
    )
    parsed = parse_legacy_map(legacy_path, edge_speed=2.5)
    assert parsed.header.node_count == 151
    assert len(parsed.edges) == 227
    assert len(legacy_path.read_text(encoding="utf-8").splitlines()) == 530
    assert g31.DEFAULT_PROFILE_OUTPUT.name == "nanning_airport_profile.json"
    assert g31.DEFAULT_LEGACY_MAP_OUTPUT.name == "nanning_legacy.txt"
