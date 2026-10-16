"""Finite initial-A R1 request contract, separate from the 32-action search.

The cooperative continuation is public program configuration. A planning
capture authenticates present source facts, never a promise of future policy.
Every verdict here is a data verdict, not a native execution certificate.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math

SCHEMA = 'g31.initial_owner_route_two_choice.v1'
START = .11
ROOT_ADMISSION_PHYSICAL = .05
HORIZON = 40.
BUDGET_NS = 100_000_000
FINALIZATION_RESERVE_NS = 40_000_000  # Experimental allocation, not a WCET bound.
JOBS = frozenset(('loaded', 'blocker', 'receiver', 'reuse1', 'reuse2'))


def participation_contract():
    return {
        'schema': SCHEMA, 'decision_owner': 'A', 'initial_model_epoch': START,
        'choices': ['native_default', 'prefer_2'],
        'fixed_action_fields': {'empty_departure': START, 'return_delay': 0.,
                                'later_action': 'native_default'},
        'initial_B': 'At .11, source-local E5 empty/available revalidation, immutable E5->1 transfer, earliest .11; native admission and actual ACK remain required.',
        'continuation': 'Reuse unchanged public-preference OwnerPolicy transport, demand publication, rejection recovery, preflight, collection and reply holds. At first_return fix delay0; at first_reuse_route fix native_default (no preference); second return0 and second reuse explicit3 unchanged.',
        'retries': 'Existing immutable transport .5 physical-second retry and real delivered terminal ACK rules; no wall-time expiry can invent a terminal ACK.',
        'authority': 'A priori cooperative policy/code contract, not learned from planning IDs or authenticated future payload; no joint independent time-limited selection.',
        'protection': 'Conditional same-input five-job point prediction only; no all-business native protection, model-error, stability or deadlock certificate.',
        'request_scope': 'Initial owner-A first hop only. Future maintenance belongs to the fixed participant policy and is not certified by first-hop closure.',
    }


def contract_sha256():
    return hashlib.sha256(json.dumps(participation_contract(), separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def fixed_actions(actions):
    """Select two exact existing actions, with the original baseline first."""
    expected = [dict(initial_action=choice, empty_departure=START, return_delay=0.,
                     later_action='native_default') for choice in ('native_default', 'prefer_2')]
    if type(actions) is not list or len(actions) != 32 or actions[0] != expected[0]:
        raise ValueError('initial_stage:unexpected_original_action_domain')
    for item in expected:
        if sum(row == item for row in actions) != 1:
            raise ValueError('initial_stage:missing_or_duplicate_fixed_action')
    return copy.deepcopy(expected)


def completion(result):
    if (type(result) is not dict or result.get('status') != 'conditional_prediction'
            or type(result.get('completion')) is not dict or set(result['completion']) != JOBS
            or any(type(t) not in (int, float) or not math.isfinite(t) or not 0 <= t <= HORIZON
                   for t in result['completion'].values())
            or result.get('native_protection_certified') is not False):
        return None
    return result['completion']


def select(baseline, candidate, *, decision_budget_expired):
    """Strict zero regression; ties keep default; partial/unknown never wins."""
    base = completion(baseline)
    if base is None:
        return {'status': 'unknown_baseline', 'choice': None, 'candidate_eligible': None}
    if decision_budget_expired:
        return {'status': 'budget_exhausted_default_incumbent', 'choice': 'native_default',
                'candidate_eligible': None}
    trial = completion(candidate)
    if trial is None:
        return {'status': 'default_incumbent', 'choice': 'native_default',
                'candidate_eligible': False if candidate.get('status') == 'conditional_protection_rejected_prefix' else None}
    eligible = all(trial[j] <= base[j] for j in JOBS)
    improvement = sum(trial[j] for j in sorted(JOBS)) < sum(base[j] for j in sorted(JOBS))
    return {'status': 'conditional_two_choice_selection',
            'choice': 'prefer_2' if eligible and improvement else 'native_default',
            'candidate_eligible': eligible}


def validate_final_local(view, bundle, choice):
    """Fresh A source and same-owner receiver checks, followed by native guard.

This does not reserve a berth. Native command execution must revalidate again.
The source contract excludes prior physical actions before the initial epoch.
"""
    try:
        if choice not in ('native_default', 'prefer_2') or view['owner_id'] != 'A' or view['now'] != START:
            raise ValueError('initial_stage:owner_or_epoch')
        rows = [t for t in view['trays'] if t['tray_id'] == 'L']
        jobs = [j for j in view['jobs'] if j['business_bag_id'] == 'loaded']
        if len(rows) != 1 or len(jobs) != 1:
            raise ValueError('initial_stage:source_population')
        tray, captured = rows[0], bundle['trays']['L']
        fields = ('tray_id', 'business_bag_id', 'node', 'mode', 'edge_from', 'edge_to',
                  'reception_node', 'generation', 'traversal_id', 'committed_prefix')
        if (any(tray[k] != captured[k] for k in fields)
                or (tray['node'], tray['mode'], tray['business_bag_id']) != (0, 'loaded', 'loaded')
                or any(type(tray[k]) is not int or tray[k] != -1 for k in ('edge_from','edge_to','reception_node'))
                or any(type(tray[k]) is not int or tray[k] < 0 for k in ('generation','traversal_id'))
                or tray['committed_prefix'] != [0] or jobs[0].get('allow_suffix_reroute') is not True
                or view['known_faults']):
            raise ValueError('initial_stage:changed_source_or_fault')
        if choice == 'prefer_2':
            target = [n for n in view['node_contracts'] if n['node'] == 2]
            if (len(target) != 1 or target[0]['resource_owner'] != 'A'
                    or type(target[0]['capacity']) is not int or target[0]['capacity'] <= 0
                    or type(target[0]['occupancy']) is not int
                    or not 0 <= target[0]['occupancy'] < target[0]['capacity']):
                raise ValueError('initial_stage:receiver_not_locally_available')
        return {'status': 'fresh_local_precondition_checked', 'source': copy.deepcopy(tray),
                'receiver_reservation_certified': False, 'native_execution_certified': False}
    except (KeyError, TypeError, ValueError) as error:
        return {'status': 'unknown_final_local_precondition', 'reason': str(error),
                'native_execution_certified': False}


def observed_first_hop(view, source):
    """Reservation alone is insufficient; preserve the first source identity."""
    try:
        if view['owner_id'] != 'A' or type(view['now']) not in (int, float) or not math.isfinite(view['now']):
            return None
        rows = [t for t in view['trays'] if t['tray_id'] == source['tray_id']]
        if len(rows) != 1:
            return None
        tray = rows[0]
        prefix = tray['committed_prefix']
        if (tray['generation'] != source['generation'] or tray['business_bag_id'] != source['business_bag_id']
                or type(prefix) is not list or len(prefix) < 2 or prefix[0] != 0
                or any(type(n) is not int for n in prefix) or prefix[1] not in (1, 2)):
            return None
        # A later completed edge or current post-exit node proves passage. A
        # pending edge_to/prefix at source0 does not. Moving proof requires the
        # source-observed entry receipt exposed as a finite future exit time.
        exited = tray['node'] != 0 or len(prefix) > 2
        exit_at = tray.get('edge_exit_at')
        entered = (tray['node'] == 0 and tray['edge_from'] == 0 and tray['edge_to'] == prefix[1]
                   and type(exit_at) in (int, float) and math.isfinite(exit_at) and exit_at > view['now'])
        if not (exited or entered):
            return None
        return {'from': 0, 'to': prefix[1], 'observed_at': view['now'],
                'evidence': 'post_exit_prefix' if exited else 'observed_entry_future_exit',
                'tray': copy.deepcopy(tray)}
    except (KeyError, TypeError, ValueError):
        return None


def closure(choice, hop, command, *, queried_owner, request_id, now, timestamp_complete):
    """No accepted submit/updated ACK/reservation can alone close the root."""
    result = {'status': 'open_pending_evidence', 'closed': False, 'ack_required': choice == 'prefer_2'}
    if timestamp_complete is not True or queried_owner != 'A':
        return result
    if choice == 'native_default':
        if hop is not None and hop['observed_at'] <= now:
            return {**result, 'status': 'closed_native_default_first_hop', 'closed': True,
                    'ack_status': 'not_applicable_no_command'}
        return result
    if choice != 'prefer_2' or type(command) is not dict:
        return result
    ack = command.get('last_delivered_ack', {})
    # Native protocol_command does not return owner_id. Bind the actual query
    # argument explicitly; never add a synthesized owner field to its result.
    if (command.get('request_id') != request_id
            or command.get('kind') != 'route' or not ack
            or type(ack.get('delivered_at')) not in (int,float) or not math.isfinite(ack['delivered_at'])
            or not 0 <= ack['delivered_at'] <= now):
        return result
    if ack.get('status') in ('rejected', 'expired', 'failed', 'cancelled'):
        return {**result, 'status': 'closed_delivered_terminal_failure', 'closed': True,
                'ack_status': ack['status']}
    if ack.get('status') != 'updated' or hop is None or hop['observed_at'] > now:
        return result
    return {**result, 'status': 'closed_updated_and_requested_first_hop' if hop['to'] == 2
            else 'closed_updated_but_other_first_hop', 'closed': True,
            'ack_status': 'updated', 'requested_hop_executed': hop['to'] == 2}
