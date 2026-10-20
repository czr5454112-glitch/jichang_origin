"""Draft full failure-aware saved audit plus passive constructor sidecar.

The original saved loop decodes each raw once. Its existing branch callback is
wrapped only to retain a small diagnostic clock projection, then the complete
original branch/root/query/RPC/physical checks execute unchanged.
"""
from __future__ import annotations
import copy
from pathlib import Path
from types import SimpleNamespace
from . import verify_initial_owner_route_single_capture_owned_codec_campaign as previous
from . import single_capture_static_inventory_runtime as runtime

require = runtime.require


def branch_clocks(raw, key, envelope):
    require(raw['key'] == key, 'static_saved_branch_key')
    records = raw['root_records']
    roots = []
    for record in records:
        evidence = record['value']['evidence']
        roots.append({'root_id': evidence['root_id'],
            'root_started_ns': evidence['root_started_ns'],
            'root_deadline_ns': evidence['root_deadline_ns'],
            'decision_cutoff_ns': evidence['decision_cutoff_ns'],
            'outside_return_ns': record['outside_return_ns'],
            'has_actual_advance': bool(evidence['runtime_query_proof']['advance_calls'])})
    return {'key': key, 'envelope': copy.deepcopy(envelope), 'roots': roots,
        'clocks': copy.deepcopy(raw['clocks']),
        'root_constructed': raw['root_constructed'], 'failure': raw['failure'],
        'has_native_batches': bool(raw['native_batches'])}


def make_namespace(campaign):
    original = previous.make_namespace(campaign)
    observations = {}
    def observed_branch(raw, row, key, *, branch_envelope):
        require(key not in observations, 'static_saved_repeated_branch')
        # No raw/root container escapes this call. On malformed data the audit
        # fails; a missing diagnostic clock is never invented as a safe zero.
        try:
            observations[key] = branch_clocks(raw, key, branch_envelope)
        except Exception as error:
            # Do not let an extra diagnostic prevent the original independent
            # row/RPC checks. The final sidecar checker rejects this explicitly.
            observations[key] = {'projection_error': type(error).__name__ + ': ' + str(error)}
        return original.verify_branch(raw, row, key, branch_envelope=branch_envelope)
    original.namespace['verify_branch'] = observed_branch
    return SimpleNamespace(original=original, verify_saved=original.verify_saved,
        verify_branch=observed_branch, observations=observations,
        source_proof=original.source_proof)


def static_lifetime(record, C_record, observations, ledger):
    require(not any('projection_error' in value for value in observations.values()),
        'static_saved_raw_clock_projection_failed')
    require(type(record) is dict and record['schema'] == runtime.SCHEMA
        and record['status'] == 'closed_identity_checked'
        and record['cold_bind_status'] == 'returned', 'static_saved_lifecycle')
    start, end = record['cold_bind_started_ns'], record['cold_bind_finished_ns']
    require(type(start) is int and type(end) is int
        and C_record['load_started_ns'] <= start <= end <= C_record['setup_finished_ns'],
        'static_saved_cold_clock')
    proof = record['binding_proof']
    require(proof == C_record['binding_proof']
        and proof['static_inventory']['cold_original_method_inventory_calls'] == 1
        and proof['static_inventory']['cold_original_collection_inventory_calls'] == 1
        and proof['static_inventory']['dynamic_session_handle_transport_owner_ACK_current_checks_removed'] == 0
        and proof['constructor_callable_returns_reviewed_exact_class'] is True,
        'static_saved_binding_proof')
    require(record['cold_binding_charged_to_campaign'] is True
        and record['per_root_cycle_cleanup_claimed'] is False
        and record['constructor_CPU_or_inventory_only_claimed'] is False
        and record['no_per_root_disk_write'] is True
        and record['actual_direct_C_supported'] is None, 'static_saved_timing_scope')
    rows = record['constructors']; require(type(rows) is list, 'static_saved_rows')
    by_key, unverified, previous_end = {}, {}, C_record['setup_finished_ns']
    for ordinal, row in enumerate(rows):
        require(type(row) is dict and type(row['ordinal']) is int and row['ordinal'] == ordinal
            and row['status'] in ('constructor_returned', 'constructor_raised'), 'static_saved_row_status')
        clocks = [row['started_ns'], row['finished_ns']]
        require(all(type(x) is int for x in clocks)
            and previous_end <= clocks[0] <= clocks[1] <= C_record['close_started_ns'],
            'static_saved_constructor_clock')
        previous_end = clocks[1]
        root = row['root']
        require(type(root) is dict and set(root) == {'request_id', 'started_ns', 'deadline_ns', 'cutoff_ns'}
            and type(root['request_id']) is str and bool(root['request_id'])
            and all(type(root[name]) is int for name in ('started_ns', 'deadline_ns', 'cutoff_ns')),
            'static_saved_root_scalar_types')
        # request_id is a correlation value only; authority stays in the
        # original exact-session/endpoints/root replay, never in this mapping.
        matches = [key for key, value in observations.items()
            if root['request_id'] == key.replace('/', ':')
            and root['started_ns'] == value['clocks']['root_started_ns']]
        if not matches:
            # A branch can fail during export after a constructor ran. The old
            # saved checker preserves that missing-raw denominator. Retain the
            # reported timer under its actual attempt, but do NOT certify it as
            # a verified root constructor or silently assign zero cost.
            missing = [key for key, entry in ledger.items() if key not in observations
                and entry['status'] == 'unknown_failed'
                and root['request_id'] == key.replace('/', ':')]
            require(len(missing) == 1 and missing[0] not in unverified,
                'static_saved_unbound_constructor')
            key = missing[0]; entry = ledger[key]
            require(entry['attempt_started_ns'] <= root['started_ns'] <= clocks[0] <= clocks[1]
                <= entry['attempt_finished_ns'], 'static_saved_missing_raw_attempt')
            unverified[key] = {'status': 'unknown_missing_raw_constructor_not_certified',
                'reported_status': row['status'], 'reported_wall_ms': (clocks[1]-clocks[0])/1e6,
                'wall_ms': None}
            continue
        require(len(matches) == 1 and matches[0] not in by_key, 'static_saved_root_correlation')
        key = matches[0]; observed = observations[key]
        envelope = observed['envelope']
        require(envelope == {'attempt_started_ns': ledger[key]['attempt_started_ns'],
            'attempt_finished_ns': ledger[key]['attempt_finished_ns']}, 'static_saved_attempt_binding')
        require(envelope['attempt_started_ns'] <= root['started_ns'] <= clocks[0] <= clocks[1]
            <= observed['clocks']['result_capture_started_ns'] <= envelope['attempt_finished_ns'],
            'static_saved_root_envelope')
        require(root['deadline_ns'] == root['started_ns'] + 100_000_000
            and root['cutoff_ns'] == root['started_ns'] + 60_000_000,
            'static_saved_original_root_budgets')
        for emitted in observed['roots']:
            require(emitted['root_id'] == root['request_id']
                and emitted['root_started_ns'] == root['started_ns']
                and emitted['root_deadline_ns'] == root['deadline_ns']
                and emitted['decision_cutoff_ns'] == root['cutoff_ns']
                and clocks[1] <= emitted['outside_return_ns'], 'static_saved_published_root_binding')
        require((row['status'] == 'constructor_returned' and row['error_type'] is None)
            or (row['status'] == 'constructor_raised' and type(row['error_type']) is str
                and observed['failure'] is not None), 'static_saved_constructor_failure')
        by_key[key] = {'status': row['status'], 'wall_ms': (clocks[1]-clocks[0])/1e6}
    for key, observed in observations.items():
        must_return = (observed['root_constructed'] and observed['failure'] is None
            or observed['has_native_batches']
            or any(x['has_actual_advance'] for x in observed['roots']))
        if must_return:
            require(by_key.get(key, {}).get('status') == 'constructor_returned',
                'static_saved_missing_actual_constructor')
    return {'status': 'passed_constructor_sidecar_bound_to_original_saved_checks',
        'cold_binding_ms': (end-start)/1e6, 'constructor_rows': len(rows),
        'rows': by_key, 'missing_before_constructor_failures': sorted(set(observations)-set(by_key)),
        'unverified_missing_raw_constructor_rows': unverified,
        'interval_scope': 'Full constructor wall, nested inside complete root; not additive to root wall or CPU/inventory-only attribution.',
        'per_root_cycle_cleanup_certified': False, 'native_authority_from_sidecar': False}


def verify_saved(output, expected):
    from . import initial_owner_route_static_inventory_campaign as campaign
    namespace = make_namespace(campaign)
    result = namespace.verify_saved(output, expected)
    plan = campaign.verify_plan(output, expected)
    ledger = campaign.read(Path(output)/'branch_ledger.json')
    C_path, static_path = Path(output)/'C_provider_lifetime.json', Path(output)/'static_inventory_lifetime.json'
    C_record = campaign.read(C_path)
    result['C_provider_lifetime'] = previous.provider_lifetime(C_record, plan, ledger)
    result['static_inventory_lifetime'] = static_lifetime(campaign.read(static_path), C_record,
        namespace.observations, ledger)
    result['C_provider_lifetime_reference'] = campaign.reference(C_path)
    result['static_inventory_lifetime_reference'] = campaign.reference(static_path)
    result['original_failure_aware_schema'] = result['schema']
    result['schema'] = 'g31.initial_single_capture.static_inventory_saved.v1'
    result['actual_direct_C_support_measured'] = False
    result['native_reexecution'] = False
    return result


def source_proof():
    from . import initial_owner_route_static_inventory_campaign as campaign
    namespace = make_namespace(campaign)
    return {'schema': 'g31.initial_single_capture.static_inventory_saved_source.v1',
        'original_complete_checks': namespace.source_proof(),
        'single_existing_raw_decode_with_passive_branch_clock_projection': True,
        'accepted_C_lifetime_checker_code_unchanged_third_file_check_retained': True,
        'both_root_replay_levels_new_campaign': True,
        'constructor_missing_or_malformed_is_not_silently_zero': True,
        'original_failed_saved_status_never_promoted': True,
        'constructor_wall_nested_in_original_complete_root_not_CPU': True,
        'native_or_predictor_or_C_execution': False}
