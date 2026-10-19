"""Conservative public component domain; conditional forecasts grant no promise.

A keeps the incumbent route and return components. B may use an already
queried, protected joint estimate whose A components equal that incumbent.
This makes the effective vector identical to B's checked vector without
reading A's private proposal. Native refusal, missing ACKs and model error
remain possible; this restriction is not a resource reservation protocol.
"""
from __future__ import annotations

import copy
import math
import time

from . import live_obligation_projection_protocol as protocol
from . import live_obligation_full32_suffix_partition as domain

CONTRACT = 'g31.initial_components.A_incumbent_B_queried_deviation.v1'
OWNER_FIELDS = {'A': ('initial_action', 'return_delay'),
                'B': ('empty_departure', 'later_action')}
JOBS = ('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker')


def require(value, reason):
    if not value:
        raise ValueError('component_compatibility:' + reason)


def known(row):
    completion = row.get('completion')
    return (row.get('status') == 'conditional_forecast' and type(completion) is dict
        and set(completion) == set(JOBS) and all(type(completion[job]) is float
            and math.isfinite(completion[job]) and completion[job] >= 0 for job in JOBS))


def select_component(selection, owner, incumbent_index):
    started = time.perf_counter_ns()
    require(owner in OWNER_FIELDS and incumbent_index == 4, 'owner_and_frozen_incumbent04')
    data = selection['provider_evidence']
    rows = data['rows']
    require(data['owner'] == owner and len(rows) == 32
        and [row['candidate_index'] for row in rows] == list(range(32)), 'own_complete_domain')
    domain.partition([row['action'] for row in rows])
    baseline = rows[incumbent_index]
    require(baseline['action'] == protocol.incumbent_action(), 'unchanged_incumbent_action')
    queried = selection['accounting']['query_indices']
    require(type(queried) is list and len(set(queried)) == len(queried)
        and all(type(index) is int and 0 <= index < 32 for index in queried)
        and incumbent_index in queried, 'actual_selector_query_domain')
    allowed = selection['allowed_candidate_indices']

    def protected(row):
        return known(row) and known(baseline) and all(
            row['completion'][job] <= baseline['completion'][job] for job in JOBS)

    def compatible(row):
        return all(row['action'][field] == baseline['action'][field] for field in OWNER_FIELDS['A'])

    candidates = [index for index in queried if index in allowed and protected(rows[index])
        and (index == incumbent_index if owner == 'A' else compatible(rows[index]))]
    selected = min(candidates, key=lambda index: (
        sum(rows[index]['completion'][job] for job in JOBS), index)) if candidates else None
    protected_indices = [index for index, row in enumerate(rows) if protected(row)]
    excluded = [index for index in protected_indices if not compatible(rows[index])]
    result = {'contract': CONTRACT, 'owner': owner,
        'status': 'conditional_compatible_component' if selected is not None else 'unknown_no_compatible_component',
        'original_selected_index': selection['selected_index'], 'selected_index': selected,
        'selected_action': copy.deepcopy(rows[selected]['action']) if selected is not None else None,
        'original_proposal_rejected': selection['selected_index'] != selected,
        'reason': 'A_incumbent_components_and_B_own_queried_protected_joint_witness',
        'eligible_queried_indices': candidates, 'original_query_indices': list(queried),
        'protected_full_domain_indices': protected_indices,
        'protected_indices_excluded_by_public_contract': excluded,
        'admissibility_rows_examined': len(queried), 'diagnostic_rows_examined': 32,
        'additional_model_predictions': 0, 'additional_selector_queries': 0,
        'peer_private_information_read': False, 'hard_reservation_granted': False,
        'native_protection_certified': False, 'physical_execution_certified': False,
        'fallback_scope': 'Incumbent component before submission only; issued commands retain their original identity.',
        'unresolved_scope': 'R1 deviation and joint25 are excluded; unavailable native promises and later refusal remain unknown.'}
    result['filter_wall_ns'] = time.perf_counter_ns() - started
    return result
