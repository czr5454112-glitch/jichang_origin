from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from hashlib import sha256
import json

import pytest

from test_ics_circulation_v3_business_inputs import case, rebind, make_densified_case
from test_ics_circulation_v3_business_projection import projection_case, declaration, seal
from scripts.experiments.ics_circulation_v3.business_inputs import BusinessInputError, load_business_workload
from scripts.experiments.ics_circulation_v3.business_projection import (
    project_business_destinations, projection_sha256)
from scripts.experiments.ics_circulation_v3.business_runtime import (
    build_business_runtime, parse_runtime_proxy_contract)
from scripts.experiments.ics_circulation_v3.business_projection_runtime import (
    BINDING_FIELDS, RUN_POLICIES, SOURCE_PATH_FIELDS, ProjectedBusinessRuntime,
    build_projected_business_runtime)
from scripts.experiments.ics_circulation_v3.model import Bag
from scripts.experiments.ics_circulation_v3.storage_contracts import StorageBag


def run_declaration(original, projected, runtime):
    return dict(RUN_POLICIES, run_id="fixture-projection-run", title="Source authenticated fixture proxy",
        source_workload_sha256=original.content_sha256,
        input_contract_sha256=original.contract.canonical_sha256,
        projection_sha256=projected.content_sha256,
        projection_contract_sha256=projected.contract.canonical_sha256,
        runtime_contract_sha256=parse_runtime_proxy_contract(runtime, original).canonical_sha256,
        graph_sha256=original.contract.graph_sha256, assumption_id="test-explicit-proxy",
        source_ref="test original source artifacts and frozen projection")


@pytest.fixture
def runtime_case(projection_case):
    source, _, _ = projection_case
    graph = json.loads(source["graph_profile"].read_text())
    for node in graph["nodes"]:
        node["system_key"] = "explicit-fixture-zone"
    source["graph_profile"].write_text(json.dumps(graph), encoding="utf-8")
    source["contract"]["graph_sha256"] = sha256(source["graph_profile"].read_bytes()).hexdigest()
    rebind(source)
    original = load_business_workload(**source)
    projection_contract = dict(declaration(original), unload_seconds="0.1")
    projected = project_business_destinations(original, source["graph_profile"], projection_contract)
    runtime = dict(schema="ics_business_runtime_proxy_v1", contract_id="explicit-runtime-fixture",
        evidence_status="proxy_research", input_contract_sha256=original.contract.canonical_sha256,
        graph_sha256=original.contract.graph_sha256,
        node_resource_policy="exact_bound_input_node_capacity_and_loaded_wait",
        empty_wait_policy="same_as_declared_loaded_wait_proxy",
        edge_permission_policy="both_modes_all_source_directed_edges_proxy",
        edge_capacity_policy="preserve_source_integer_including_closed_zero",
        travel_policy="exact_length_over_speed_ceil_to_input_tick",
        partition_by_node={n.node_id: "fixture-control" for n in original.contract.nodes},
        module=dict(kind="existing_fixed_fifo_proxy", loading_seconds="0", unload_seconds="0.1",
            hold_seconds_by_node={n.node_id: "0" for n in original.contract.nodes},
            reception_capacity=1, export_min_stock=0),
        routing=dict(route_mode="whole_route", search_horizon=80, candidate_count=1,
            expansion_limit=10000, static_path_limit=12, local_label_limit=3,
            dynamic_local=True, deadline_ms=None, cache_contract="isolated_replay_v1"),
        reactive_empty_dispatch=True, coordination_order="route_then_prebalance",
        evidence=[dict(field=k, source_ref="explicit fixture", assumption_id="test-"+k) for k in
            ("permissions", "module", "partition", "travel_capacity", "routing", "coordination")])
    return dict(original=original, projection=projected, source_inputs=source,
        projection_declaration=projection_contract, runtime_contract=runtime,
        run_contract=run_declaration(original, projected, runtime), profile_path=source["graph_profile"])


def test_only_destination_changes_private_tape_and_full_provenance(runtime_case):
    result = build_projected_business_runtime(**runtime_case)
    original = runtime_case["original"]
    old = build_business_runtime(original, runtime_case["profile_path"], runtime_case["runtime_contract"])
    assert type(result) is ProjectedBusinessRuntime
    assert result.initial == old.initial
    assert result.initial.bags == result.initial.storage_progress == {}
    assert len(result.future_bags) == result.source_business_count == 2
    assert result.source_segment_count == 3 and len(result.initial.trays) == 1
    for before, after, record in zip(old.future_bags, result.future_bags, runtime_case["projection"].records):
        assert after == replace(before, destination=record.projected_destination)
        assert type(after) is type(before)
        assert record.original_destination == "1" and record.projected_destination in ("3", "5")
    early, direct = result.future_bags
    assert isinstance(early, StorageBag) and type(direct) is Bag
    assert early.storage == old.future_bags[0].storage
    assert early.storage.published_at == early.arrival
    assert result.environment_projection.original == original
    assert result.environment_projection.projection == runtime_case["projection"]
    assert result.environment_projection.run_contract.projection_sha256 == runtime_case["projection"].content_sha256
    assert result.simulation_kwargs() == old.simulation_kwargs()
    assert result.generator_factory == old.generator_factory
    assert result.contract == old.contract
    assert result.closed_edge_ids == old.closed_edge_ids == ("2->1",)
    assert result.edge_travel_seconds == old.edge_travel_seconds
    assert result.input_binding_sha256 == original.input_sha256
    assert original.tasks[0].final_destination == "1"
    with pytest.raises(FrozenInstanceError):
        result.environment_projection.original = None


def test_densified_complete_parent_family_and_every_task_preserved(runtime_case):
    source = runtime_case["source_inputs"]
    make_densified_case(source)
    original = load_business_workload(**source)
    contract = dict(runtime_case["projection_declaration"], source_workload_sha256=original.content_sha256)
    projected = project_business_destinations(original, runtime_case["profile_path"], contract)
    runtime_case.update(original=original, projection=projected, projection_declaration=contract,
        run_contract=run_declaration(original, projected, runtime_case["runtime_contract"]))
    result = build_projected_business_runtime(**runtime_case)
    assert len(result.future_bags) == result.source_business_count == 4 and result.source_segment_count == 6
    assert len(projected.groups) == 1 and projected.groups[0].flight_instance_count == 2
    assert len({b.destination for b in result.future_bags}) == 1
    assert [b.bag_id for b in result.future_bags] == [t.business_bag_id for t in original.tasks]
    assert original.independent_observed_operating_days == 0


@pytest.mark.parametrize("field", sorted(BINDING_FIELDS))
def test_fixed_external_run_bindings_fail_closed(runtime_case, field):
    runtime_case["run_contract"][field] = "0" * 64
    with pytest.raises(BusinessInputError, match="binding mismatch"):
        build_projected_business_runtime(**runtime_case)


@pytest.mark.parametrize("field", sorted(SOURCE_PATH_FIELDS | {"contract"}))
def test_source_revalidation_is_mandatory(runtime_case, field):
    del runtime_case["source_inputs"][field]
    with pytest.raises(BusinessInputError, match="source_inputs"):
        build_projected_business_runtime(**runtime_case)


@pytest.mark.parametrize("field", sorted(SOURCE_PATH_FIELDS))
def test_changed_source_bytes_refused_even_without_changing_memory(runtime_case, field):
    path = runtime_case["source_inputs"][field]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(BusinessInputError):
        build_projected_business_runtime(**runtime_case)


@pytest.mark.parametrize("change", ["destination", "protected", "deadline", "identity", "lifecycle", "drop"])
def test_double_resealed_payloads_and_declarations_cannot_rewrite_raw_source(runtime_case, change):
    original = runtime_case["original"]
    early, direct = original.tasks
    changes = {
        "destination": dict(final_destination="5"), "protected": dict(protected=False),
        "deadline": dict(deadline=99999, deadline_seconds=Decimal(99999)),
        "identity": dict(business_bag_id="invented-business-bag"),
        "lifecycle": dict(lifecycle="direct", storage_node=None, scheduled_release_seconds=None,
                          release_at=None, published_at=None)}
    tasks = (direct,) if change == "drop" else (replace(early, **changes[change]), direct)
    # Destination must be consistent for the full parent family, even in this
    # hostile new declaration. All public memory seals are actively replaced.
    if change == "destination":
        tasks = tuple(replace(t, final_destination="5") for t in original.tasks)
    modified = seal(replace(original, tasks=tasks,
        raw_business_count=len(tasks), original_count=len(tasks),
        old_segment_count=sum(len(t.old_segment_ids) for t in tasks)))
    declaration2 = dict(runtime_case["projection_declaration"], source_workload_sha256=modified.content_sha256)
    projected2 = project_business_destinations(modified, runtime_case["profile_path"], declaration2)
    runtime_case.update(original=modified, projection=projected2, projection_declaration=declaration2,
        run_contract=run_declaration(modified, projected2, runtime_case["runtime_contract"]))
    with pytest.raises(BusinessInputError, match="complete reloaded source"):
        build_projected_business_runtime(**runtime_case)


def test_fixed_external_projection_declaration_rejects_changed_embedded_contract(runtime_case):
    external = deepcopy(runtime_case["projection_declaration"])
    altered = dict(external, salt="different-experiment")
    changed = project_business_destinations(runtime_case["original"], runtime_case["profile_path"], altered)
    runtime_case.update(projection=changed,
        run_contract=run_declaration(runtime_case["original"], changed, runtime_case["runtime_contract"]))
    with pytest.raises(BusinessInputError, match="external projection declaration"):
        build_projected_business_runtime(**runtime_case)


@pytest.mark.parametrize("change", ["split_group", "drop", "domain", "source"])
def test_resealed_projection_still_requires_full_semantic_recomputation(runtime_case, change):
    projected = runtime_case["projection"]
    if change == "split_group":
        changed = replace(projected, records=(replace(projected.records[0], projected_destination="1"), projected.records[1]))
    elif change == "drop":
        changed = replace(projected, records=projected.records[:1], source_business_count=1)
    elif change == "domain":
        changed = replace(projected, groups=(replace(projected.groups[0], necessary_domain=("1", "3", "5")),))
    else:
        changed = replace(projected, source_input_sha256=())
    changed = replace(changed, content_sha256=projection_sha256(changed))
    runtime_case.update(projection=changed,
        run_contract=run_declaration(runtime_case["original"], changed, runtime_case["runtime_contract"]))
    with pytest.raises(BusinessInputError, match="projection differs"):
        build_projected_business_runtime(**runtime_case)


def test_exact_unload_contract_must_match_even_if_ceil_ticks_match(runtime_case):
    runtime_case["runtime_contract"]["module"]["unload_seconds"] = "0.2"
    runtime_case["run_contract"] = run_declaration(runtime_case["original"], runtime_case["projection"], runtime_case["runtime_contract"])
    with pytest.raises(BusinessInputError, match="exact unload seconds mismatch"):
        build_projected_business_runtime(**runtime_case)


def test_distinct_graph_path_same_bytes_allowed(runtime_case, tmp_path):
    copy = tmp_path / "same-graph-different-name.json"
    copy.write_bytes(runtime_case["profile_path"].read_bytes())
    runtime_case["profile_path"] = copy
    assert len(build_projected_business_runtime(**runtime_case).future_bags) == 2


def test_old_adapter_rejects_projection_and_projected_runtime(runtime_case):
    result = build_projected_business_runtime(**runtime_case)
    for wrong in (runtime_case["projection"], result):
        with pytest.raises(BusinessInputError, match="BusinessWorkload"):
            build_business_runtime(wrong, runtime_case["profile_path"], runtime_case["runtime_contract"])


def test_source_change_during_recompute_refused(runtime_case, monkeypatch):
    from scripts.experiments.ics_circulation_v3 import business_projection_runtime as module
    original = module.validate_business_projection
    def change_after(*args):
        original(*args)
        path = runtime_case["source_inputs"]["source_timetable"]
        path.write_bytes(path.read_bytes() + b"\n")
    monkeypatch.setattr(module, "validate_business_projection", change_after)
    with pytest.raises(BusinessInputError, match="source changed during"):
        build_projected_business_runtime(**runtime_case)


@pytest.mark.parametrize("field", sorted(RUN_POLICIES))
def test_run_policy_is_explicit_and_cannot_silently_fall_back(runtime_case, field):
    del runtime_case["run_contract"][field]
    with pytest.raises(BusinessInputError, match="projection run contract"):
        build_projected_business_runtime(**runtime_case)
