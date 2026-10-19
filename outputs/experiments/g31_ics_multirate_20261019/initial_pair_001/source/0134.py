"""Read-only invalidation of supplied later evidence, not an execution cache.

Episode identities are caller-supplied provenance, not native capabilities.
Both snapshots are rebuilt from their raw delivered endpoints on every audit.
No prediction, local-suffix repair, command, or native observation is performed.
"""
from __future__ import annotations

import copy
import math

from . import foundation_later_seed as later


VERSION = 'g31.foundation.service_refresh.v1'
RECORD_SCHEMA = 'g31.foundation.service_refresh_record.v1'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def metadata(record):
    later.delivered.encoded(record)
    require(type(record) is dict and record.get('schema') == RECORD_SCHEMA, 'record_schema')
    require(type(record.get('episode_id')) is str and bool(record['episode_id'].strip()), 'episode_identity')
    require(record.get('owner') in ('A', 'B'), 'owner_identity')
    reference = record.get('original_reference_sha256')
    require(type(reference) is str and len(reference) == 64
            and all(character in '0123456789abcdef' for character in reference), 'original_reference_sha256')
    require(type(record.get('evidence')) is dict, 'evidence_dictionary')
    require(record['evidence'].get('owner') == record['owner'], 'record_evidence_owner_mismatch')


def make_record(evidence, *, episode_id, original_reference_sha256):
    """Package detached data; only refresh_audit performs evidence validation."""
    later.delivered.encoded(evidence)
    record = {'schema': RECORD_SCHEMA, 'episode_id': episode_id,
              'owner': evidence.get('owner') if type(evidence) is dict else None,
              'original_reference_sha256': original_reference_sha256,
              'evidence': copy.deepcopy(evidence)}
    metadata(record)
    return record


def dependencies(seed):
    bundle, evidence = seed['bundle'], seed['evidence']
    return {
        'model_and_action_domain': {'schema': seed['schema'], 'phase': seed['phase'],
            'case': seed['case_from_public_contract'], 'actions': seed['action_ids'],
            'continuation': seed['continuation']},
        'epoch': seed['at'],
        'jobs': bundle['jobs'],
        'trays': bundle['trays'],
        'resources': bundle['resources'],
        'completed_prefix': bundle['completed_prefix'],
        'service_stability': bundle['stability'],
        'edge_entries': seed['entry_receipts'],
        'source_versions_and_validity': bundle['source_records'],
        'submitted_commands_and_acks': {'own_calls': evidence['own_calls'],
            'current_actions': bundle['owner_current_action_facts'],
            'preferences': seed['retained_preferences'], 'history': seed['retained_route_history']},
        'own_outbox': evidence.get('own_outbox'),
        'collection': evidence['collection'],
        'physical_contract': bundle['contract'],
        'protocol': bundle['protocol'],
        'raw_endpoints': evidence['information']['raw_endpoints'],
        'retained_ledger': evidence['retained'],
        'supplied_evidence': evidence,
    }


def full_domain(previous, current):
    return {'jobs': sorted(set(previous['bundle']['jobs']) | set(current['bundle']['jobs'])),
            'trays': sorted(set(previous['bundle']['trays']) | set(current['bundle']['trays'])),
            'resource_nodes': sorted(set(previous['bundle']['resources']) | set(current['bundle']['resources'])),
            'route_edges': [list(edge) for edge in sorted({(edge['from'], edge['to']) for seed in (previous, current)
                                  for edge in seed['bundle']['contract']['edge_contracts']})],
            'submitted_request_ids': sorted({call['request']['request_id'] for seed in (previous, current)
                                            for call in seed['evidence']['own_calls']})}


def transition_reasons(previous, current):
    require(current['at'] >= previous['at'], 'observation_time_regressed')
    before, after = previous['evidence']['own_calls'], current['evidence']['own_calls']
    require(len(after) >= len(before)
            and later.delivered.encoded({'calls': after[:len(before)]}) == later.delivered.encoded({'calls': before}),
            'immutable_own_submission_prefix_changed')
    for job, completed_at in previous['bundle']['completed_prefix'].items():
        require(current['bundle']['completed_prefix'].get(job) == completed_at,
                'completed_prefix_changed:' + job)
    old_sources = {source['owner']: source for source in previous['bundle']['source_records']}
    new_sources = {source['owner']: source for source in current['bundle']['source_records']}
    require(set(old_sources) == set(new_sources), 'source_owner_coverage_changed')
    for owner, source in old_sources.items():
        newer = new_sources[owner]
        require(newer['captured_at'] >= source['captured_at']
                and newer['delivered_at'] >= source['delivered_at'], 'source_epoch_regressed:' + owner)
        if newer['identity'] == source['identity']:
            require(later.delivered.encoded(newer) == later.delivered.encoded(source),
                    'immutable_source_record_changed:' + owner)
    reasons = []
    if current['at'] > previous['at']:
        reasons.append('new_epoch_without_proven_cross_event_boundary')
    if any(current['at'] >= source['valid_until'] or current['at'] - source['captured_at'] > .05
           for source in old_sources.values()):
        reasons.append('previous_source_freshness_or_expiry_passed')
    if any(row['next_bound'] is not None and current['at'] >= row['next_bound']
           for row in previous['bundle']['stability']):
        reasons.append('previous_service_stability_boundary_reached')
    return reasons


def refresh_audit(previous_record, current_record, *, audit_at=None):
    """Revalidate same-owner/episode data and conservatively invalidate all changes.

An unchanged result identifies duplicate supplied data, not a new observation.
audit_at, when provided, must be the exact new observation epoch; changing a
clock argument cannot turn an old endpoint into current native evidence.
"""
    result = {'schema': VERSION, 'status': 'unknown', 'reasons': [],
        'refresh_required': True, 'changed_dependencies': [], 'seed_build_attempts': 0,
        'original_reference_sha256': None, 'reference_identity_preserved': False,
        'episode_identity_scope': 'caller_supplied_not_native_authenticated',
        'evidence_scope': 'conditional_supplied_later_v3_data_only',
        'new_native_observation_verified': False, 'cache_execution_authorized': False,
        'local_suffix_certified': False, 'native_computation_reduced': False,
        'native_delivery_verified': False, 'native_execution_certified': False,
        'native_protection_certified': False, 'online_executable': False,
        'prediction_calls': 0,
        'dependency_closure': {'policy': 'full_model_domain_without_safe_external_boundary_proof',
            'scope': 'unknown', 'entities': {}, 'reused_suffix_entities': []}}
    try:
        metadata(previous_record)
        result['original_reference_sha256'] = previous_record['original_reference_sha256']
        metadata(current_record)
        require(previous_record['episode_id'] == current_record['episode_id'], 'different_episode')
        require(previous_record['owner'] == current_record['owner'], 'different_owner')
        require(previous_record['original_reference_sha256'] == current_record['original_reference_sha256'],
                'original_reference_changed')
        result.update(episode_id=current_record['episode_id'], owner=current_record['owner'],
                      reference_identity_preserved=True)
        seeds = []
        for name, record in (('previous', previous_record), ('current', current_record)):
            result['seed_build_attempts'] += 1
            seed = later.build_seed(record['evidence'])
            result[name + '_validation'] = {'status': seed['status'], 'reasons': seed.get('reasons', [])}
            require(seed['status'] == 'conditional_current_seed', name + '_evidence_invalid')
            require(seed['owner'] == record['owner'], name + '_validated_owner_mismatch')
            result[name + '_evidence_sha256'] = later.digest(record['evidence'])
            result[name + '_seed_sha256'] = seed['seed_sha256']
            seeds.append(seed)
        previous, current = seeds
        result.update(previous_at=previous['at'], current_at=current['at'])
        result['dependency_closure'].update(scope='full_model_domain', entities=full_domain(previous, current))
        if audit_at is not None:
            require(type(audit_at) in (int, float) and math.isfinite(audit_at), 'invalid_audit_epoch')
            require(audit_at == current['at'], 'current_evidence_epoch_not_audit_epoch')
        reasons = transition_reasons(previous, current)
        before, after = dependencies(previous), dependencies(current)
        result['dependency_hashes'] = {name: {'previous': later.digest({'value': before[name]}),
                                             'current': later.digest({'value': after[name]})} for name in before}
        result['changed_dependencies'] = [name for name, hashes in result['dependency_hashes'].items()
                                          if hashes['previous'] != hashes['current']]
        if result['changed_dependencies']:
            result.update(status='full_refresh_required', reasons=reasons + [
                'dependency_change_without_proven_safe_external_boundary',
                'all_candidate_scores_resource_notifications_and_immutable_commands_remain_in_scope'])
        else:
            result.update(status='unchanged_revalidated', refresh_required=False,
                reasons=['duplicate_revalidated_data_not_a_new_native_observation_or_cache_authorization'])
        return result
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as error:
        result['reasons'].append(str(error))
        return result
