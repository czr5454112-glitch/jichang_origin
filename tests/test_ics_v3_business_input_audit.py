"""Independent source/clock fixtures; deliberately do not import author tests."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
import gzip
from hashlib import sha256
import json

import pytest

from scripts.experiments.ics_circulation_v3.business_inputs import (
    BusinessInputError, ceil_tick, floor_tick, load_business_workload,
)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def json_write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def normalized_rows(files):
    return [json.loads(line) for line in gzip.decompress(files["normalized"].read_bytes()).splitlines()]


def bind(files):
    json_write(files["normalization_manifest"], {
        "outputs": {files["normalized"].name: digest(files["normalized"])},
        "input_sha256": {str(files[key].resolve()): digest(files[key]) for key in
                         ("raw", "canonical", "source_timetable", "source_manifest", "graph_profile")}})


def write_rows(files, rows):
    files["normalized"].write_bytes(gzip.compress(
        "\n".join(json.dumps(row) for row in rows).encode(), mtime=0))
    bind(files)


@pytest.fixture
def independent_input(tmp_path):
    files = {key: tmp_path / name for key, name in {
        "normalized": "tasks.gz", "normalization_manifest": "normalization.json",
        "raw": "projected.txt", "source_timetable": "parent.txt", "canonical": "segments.jsonl",
        "source_manifest": "manifest.json", "graph_profile": "graph.json"}.items()}
    # Non-contiguous IDs and non-ID source order expose accidental list-index identity.
    bags = [(42, "200.00000000000000000000000000001", "5000", "direct"),
            (7, "200", "5000", "early_storage"), (15, "6000.125", "6000.25", "direct")]
    header = "ID EntryTime(s) STD(s) star end Unloader Loader\n"
    files["raw"].write_text(header + "".join(
        f"{ident} {arrival} {std} 10 30 U L\n" for ident, arrival, std, _ in bags), encoding="utf-8")
    files["source_timetable"].write_text(header + "".join(
        f"{ident} {arrival} {std} 71 99 ParentU ParentL\n" for ident, arrival, std, _ in bags), encoding="utf-8")
    profile = {"nodes": [{"location": 10, "alias": "L"}, {"location": 30, "alias": "U"},
                         {"location": 40, "alias": "U2"}, {"location": 50, "alias": "E"}],
               "business_roles": {"source_candidate_ids": [10], "sink_candidate_ids": [30, 40]}, "edges": []}
    json_write(files["graph_profile"], profile)
    rows, segments = [], []
    for line, (ident, arrival, std, lifecycle) in enumerate(bags, 2):
        early = lifecycle == "early_storage"
        row = {"business_bag_id": f"projected:1x:{ident}", "source": {
            "raw_task_id": ident, "raw_sha256": digest(files["raw"]), "source_line": line,
            "parent_timetable_sha256": digest(files["source_timetable"]), "parent_task_id": ident,
            "parent_source_line": line, "flight_surrogate": [std, 99, "ParentU"],
            "synthetic_inserted": False, "time_shift_seconds": "0"},
            "arrival_seconds": arrival, "std_seconds": std, "origin": "10", "final_destination": "30",
            "lifecycle": lifecycle, "storage_node_proxy": "50" if early else None,
            "scheduled_release_seconds": "2300" if early else None,
            "old_segment_ids": [f"{ident}:storage_in", f"{ident}:storage_out"] if early else [f"{ident}:direct"],
            "physical_tray_id": None, "deadline_contract": None, "protected_contract": None,
            "storage_carrier_policy": None}
        rows.append(row)
        legs = [("storage_in", 10, 50, arrival), ("storage_out", 50, 30, "2300")] if early else [("direct", 10, 30, arrival)]
        for leg, start, goal, at in legs:
            segments.append({"task_id": ident, "segment_id": f"{ident}:{leg}", "leg": leg,
                "pallet_id": ident, "start": start, "goal": goal, "pass_time": at, "std": std,
                "original_start": 10, "original_goal": 30, "original_entry_time": arrival,
                "source_line": line, "early_bag_split": early})
    files["canonical"].write_text("\n".join(json.dumps(s) for s in segments), encoding="utf-8")
    json_write(files["source_manifest"], {"lifecycle": {"early_bag_threshold_seconds": 4800,
        "storage_out_lead_seconds": 2700, "storage_in_goal": 50, "storage_out_start": 50},
        "raw_task_count": 3, "expanded_segment_count": 4, "direct_raw_task_count": 2,
        "early_split_raw_task_count": 1, "raw_by_start": {"10": 3}, "raw_by_goal": {"30": 3}})
    files["contract"] = {"schema": "ics_business_inputs_v1", "scope": "input_only_fixed_storage_proxy",
        "contract_id": "independent-audit", "title": "Independent explicit proxy input",
        "evidence_status": "proxy_research", "graph_sha256": digest(files["graph_profile"]),
        "tick_seconds": "0.1", "deadline": {"policy": "std_minus_lead", "lead_seconds": "0.2"},
        "protection": {"policy": "explicit_ids", "business_ids": ["projected:1x:7"]},
        "initial_trays": [{"tray_id": "single-physical-tray", "node_id": "10", "available_seconds": "0.01"}],
        "initial_storage": [], "nodes": [{"node_id": str(n), "capacity": 1,
            "loaded_wait_allowed": True} for n in (10, 30, 40, 50)],
        "storage": {"node_id": "50", "capacity": 1, "carrier_policy": "on_carrier",
            "publication_policy": "irrevocable_at_bag_arrival", "release_policy": "normalized_scheduled_release",
            "uses_node_wait_capacity": True, "dedicated_retrieval": False},
        "evidence": [{"field": key, "source_ref": "independent hand fixture", "assumption_id": "audit-" + key}
                     for key in ("clock", "deadline", "protection", "initial_trays", "nodes", "storage")]}
    write_rows(files, rows)
    return files


def test_source_seconds_determine_early_threshold_before_clock_rounding(independent_input):
    result = load_business_workload(**independent_input)
    by_id = {task.source.raw_task_id: task for task in result.tasks}
    assert by_id[7].lifecycle == "early_storage"
    assert by_id[42].lifecycle == "direct"
    assert by_id[7].arrival == 2000 and by_id[42].arrival == 2001
    assert by_id[15].arrival == 60002 and by_id[15].deadline == 60000
    assert result.raw_business_count == 3 and result.old_segment_count == 4
    assert len(result.contract.initial_trays) == 1
    assert by_id[7].source.flight_surrogate == (Decimal("5000"), 99, "ParentU")
    assert by_id[7].protected and not by_id[42].protected
    assert result.independent_observed_operating_days == 0


def test_input_row_order_cannot_change_identity_or_semantics(independent_input):
    first = load_business_workload(**independent_input)
    rows = normalized_rows(independent_input)
    write_rows(independent_input, [rows[2], rows[0], rows[1]])
    second = load_business_workload(**independent_input)
    assert second.tasks == first.tasks
    assert {task.source.source_line for task in second.tasks} == {2, 3, 4}


@pytest.mark.parametrize("remove", [0, 1, 2])
def test_each_omitted_bag_is_rejected_even_after_hash_rebinding(independent_input, remove):
    rows = normalized_rows(independent_input)
    rows.pop(remove)
    write_rows(independent_input, rows)
    with pytest.raises(BusinessInputError, match="omits raw business"):
        load_business_workload(**independent_input)


def test_input_with_no_edges_retains_every_task_and_impossible_clock(independent_input):
    result = load_business_workload(**independent_input)
    assert len(result.tasks) == 3
    assert sum(task.arrival > task.deadline for task in result.tasks) == 1
    assert result.contract.runtime_adaptation_required
    assert result.information_scope == "private_environment_tape_reveal_only_on_observation"


def test_same_flight_cannot_be_split_between_destinations(independent_input):
    files = independent_input
    # Change raw, normalized, old segments and marginal manifest consistently.
    # An independent parent-flight invariant must still detect this split.
    raw = files["raw"].read_text().replace("7 200 5000 10 30 U L", "7 200 5000 10 40 U2 L")
    files["raw"].write_text(raw, encoding="utf-8")
    rows = normalized_rows(files)
    for row in rows:
        row["source"]["raw_sha256"] = digest(files["raw"])
        if row["source"]["raw_task_id"] == 7:
            row["final_destination"] = "40"
    segments = [json.loads(line) for line in files["canonical"].read_text().splitlines()]
    for row in segments:
        if row["task_id"] == 7:
            row["original_goal"] = 40
            if row["leg"] == "storage_out":
                row["goal"] = 40
    files["canonical"].write_text("\n".join(json.dumps(row) for row in segments), encoding="utf-8")
    manifest = json.loads(files["source_manifest"].read_text())
    manifest["raw_by_goal"] = {"30": 2, "40": 1}
    json_write(files["source_manifest"], manifest)
    write_rows(files, rows)
    with pytest.raises(BusinessInputError, match="flight group split"):
        load_business_workload(**files)


def test_clock_rational_reference_survives_hostile_decimal_precision():
    pairs = [("99999999999999999999999999.0000000001", "0.000001"),
             ("0.10000000000000000000000000000001", "0.1"),
             ("-0.10000000000000000000000000000001", "0.1"),
             ("0.000000000000000000000000000000001", "10")]
    for value, tick in pairs:
        exact = Fraction(value) / Fraction(tick)
        with localcontext() as context:
            context.prec = 2
            assert ceil_tick(value, tick) == -(-exact.numerator // exact.denominator)
            assert floor_tick(value, tick) == exact.numerator // exact.denominator


def test_extreme_deadline_subtraction_remains_conservative_under_context(independent_input):
    independent_input["contract"]["tick_seconds"] = "1"
    independent_input["contract"]["deadline"]["lead_seconds"] = "0.00000000000000000000000000000000001"
    with localcontext() as context:
        context.prec = 2
        result = load_business_workload(**independent_input)
    by_id = {task.source.raw_task_id: task for task in result.tasks}
    assert by_id[7].deadline == by_id[42].deadline == 4999
    assert by_id[15].deadline == 6000


@pytest.mark.parametrize("key", ["source_timetable", "canonical", "source_manifest", "graph_profile"])
def test_each_source_byte_change_is_rejected_before_semantics(independent_input, key):
    path = independent_input[key]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(BusinessInputError, match="source SHA mismatch"):
        load_business_workload(**independent_input)


def test_private_environment_output_has_no_runtime_import_side_effect(independent_input):
    # Exact source inspection is independent of a pre-imported pytest process.
    import ast
    import inspect
    from scripts.experiments.ics_circulation_v3 import business_inputs
    tree = ast.parse(inspect.getsource(business_inputs))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert all(name is None or not name.endswith(("runtime", "storage_routing")) for name in imports)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id in {"Simulation", "Tray", "StorageBag"} for node in ast.walk(tree))
