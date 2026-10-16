"""Unchanged failure-aware complete saved checks plus data-only C lifecycle."""
from __future__ import annotations
from pathlib import Path
from . import verify_initial_owner_route_single_capture_campaign as original
from . import single_capture_owned_codec_runtime as runtime


def provider_lifetime(record, plan, branches):
    require = runtime.require
    contract = plan['C_provider']
    require(type(record) is dict and record['status'] == 'closed_identity_checked', 'owned_saved_lifecycle')
    names = ('setup_started_ns', 'load_started_ns', 'setup_finished_ns', 'close_started_ns', 'close_finished_ns')
    times = [record[name] for name in names]
    require(all(type(x) is int and x >= 0 for x in times) and times == sorted(times), 'owned_saved_clock_order')
    for row in branches.values():
        if 'attempt_started_ns' in row:
            require(record['setup_finished_ns'] <= row['attempt_started_ns'] <= row['attempt_finished_ns']
                <= record['close_started_ns'], 'owned_saved_branch_envelope')
    require(record['actual_entry'] == record['actual_exit']
        and record['files_entry'] == record['files_exit'], 'owned_saved_entry_exit')
    actual = record['actual_entry']; expected = Path(contract['binary']['path']).resolve()
    require(actual['module'] == runtime.provider.MODULE
        and all(Path(actual[name]).resolve() == expected for name in ('file', 'spec_origin', 'loader_path'))
        and actual['loader_type'] == 'ExtensionFileLoader'
        and actual['binary_sha256'] == contract['binary']['sha256']
        and actual['source_sha256'] == contract['original_sources'], 'owned_saved_actual_identity')
    expected_DLLs = {name: {'path': str(Path(value['path']).resolve()), 'sha256': value['sha256']}
        for name, value in contract['runtime_dependencies'].items() if 'path' in value}
    require(actual['actual_DLLs'] == expected_DLLs, 'owned_saved_actual_DLLs')
    require(actual['contract'] == {'schema': runtime.provider.SCHEMA, 'max_depth': 64, 'max_nodes': 2000000,
        'key_scan_limit': 2000000, 'headers_python': '3.11.9', 'native_simulation_authority': False},
        'owned_saved_ABI_contract')
    require(record['files_entry'] == runtime.verify_files(contract), 'owned_saved_current_files')
    require(record['binding_proof']['same_original_complete_runtime_query_proof'] is True
        and record['direct_and_scheduler_publication_bound'] is True,
        'owned_saved_publication_binding')
    require(record['actual_direct_C_supported'] is None and record['actual_fallback_count'] is None
        and record['provider_includes_original_fallback'] is True
        and record['request_preflight_or_instrumentation_added'] is False
        and record['extension_unload_claimed'] is False and record['per_request_cycle_cleanup_claimed'] is False,
        'owned_saved_support_scope')
    return {'status': 'passed_actual_provider_identity_with_unmeasured_fallback',
        'setup_ms': (times[2]-times[0])/1e6, 'close_identity_ms': (times[4]-times[3])/1e6,
        'actual_direct_C_supported': None, 'actual_fallback_count': None,
        'provider_includes_original_fallback': True, 'extension_unload_certified': False,
        'scope': 'Cold provider setup/identity close belong to full campaign; root publication remains fully timed.'}


def make_namespace(campaign):
    # This factory retains the successful v2 defining globals, both replay
    # levels, explicit attempt envelopes and all invalid/unknown distinctions.
    return original.make_namespace(campaign)


def verify_saved(output, expected):
    from . import initial_owner_route_single_capture_owned_codec_campaign as campaign
    namespace = make_namespace(campaign)
    result = namespace.verify_saved(output, expected)
    plan = campaign.verify_plan(output, expected)
    lifetime_path = Path(output)/'C_provider_lifetime.json'
    result['C_provider_lifetime'] = provider_lifetime(campaign.read(lifetime_path), plan,
        campaign.read(Path(output)/'branch_ledger.json'))
    result['C_provider_lifetime_reference'] = campaign.reference(lifetime_path)
    result['original_failure_aware_schema'] = result['schema']
    result['schema'] = 'g31.initial_single_capture.owned_C_failure_aware_saved.v1'
    # Never replace an original failed_saved_audit with a lifecycle success.
    result['actual_direct_C_support_measured'] = False
    result['native_reexecution'] = False
    return result


def source_proof():
    from . import initial_owner_route_single_capture_owned_codec_campaign as campaign
    namespace = make_namespace(campaign)
    return {'schema': 'g31.single_capture.owned_C_saved_source.v1',
        'complete_failure_aware_source': namespace.source_proof(),
        'all_original_checks_retained': True, 'explicit_attempt_envelope_retained': True,
        'both_root_replay_levels_new_campaign': True,
        'additional_actual_provider_lifetime_and_files_checks': True,
        'reported_and_certified_root_remain_separate': True,
        'actual_direct_C_support_measured': False, 'native_or_predictor_reexecution': False}
