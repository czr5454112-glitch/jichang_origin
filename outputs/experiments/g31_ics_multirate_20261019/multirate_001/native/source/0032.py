"""Thin later-episode wrapper; process isolation and hard limits belong to caller."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from . import foundation_native_environment as environment
from . import foundation_later_control as control
from . import foundation_later_seed as current_model

SCHEMA = 'g31.foundation.later_episode.v1'


def fixed_choice(actions):
    declared = control.plain(actions)
    control.require(set(declared) <= set(control.PHASE_ACTIONS)
        and all(action in control.PHASE_ACTIONS[phase] for phase, action in declared.items()), 'declared_fixed_actions')

    def choose(observation, candidates):
        control.require(observation['schema'] == control.ACTOR_SCHEMA, 'fixed_actor_schema')
        action = declared[observation['phase']]
        selected = [candidate for candidate in candidates if candidate['action_id'] == action]
        control.require(len(selected) == 1 and selected[0]['enabled'] is True, 'requested_action_disabled_no_silent_fallback')
        return selected[0]['candidate_id']

    return choose


def completion(raw):
    control.require(raw['kind'] == 'EvaluatorRecord' and raw['summary']['status'] == 'assessed', 'completed_native_evaluator_required')
    values = {job['business_bag_id']: job['completed_at'] for job in raw['result']['jobs']}
    control.require(control.known(values) and values == raw['summary']['completion'], 'five_actual_completion_values')
    return values


def compare_terminal(baseline, candidate):
    control.require(baseline['input'] == candidate['input']
        and baseline['specification']['case'] == candidate['specification']['case'], 'same_input_comparison_required')
    base, changed = completion(baseline), completion(candidate)
    delta = {job: changed[job] - base[job] for job in control.JOBS}
    return {'status': 'strict_zero_tolerance_compared', 'per_job_delta': delta,
        'strict_protected': all(value <= 0 for value in delta.values()),
        'strict_improvement': any(value < 0 for value in delta.values()),
        'scope': 'offline actual terminal evaluator comparison; never actor or current guard input'}


def episode_summary(raw, *, source_sha256):
    values = completion(raw)
    transitions = raw['later_transitions']
    control.require(bool(transitions) and len(source_sha256) == 64, 'bound_later_transitions_required')
    effective = [transition for transition in transitions
        if transition['actual_physical_effect']['next_edge_enter'] is not None
        and transition['ACK_status'] in ('received', 'updated', 'not_applicable_no_command')]
    return {'schema': SCHEMA, 'scene_id': raw['specification']['case'], 'episode_id': source_sha256,
        'source_raw_sha256': source_sha256, 'behavior_mode': raw['summary']['behavior_mode'],
        'status': 'assessed', 'transition_count': len(transitions), 'actual_effective_count': len(effective),
        'executed_actions': [transition['executed_action_id'] for transition in transitions],
        'actual_terminal_completion': values,
        'original_reference_sha256_by_owner': {transition['owner']: transition['initial_reference_sha256'] for transition in transitions},
        'candidate_protection_status': {transition['phase']: {candidate['action_id']: candidate['guard_status']
            for candidate in transition['candidate_mask']} for transition in transitions},
        'two_temporal_points_observed': len({transition['selected_at'] for transition in effective}) >= 2,
        'protected_nondefault_trajectory_verified': False, 'rl_ready': False,
        'strict_protected': None, 'complete_request_100ms_certified': False,
        'scope': 'One deterministic native episode; effective decisions alone do not establish protected multi-step RL.'}


def run_episode(output_dir, *, choose, model=current_model, mode='guarded',
                phases=tuple(control.PHASE_ACTIONS), case='mechanism', method='incumbent'):
    """Run exactly one fresh branch. The caller MUST enforce an outer hard timeout."""
    output = Path(output_dir).resolve()
    control.require(not output.exists(), 'fresh_episode_output_required')
    control.require(callable(choose), 'explicit_actor_required')
    output.mkdir(parents=True)
    environment.write(output / 'episode_contract.json', {'schema': SCHEMA, 'case': case, 'method': method,
        'mode': mode, 'phases': list(phases), 'model_version': getattr(model, 'VERSION', None),
        'actor_contract': 'choose(detached later_actor.v1, detached candidate mask) -> candidate_id',
        'process_hard_limit_required': True, 'original_reference_refresh_allowed': False,
        'diagnostic_is_not_protected_deployment': mode == 'diagnostic_intervention'})
    receipt = environment.run_baseline(output / 'native', case=case, method=method,
        later_choose=choose, later_model=model, later_mode=mode, later_phases=phases)
    summary = {'schema': SCHEMA, 'status': receipt['status'], 'rl_ready': False,
        'native_receipt': str(output / 'native/receipt.json')}
    if receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed':
        artifact = receipt['raw_artifact']
        payload = Path(artifact['path']).read_bytes()
        control.require(hashlib.sha256(payload).hexdigest() == artifact['sha256'], 'episode_raw_identity')
        summary.update(episode_summary(json.loads(gzip.decompress(payload)), source_sha256=artifact['sha256']))
    environment.write(output / 'episode.json', summary)
    return receipt
