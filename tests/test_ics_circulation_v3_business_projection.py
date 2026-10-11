from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from hashlib import sha256
import json

import pytest

from test_ics_circulation_v3_business_inputs import case, rebind, make_densified_case
from scripts.experiments.ics_circulation_v3.business_inputs import (
    BusinessInputError, business_workload_sha256, load_business_workload)
from scripts.experiments.ics_circulation_v3.business_projection import (
    BusinessProjectionError, POLICIES, project_business_destinations,
    projection_sha256, validate_business_projection)


def seal(workload):
    return replace(workload, content_sha256=business_workload_sha256(workload))


def declaration(workload):
    return dict(POLICIES, projection_id="test-static-proxy-v1", title="Static necessary proxy",
        source_workload_sha256=workload.content_sha256, graph_sha256=workload.contract.graph_sha256,
        salt="fixed-before-any-results", unload_seconds="0", assumption_id="test-declaration",
        source_ref="constructed test graph")


@pytest.fixture
def projection_case(case):
    profile = json.loads(case["graph_profile"].read_text())
    profile["nodes"] += [{"location": i, "alias": f"n{i}"} for i in range(3, 8)]
    profile["business_roles"] = {"source_candidate_ids": [0, 4], "sink_candidate_ids": [1, 3, 5, 6]}
    profile["edges"] = [dict(start=a, end=b, length=length, speed="1", capacity=capacity)
        for a, b, length, capacity in ((0, 2, "0.6", 1), (2, 3, "0.6", 1),
        (3, 4, "0.6", 1), (0, 5, "0.2", 1), (2, 5, "2.1", 1), (5, 4, "0.5", 1),
        (0, 1, "0.5", 1), (1, 4, "0.5", 1), (2, 1, "0.1", 0),
        (2, 6, "0.1", 1), (2, 7, "0.1", 1), (7, 4, "0.1", 1))]
    case["graph_profile"].write_text(json.dumps(profile), encoding="utf-8")
    contract = case["contract"]
    contract["graph_sha256"] = sha256(case["graph_profile"].read_bytes()).hexdigest()
    contract["tick_seconds"] = "1"
    contract["nodes"] += [{"node_id": str(i), "capacity": 2, "loaded_wait_allowed": True} for i in range(3, 8)]
    rebind(case)
    workload = load_business_workload(**case)
    return case, workload, declaration(workload)


def test_whole_flight_early_direct_and_return_roles(projection_case):
    case, original, contract = projection_case
    projected = project_business_destinations(original, case["graph_profile"], contract)
    assert len(projected.records) == projected.source_business_count == 2
    assert projected.source_segment_count == 3
    group, = projected.groups
    assert group.structural_domain == group.necessary_domain == ("3", "5")
    assert {r.projected_destination for r in projected.records} == {group.projected_destination}
    assert tuple(r.original for r in projected.records) == original.tasks
    assert all(r.original_destination == "1" for r in projected.records)
    # 1 is direct-reachable but not early-reachable; the whole group excludes it.
    rejected = {c.final_destination: c for c in group.candidates}
    assert "early_storage_to_final_unreachable" in rejected["1"].rejection_reasons
    assert "no_empty_return_to_any_legal_loader" in rejected["6"].rejection_reasons
    assert rejected["3"].return_loader_ids == ("4",)  # Not original source 0.
    assert "7" not in {c.final_destination for c in group.candidates}  # Transit is not a legal final.
    assert projected.source_operation_contract.initial_trays == original.contract.initial_trays
    assert len(projected.source_operation_contract.initial_trays) == 1
    validate_business_projection(projected, original, case["graph_profile"])


def test_legal_original_is_retained_for_every_salt(projection_case):
    case, original, _ = projection_case
    original = seal(replace(original, tasks=tuple(replace(t, final_destination="5") for t in original.tasks)))
    for salt in ("first", "second"):
        contract = dict(declaration(original), salt=salt)
        projected = project_business_destinations(original, case["graph_profile"], contract)
        assert all(r.projected_destination == "5" for r in projected.records)
        assert projected.groups[0].decision == "retained_legal_original"
        assert projected.groups[0].selection_sha256 is None


def test_derived_copies_share_parent_flight_decision_without_new_observed_day(projection_case):
    case, original, contract = projection_case
    first = project_business_destinations(original, case["graph_profile"], contract)
    make_densified_case(case)
    dense = load_business_workload(**case)
    second = project_business_destinations(dense, case["graph_profile"], declaration(dense))
    assert second.source_business_count == 4
    assert second.original_count == second.derived_count == 2
    assert len(second.groups) == 1 and second.groups[0].flight_instance_count == 2
    assert second.groups[0].group_id == first.groups[0].group_id
    assert second.groups[0].projected_destination == first.groups[0].projected_destination
    assert second.independent_observed_operating_days == 0 and second.source_timetable_count == 1
    assert tuple(r.original for r in second.records) == dense.tasks


def test_independent_order_and_declared_hash_ranking(projection_case):
    case, original, contract = projection_case
    projected = project_business_destinations(original, case["graph_profile"], contract)
    group = projected.groups[0]
    def independent_rank(node):
        encoded = json.dumps([POLICIES["schema"], contract["salt"], list(group.parent_flight_key), node],
                             sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        return sha256(encoded).hexdigest(), node
    assert (group.selection_sha256, group.projected_destination) == min(map(independent_rank, ("3", "5")))
    reordered = seal(replace(original, tasks=original.tasks[::-1]))
    again = project_business_destinations(reordered, case["graph_profile"], declaration(reordered))
    assert again.groups == projected.groups
    assert again.records == projected.records[::-1]


def test_per_edge_ceil_deadline_is_not_ceil_total(projection_case):
    case, original, _ = projection_case
    # With two edges of 0.6s, exact loaded travel is 1.2s but actual tick travel is 2.
    direct = replace(original.tasks[1], arrival_seconds=Decimal(0), arrival=0,
                     deadline_seconds=Decimal("1.9"), deadline=1)
    original = seal(replace(original, tasks=(direct,), raw_business_count=1,
                            old_segment_count=1, original_count=1))
    projected = project_business_destinations(original, case["graph_profile"], declaration(original))
    candidates = {c.final_destination: c for c in projected.groups[0].candidates}
    assert candidates["3"].minimum_protected_seconds_slack == "7/10"
    assert candidates["3"].minimum_protected_tick_slack == -1
    assert candidates["3"].structural_necessary and not candidates["3"].deadline_necessary
    assert "3" not in projected.groups[0].necessary_domain


def test_seconds_and_tick_shortest_paths_are_solved_separately(projection_case):
    case, original, _ = projection_case
    profile = json.loads(case["graph_profile"].read_text())
    profile["edges"] += [dict(start=a, end=b, length=length, speed="1", capacity=1)
        for a, b, length in ((0, 3, "1.9"), (0, 7, "0.4"), (7, 2, "0.4"))]
    profile["edges"] = [dict(e, length="10") if e["start"] == 0 and e["end"] == 2 else e for e in profile["edges"]]
    profile["edges"] = [dict(e, length="0.4") if e["start"] == 2 and e["end"] == 3 else e for e in profile["edges"]]
    case["graph_profile"].write_text(json.dumps(profile), encoding="utf-8")
    original = seal(replace(original, tasks=(original.tasks[0], replace(original.tasks[1],
        deadline_seconds=Decimal("4003.91"), deadline=4003)), contract=replace(original.contract,
        graph_sha256=sha256(case["graph_profile"].read_bytes()).hexdigest())))
    # Three 0.4s edges win in seconds (1.2) but the 1.9s single edge wins in ticks (2).
    projected = project_business_destinations(original, case["graph_profile"], declaration(original))
    candidate = next(c for c in projected.groups[0].candidates if c.final_destination == "3")
    assert candidate.minimum_protected_seconds_slack == "27/10"
    assert candidate.minimum_protected_tick_slack == 0


def test_empty_domain_fails_without_mutating_or_dropping_source(projection_case):
    case, original, _ = projection_case
    impossible = seal(replace(original, tasks=tuple(replace(t, deadline=-1, deadline_seconds=Decimal(-1)) for t in original.tasks)))
    before = impossible.content_sha256
    with pytest.raises(BusinessProjectionError, match="empty whole-flight"):
        project_business_destinations(impossible, case["graph_profile"], declaration(impossible))
    assert impossible.content_sha256 == before and len(impossible.tasks) == 2


@pytest.mark.parametrize("field", ["salt", "candidate_policy", "deadline_policy", "unload_seconds", "source_ref", "result_dependency"])
def test_missing_policy_has_no_implicit_default(projection_case, field):
    case, original, contract = projection_case
    del contract[field]
    with pytest.raises(BusinessProjectionError, match="exact projection contract"):
        project_business_destinations(original, case["graph_profile"], contract)


@pytest.mark.parametrize("field,value", [("evidence_status", "confirmed"), ("candidate_policy", "all_nodes"),
    ("selection_policy", "best_completed_result"), ("salt", ""), ("unload_seconds", "-1"),
    ("source_workload_sha256", "0" * 64), ("graph_sha256", "0" * 64)])
def test_unsupported_or_unbound_contract_rejected(projection_case, field, value):
    case, original, contract = projection_case
    contract[field] = value
    with pytest.raises(BusinessInputError):
        project_business_destinations(original, case["graph_profile"], contract)


@pytest.mark.parametrize("reseal", [False, True])
@pytest.mark.parametrize("change", ["origin", "deadline", "release", "raw_identity", "destination", "drop", "group", "metadata"])
def test_projected_payload_tamper_rejected_even_if_resealed(projection_case, change, reseal):
    case, original, contract = projection_case
    projected = project_business_destinations(original, case["graph_profile"], contract)
    row = projected.records[0]
    if change == "origin":
        row = replace(row, original=replace(row.original, origin="4"))
    elif change == "deadline":
        row = replace(row, original=replace(row.original, deadline=99999))
    elif change == "release":
        row = replace(row, original=replace(row.original, release_at=0))
    elif change == "raw_identity":
        row = replace(row, original=replace(row.original, source=replace(row.original.source, raw_task_id=999)))
    elif change == "destination":
        row = replace(row, projected_destination="5" if row.projected_destination == "3" else "3")
    elif change == "drop":
        projected = replace(projected, records=projected.records[1:])
    elif change == "group":
        group = replace(projected.groups[0], necessary_domain=("1",))
        projected = replace(projected, groups=(group,))
    elif change == "metadata":
        projected = replace(projected, source_business_count=1, runtime_adaptation_required=False)
    if change not in ("drop", "group", "metadata"):
        projected = replace(projected, records=(row,) + projected.records[1:])
    if reseal:
        projected = replace(projected, content_sha256=projection_sha256(projected))
    with pytest.raises(BusinessProjectionError):
        validate_business_projection(projected, original, case["graph_profile"])


def test_original_source_contract_profile_and_group_tampering_rejected(projection_case):
    case, original, contract = projection_case
    changed = replace(original, tasks=original.tasks[:1])
    with pytest.raises(BusinessProjectionError, match="content binding"):
        project_business_destinations(changed, case["graph_profile"], contract)
    changed = seal(changed)
    with pytest.raises(BusinessProjectionError, match="denominator"):
        project_business_destinations(changed, case["graph_profile"], declaration(changed))
    inconsistent = seal(replace(original, tasks=(original.tasks[0], replace(original.tasks[1], final_destination="3"))))
    with pytest.raises(BusinessProjectionError, match="inconsistent final"):
        project_business_destinations(inconsistent, case["graph_profile"], declaration(inconsistent))
    case["graph_profile"].write_text(case["graph_profile"].read_text() + "\n", encoding="utf-8")
    with pytest.raises(BusinessProjectionError, match="profile bytes"):
        project_business_destinations(original, case["graph_profile"], contract)


def test_new_type_is_immutable_and_cannot_silently_enter_old_runtime(projection_case):
    from scripts.experiments.ics_circulation_v3.business_runtime import build_business_runtime
    case, original, contract = projection_case
    projected = project_business_destinations(original, case["graph_profile"], contract)
    with pytest.raises(FrozenInstanceError):
        projected.records[0].projected_destination = "1"
    with pytest.raises(BusinessInputError, match="audited BusinessWorkload required"):
        build_business_runtime(projected, case["graph_profile"], {})
