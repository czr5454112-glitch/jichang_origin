from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_PATH,
    CANONICAL_MAP_SHA256,
    normalised_text_sha256,
)
from scripts.eval.g4irsf12_resource_semantics import (
    BUFFER_BOUNDARY_REPORT,
    DIRECTED_CORRIDOR_TABLE,
    MERGE_INVENTORY_TABLE,
    RESOURCE_AB_TABLE,
    RESOURCE_AUDIT_REPORT,
    build_source_evidence,
    build_static_audit,
    build_topology_audit,
    resource_mode_configs,
    write_resource_semantics_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixed_map_topology_audit_is_complete_and_directional() -> None:
    audit = build_topology_audit()
    summary = audit["summary"]

    assert summary["node_count"] == 54
    assert summary["directed_edge_count"] == 69
    assert len(audit["directed_corridors"]) == 69
    assert len(audit["nodes"]) == 54
    assert len({row["directed_edge"] for row in audit["directed_corridors"]}) == 69
    assert summary["directed_scc_count"] == len(audit["sccs"])
    assert summary["weak_projection_bridge_count"] == len(
        audit["weak_projection_bridges"]
    )

    # map2 has no pair where both u->v and v->u exist.  The min/max corridor
    # key is still a semantic smell, but it aliases zero actual edge calendars
    # on this protected topology; the audit must retain that negative result.
    assert summary["reverse_pair_count"] == 0
    assert summary["direction_aliasing_present_on_fixed_map"] is False
    assert audit["reverse_pairs"] == []
    assert all(
        row["current_cross_direction_calendar_share"] is False
        for row in audit["directed_corridors"]
    )


def test_reviewed_legacy_path_uses_directed_edges_and_node_windows() -> None:
    evidence = build_source_evidence(ROOT)
    conclusions = evidence["conclusions"]

    assert conclusions["legacy_reviewed_graph_is_directed"] is True
    assert conclusions["legacy_reviewed_conflict_resource"] == (
        "node_arrival_departure_windows"
    )
    assert conclusions["legacy_reviewed_edge_capacity_one_implemented"] is False
    assert conclusions["legacy_reviewed_full_travel_edge_exclusivity_implemented"] is False
    assert conclusions["legacy_reviewed_reverse_pair_calendar_merge_implemented"] is False
    assert conclusions["legacy_goal_node_window_exemption_observed"] is True
    assert conclusions["authoritative_edge_entry_headway_seconds"] is None
    assert all(row["line"] > 0 for row in evidence["anchors"].values())


def test_unknown_headway_modes_fail_closed() -> None:
    modes = {mode["short_id"]: mode for mode in resource_mode_configs()}

    assert set(modes) == {"R0", "R1", "R2", "R3", "R4"}
    assert modes["R0"]["execution_readiness"] == "READY_AS_NEGATIVE_CONTROL"
    for mode_id in ("R2", "R4"):
        assert modes[mode_id]["entry_headway_seconds"] is None
        assert modes[mode_id]["execution_readiness"] == (
            "REQUIRES_EXPLICIT_SENSITIVITY_HEADWAY_BEFORE_EXECUTION"
        )
        assert modes[mode_id]["promotion_eligible"] is False
    assert all(mode["reservation_depth"] == 1 for mode in modes.values())
    assert all(mode["runtime_full_astar_allowed"] is False for mode in modes.values())


def test_writer_publishes_static_bundle_without_touching_protected_inputs(
    tmp_path: Path,
) -> None:
    protected = [
        CANONICAL_MAP_PATH,
        ROOT / "legacy/jichang_origin_readonly/src/App/Astar.java",
        ROOT / "legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java",
        ROOT / "data/processed/tasks/inputdata.jsonl",
    ]
    before = {path: _sha256(path) for path in protected}

    audit = build_static_audit(ROOT)
    manifest = write_resource_semantics_artifacts(audit, tmp_path)

    assert normalised_text_sha256(CANONICAL_MAP_PATH) == CANONICAL_MAP_SHA256
    assert {path: _sha256(path) for path in protected} == before
    for relative in (
        DIRECTED_CORRIDOR_TABLE,
        MERGE_INVENTORY_TABLE,
        RESOURCE_AB_TABLE,
        RESOURCE_AUDIT_REPORT,
        BUFFER_BOUNDARY_REPORT,
    ):
        assert (tmp_path / relative).is_file()

    with (tmp_path / DIRECTED_CORRIDOR_TABLE).open(encoding="utf-8", newline="") as handle:
        directed_rows = list(csv.DictReader(handle))
    with (tmp_path / RESOURCE_AB_TABLE).open(encoding="utf-8", newline="") as handle:
        ab_rows = list(csv.DictReader(handle))
    published_manifest = json.loads(
        (tmp_path / manifest["manifest_path"]).read_text(encoding="utf-8")
    )

    assert len(directed_rows) == 69
    assert len(ab_rows) == 5
    assert {row["execution_status"] for row in ab_rows} == {
        "NOT_EXECUTED_STATIC_CONFIGURATION_ONLY"
    }
    assert published_manifest["runtime_ab_executed"] is False
    assert published_manifest["protected_inputs_modified"] is False
    assert len(published_manifest["configs"]) == 5

    report = (tmp_path / RESOURCE_AUDIT_REPORT).read_text(encoding="utf-8")
    assert "contains no reverse edge pair" in report
    assert "No static result authorizes 43,603-segment full execution" in report
