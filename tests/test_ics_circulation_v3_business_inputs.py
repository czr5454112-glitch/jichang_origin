from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal
import gzip
from hashlib import sha256
import json

import pytest

from scripts.experiments.ics_circulation_v3.business_inputs import (
    BusinessInputError, ceil_tick, floor_tick, load_business_workload,
    parse_operation_contract, seconds,
)


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def rebind(case):
    audit = {"outputs": {case["normalized"].name: digest(case["normalized"])},
        "input_sha256": {str(case[k].resolve()): digest(case[k]) for k in (
            "raw", "canonical", "source_timetable", "source_manifest", "graph_profile")}}
    write_json(case["normalization_manifest"], audit)


def change_normalized(case, update):
    rows = [json.loads(x) for x in gzip.decompress(case["normalized"].read_bytes()).splitlines()]
    update(rows)
    case["normalized"].write_bytes(gzip.compress("\n".join(json.dumps(x) for x in rows).encode(), mtime=0))
    rebind(case)


@pytest.fixture
def case(tmp_path):
    profile = {"nodes": [{"location": 0, "alias": "L"}, {"location": 1, "alias": "U"},
                          {"location": 2, "alias": "S"}],
        "business_roles": {"source_candidate_ids": [0], "sink_candidate_ids": [1]}, "edges": []}
    contract = {"schema": "ics_business_inputs_v1", "scope": "input_only_fixed_storage_proxy",
        "contract_id": "tiny-v1", "title": "Explicit test proxy", "evidence_status": "proxy_research",
        "graph_sha256": "", "tick_seconds": "10", "deadline": {"policy": "std_minus_lead", "lead_seconds": "0.2"},
        "protection": {"policy": "all", "business_ids": []}, "initial_storage": [],
        "initial_trays": [{"tray_id": "finite0", "node_id": "0", "available_seconds": "0.1"}],
        "nodes": [{"node_id": str(i), "capacity": 2, "loaded_wait_allowed": True} for i in range(3)],
        "storage": {"node_id": "2", "capacity": 2, "carrier_policy": "on_carrier",
            "publication_policy": "irrevocable_at_bag_arrival", "release_policy": "normalized_scheduled_release",
            "uses_node_wait_capacity": True, "dedicated_retrieval": False},
        "evidence": [{"field": x, "source_ref": "test fixture, not field operation", "assumption_id": "test-"+x}
                     for x in ("clock", "deadline", "protection", "initial_trays", "nodes", "storage")]}
    result = {key: tmp_path / filename for key, filename in {
        "normalized": "business_tasks_1x.jsonl.gz", "normalization_manifest": "audit.json",
        "raw": "raw.txt", "canonical": "canonical.jsonl", "source_timetable": "source.txt",
        "source_manifest": "source_manifest.json", "graph_profile": "profile.json"}.items()}
    write_json(result["graph_profile"], profile)
    contract["graph_sha256"] = digest(result["graph_profile"])
    header = "ID EntryTime(s) STD(s) star end Unloader Loader\n"
    raw = header + "0 0.1 5000 0 1 U L\n1 4000.01 5000 0 1 U L\n"
    result["raw"].write_text(raw, encoding="utf-8")
    result["source_timetable"].write_text(raw, encoding="utf-8")
    segments, normalized = [], []
    for ident, entry, early in ((0, 0.1, True), (1, 4000.01, False)):
        legs = {"storage_in": (0, 2, entry), "storage_out": (2, 1, 2300)} if early else {"direct": (0, 1, entry)}
        for leg, (start, goal, at) in legs.items():
            segments.append(dict(task_id=ident, segment_id=f"{ident}:{leg}", leg=leg,
                pallet_id=ident, start=start, goal=goal, pass_time=at, std=5000,
                original_start=0, original_goal=1, original_entry_time=entry,
                source_line=ident+2, early_bag_split=early))
        normalized.append(dict(business_bag_id=f"projected:1x:{ident}",
            source=dict(raw_sha256=digest(result["raw"]), raw_task_id=ident, source_line=ident+2,
                parent_timetable_sha256=digest(result["source_timetable"]), parent_task_id=ident,
                parent_source_line=ident+2, flight_surrogate=[5000, 1, "U"], synthetic_inserted=False, time_shift_seconds=0),
            arrival_seconds=entry, std_seconds=5000, origin="0", final_destination="1",
            lifecycle="early_storage" if early else "direct", storage_node_proxy="2" if early else None,
            scheduled_release_seconds=2300 if early else None,
            old_segment_ids=[f"{ident}:{leg}" for leg in legs], physical_tray_id=None,
            deadline_contract=None, protected_contract=None, storage_carrier_policy=None))
    result["canonical"].write_text("\n".join(json.dumps(x) for x in segments), encoding="utf-8")
    result["normalized"].write_bytes(gzip.compress("\n".join(json.dumps(x) for x in normalized).encode(), mtime=0))
    write_json(result["source_manifest"], {"lifecycle": {"early_bag_threshold_seconds": 4800,
        "storage_out_lead_seconds": 2700, "storage_in_goal": 2, "storage_out_start": 2},
        "raw_task_count": 2, "expanded_segment_count": 3, "direct_raw_task_count": 1,
        "early_split_raw_task_count": 1, "raw_by_start": {"0": 2}, "raw_by_goal": {"1": 2}})
    result["contract"] = contract
    rebind(result)
    return result


def test_full_business_identity_finite_inventory_and_conservative_clocks(case):
    result = load_business_workload(**case)
    assert result.raw_business_count == 2 and result.old_segment_count == 3
    assert len(result.contract.initial_trays) == 1
    early, direct = result.tasks
    assert early.arrival == 1 and direct.arrival == 401
    assert early.deadline == direct.deadline == 499
    assert early.release_at == 230 and early.published_at == early.arrival
    assert early.storage_node == "2" and direct.storage_node is None
    assert early.deadline_seconds == Decimal("4999.8")
    assert all(task.protected for task in result.tasks)
    assert result.contract.initial_trays[0].available_at == 1
    assert result.contract.runtime_adaptation_required
    assert result.information_scope.startswith("private_environment")
    # This fixture has no edges. Unreachable tasks must remain present.
    assert result.tasks[0].source_identity == (digest(case["raw"]), 0)


def test_immutable_nested_input_objects(case):
    result = load_business_workload(**case)
    with pytest.raises(FrozenInstanceError):
        result.tasks[0].deadline = 999
    with pytest.raises(FrozenInstanceError):
        result.tasks[0].source.raw_task_id = 99
    with pytest.raises(TypeError):
        result.contract.initial_trays[0] = None


@pytest.mark.parametrize("value,tick,ceil,floor", [
    ("10.00000000000000000001", "10", 2, 1), ("9.99999999999999999999", "10", 1, 0),
    ("-0.1", "10", 0, -1), ("1.25", ".25", 5, 5),
    ("10.000000000000000000000000000000000000001", "10", 2, 1)])
def test_decimal_clock_boundaries(value, tick, ceil, floor):
    assert ceil_tick(value, tick) == ceil
    assert floor_tick(value, tick) == floor


@pytest.mark.parametrize("value", [None, True, "NaN", "Infinity", "-Infinity", "bad"])
def test_nonfinite_clock_rejected(value):
    with pytest.raises(BusinessInputError):
        seconds(value)


@pytest.mark.parametrize("field", ["tick_seconds", "deadline", "protection", "initial_trays", "storage", "evidence"])
def test_unresolved_required_contract_fields_fail_closed(case, field):
    case["contract"][field] = None
    with pytest.raises(BusinessInputError):
        load_business_workload(**case)


@pytest.mark.parametrize("field,value", [
    ("carrier_policy", "off_carrier"), ("publication_policy", "future_dynamic"),
    ("uses_node_wait_capacity", False), ("dedicated_retrieval", True), ("capacity", 99), ("capacity", True)])
def test_unsupported_storage_contract_rejected(case, field, value):
    case["contract"]["storage"][field] = value
    with pytest.raises(BusinessInputError):
        load_business_workload(**case)


def test_no_silent_confirmed_label_or_protection_elimination(case):
    case["contract"]["evidence_status"] = "confirmed"
    with pytest.raises(BusinessInputError, match="cannot certify"):
        load_business_workload(**case)
    case["contract"]["evidence_status"] = "proxy_research"
    case["contract"]["protection"] = {"policy": "explicit_ids", "business_ids": []}
    with pytest.raises(BusinessInputError, match="empty protection"):
        load_business_workload(**case)


def test_explicit_protection_and_impossible_deadline_kept(case):
    case["contract"]["protection"] = {"policy": "explicit_ids", "business_ids": ["projected:1x:1"]}
    case["contract"]["deadline"]["lead_seconds"] = "6000"
    result = load_business_workload(**case)
    assert [t.protected for t in result.tasks] == [False, True]
    assert all(t.deadline == -100 for t in result.tasks)
    assert len(result.tasks) == 2


def test_unknown_protected_identity_rejected(case):
    case["contract"]["protection"] = {"policy": "explicit_ids", "business_ids": ["missing"]}
    with pytest.raises(BusinessInputError, match="protected IDs absent"):
        load_business_workload(**case)


def test_duplicate_inventory_capacity_and_wait_permission_rejected(case):
    old = deepcopy(case["contract"])
    case["contract"]["initial_trays"] *= 2
    with pytest.raises(BusinessInputError, match="duplicate initial tray"):
        load_business_workload(**case)
    case["contract"] = deepcopy(old)
    case["contract"]["nodes"][0]["capacity"] = 0
    with pytest.raises(BusinessInputError, match="exceeds node"):
        load_business_workload(**case)
    case["contract"] = deepcopy(old)
    case["contract"]["nodes"][2]["loaded_wait_allowed"] = False
    with pytest.raises(BusinessInputError, match="waiting permission"):
        load_business_workload(**case)


def test_raw_mutation_is_detected_before_semantic_reads(case):
    case["raw"].write_text(case["raw"].read_text() + "\n", encoding="utf-8")
    with pytest.raises(BusinessInputError, match="raw: source SHA mismatch"):
        load_business_workload(**case)


def test_normalized_byte_binding_checked(case):
    case["normalized"].write_bytes(case["normalized"].read_bytes() + b"x")
    with pytest.raises(BusinessInputError, match="normalized SHA mismatch"):
        load_business_workload(**case)


@pytest.mark.parametrize("alter,error", [
    (lambda rows: rows.pop(), "omits raw business"),
    (lambda rows: rows.append(deepcopy(rows[0])), "duplicate normalized raw"),
    (lambda rows: rows[0].update(physical_tray_id="fake-tray"), "physical_tray_id"),
    (lambda rows: rows[0].update(arrival_seconds=0), "source seconds mismatch"),
    (lambda rows: rows[0]["source"].update(parent_task_id=1), "source line mismatch"),
    (lambda rows: rows[0]["source"].update(flight_surrogate=[6000, 1, "U"]), "flight surrogate mismatch"),
    (lambda rows: rows[0].update(old_segment_ids=["0:storage_in"]), "old segment identity"),
    (lambda rows: rows[0].update(lifecycle="direct"), "lifecycle mismatch"),
    (lambda rows: rows[0].update(scheduled_release_seconds=2200), "release mismatch"),
    (lambda rows: rows[0].update(business_bag_id="another-bag"), "source namespace"),
])
def test_semantic_tampering_caught_even_after_artifact_rebinding(case, alter, error):
    change_normalized(case, alter)
    with pytest.raises(BusinessInputError, match=error):
        load_business_workload(**case)


def test_canonical_missing_storage_out_does_not_become_one_completed_bag(case):
    lines = case["canonical"].read_text().splitlines()
    case["canonical"].write_text("\n".join([lines[0], lines[2]]), encoding="utf-8")
    rebind(case)
    with pytest.raises(BusinessInputError, match="exact complete old segment set"):
        load_business_workload(**case)


def test_duplicate_or_unproven_evidence_rejected(case):
    case["contract"]["evidence"][0]["assumption_id"] = None
    with pytest.raises(BusinessInputError, match="assumption_id"):
        load_business_workload(**case)


def test_forecast_or_runtime_fields_cannot_be_silently_ignored(case):
    case["contract"]["future_forecast_visible"] = True
    with pytest.raises(BusinessInputError, match="unsupported fields"):
        load_business_workload(**case)


def make_densified_case(case):
    original_rows = [json.loads(x) for x in gzip.decompress(case["normalized"].read_bytes()).splitlines()]
    all_rows = deepcopy(original_rows)
    original_segments = [json.loads(x) for x in case["canonical"].read_text().splitlines()]
    all_segments = deepcopy(original_segments)
    case["raw"].write_text(case["raw"].read_text() +
                          "2 100.1 5100 0 1 U L\n3 4100.01 5100 0 1 U L\n", encoding="utf-8")
    for original in original_rows:
        row = deepcopy(original)
        ident = row["source"]["raw_task_id"] + 2
        row["source"].update(raw_task_id=ident, source_line=ident+2, synthetic_inserted=True, time_shift_seconds=100)
        row["arrival_seconds"] += 100
        row["std_seconds"] += 100
        if row["scheduled_release_seconds"] is not None:
            row["scheduled_release_seconds"] += 100
        row["old_segment_ids"] = [f"{ident}:" + s.split(":")[1] for s in row["old_segment_ids"]]
        all_rows.append(row)
    for row in all_rows:
        row["business_bag_id"] = f'projected:2x:{row["source"]["raw_task_id"]}'
        row["source"]["raw_sha256"] = digest(case["raw"])
    for original in original_segments:
        row = deepcopy(original)
        ident = row["task_id"] + 2
        row.update(task_id=ident, pallet_id=ident, segment_id=f'{ident}:{row["leg"]}', source_line=ident+2)
        for field in ("original_entry_time", "pass_time", "std"):
            row[field] += 100
        all_segments.append(row)
    case["canonical"].write_text("\n".join(json.dumps(x) for x in all_segments), encoding="utf-8")
    case["normalized"].write_bytes(gzip.compress("\n".join(json.dumps(x) for x in all_rows).encode(), mtime=0))
    manifest = json.loads(case["source_manifest"].read_text())
    manifest.update(raw_task_count=4, expanded_segment_count=6, direct_raw_task_count=2,
                    early_split_raw_task_count=2, raw_by_start={"0": 4}, raw_by_goal={"1": 4})
    write_json(case["source_manifest"], manifest)
    rebind(case)


def test_complete_densified_manifest_preserves_parent_bags_and_one_source_day(case):
    make_densified_case(case)
    result = load_business_workload(**case)
    assert result.raw_business_count == 4 and result.old_segment_count == 6
    assert result.original_count == result.derived_count == 2
    assert result.source_timetable_count == 1
    assert result.independent_observed_operating_days == 0
    derived = [t for t in result.tasks if t.source.synthetic_inserted]
    assert {t.source.parent_task_id for t in derived} == {0, 1}
    assert {t.source.time_shift_seconds for t in derived} == {Decimal(100)}
    assert len(result.contract.initial_trays) == 1


def test_densified_parent_identity_cannot_be_swapped(case):
    make_densified_case(case)
    def swap(rows):
        rows[2]["source"].update(parent_task_id=1, parent_source_line=3)
    change_normalized(case, swap)
    with pytest.raises(BusinessInputError, match="source parent rank"):
        load_business_workload(**case)


def test_exact_deadline_subtraction_does_not_relax_fraction_beyond_decimal_context(case):
    case["contract"]["deadline"]["lead_seconds"] = "0.000000000000000000000000000000000000001"
    result = load_business_workload(**case)
    assert all(t.deadline == 499 for t in result.tasks)


def test_explicit_zero_inventory_and_closed_storage_are_kept_not_defaulted(case):
    case["contract"]["initial_trays"] = []
    case["contract"]["storage"]["capacity"] = 0
    case["contract"]["nodes"][2]["capacity"] = 0
    result = load_business_workload(**case)
    assert len(result.tasks) == 2 and result.contract.initial_trays == ()
    assert result.contract.storage.capacity == 0
