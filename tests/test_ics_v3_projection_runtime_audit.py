"""Independent Round11 source/runtime boundary probes with self-authored raw files.

No author fixture import. Projection candidate expectations below come from the
six-node declared graph. All raw, parent, segment and normalized source artifacts
are generated explicitly and retain the complete two-family 2x denominator.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal
from fractions import Fraction
import gzip
from hashlib import sha256
import json

import pytest

from scripts.experiments.ics_circulation_v3.business_inputs import (
    BusinessInputError, business_workload_sha256, load_business_workload,
)
from scripts.experiments.ics_circulation_v3.business_projection import (
    BusinessProjectionError, project_business_destinations, projection_sha256,
)


AUDIT_COUNTERS = {'adapter_calls': 0, 'physical_runs': 0}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True), encoding='utf-8')


def reseal_workload(workload):
    return replace(workload, content_sha256=business_workload_sha256(workload))


def reseal_projection(projection):
    return replace(projection, content_sha256=projection_sha256(projection))


def bind_sources(source):
    write_json(source['normalization_manifest'], {
        'outputs': {source['normalized'].name: digest(source['normalized'])},
        'input_sha256': {str(source[k].resolve()): digest(source[k]) for k in
                        ('raw', 'canonical', 'source_timetable', 'source_manifest', 'graph_profile')},
    })


@pytest.fixture
def audit_case(tmp_path):
    # Storage 1 cannot reach original sink 2. It reaches 3/4, which can return
    # to loader5; loader5 cannot reach loader0. Original legal3 is retained.
    aliases = ['L0', 'E', 'U2', 'U3', 'U4', 'L5']
    profile = {
        'nodes': [{'location': i, 'alias': alias, 'system_key': 'audit-zone'} for i, alias in enumerate(aliases)],
        'business_roles': {'source_candidate_ids': [0, 5], 'sink_candidate_ids': [2, 3, 4]},
        'edges': [dict(start=a, end=b, length=length, speed='1', capacity=cap)
                  for a, b, length, cap in [(0, 1, '10.00000000000000000001', 1),
                      (0, 2, '3', 1), (1, 3, '10', 1), (1, 4, '20', 2),
                      (3, 5, '7.1', 1), (4, 5, '5', 1), (2, 5, '4', 1),
                      (5, 1, '6', 1), (5, 0, '1', 0)]],
    }
    source = {key: tmp_path / name for key, name in {
        'normalized': 'audit_business_2x.jsonl.gz', 'normalization_manifest': 'audit_bindings.json',
        'raw': 'audit_2x.txt', 'canonical': 'audit_segments.jsonl',
        'source_timetable': 'audit_parent.txt', 'source_manifest': 'audit_manifest.json',
        'graph_profile': 'audit_graph.json'}.items()}
    write_json(source['graph_profile'], profile)
    parents = [(0, Decimal('10.00000000000000000001'), Decimal('5200.00000000000000000001'), 2),
               (1, Decimal('4000.00000000000000000001'), Decimal('5200.00000000000000000001'), 2),
               (2, Decimal('40.00000000000000000001'), Decimal('5800.00000000000000000001'), 3),
               (3, Decimal('4700.00000000000000000001'), Decimal('5800.00000000000000000001'), 3)]
    # Fraction arithmetic prevents the fixture itself losing source precision.
    def shifted(value, amount):
        raw = str(value)
        whole, dot, fractional = raw.partition('.')
        return str(int(whole) + amount) + dot + fractional
    all_rows = [(ident, str(arrival), str(std), dest, ident, 0) for ident, arrival, std, dest in parents]
    all_rows += [(ident+4, shifted(arrival, shift), shifted(std, shift), dest, ident, shift)
                 for ident, arrival, std, dest in parents for shift in [1800 if dest == 2 else 3600]]
    header = 'ID EntryTime(s) STD(s) star end Unloader Loader\n'
    def raw_line(row):
        ident, arrival, std, dest, _, _ = row
        return f'{ident} {arrival} {std} 0 {dest} {aliases[dest]} L0\n'
    source['source_timetable'].write_text(header + ''.join(map(raw_line, all_rows[:4])), encoding='utf-8')
    source['raw'].write_text(header + ''.join(map(raw_line, all_rows)), encoding='utf-8')
    segments, normalized = [], []
    for ident, arrival, std, dest, parent, shift in all_rows:
        early = Fraction(std)-Fraction(arrival) >= 4800
        release = shifted(std, -2700) if early else None
        legs = [('storage_in', 0, 1, arrival), ('storage_out', 1, dest, release)] if early else [('direct', 0, dest, arrival)]
        for leg, start, goal, at in legs:
            segments.append(dict(task_id=ident, segment_id=f'{ident}:{leg}', leg=leg,
                pallet_id=ident, start=start, goal=goal, pass_time=at, std=std,
                original_start=0, original_goal=dest, original_entry_time=arrival,
                source_line=ident+2, early_bag_split=early))
        normalized.append(dict(business_bag_id=f'projected:2x:{ident}',
            source=dict(raw_sha256=digest(source['raw']), raw_task_id=ident, source_line=ident+2,
                parent_timetable_sha256=digest(source['source_timetable']), parent_task_id=parent,
                parent_source_line=parent+2, flight_surrogate=[str(parents[parent][2]), dest, aliases[dest]],
                synthetic_inserted=bool(shift), time_shift_seconds=shift),
            arrival_seconds=arrival, std_seconds=std, origin='0', final_destination=str(dest),
            lifecycle='early_storage' if early else 'direct', storage_node_proxy='1' if early else None,
            scheduled_release_seconds=release, old_segment_ids=[f'{ident}:{leg[0]}' for leg in legs],
            physical_tray_id=None, deadline_contract=None, protected_contract=None, storage_carrier_policy=None))
    source['canonical'].write_text('\n'.join(json.dumps(row) for row in segments), encoding='utf-8')
    source['normalized'].write_bytes(gzip.compress('\n'.join(json.dumps(row) for row in normalized).encode(), mtime=0))
    write_json(source['source_manifest'], dict(lifecycle=dict(early_bag_threshold_seconds=4800,
        storage_out_lead_seconds=2700, storage_in_goal=1, storage_out_start=1),
        raw_task_count=8, expanded_segment_count=12, direct_raw_task_count=4, early_split_raw_task_count=4,
        raw_by_start={'0': 8}, raw_by_goal={'2': 4, '3': 4}))
    source['contract'] = dict(schema='ics_business_inputs_v1', scope='input_only_fixed_storage_proxy',
        contract_id='independent-source', title='Independent two-flight proxy', evidence_status='proxy_research',
        graph_sha256=digest(source['graph_profile']), tick_seconds='10',
        deadline=dict(policy='std_minus_lead', lead_seconds='0.00000000000000000002'),
        protection=dict(policy='explicit_ids', business_ids=['projected:2x:0', 'projected:2x:1', 'projected:2x:4', 'projected:2x:5']),
        initial_storage=[], initial_trays=[dict(tray_id='audit-t0', node_id='0', available_seconds='0'),
                                          dict(tray_id='audit-t5', node_id='5', available_seconds='0')],
        nodes=[dict(node_id=str(i), capacity=2, loaded_wait_allowed=True) for i in range(6)],
        storage=dict(node_id='1', capacity=2, carrier_policy='on_carrier',
            publication_policy='irrevocable_at_bag_arrival', release_policy='normalized_scheduled_release',
            uses_node_wait_capacity=True, dedicated_retrieval=False),
        evidence=[dict(field=k, source_ref='independent raw fixture', assumption_id='audit-'+k) for k in
                  ('clock', 'deadline', 'protection', 'initial_trays', 'nodes', 'storage')])
    bind_sources(source)
    original = load_business_workload(**source)
    declaration = dict(schema='ics_business_destination_projection_v1', evidence_status='proxy_research',
        grouping_policy='whole_parent_flight_family_with_all_derived_copies',
        selection_policy='retain_legal_original_else_min_sha256_rank', node_order='unicode_lexical_string_id',
        candidate_policy='original_role_unloaders_with_return_to_any_original_loader',
        edge_policy='both_modes_positive_original_directed_edges_proxy',
        deadline_policy='original_protected_deadline_exact_seconds_and_per_edge_ceil_ticks',
        preservation_policy='all_original_task_fields_and_full_denominator', result_dependency='none_source_and_declared_contract_only',
        projection_id='independent-projection', title='Independent destination proxy',
        source_workload_sha256=original.content_sha256, graph_sha256=original.contract.graph_sha256,
        salt='fixed-before-observation-11', unload_seconds='10.00000000000000000001',
        assumption_id='audit-projection', source_ref='independent-projection-audit')
    projection = project_business_destinations(original, source['graph_profile'], declaration)
    runtime = dict(schema='ics_business_runtime_proxy_v1', contract_id='independent-runtime', evidence_status='proxy_research',
        input_contract_sha256=original.contract.canonical_sha256, graph_sha256=original.contract.graph_sha256,
        node_resource_policy='exact_bound_input_node_capacity_and_loaded_wait',
        empty_wait_policy='same_as_declared_loaded_wait_proxy', edge_permission_policy='both_modes_all_source_directed_edges_proxy',
        edge_capacity_policy='preserve_source_integer_including_closed_zero', travel_policy='exact_length_over_speed_ceil_to_input_tick',
        partition_by_node={str(i): 'audit-owner' for i in range(6)},
        module=dict(kind='existing_fixed_fifo_proxy', loading_seconds='0', unload_seconds=declaration['unload_seconds'],
            hold_seconds_by_node={str(i): '10.1' for i in range(6)}, reception_capacity=1, export_min_stock=0),
        routing=dict(route_mode='whole_route', search_horizon=1200, candidate_count=3, expansion_limit=10000,
            static_path_limit=12, local_label_limit=3, dynamic_local=True, deadline_ms=None, cache_contract='isolated_replay_v1'),
        reactive_empty_dispatch=False, coordination_order='route_then_prebalance',
        evidence=[dict(field=k, source_ref='independent runtime fixture', assumption_id='audit-'+k) for k in
                  ('permissions', 'module', 'partition', 'travel_capacity', 'routing', 'coordination')])
    return dict(source=source, original=original, declaration=declaration, projection=projection, runtime=runtime)


def test_independent_fixture_complete_family_and_hand_computed_clock(audit_case):
    original, projection = audit_case['original'], audit_case['projection']
    assert (original.raw_business_count, original.old_segment_count, original.original_count, original.derived_count) == (8, 12, 4, 4)
    by_id = {task.business_bag_id: task for task in original.tasks}
    assert (by_id['projected:2x:0'].arrival, by_id['projected:2x:0'].deadline, by_id['projected:2x:0'].release_at) == (2, 519, 251)
    assert len(projection.groups) == 2
    assert {frozenset(group.business_bag_ids) for group in projection.groups} == {
        frozenset(f'projected:2x:{i}' for i in (0, 1, 4, 5)),
        frozenset(f'projected:2x:{i}' for i in (2, 3, 6, 7)),
    }
    assert all(group.necessary_domain == ('3', '4') and group.flight_instance_count == 2 for group in projection.groups)
    assert next(group for group in projection.groups if group.original_destination == '3').projected_destination == '3'
    assert all(record.original == by_id[record.original.business_bag_id] for record in projection.records)


def make_run(case):
    runtime_json = json.dumps(case['runtime'], sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return dict(schema='ics_business_projection_runtime_v1', evidence_status='proxy_research',
        source_validation='reload_complete_raw_canonical_parent_normalized_and_compare',
        adaptation_policy='verified_projection_changes_only_private_bag_destination',
        future_policy='private_environment_tape_reveal_only_on_observation',
        denominator_policy='complete_source_before_any_explicit_external_window',
        run_id='independent-run', title='Independent fixed proxy runtime',
        source_workload_sha256=case['original'].content_sha256,
        input_contract_sha256=case['original'].contract.canonical_sha256,
        projection_sha256=case['projection'].content_sha256,
        projection_contract_sha256=case['projection'].contract.canonical_sha256,
        runtime_contract_sha256=sha256(runtime_json.encode()).hexdigest(),
        graph_sha256=case['original'].contract.graph_sha256,
        assumption_id='independent-frozen-run', source_ref='independent-audit')


def adapt(case, *, run=None, source=None, profile=None):
    from scripts.experiments.ics_circulation_v3.business_projection_runtime import build_projected_business_runtime
    AUDIT_COUNTERS['adapter_calls'] += 1
    return build_projected_business_runtime(case['original'], case['projection'],
        source_inputs=case['source'] if source is None else source,
        projection_declaration=case['declaration'], runtime_contract=case['runtime'],
        run_contract=make_run(case) if run is None else run,
        profile_path=case['source']['graph_profile'] if profile is None else profile)


def test_runtime_preserves_every_non_destination_field_and_original_object(audit_case):
    from scripts.experiments.ics_circulation_v3.business_runtime import build_business_runtime
    from scripts.experiments.ics_circulation_v3.model import Bag
    from scripts.experiments.ics_circulation_v3.storage_contracts import StorageBag
    original = audit_case['original']
    before = asdict(original)
    base = build_business_runtime(original, audit_case['source']['graph_profile'], audit_case['runtime'])
    result = adapt(audit_case)
    assert result.initial == base.initial
    assert asdict(original) == before
    assert result.environment_projection.original == original
    assert result.environment_projection.projection == audit_case['projection']
    assert result.source_business_count == 8 and result.source_segment_count == 12
    assert set(result.initial.trays) == {'audit-t0', 'audit-t5'}
    expected = {row.original.business_bag_id: row for row in audit_case['projection'].records}
    for source, projected in zip(base.future_bags, result.future_bags):
        changed = asdict(projected)
        assert changed.pop('destination') == expected[source.bag_id].projected_destination
        prior = asdict(source)
        prior.pop('destination')
        assert changed == prior and type(projected) is type(source)
        assert (type(projected) is StorageBag) == ('storage' in changed)
        assert type(projected) in (Bag, StorageBag)
    assert result.initial.network.edges['0->1'].travel_time == 2
    assert result.initial.network.edges['5->0'].capacity == 0 and result.closed_edge_ids == ('5->0',)
    assert result.initial.module.unload_ticks == 2
    assert result.initial.module.hold_by_node == {str(i): 2 for i in range(6)}
    assert result.simulation_kwargs() == base.simulation_kwargs()
    assert result.input_binding_sha256 == original.input_sha256


@pytest.mark.parametrize('field', ['source_workload_sha256', 'input_contract_sha256', 'projection_sha256',
    'projection_contract_sha256', 'runtime_contract_sha256', 'graph_sha256'])
def test_fixed_run_declaration_rejects_each_wrong_artifact(audit_case, field):
    run = make_run(audit_case)
    run[field] = 'f' * 64
    with pytest.raises(BusinessInputError, match='binding mismatch'):
        adapt(audit_case, run=run)


@pytest.mark.parametrize('field', ['normalized', 'normalization_manifest', 'raw', 'canonical',
    'source_timetable', 'source_manifest', 'graph_profile', 'contract'])
def test_every_original_source_input_required(audit_case, field):
    source = dict(audit_case['source'])
    source.pop(field)
    with pytest.raises(BusinessInputError):
        adapt(audit_case, source=source)


@pytest.mark.parametrize('field,value', [('salt', 'outcome-selected-salt'), ('unload_seconds', '10.01'),
    ('source_workload_sha256', 'a'*64), ('projection_id', 'different-external-declaration')])
def test_external_projection_declaration_is_not_ignored(audit_case, field, value):
    case = dict(audit_case, declaration=dict(audit_case['declaration']))
    case['declaration'][field] = value
    with pytest.raises(BusinessInputError):
        adapt(case)


@pytest.mark.parametrize('seconds', ['10.00000000000000000002', '19.99', '0', '20.01'])
def test_exact_projection_unload_contract_not_just_rounded_ticks(audit_case, seconds):
    case = dict(audit_case, runtime=deepcopy(audit_case['runtime']))
    case['runtime']['module']['unload_seconds'] = seconds
    # Deliberately update the run's runtime SHA: semantic agreement must still
    # reject the differing projection assumption, even when tick-ceil is two.
    with pytest.raises(BusinessInputError, match='exact unload seconds'):
        adapt(case)


def altered_projection(projection, attack):
    records, groups = list(projection.records), list(projection.groups)
    if attack == 'one_final':
        records[0] = replace(records[0], projected_destination='4' if records[0].projected_destination == '3' else '3')
    elif attack == 'whole_family_wrong_rank':
        group = next(g for g in groups if g.original_destination == '2')
        destination = '4' if group.projected_destination == '3' else '3'
        records = [replace(r, projected_destination=destination) if r.group_id == group.group_id else r for r in records]
        groups = [replace(g, projected_destination=destination) if g.group_id == group.group_id else g for g in groups]
    elif attack == 'remove_derived':
        records = [r for r in records if r.original.business_bag_id != 'projected:2x:4']
    elif attack == 'duplicate_source':
        records[-1] = records[0]
    elif attack == 'record_order':
        records.reverse()
    elif attack == 'domain':
        groups[0] = replace(groups[0], necessary_domain=('3',))
    elif attack == 'family_membership':
        groups[0] = replace(groups[0], business_bag_ids=groups[0].business_bag_ids[:-1])
    elif attack == 'instance_count':
        groups[0] = replace(groups[0], flight_instance_count=1)
    elif attack == 'original_protection':
        records[0] = replace(records[0], original=replace(records[0].original, protected=False))
    elif attack == 'original_segments':
        records[0] = replace(records[0], original=replace(records[0].original, old_segment_ids=('fake',)))
    elif attack == 'original_release':
        records[0] = replace(records[0], original=replace(records[0].original, release_at=1))
    elif attack == 'old_destination':
        records[0] = replace(records[0], original_destination=records[0].projected_destination)
    else:
        raise AssertionError(attack)
    return reseal_projection(replace(projection, records=tuple(records), groups=tuple(groups)))


@pytest.mark.parametrize('attack', ['one_final', 'whole_family_wrong_rank', 'remove_derived',
    'duplicate_source', 'record_order', 'domain', 'family_membership', 'instance_count',
    'original_protection', 'original_segments', 'original_release', 'old_destination'])
def test_resealed_projection_and_updated_run_cannot_bypass_full_source_recompute(audit_case, attack):
    case = dict(audit_case, projection=altered_projection(audit_case['projection'], attack))
    with pytest.raises(BusinessInputError):
        adapt(case)


@pytest.mark.parametrize('field,value', [('protected', False), ('deadline', 9999),
    ('final_destination', '4'), ('arrival', 0), ('published_at', 0), ('release_at', 2),
    ('old_segment_ids', ('fake',))])
def test_resealed_original_projection_and_declaration_still_require_raw_reload(audit_case, field, value):
    original = audit_case['original']
    changed = replace(original.tasks[0], **{field: value})
    fake = reseal_workload(replace(original, tasks=(changed,) + original.tasks[1:]))
    # The payload, self-seal, external source declaration and run SHA all move;
    # unchanged raw/canonical source must remain authoritative at this boundary.
    declaration = dict(audit_case['declaration'], source_workload_sha256=fake.content_sha256)
    from scripts.experiments.ics_circulation_v3.business_projection import parse_projection_contract
    contract = parse_projection_contract(declaration, fake)
    projected = audit_case['projection']
    records = tuple(replace(r, original=changed) if r.original.business_bag_id == changed.business_bag_id else r for r in projected.records)
    projected = reseal_projection(replace(projected, records=records, contract=contract))
    case = dict(audit_case, original=fake, projection=projected, declaration=declaration)
    with pytest.raises(BusinessInputError, match='complete reloaded source'):
        adapt(case)


@pytest.mark.parametrize('source_field', ['normalized', 'raw', 'canonical', 'source_timetable', 'source_manifest', 'graph_profile'])
def test_changed_source_bytes_cannot_hide_behind_unchanged_objects(audit_case, source_field):
    path = audit_case['source'][source_field]
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(BusinessInputError):
        adapt(audit_case)


@pytest.mark.parametrize('attack', ['normalized_missing_derived', 'canonical_wrong_goal', 'manifest_count'])
def test_rebound_source_manifest_still_requires_semantic_full_source(audit_case, attack):
    source = audit_case['source']
    if attack == 'normalized_missing_derived':
        rows = [json.loads(line) for line in gzip.decompress(source['normalized'].read_bytes()).splitlines()]
        rows = [row for row in rows if row['source']['raw_task_id'] != 4]
        source['normalized'].write_bytes(gzip.compress('\n'.join(map(json.dumps, rows)).encode(), mtime=0))
    elif attack == 'canonical_wrong_goal':
        rows = [json.loads(line) for line in source['canonical'].read_text().splitlines()]
        rows[0]['goal'] = 4
        source['canonical'].write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
    else:
        value = json.loads(source['source_manifest'].read_bytes())
        value['expanded_segment_count'] = 11
        write_json(source['source_manifest'], value)
    bind_sources(source)
    with pytest.raises(BusinessInputError):
        adapt(audit_case)


def test_source_changes_during_projection_recompute_fail_at_exit(audit_case, monkeypatch):
    from scripts.experiments.ics_circulation_v3 import business_projection_runtime as module
    real = module.validate_business_projection
    def alter_after_validation(*args, **kwargs):
        result = real(*args, **kwargs)
        raw = audit_case['source']['raw']
        raw.write_bytes(raw.read_bytes() + b'\n')
        return result
    monkeypatch.setattr(module, 'validate_business_projection', alter_after_validation)
    with pytest.raises(BusinessInputError, match='source changed during projection adaptation'):
        adapt(audit_case)


def test_fixed_run_rejects_new_projection_even_if_new_declaration_is_valid(audit_case):
    fixed_run = make_run(audit_case)
    declaration = dict(audit_case['declaration'], salt='another-declared-source-experiment')
    projection = project_business_destinations(audit_case['original'], audit_case['source']['graph_profile'], declaration)
    with pytest.raises(BusinessInputError, match='binding mismatch'):
        adapt(dict(audit_case, declaration=declaration, projection=projection), run=fixed_run)


def test_all_initial_policy_and_restored_policy_objects_exclude_future_source_ledger(audit_case):
    from scripts.experiments.ics_circulation_v3.runtime import Simulation
    result = adapt(audit_case)
    all_ids = {bag.bag_id for bag in result.future_bags}
    policy_arguments = result.simulation_kwargs()
    assert set(policy_arguments) == {'generator_factory', 'route_mode', 'search_horizon',
                                    'candidate_count', 'reactive_empty_dispatch', 'coordination_order'}
    assert result.initial.bags == {} and result.initial.storage_progress == {}
    for value in (asdict(result.initial), policy_arguments, result.generator_factory):
        assert not any(ident in repr(value) for ident in all_ids)
        assert 'ProjectionEnvironmentProvenance' not in repr(value)
    AUDIT_COUNTERS['physical_runs'] += 1
    engine = Simulation(result.initial, future_bags=result.future_bags, **policy_arguments)
    assert not engine.observe().bags
    engine.advance(3)
    observed = engine.observe()
    assert set(observed.bags) == {'projected:2x:0'}
    assert observed.bags['projected:2x:0'].storage.published_at == 2
    assert observed.storage_progress == {}  # the first real edge arrives at4
    checkpoint = engine.checkpoint()
    assert checkpoint.state == observed
    private_future = {bag.bag_id for bags in checkpoint.pending_arrivals.values() for bag in bags}
    assert private_future == all_ids - set(observed.bags)
    for value in (checkpoint.state, checkpoint.generator, checkpoint.generator_factory,
                  checkpoint.route_selector, checkpoint.slow_controller, checkpoint.observer):
        assert not any(ident in repr(value) for ident in private_future)
        assert 'ProjectionEnvironmentProvenance' not in repr(value)
        assert 'BusinessProjection(' not in repr(value) and 'BusinessWorkload(' not in repr(value)
    AUDIT_COUNTERS['physical_runs'] += 1
    restored = Simulation.from_checkpoint(checkpoint)
    assert restored.observe() == observed
    physical = engine.advance(258)
    replay = restored.advance(258)
    def stable(value):
        raw = asdict(value)
        raw['policy_stats'] = {k: v for k, v in raw['policy_stats'].items() if not k.endswith('_ms')}
        return raw
    assert stable(physical) == stable(replay)
    first = next(bag for bag in result.future_bags if bag.bag_id == 'projected:2x:0')
    final_arrival = 251 + (1 if first.destination == '3' else 2)
    assert physical.completed['projected:2x:0'] == final_arrival + 2
    progress = physical.final_snapshot.storage_progress['projected:2x:0']
    assert progress.arrived_at == 4 and progress.departed_at == 251
    assert progress.tray_id == 'audit-t0'
    release = next(e for e in physical.trace if e['event'] == 'tray_state' and
                   e.get('tray_id') == 'audit-t0' and e.get('mode') == 'empty')
    assert release['time'] == final_arrival + 4
    assert set(physical.final_snapshot.trays) == {'audit-t0', 'audit-t5'}
