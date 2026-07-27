from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlparse

import pytest

from scripts.eval import g4irsf13_thesis_priority_extraction as extraction


@pytest.fixture(scope="module")
def real_graph() -> dict:
    return extraction._load_graph(extraction.ROOT)


@pytest.fixture(scope="module")
def real_tasks() -> list[dict]:
    return extraction._load_tasks(extraction.ROOT)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_equations_4_2_to_4_5_weight_relation_and_fifo_are_exact() -> None:
    assert extraction.validate_formula_rows() == []
    by_id = {
        row["record_id"]: row["exact_expression"]
        for row in extraction.FORMULA_ROWS
    }
    assert by_id["equation_4_2"] == (
        "r_k = p1*T_disrupt_k*I_disrupt_k + "
        "p2*T_conflict_k*I_conflict_k + "
        "p3*T_departure_k + p4*T_wait_k"
    )
    assert by_id["equation_4_3"] == "T_conflict_k = t_conflict_k - t"
    assert by_id["equation_4_4"] == "T_departure_k = tau_k - t"
    assert by_id["equation_4_5"] == "T_wait_k = t - t_k"
    assert by_id["weight_relation"] == "p1 > p3 > p2 > p4"
    assert by_id["stated_order_and_tie"] == (
        "fault-affected > nearer departure > conflict > new; "
        "first-in-first-out tie"
    )


def test_legacy_java_comparator_is_coarse_and_stable_not_thesis_formula() -> None:
    assert extraction.legacy_pass_time_compare(12.0, 10.0) == 2
    assert extraction.legacy_pass_time_compare(10.1, 10.9) == 0
    assert extraction.legacy_pass_time_compare(10.9, 10.1) == 0
    assert extraction.legacy_stable_pass_time_order(
        (("later_but_first", 10.9), ("earlier_but_tied", 10.1))
    ) == ("later_but_first", "earlier_but_tied")


def test_all_graph_motifs_come_from_protected_real_map2(
    real_graph: dict,
) -> None:
    motifs = extraction.real_map_motifs(real_graph)
    assert len(real_graph["nodes"]) == 54
    assert len(motifs["edges"]) == 69

    # Real edge, real merge, real split, real weak-projection bridge, and EBS.
    assert (0, 6) in motifs["edges"]
    assert 8 in motifs["merge_nodes"]
    assert 6 in motifs["split_nodes"]
    assert (0, 6) in motifs["weak_projection_bridges"]
    assert len(motifs["weak_projection_bridges"]) == 11
    assert motifs["ebs_nodes"] == (52,)
    assert set(motifs["goal_nodes"]) == {47, 48, 49, 50, 51}


def test_arc_1_to_8_mapping_is_exact_on_real_map2(real_graph: dict) -> None:
    edges = {
        (int(row["start"]), int(row["end"])): float(row["length"])
        for row in real_graph["edges"]
    }
    assert extraction.ARC_1_TO_8 == (
        (1, 0, 6, 8.0),
        (2, 1, 7, 12.0),
        (3, 2, 9, 9.0),
        (4, 3, 16, 4.0),
        (5, 4, 17, 9.0),
        (6, 5, 19, 4.0),
        (7, 6, 8, 7.0),
        (8, 6, 12, 25.0),
    )
    for _arc_id, start, end, length in extraction.ARC_1_TO_8:
        assert edges[(start, end)] == length


def test_table_5_5_has_all_sixteen_exact_paper_rows() -> None:
    assert len(extraction.THESIS_FAULT_SCENARIOS) == 16
    by_arcs = {
        arcs: (affected, success)
        for _name, arcs, affected, success
        in extraction.THESIS_FAULT_SCENARIOS
    }
    assert by_arcs[(1,)] == (1, 1.00)
    assert by_arcs[(2,)] == (7, 0.88)
    assert by_arcs[(5,)] == (24, 0.97)
    assert by_arcs[(4, 5)] == (54, 0.00)
    assert by_arcs[(3, 5, 8)] == (51, 0.05)
    assert by_arcs[(4, 6, 7)] == (30, 0.26)


def test_ebs_source52_and_raw_bag_completion_use_real_inputs(
    real_graph: dict,
    real_tasks: list[dict],
) -> None:
    rows = extraction.build_ebs_audit_rows(real_graph, real_tasks)
    assert all(row["status"] == "PASS" for row in rows)
    by_id = {row["check_id"]: row for row in rows}
    assert by_id["protected_task_identity"]["observed"] == (
        "segments=43603;raw_bags=28506"
    )
    assert by_id["storage_split_cardinality"]["observed"] == (
        "direct=13409;storage_in=15097;storage_out=15097"
    )
    assert by_id["storage_in_goal_47"]["observed"] == (
        "all_goal47=True;node_type=2;outdegree=0"
    )
    assert by_id["storage_out_source_52"]["observed"] == (
        "all_start52=True;node_type=1;indegree=0;outdegree=2"
    )
    assert by_id["storage_out_release_std_minus_2700"]["observed"] == (
        "rows=15097;all_exact=True"
    )
    assert "storage-in completion alone is partial" in by_id[
        "raw_bag_completion_contract"
    ]["control_contract"]


def test_localized_priority_variants_are_deterministic_on_real_merge_context(
    real_graph: dict,
) -> None:
    # The context node is the real merge 8; no synthetic graph is constructed.
    assert 8 in extraction.real_map_motifs(real_graph)["merge_nodes"]
    fault = extraction.localized_priority_key(
        "Q1",
        fault_affected=True,
        deadline_slack_seconds=120.0,
        age_seconds=2.0,
        current_contention=True,
        entry_sequence=2,
        stable_id=20,
    )
    ordinary = extraction.localized_priority_key(
        "Q1",
        fault_affected=False,
        deadline_slack_seconds=10.0,
        age_seconds=100.0,
        current_contention=True,
        entry_sequence=1,
        stable_id=10,
    )
    assert fault < ordinary

    older = extraction.localized_priority_key(
        "Q3",
        fault_affected=False,
        deadline_slack_seconds=60.0,
        age_seconds=100.0,
        current_contention=False,
        entry_sequence=0,
        stable_id=8,
        fault_generation=0,
    )
    newer = extraction.localized_priority_key(
        "Q3",
        fault_affected=False,
        deadline_slack_seconds=60.0,
        age_seconds=10.0,
        current_contention=False,
        entry_sequence=0,
        stable_id=7,
        fault_generation=0,
    )
    assert older < newer
    with pytest.raises(ValueError, match="unsupported"):
        extraction.localized_priority_key(
            "Q0",
            fault_affected=False,
            deadline_slack_seconds=1.0,
            age_seconds=1.0,
            current_contention=False,
            entry_sequence=0,
            stable_id=0,
        )


def test_literature_matrix_uses_primary_sources_and_fail_closed_boundaries() -> None:
    assert extraction.validate_literature_rows() == []
    assert len(extraction.LITERATURE_ROWS) == 11
    by_id = {
        row["literature_id"]: row for row in extraction.LITERATURE_ROWS
    }
    assert by_id["PIBT_PREFERENCE_SOCS_2025"]["identifier"] == (
        "10.1609/socs.v18i1.35982"
    )
    assert by_id["ONLINE_GGO_AAAI_2025"]["identifier"] == (
        "10.1609/aaai.v39i14.33614"
    )
    assert by_id["WINC_MAPF_AAAI_2025"]["identifier"] == (
        "10.1609/aaai.v39i22.34499"
    )
    assert by_id["MAP_EXECUTION_UNCERTAINTY_SOCS_2024"]["identifier"] == (
        "10.1609/socs.v17i1.31543"
    )
    assert by_id["REALTIME_SIPP_SOCS_2024"]["identifier"] == (
        "10.1609/socs.v17i1.31554"
    )
    for row in extraction.LITERATURE_ROWS:
        source = row["primary_source"]
        if source.startswith("https://"):
            parsed = urlparse(source)
            assert parsed.scheme == "https"
            assert parsed.hostname in extraction.ALLOWED_PRIMARY_HOSTS


def test_rendered_outputs_are_deterministic_complete_and_current() -> None:
    outputs = extraction.render_outputs(extraction.ROOT)
    assert set(outputs) == {
        extraction.THESIS_REPORT_PATH,
        extraction.FORMULA_TABLE_PATH,
        extraction.LOCAL_DESIGN_REPORT_PATH,
        extraction.EBS_AUDIT_TABLE_PATH,
        extraction.LITERATURE_REPORT_PATH,
    }
    assert extraction.check_outputs(extraction.ROOT, outputs) == []

    formula_rows = _read_csv(extraction.ROOT / extraction.FORMULA_TABLE_PATH)
    assert len(formula_rows) == 6
    assert tuple(formula_rows[0]) == extraction.FORMULA_FIELDS

    ebs_rows = _read_csv(extraction.ROOT / extraction.EBS_AUDIT_TABLE_PATH)
    assert len(ebs_rows) == 10
    assert all(row["status"] == "PASS" for row in ebs_rows)

    thesis = (
        extraction.ROOT / extraction.THESIS_REPORT_PATH
    ).read_text(encoding="utf-8")
    assert "SOURCE_EXTRACTION_COMPLETE" in thesis
    assert "p1 > p3 > p2 > p4" in thesis
    assert "Table 5.5 (paper-reported only)" in thesis
    assert "not G4IRSF13 runtime results" in thesis

    design = (
        extraction.ROOT / extraction.LOCAL_DESIGN_REPORT_PATH
    ).read_text(encoding="utf-8")
    assert "legacy_order_one_step_diagnostic" in design
    assert "`reservation_depth = 1`" in design
    assert "`runtime_full_astar_calls = 0`" in design
    assert "`future_routes_stored = 0`" in design
    assert "`global_reservation_scans = 0`" in design
    assert "Storage-in completion is not raw-bag completion" in design

    literature = (
        extraction.ROOT / extraction.LITERATURE_REPORT_PATH
    ).read_text(encoding="utf-8")
    assert "coverage: `11/11 COMPLETE`" in literature
    assert literature.count("### ") == 11
    assert "PIBT-inspired bounded local coordination" in literature
    assert "Do not run runtime CBS" in literature


def test_external_source_provenance_is_hash_bound() -> None:
    assert extraction.THESIS_SHA256 == (
        "37e61b8e4d67e56c0fa14c43b230be965e200106704363f06b80a4e6a151e1aa"
    )
    assert extraction.LEGACY_SOURCE_SHA256["src/RUN/Main.java"] == (
        "af7ba8f8224a480f61e4d4b010d0c6fcf5e8798cccfdf6f298d786ac053bf5af"
    )
    assert extraction.LEGACY_SOURCE_SHA256["arc.txt"] == (
        "1348553fc9a7f0bb6aaa3f823a151502b7fc6beac55c3f6eeb92a59a3758811c"
    )
